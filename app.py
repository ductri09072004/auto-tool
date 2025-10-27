from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
import os
import subprocess
import json
import requests
import shutil
import re
from urllib.parse import urlparse
from datetime import datetime
import tempfile
import time
import threading
from service_manager import ServiceManager
from api_db import register_db_api
from config import GITHUB_TOKEN, GHCR_TOKEN, MANIFESTS_REPO_TOKEN, ARGOCD_WEBHOOK_URL, DASHBOARD_TOKEN, WEBHOOK_URL, TEMPLATE_A_PATH, TEMPLATE_B_PATH, FALLBACK_TEMPLATE_B, REPO_B_SERVICES_PATH

# Environment detection
def is_railway_environment():
    """Check if running on Railway (cloud environment)"""
    return os.getenv('RAILWAY_ENVIRONMENT') is not None or os.getenv('PORT') is not None

def has_git_command():
    """Check if git command is available"""
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def _get_argocd_session_token():
    """Get ArgoCD session token using admin password"""
    try:
        from config import ARGOCD_SERVER_URL, ARGOCD_ADMIN_PASSWORD
        import requests
        
        if not ARGOCD_ADMIN_PASSWORD:
            print("❌ ARGOCD_ADMIN_PASSWORD not set")
            return None
        
        # Login to ArgoCD to get session token
        login_url = f"{ARGOCD_SERVER_URL}/api/v1/session"
        login_data = {
            "username": "admin",
            "password": ARGOCD_ADMIN_PASSWORD
        }
        
        print(f"🔐 Attempting to login to ArgoCD at {login_url}")
        headers = {'ngrok-skip-browser-warning': 'true'}
        response = requests.post(login_url, json=login_data, headers=headers, timeout=10, verify=False, allow_redirects=True)
        
        if response.status_code == 200:
            token = response.json().get('token')
            if token:
                print(f"✅ Successfully obtained ArgoCD session token")
                return token
            else:
                print("❌ No token in response")
                return None
        else:
            print(f"❌ Login failed: {response.status_code} {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting session token: {e}")
        return None

def _check_argocd_application_status(service_name):
    """Check ArgoCD application status via API"""
    try:
        from config import ARGOCD_SERVER_URL, ARGOCD_TOKEN, ARGOCD_ADMIN_PASSWORD
        import requests
        
        # Get token if not available
        token = ARGOCD_TOKEN
        if not token and ARGOCD_ADMIN_PASSWORD:
            token = _get_argocd_session_token()
        
        if not token:
            print("❌ No ArgoCD token available")
            return None
        
        # Check application status
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }
        
        response = requests.get(
            f"{ARGOCD_SERVER_URL}/api/v1/applications/{service_name}",
            headers=headers,
            timeout=10,
            verify=False,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            app_data = response.json()
            status = app_data.get('status', {})
            sync_status = status.get('sync', {}).get('status', 'Unknown')
            health_status = status.get('health', {}).get('status', 'Unknown')
            return {
                'sync_status': sync_status,
                'health_status': health_status,
                'synced': sync_status == 'Synced'
            }
        else:
            print(f"❌ Failed to get ArgoCD application status: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error checking ArgoCD application status: {e}")
        return None

def _deploy_argocd_application_via_api(service_name, repo_b_url, namespace):
    """Deploy ArgoCD Application via ArgoCD API instead of kubectl"""
    try:
        # Get ArgoCD server URL and token from config
        from config import ARGOCD_SERVER_URL, ARGOCD_TOKEN, ARGOCD_ADMIN_PASSWORD
        argocd_server = ARGOCD_SERVER_URL
        argocd_token = ARGOCD_TOKEN
        
        # Debug logging
        print(f"🔍 ArgoCD Debug Info:")
        print(f"   Server URL: {argocd_server}")
        print(f"   Token: {'SET' if argocd_token else 'NOT SET'}")
        print(f"   Admin Password: {'SET' if ARGOCD_ADMIN_PASSWORD else 'NOT SET'}")
        
        # If no token, try to get session token using admin password
        if not argocd_token and ARGOCD_ADMIN_PASSWORD:
            print("🔑 No ARGOCD_TOKEN found, trying to get session token...")
            argocd_token = _get_argocd_session_token()
            if argocd_token:
                print("✅ Successfully obtained session token")
            else:
                print("❌ Failed to get session token")
        
        if not argocd_token:
            return {'success': False, 'error': 'ARGOCD_TOKEN not configured and cannot get session token'}
        
        # Prepare application data
        app_data = {
            "metadata": {
                "name": service_name,
                "namespace": "argocd",
                "finalizers": ["resources-finalizer.argocd.argoproj.io"]
            },
            "spec": {
                "project": "default",
                "source": {
                    "repoURL": repo_b_url.replace('.git', ''),
                    "targetRevision": "HEAD",
                    "path": f"services/{service_name}/k8s"
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": namespace
                },
                "syncPolicy": {
                    "automated": {
                        "prune": True,
                        "selfHeal": True
                    },
                    "syncOptions": [
                        "CreateNamespace=true",
                        "PrunePropagationPolicy=foreground",
                        "PruneLast=true",
                        "RespectIgnoreDifferences=true",
                        "ServerSideApply=true"
                    ],
                    "retry": {
                        "backoff": {
                            "duration": "5s",
                            "factor": 2,
                            "maxDuration": "3m"
                        },
                        "limit": 5
                    }
                }
            }
        }
        
        # Make API call to ArgoCD
        headers = {
            'Authorization': f'Bearer {argocd_token}',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }
        
        # Try to create application
        create_url = f"{argocd_server}/api/v1/applications"
        response = requests.post(create_url, json=app_data, headers=headers, timeout=30, verify=False, allow_redirects=True)
        
        if response.status_code in [200, 201]:
            print(f"✅ ArgoCD Application '{service_name}' created successfully")
            return {'success': True, 'message': 'Application created via ArgoCD API'}
        elif response.status_code == 409:
            # Application already exists, try to update
            print(f"Application '{service_name}' already exists, updating...")
            update_url = f"{argocd_server}/api/v1/applications/{service_name}"
            update_response = requests.put(update_url, json=app_data, headers=headers, timeout=30, verify=False, allow_redirects=True)
            
            if update_response.status_code in [200, 201]:
                print(f"✅ ArgoCD Application '{service_name}' updated successfully")
                return {'success': True, 'message': 'Application updated via ArgoCD API'}
            else:
                return {'success': False, 'error': f'Update failed: {update_response.status_code} - {update_response.text}'}
        else:
            return {'success': False, 'error': f'Create failed: {response.status_code} - {response.text}'}
            
    except Exception as e:
        return {'success': False, 'error': f'ArgoCD API error: {str(e)}'}

def _create_inline_template(template_name, service_name, namespace, port, replicas, min_replicas, max_replicas, cpu_request, cpu_limit, memory_request, memory_limit, gh_owner, repo_name, image_tag):
    """Create inline template content for Railway deployment when local templates are not available"""
    
    if template_name == 'deployment.yaml':
        return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service_name}
  namespace: {namespace}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {service_name}
  template:
    metadata:
      labels:
        app: {service_name}
    spec:
      containers:
      - name: {service_name}
        image: ghcr.io/{gh_owner}/{repo_name}:{image_tag}
        ports:
        - containerPort: {port}
        resources:
          requests:
            memory: {memory_request}
            cpu: {cpu_request}
          limits:
            memory: {memory_limit}
            cpu: {cpu_limit}
        livenessProbe:
          httpGet:
            path: /api/health
            port: {port}
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/health
            port: {port}
          initialDelaySeconds: 5
          periodSeconds: 5"""

    elif template_name == 'service.yaml':
        return f"""apiVersion: v1
kind: Service
metadata:
  name: {service_name}
  namespace: {namespace}
spec:
  selector:
    app: {service_name}
  ports:
  - port: 80
    targetPort: {port}
  type: ClusterIP"""

    elif template_name == 'configmap.yaml':
        return f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {service_name}-config
  namespace: {namespace}
data:
  PORT: "{port}"
  NODE_ENV: "production"
  SERVICE_NAME: "{service_name}" """

    elif template_name == 'hpa.yaml':
        return f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {service_name}-hpa
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {service_name}
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70"""

    elif template_name == 'ingress.yaml':
        return f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {service_name}-ingress
  namespace: {namespace}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: {service_name}.example.local
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: {service_name}
            port:
              number: 80"""

    elif template_name == 'ingress-gateway.yaml':
        return f"""apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: {service_name}-vs
  namespace: {namespace}
spec:
  hosts:
  - {service_name}.example.local
  gateways:
  - {service_name}-gateway
  http:
  - match:
    - uri:
        prefix: /api
    route:
    - destination:
        host: {service_name}
        port:
          number: 80"""

    elif template_name == 'namespace.yaml':
        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    name: {namespace}"""

    elif template_name == 'secret.yaml':
        return f"""apiVersion: v1
kind: Secret
metadata:
  name: {service_name}-secret
  namespace: {namespace}
type: Opaque
data:
  # Add your secret data here
  # Example: key: <base64-encoded-value>"""

    else:
        return f"# Template for {template_name} not implemented"

def _delete_yaml_files_via_github_api(service_name, repo_url, yaml_files_to_delete):
    """Delete YAML files using GitHub API instead of git commands"""
    try:
        import re
        
        # Parse repository URL
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            print(f"Invalid GitHub repository URL: {repo_url}")
            return False
        
        owner = match.group(1)
        repo_name = match.group(2)
        
        headers = {'Authorization': f'token {MANIFESTS_REPO_TOKEN}', 'Accept': 'application/vnd.github+json'}
        
        deleted_count = 0
        
        # Delete each YAML file
        for yaml_file in yaml_files_to_delete:
            file_path = f"services/{service_name}/k8s/{yaml_file}"
            
            # Retry logic for handling 409 conflicts
            max_retries = 3
            for attempt in range(max_retries):
                # Check if file exists (get fresh SHA each time)
                contents_url = f'https://api.github.com/repos/{owner}/{repo_name}/contents/{file_path}'
                get_response = requests.get(contents_url, headers=headers)
                
                if get_response.status_code == 200:
                    # File exists, delete it with fresh SHA
                    existing_data = get_response.json()
                    delete_data = {
                        'message': f'Delete {yaml_file} after ArgoCD sync for {service_name}',
                        'sha': existing_data['sha']
                    }
                    
                    delete_response = requests.delete(contents_url, headers=headers, json=delete_data)
                    
                    if delete_response.status_code in [200, 204]:
                        print(f"Deleted {yaml_file}")
                        deleted_count += 1
                        break  # Success, move to next file
                    elif delete_response.status_code == 409:
                        # Conflict - file was modified by another commit
                        print(f"⚠️ Conflict deleting {yaml_file} (attempt {attempt + 1}/{max_retries}), retrying...")
                        if attempt < max_retries - 1:
                            import time
                            time.sleep(1)  # Wait 1 second before retry
                            continue
                        else:
                            print(f"Failed to delete {yaml_file} after {max_retries} attempts due to conflicts")
                    else:
                        print(f"Failed to delete {yaml_file}: {delete_response.status_code}")
                        break
                else:
                    print(f"File {yaml_file} not found, skipping")
                    break
        
        # Also delete ArgoCD Application file
        apps_file_path = f"apps/{service_name}-application.yaml"
        apps_contents_url = f'https://api.github.com/repos/{owner}/{repo_name}/contents/{apps_file_path}'
        apps_get_response = requests.get(apps_contents_url, headers=headers)
        
        if apps_get_response.status_code == 200:
            apps_existing_data = apps_get_response.json()
            apps_delete_data = {
                'message': f'Delete ArgoCD Application after sync for {service_name}',
                'sha': apps_existing_data['sha']
            }
            
            apps_delete_response = requests.delete(apps_contents_url, headers=headers, json=apps_delete_data)
            
            if apps_delete_response.status_code in [200, 204]:
                print(f"Deleted apps/{service_name}-application.yaml")
                deleted_count += 1
            else:
                print(f"Failed to delete ArgoCD Application: {apps_delete_response.status_code}")
        
        print(f"Successfully deleted {deleted_count} files for {service_name}")
        return True
        
    except Exception as e:
        print(f"Error deleting YAML files via GitHub API: {e}")
        return False

def push_files_to_github_api(repo_url, files_to_push, commit_message, github_token):
    """Push files to GitHub repository using GitHub Contents API instead of git commands"""
    try:
        import re
        import base64
        
        # Parse repository URL
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return {'success': False, 'error': 'Invalid GitHub repository URL'}
        
        owner = match.group(1)
        repo_name = match.group(2)
        
        headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github+json'}
        
        # Push each file individually using Contents API
        for file_path, file_content in files_to_push.items():
            # Prepare file data
            if isinstance(file_content, str):
                content_bytes = file_content.encode('utf-8')
            else:
                content_bytes = file_content
            
            content_b64 = base64.b64encode(content_bytes).decode('utf-8')
            
            # Retry logic for handling 409 conflicts
            max_retries = 3
            for attempt in range(max_retries):
                # Check if file exists (get fresh SHA each time)
                contents_url = f'https://api.github.com/repos/{owner}/{repo_name}/contents/{file_path}'
                print(f"🔍 Checking file status: {file_path}")
                get_response = requests.get(contents_url, headers=headers)
                print(f"   GET Status: {get_response.status_code}")
                
                file_data = {
                    'message': f'{commit_message} - {file_path}',
                    'content': content_b64
                }
                
                if get_response.status_code == 200:
                    # File exists, update it with fresh SHA
                    existing_data = get_response.json()
                    sha = existing_data.get('sha')
                    if sha:
                        file_data['sha'] = sha
                        print(f"📝 Updating existing file {file_path} with SHA {sha[:10]}...")
                    else:
                        print(f"⚠️ Warning: File {file_path} exists but no SHA found in response")
                    put_response = requests.put(contents_url, headers=headers, json=file_data)
                elif get_response.status_code == 404:
                    # File doesn't exist, create it
                    print(f"📄 Creating new file {file_path}")
                    put_response = requests.put(contents_url, headers=headers, json=file_data)
                else:
                    return {'success': False, 'error': f'Failed to check file status for {file_path}: {get_response.status_code} - {get_response.text}'}
                
                if put_response.status_code in [200, 201]:
                    print(f"✅ Successfully pushed {file_path}")
                    break  # Success, move to next file
                elif put_response.status_code == 409:
                    # Conflict - file was modified by another commit
                    print(f"⚠️ Conflict for {file_path} (attempt {attempt + 1}/{max_retries}), retrying...")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2)  # Wait 2 seconds before retry
                        # Re-fetch the latest SHA before retrying
                        print(f"   Re-fetching latest SHA for {file_path}...")
                        get_response = requests.get(contents_url, headers=headers)
                        if get_response.status_code == 200:
                            existing_data = get_response.json()
                            sha = existing_data.get('sha')
                            if sha:
                                file_data['sha'] = sha
                                print(f"   Updated SHA to {sha[:10]}...")
                        continue
                    else:
                        return {'success': False, 'error': f'Failed to push {file_path} after {max_retries} attempts due to conflicts: {put_response.text}'}
                else:
                    return {'success': False, 'error': f'Failed to push {file_path}: {put_response.status_code} - {put_response.text}'}
        
        return {'success': True, 'message': f'Successfully pushed {len(files_to_push)} files'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Global variable to track port-forward process
port_forward_process = None
try:
    # PyNaCl is required to encrypt secrets for GitHub API
    from nacl import encoding, public
except Exception:
    public = None

app = Flask(__name__)

# Initialize Service Manager with environment variables
mongo_uri = os.environ.get('MONGO_URI', 'mongodb+srv://BlueDuck2:Fcsunny0907@tpexpress.zjf26.mongodb.net/?retryWrites=true&w=majority&appName=TPExpress')
mongo_db = os.environ.get('MONGO_DB', 'AutoToolDevOPS')
service_manager = ServiceManager(mongo_uri, mongo_db)
register_db_api(app, service_manager)

def start_port_forward():
    """Start port-forward in background if not already running"""
    global port_forward_process
    
    # Skip port-forward on Railway environment
    if is_railway_environment():
        print("Skipping port-forward on Railway environment")
        return False
    
    # Check if port-forward is already running
    if port_forward_process and port_forward_process.poll() is None:
        print("Port-forward already running")
        return True
    
    try:
        # Start port-forward in background
        print("Starting port-forward...")
        port_forward_process = subprocess.Popen([
            'kubectl', '-n', 'ingress-nginx', 'port-forward', 
            'svc/ingress-nginx-controller', '8081:80'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a moment to see if it starts successfully
        time.sleep(1)
        if port_forward_process.poll() is None:
            print("Port-forward started successfully")
            return True
        else:
            print("Failed to start port-forward")
            return False
            
    except Exception as e:
        print(f"Error starting port-forward: {e}")
        return False

def stop_port_forward():
    """Stop port-forward process"""
    global port_forward_process
    if port_forward_process and port_forward_process.poll() is None:
        port_forward_process.terminate()
        print("Port-forward stopped")

# Disable client/proxy caching for portal responses
@app.after_request
def add_no_cache_headers(response):
    try:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    except Exception:
        pass
    return response

# GitHub configuration comes from config.py (GITHUB_TOKEN)

# Monitoring configuration
PROMETHEUS_URL = "http://localhost:9090"
GITHUB_ORG = os.getenv('GITHUB_ORG', 'your_organization')
DEFAULT_REPO_B_URL = os.getenv('DEFAULT_REPO_B_URL', 'https://github.com/ductri09072004/demo_fiss1_B')

def _encrypt_secret(public_key: str, secret_value: str) -> str:
    """Encrypt a secret using GitHub Actions public key (libsodium sealed box)."""
    try:
        from nacl import encoding, public
    except ImportError:
        raise RuntimeError("PyNaCl is required to encrypt GitHub secrets. Please install pynacl.")
    
    pk = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder().encode(encrypted).decode("utf-8")

def ensure_repo_secrets(repo_url: str, github_token: str = None, manifests_token: str = None, service_name: str = None) -> bool:
    """Ensure GHCR_TOKEN, MANIFESTS_REPO_TOKEN, and ARGOCD_WEBHOOK_URL exist in repo secrets."""
    try:
        parsed = urlparse(repo_url)
        path = parsed.path.lstrip('/')
        if path.endswith('.git'):
            path = path[:-4]
        parts = path.split('/')
        if len(parts) < 2:
            return False
        owner, repo_name = parts[0], parts[1]
        base = f"https://api.github.com/repos/{owner}/{repo_name}/actions/secrets"
        token_to_use = github_token or GITHUB_TOKEN
        
        print(f"\n{'='*80}")
        print(f"🔐 DEBUG: ensure_repo_secrets called")
        print(f"   Repo URL: {repo_url}")
        print(f"   Repo: {owner}/{repo_name}")
        print(f"   GitHub Token: {'SET' if token_to_use else 'NOT SET'}")
        print(f"   Manifests Token (param): {'SET' if manifests_token else 'NOT SET'}")
        print(f"   MANIFESTS_REPO_TOKEN (config): {'SET' if MANIFESTS_REPO_TOKEN else 'NOT SET'}")
        print(f"   ARGOCD_WEBHOOK_URL: {'SET' if ARGOCD_WEBHOOK_URL else 'NOT SET'}")
        print(f"{'='*80}\n")
        
        headers = {
            'Authorization': f'token {token_to_use}',
            'Accept': 'application/vnd.github+json'
        }

        # Fetch public key
        print(f"📥 Fetching public key from: {base}/public-key")
        pk_resp = requests.get(f"{base}/public-key", headers=headers)
        print(f"   Response status: {pk_resp.status_code}")
        if pk_resp.status_code != 200:
            print(f"❌ WARNING: Cannot access repo secrets: {pk_resp.status_code}")
            print(f"   Response: {pk_resp.text}")
            print(f"   This might be because Actions is not enabled or no permission")
            print(f"   Continuing without setting secrets...")
            return True  # Continue deployment, just skip secrets
            
        pk_json = pk_resp.json()
        repo_public_key = pk_json.get('key')
        key_id = pk_json.get('key_id')
        if not repo_public_key or not key_id:
            print(f"❌ Failed to get public key or key_id")
            return False

        # Encrypt and upsert secrets
        # GHCR_TOKEN: Use user's token (for pushing Docker images to their GHCR)
        ghcr_token = GHCR_TOKEN or github_token
        # MANIFESTS_REPO_TOKEN: Use provided token (for pushing to our Repo B)
        if not manifests_token:
            manifests_token = MANIFESTS_REPO_TOKEN
        
        print(f"\n🔑 Setting secrets for repo: {owner}/{repo_name}")
        print(f"   GHCR_TOKEN: {'SET' if ghcr_token else 'EMPTY'}")
        print(f"   MANIFESTS_REPO_TOKEN: {'SET' if manifests_token else 'EMPTY'}")
        print(f"   ARGOCD_WEBHOOK_URL: {'SET' if ARGOCD_WEBHOOK_URL else 'EMPTY'}")
        
        from config import ARGOCD_SERVER_URL, ARGOCD_ADMIN_PASSWORD
        
        updates = {
            'GHCR_TOKEN': ghcr_token,
            'MANIFESTS_REPO_TOKEN': manifests_token,
            'ARGOCD_WEBHOOK_URL': ARGOCD_WEBHOOK_URL,
            'ARGOCD_SERVER_URL': ARGOCD_SERVER_URL,
            'ARGOCD_ADMIN_PASSWORD': ARGOCD_ADMIN_PASSWORD
        }
        
        # Add SERVICE_NAME if provided - use UI service name
        if service_name:
            updates['SERVICE_NAME'] = service_name
            print(f"   SERVICE_NAME set to UI service name: {service_name}")
            print(f"   This will be used by CI/CD to find folder: services/{service_name}/k8s/")
        else:
            print(f"   ⚠️ No service_name provided - SERVICE_NAME secret will not be set")
        
        # Track results
        results = {}
        for name, value in updates.items():
            print(f"\n🔧 Processing secret: {name}")
            print(f"   Value: {'SET' if value else 'EMPTY'}")
            
            if not value:
                print(f"   ⚠️ WARNING: {name} is empty, skipping...")
                results[name] = {'status': 'skipped', 'reason': 'empty_value'}
                continue
                
            # Retry logic for setting secrets
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    encrypted_value = _encrypt_secret(repo_public_key, value)
                    put_resp = requests.put(
                        f"{base}/{name}",
                        headers={**headers, 'Content-Type': 'application/json'},
                        json={'encrypted_value': encrypted_value, 'key_id': key_id}
                    )
                    
                    print(f"   Attempt {attempt + 1}/{max_retries}: Status {put_resp.status_code}")
                    
                    if put_resp.status_code in [201, 204]:
                        print(f"   ✅ SUCCESS: Successfully set secret {name}")
                        results[name] = {'status': 'success', 'attempt': attempt + 1}
                        break
                    else:
                        print(f"   ❌ ERROR: Failed to set {name}: {put_resp.status_code}")
                        print(f"      Response: {put_resp.text[:200]}")
                        if attempt < max_retries - 1:
                            print(f"   ⏳ Retrying in 5 seconds...")
                            time.sleep(5)
                        else:
                            print(f"   ❌ CRITICAL: Failed to set {name} after {max_retries} attempts!")
                            results[name] = {'status': 'failed', 'attempts': max_retries, 'last_status': put_resp.status_code}
                            if name in ['MANIFESTS_REPO_TOKEN', 'ARGOCD_WEBHOOK_URL']:
                                print(f"   ❌ CRITICAL: {name} is required for GitHub Actions to work!")
                                return False
                except Exception as e:
                    print(f"   ❌ ERROR: Exception while setting secret {name}: {e}")
                    if attempt < max_retries - 1:
                        print(f"   ⏳ Retrying in 5 seconds...")
                        time.sleep(5)
                    else:
                        results[name] = {'status': 'exception', 'error': str(e)}
                        if name in ['MANIFESTS_REPO_TOKEN', 'ARGOCD_WEBHOOK_URL']:
                            print(f"   ❌ CRITICAL: {name} is required for GitHub Actions to work!")
                            return False
        
        # Summary
        print(f"\n{'='*80}")
        print(f"📊 Summary of secrets setup:")
        for name, result in results.items():
            status = result.get('status', 'unknown')
            if status == 'success':
                print(f"   ✅ {name}: SUCCESS (attempt {result.get('attempt', '?')})")
            elif status == 'skipped':
                print(f"   ⚠️ {name}: SKIPPED ({result.get('reason', 'unknown')})")
            elif status == 'failed':
                print(f"   ❌ {name}: FAILED (after {result.get('attempts', '?')} attempts)")
            else:
                print(f"   ❌ {name}: ERROR - {result.get('error', 'unknown error')}")
        print(f"{'='*80}\n")
        
        print("✅ All secrets processed (some may be skipped or failed)")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: ensure_repo_secrets error: {e}")
        import traceback
        traceback.print_exc()
        print(f"   This will cause GitHub Actions to fail!")
        return False  # Return False to indicate failure

def add_prometheus_scrape_job(service_name, service_port):
    """Add Prometheus scrape job for new service"""
    try:
        # Create new scrape job config (aligned under scrape_configs)
        job_config = (
            f"  # {service_name} service\n"
            f"  - job_name: '{service_name}-service'\n"
            f"    static_configs:\n"
            f"    - targets:\n"
            f"      - 'host.docker.internal:{service_port}'  # {service_name} service\n"
            f"    metrics_path: /metrics\n"
            f"    scrape_interval: 30s\n"
        )

        # Append safely using heredoc to avoid escaping issues on Windows → docker → sh
        docker_exec_cmd = (
            'docker exec bt-api-prometheus sh -lc '
            '"cat >> /etc/prometheus/prometheus.yml <<\'EOF\'\n'
            + job_config.replace("\r\n", "\n").replace("\r", "\n") +
            'EOF\n"'
        )
        result = subprocess.run(docker_exec_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Reload Prometheus config
            reload_response = requests.post(f"{PROMETHEUS_URL}/-/reload")
            return reload_response.status_code == 200
        else:
            print(f"Failed to add Prometheus job: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error adding Prometheus job: {e}")
        return False


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/argocd')
@app.route('/argocd/')
@app.route('/argocd/<path:path>')
def argocd_proxy(path=''):
    """Proxy requests to ArgoCD server"""
    try:
        from config import ARGOCD_SERVER_URL
        print(f"DEBUG: ArgoCD proxy called with path='{path}'")
        print(f"DEBUG: ARGOCD_SERVER_URL = {ARGOCD_SERVER_URL}")
        
        # Check if ArgoCD is configured
        if not ARGOCD_SERVER_URL or ARGOCD_SERVER_URL == 'https://argocd.your-domain.com':
            return jsonify({
                'error': 'ArgoCD not configured',
                'message': 'Please set ARGOCD_SERVER_URL environment variable to your ArgoCD server URL',
                'current_url': ARGOCD_SERVER_URL,
                'instructions': 'Set ARGOCD_SERVER_URL to your ArgoCD server URL (e.g., http://localhost:8080 for local ArgoCD)'
            }), 500
        
        # If ARGOCD_SERVER_URL is localhost, we need to handle it differently
        if ARGOCD_SERVER_URL == 'http://localhost:8080':
            return jsonify({
                'error': 'Local ArgoCD detected',
                'message': 'Local ArgoCD detected. Please start ArgoCD locally and ensure it\'s running on port 8080',
                'current_url': ARGOCD_SERVER_URL,
                'instructions': '1. Start ArgoCD locally: python setup_argocd_local.py\n2. Ensure ArgoCD is running on localhost:8080\n3. This proxy will forward requests to your local ArgoCD'
            }), 500
        
        # Check if using ngrok URL
        if 'ngrok' in ARGOCD_SERVER_URL:
            print(f"🌐 Using ngrok URL: {ARGOCD_SERVER_URL}")
            print("📋 Make sure ArgoCD is running locally and ngrok tunnel is active")
        
        # Remove trailing slash from base URL
        base_url = ARGOCD_SERVER_URL.rstrip('/')
        
        # Construct target URL
        if path:
            target_url = f"{base_url}/{path}"
        else:
            target_url = base_url
            
        # Add query parameters if present
        if request.query_string:
            target_url += f"?{request.query_string.decode()}"
        
        print(f"Proxying to ArgoCD: {target_url}")
        
        # Forward the request
        response = requests.request(
            method=request.method,
            url=target_url,
            headers={key: value for (key, value) in request.headers if key != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30
        )
        
        # Create Flask response
        flask_response = make_response(response.content)
        flask_response.status_code = response.status_code
        
        # Copy headers
        for key, value in response.headers.items():
            if key.lower() not in ['content-encoding', 'content-length', 'transfer-encoding']:
                flask_response.headers[key] = value
                
        return flask_response
        
    except Exception as e:
        print(f"ArgoCD proxy error: {e}")
        return jsonify({
            'error': 'ArgoCD proxy failed',
            'message': str(e)
        }), 500

@app.route('/dashboard')
def dashboard():
    return render_template('service_dashboard.html')

@app.route('/argocd-status')
def argocd_status():
    """Check ArgoCD connection status"""
    try:
        from config import ARGOCD_SERVER_URL, ARGOCD_TOKEN
        
        if not ARGOCD_SERVER_URL or ARGOCD_SERVER_URL == 'http://localhost:8080':
            return jsonify({
                'status': 'not_configured',
                'message': 'ArgoCD not configured. Please set ARGOCD_SERVER_URL environment variable.',
                'url': ARGOCD_SERVER_URL
            })
        
        if not ARGOCD_TOKEN:
            return jsonify({
                'status': 'no_token',
                'message': 'ArgoCD token not configured. Please set ARGOCD_TOKEN environment variable.',
                'url': ARGOCD_SERVER_URL
            })
        
        # Test connection to ArgoCD
        try:
            response = requests.get(f"{ARGOCD_SERVER_URL}/api/v1/version", 
                                  headers={'Authorization': f'Bearer {ARGOCD_TOKEN}'}, 
                                  timeout=10)
            
            if response.status_code == 200:
                return jsonify({
                    'status': 'connected',
                    'message': 'ArgoCD connection successful',
                    'url': ARGOCD_SERVER_URL,
                    'version': response.json().get('Version', 'Unknown')
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'ArgoCD connection failed: {response.status_code}',
                    'url': ARGOCD_SERVER_URL
                })
                
        except requests.exceptions.RequestException as e:
            return jsonify({
                'status': 'connection_error',
                'message': f'Cannot connect to ArgoCD: {str(e)}',
                'url': ARGOCD_SERVER_URL
            })
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error checking ArgoCD status: {str(e)}'
        })

# Service Management API Endpoints
@app.route('/api/services', methods=['GET'])
def get_services():
    """Get list of services from MongoDB, enrich with K8s + health metrics."""
    try:
        from config import ARGOCD_SERVER_URL
        services = []

        db_services = service_manager.get_services() or []
        default_repo_url = DEFAULT_REPO_B_URL

        # Get ArgoCD applications list first
        argocd_apps = set()
        if is_railway_environment():
            try:
                session_token = _get_argocd_session_token()
                if session_token:
                    headers = {
                        'Authorization': f'Bearer {session_token}',
                        'ngrok-skip-browser-warning': 'true'
                    }
                    apps_response = requests.get(f"{ARGOCD_SERVER_URL}/api/v1/applications", 
                                               headers=headers, timeout=15, verify=False)
                    if apps_response.status_code == 200:
                        apps_data = apps_response.json()
                        for app in apps_data.get('items', []):
                            app_name = app.get('metadata', {}).get('name')
                            if app_name:
                                argocd_apps.add(app_name)
                        print(f"✅ Found {len(argocd_apps)} applications in ArgoCD")
                    else:
                        print(f"⚠️ Could not get ArgoCD applications list: {apps_response.status_code}")
                else:
                    print("⚠️ Could not get ArgoCD session token")
            except Exception as e:
                print(f"⚠️ Error getting ArgoCD applications: {e}")

        for svc in db_services:
            service_name = svc.get('name') or svc.get('service_name')
            if not service_name:
                continue
            
            # Only show services that exist in both MongoDB and ArgoCD
            if is_railway_environment() and argocd_apps and service_name not in argocd_apps:
                print(f"⏭️ Skipping {service_name} - not found in ArgoCD")
                continue

            port = int(svc.get('port') or 5001)
            description = svc.get('description') or f'Demo service {service_name}'
            created_at = svc.get('created_at') or 'Unknown'

            metadata = svc.get('metadata', {}) if isinstance(svc.get('metadata'), dict) else {}
            repo_b_url = metadata.get('repo_b_url') or default_repo_url
            owner_repo = 'ductri09072004/demo_fiss1_B'
            try:
                if repo_b_url and 'github.com' in repo_b_url:
                    p = urlparse(repo_b_url)
                    parts = [x for x in p.path.strip('/').split('/') if x]
                    if len(parts) >= 2:
                        owner_repo = f"{parts[0]}/{parts[1].replace('.git','')}"
            except Exception:
                pass

            try:
                if is_railway_environment():
                    # Use ArgoCD API instead of kubectl on Railway
                    session_token = _get_argocd_session_token()
                    if session_token:
                        # Get application info from ArgoCD API
                        headers = {
                            'Authorization': f'Bearer {session_token}',
                            'ngrok-skip-browser-warning': 'true'
                        }
                        app_response = requests.get(f"{ARGOCD_SERVER_URL}/api/v1/applications/{service_name}", 
                                                 headers=headers, timeout=10, verify=False)
                        if app_response.status_code == 200:
                            app_data = app_response.json()
                            
                            # Check if application has running pods (Health status must be Healthy)
                            status = app_data.get('status', {})
                            health = status.get('health', {}).get('status', 'Unknown')
                            sync = status.get('sync', {}).get('status', 'Unknown')
                            
                            # Only show services with running pods (Healthy status)
                            if health != 'Healthy':
                                print(f"⏭️ Skipping {service_name}: Health status is {health} (no running pods)")
                                continue
                            
                            # Get resource info from MongoDB service document directly
                            cpu_request = svc.get('cpu_request')
                            memory_request = svc.get('memory_request')
                            cpu_limit = svc.get('cpu_limit')
                            memory_limit = svc.get('memory_limit')
                            
                            deployment = {
                                'spec': {
                                    'template': {
                                        'spec': {
                                            'containers': [{
                                                'resources': {
                                                    'requests': {
                                                        'cpu': cpu_request or 'N/A',
                                                        'memory': memory_request or 'N/A'
                                                    },
                                                    'limits': {
                                                        'cpu': cpu_limit or 'N/A',
                                                        'memory': memory_limit or 'N/A'
                                                    }
                                                }
                                            }]
                                        }
                                    }
                                }
                            }
                        else:
                            print(f"⚠️ ArgoCD API returned {app_response.status_code} for {service_name}")
                            health_status = 'Unknown'
                            sync_status = 'Unknown'
                    else:
                        print(f"⚠️ Could not get ArgoCD session token for {service_name}")
                        # Skip service if we can't verify pod status
                        print(f"⏭️ Skipping {service_name}: Cannot verify pod status (ArgoCD API unavailable)")
                        continue
                else:
                    # Local environment: check if pods are running
                    try:
                        # Check if namespace exists
                        subprocess.run(['kubectl', 'get', 'namespace', service_name], capture_output=True, text=True, check=True)
                        
                        # Check if deployment exists and has running pods
                        deploy_result = subprocess.run(['kubectl', 'get', 'deployment', service_name, '-n', service_name, '-o', 'json'], capture_output=True, text=True, check=True)
                        deployment = json.loads(deploy_result.stdout)
                        
                        # Check pod status
                        pods_result = subprocess.run(['kubectl', 'get', 'pods', '-n', service_name, '-l', f'app={service_name}', '--no-headers'], capture_output=True, text=True)
                        if pods_result.returncode != 0 or not pods_result.stdout.strip():
                            print(f"⏭️ Skipping {service_name}: No running pods found")
                            continue
                        
                        # Check if any pods are running
                        running_pods = [line for line in pods_result.stdout.strip().split('\n') if 'Running' in line]
                        if not running_pods:
                            print(f"⏭️ Skipping {service_name}: No pods in Running state")
                            continue
                            
                    except subprocess.CalledProcessError as e:
                        print(f"⏭️ Skipping {service_name}: Deployment not found or error - {e}")
                        continue

                cpu_request = 'N/A'
                cpu_limit = 'N/A'
                memory_request = 'N/A'
                memory_limit = 'N/A'
                try:
                    containers = deployment['spec']['template']['spec']['containers']
                    if containers:
                        resources = containers[0].get('resources', {})
                        reqs = resources.get('requests', {})
                        lims = resources.get('limits', {})
                        cpu_request = reqs.get('cpu', 'N/A')
                        cpu_limit = lims.get('cpu', 'N/A')
                        memory_request = reqs.get('memory', 'N/A')
                        memory_limit = lims.get('memory', 'N/A')
                except Exception as e:
                    print(f"Warning: Could not extract resources for {service_name}: {e}")

                cpu_usage = 'N/A'
                memory_usage = 'N/A'
                disk_usage = 'N/A'
                process_memory = 'N/A'
                total_requests = 0
                avg_response_time = 'N/A'
                uptime = 'N/A'
                
                # Health metrics collection with fallback strategy
                if is_railway_environment():
                    # Railway: Use ArgoCD API + basic metrics
                    try:
                        session_token = _get_argocd_session_token()
                        if session_token:
                            headers = {
                                'Authorization': f'Bearer {session_token}',
                                'ngrok-skip-browser-warning': 'true'
                            }
                            app_response = requests.get(f"{ARGOCD_SERVER_URL}/api/v1/applications/{service_name}", 
                                                       headers=headers, timeout=10, verify=False)
                            if app_response.status_code == 200:
                                app_data = app_response.json()
                                status = app_data.get('status', {})
                                
                                # Basic metrics from ArgoCD
                                health_status = status.get('health', {}).get('status', 'Unknown')
                                sync_status = status.get('sync', {}).get('status', 'Unknown')
                                
                                # Pod info for uptime calculation
                                resources = status.get('resources', [])
                                if resources:
                                    pod = resources[0] if resources else {}
                                    created_at = pod.get('createdAt', '')
                                    if created_at:
                                        from datetime import datetime
                                        try:
                                            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                            uptime_seconds = (datetime.now().replace(tzinfo=created_time.tzinfo) - created_time).total_seconds()
                                            uptime = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"
                                        except:
                                            uptime = 'N/A'
                                    else:
                                        uptime = 'N/A'
                                else:
                                    uptime = 'N/A'
                                
                                # Set basic metrics (no detailed CPU/memory from ArgoCD API)
                                cpu_usage = 'N/A'
                                memory_usage = 'N/A'
                                disk_usage = 'N/A'
                                process_memory = 'N/A'
                                total_requests = 0
                                avg_response_time = 'N/A'
                                
                                print(f"✅ ArgoCD metrics collected for {service_name}: Health={health_status}, Sync={sync_status}")
                            else:
                                print(f"⚠️ ArgoCD API returned {app_response.status_code} for {service_name}")
                        else:
                            print(f"⚠️ Could not get ArgoCD session token for {service_name}")
                    except Exception as e:
                        print(f"⚠️ Error getting ArgoCD metrics for {service_name}: {e}")
                else:
                    # Local: Try /api/health endpoint first, fallback to basic metrics
                    try:
                        import requests as http_requests
                        health_url = f"http://127.0.0.1:8081/api/{service_name}/api/health"
                        headers = {'Host': 'gateway.local'}
                        try:
                            health_response = http_requests.get(health_url, headers=headers, timeout=3)
                        except requests.exceptions.ConnectionError:
                            start_port_forward()
                            time.sleep(2)
                            health_response = http_requests.get(health_url, headers=headers, timeout=5)
                        
                        if health_response.status_code == 200:
                            # Service has /api/health endpoint - use detailed metrics
                            health_data = health_response.json()
                            system_metrics = health_data.get('system_metrics', {})
                            service_metrics = health_data.get('service_metrics', {})
                            cpu_usage = system_metrics.get('cpu_usage', 'N/A')
                            memory_usage = system_metrics.get('memory_usage', 'N/A')
                            disk_usage = system_metrics.get('disk_usage', 'N/A')
                            process_memory = system_metrics.get('process_memory_mb', 'N/A')
                            total_requests = service_metrics.get('total_requests', 0)
                            avg_response_time = service_metrics.get('avg_response_time_ms', 'N/A')
                            uptime = health_data.get('uptime', 'N/A')
                            print(f"✅ Health endpoint metrics collected for {service_name}")
                        else:
                            # Service doesn't have /api/health - use basic metrics
                            print(f"⚠️ Service {service_name} doesn't have /api/health endpoint, using basic metrics")
                            cpu_usage = 'N/A'
                            memory_usage = 'N/A'
                            disk_usage = 'N/A'
                            process_memory = 'N/A'
                            total_requests = 0
                            avg_response_time = 'N/A'
                            uptime = 'N/A'
                    except Exception as e:
                        print(f"Warning: Could not get health metrics for {service_name}: {e}")

                try:
                    if is_railway_environment():
                        # Use ArgoCD API instead of kubectl on Railway
                        session_token = _get_argocd_session_token()
                        if session_token:
                            headers = {
                                'Authorization': f'Bearer {session_token}',
                                'ngrok-skip-browser-warning': 'true'
                            }
                            app_response = requests.get(f"{ARGOCD_SERVER_URL}/api/v1/applications/{service_name}", 
                                                       headers=headers, timeout=10, verify=False)
                            if app_response.status_code == 200:
                                argocd_app = app_response.json()
                                health_status = argocd_app['status'].get('health', {}).get('status', 'Unknown')
                                sync_status = argocd_app['status'].get('sync', {}).get('status', 'Unknown')
                            else:
                                health_status = 'Unknown'
                                sync_status = 'Unknown'
                        else:
                            health_status = 'Unknown'
                            sync_status = 'Unknown'
                    else:
                        argocd_result = subprocess.run(['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'json'], capture_output=True, text=True, check=True)
                        argocd_app = json.loads(argocd_result.stdout)
                        health_status = argocd_app['status'].get('health', {}).get('status', 'Unknown')
                        sync_status = argocd_app['status'].get('sync', {}).get('status', 'Unknown')
                except Exception as e:
                    print(f"Warning: Could not get ArgoCD status for {service_name}: {e}")
                    health_status = 'Unknown'
                    sync_status = 'Unknown'

                replicas = deployment['spec'].get('replicas', 1)
                status = 'active' if health_status == 'Healthy' else 'degraded'

            except subprocess.CalledProcessError:
                health_status = 'Not Deployed'
                sync_status = 'Unknown'
                replicas = 0
                status = 'not_deployed'
                cpu_request = 'N/A'
                cpu_limit = 'N/A'
                memory_request = 'N/A'
                memory_limit = 'N/A'
                cpu_usage = 'N/A'
                memory_usage = 'N/A'
                disk_usage = 'N/A'
                process_memory = 'N/A'
                total_requests = 0
                avg_response_time = 'N/A'
                uptime = 'N/A'

            services.append({
                'name': service_name,
                'namespace': svc.get('namespace') or service_name,
                'port': port,
                'replicas': replicas,
                'health_status': health_status,
                'sync_status': sync_status,
                'description': description,
                'created_at': created_at,
                'status': status,
                'cpu_request': cpu_request,
                'cpu_limit': cpu_limit,
                'memory_request': memory_request,
                'memory_limit': memory_limit,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'process_memory': process_memory,
                'total_requests': total_requests,
                'avg_response_time': avg_response_time,
                'uptime': uptime,
                'repo_path': f"https://github.com/{owner_repo}/tree/main/services/{service_name}",
                'k8s_path': f"https://github.com/{owner_repo}/tree/main/services/{service_name}/k8s"
            })

        # Filter to only show healthy services
        healthy_services = [service for service in services if service.get('status') == 'active']
        
        healthy_services.sort(key=lambda x: x['name'])
        return jsonify({'services': healthy_services})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/update', methods=['PUT'])
def update_service(service_name):
    """Update service configuration"""
    try:
        data = request.get_json()
        
        # Get GitHub token from headers or use default
        github_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not github_token:
            return jsonify({'error': 'GitHub token required'}), 400
        
        # Validate required fields (port excluded as it cannot be changed)
        required_fields = ['description', 'replicas', 'min_replicas', 'max_replicas', 
                          'cpu_request', 'cpu_limit', 'memory_request', 'memory_limit']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Update service configuration in repository
        result = update_service_config(service_name, data, github_token)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'Service {service_name} updated successfully',
                'details': result.get('details', {})
            })
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/set-token', methods=['POST'])
def set_dashboard_token():
    """Set dashboard token for read-only operations"""
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        
        if not token:
            return jsonify({'error': 'Token is required'}), 400
        
        # Validate token
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json'}
        test_response = requests.get('https://api.github.com/user', headers=headers)
        if test_response.status_code != 200:
            return jsonify({'error': 'Invalid GitHub token'}), 400
        
        # Store token in session or return success
        # For now, just validate and return success
        return jsonify({'message': 'Token validated successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/debug-list', methods=['GET'])
def debug_list_services():
    try:
        # Fixed GitHub repo for debug listing
        owner, repo = 'ductri09072004', 'demo_fiss1_B'
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'dev-portal'}
        # Use dashboard token for read-only operations
        token_to_use = DASHBOARD_TOKEN or MANIFESTS_REPO_TOKEN
        if token_to_use:
            headers['Authorization'] = f'token {token_to_use}'
        url = f"https://api.github.com/repos/ductri09072004/demo_fiss1_B/contents/services?ref=main"
        r = requests.get(url, headers=headers)
        out = {
            'url': url,
            'status_code': r.status_code,
            'rate_limit_remaining': r.headers.get('X-RateLimit-Remaining'),
            'scopes': r.headers.get('X-OAuth-Scopes'),
        }
        try:
            body = r.json()
        except Exception:
            body = r.text
        # Only include names to keep output small
        if isinstance(body, list):
            out['items'] = [
                {
                    'name': it.get('name'),
                    'type': it.get('type')
                } for it in body
            ]
        else:
            out['body'] = body
        return jsonify(out)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# Mongo-backed APIs are registered in api_db.register_db_api(app, service_manager)

def read_service_info(service_name, k8s_path):
    """Read service information from k8s files"""
    service_info = {
        'port': 5001,
        'description': f'Demo service {service_name}',
        'created_at': 'Unknown'
    }
    
    try:
        # Read from configmap.yaml
        configmap_path = os.path.join(k8s_path, 'configmap.yaml')
        if os.path.exists(configmap_path):
            with open(configmap_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract PORT value
                import re
                port_match = re.search(r'PORT:\s*"(\d+)"', content)
                if port_match:
                    service_info['port'] = int(port_match.group(1))
        
        # Read from deployment.yaml for description
        deployment_path = os.path.join(k8s_path, 'deployment.yaml')
        if os.path.exists(deployment_path):
            with open(deployment_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract description from labels or annotations
                desc_match = re.search(r'description:\s*"([^"]*)"', content)
                if desc_match:
                    service_info['description'] = desc_match.group(1)
        
        # Get file creation time
        if os.path.exists(k8s_path):
            import time
            created_time = os.path.getctime(k8s_path)
            service_info['created_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(created_time))
            
    except Exception as e:
        print(f"Error reading service info for {service_name}: {e}")
    
    return service_info

@app.route('/api/services/<service_name>', methods=['DELETE'])
def delete_service(service_name):
    """Delete a service"""
    try:
        # 1) Delete ArgoCD application (remove finalizers if blocking)
        try:
            subprocess.run(['kubectl', 'delete', 'application', service_name, '-n', 'argocd'], check=True)
        except subprocess.CalledProcessError:
            # try remove finalizers then delete again
            try:
                subprocess.run([
                    'kubectl','patch','application',service_name,'-n','argocd',
                    "--type","merge","-p","{\"metadata\":{\"finalizers\":null}}"
                ], check=True)
                subprocess.run(['kubectl', 'delete', 'application', service_name, '-n', 'argocd'], check=False)
            except subprocess.CalledProcessError:
                pass

        # 2) Proactively delete namespaced resources that often block deletion
        try:
            resource_groups = [
                ['deployment','statefulset','daemonset','replicaset','pod'],
                ['service','ingress','endpoints'],
                ['configmap','secret','serviceaccount'],
                ['job','cronjob','hpa'],
                ['pvc']
            ]
            for group in resource_groups:
                subprocess.run(['kubectl','delete',*group,'--all','-n',service_name,'--ignore-not-found'], check=False, capture_output=True, text=True)

            # Force delete any remaining pods
            subprocess.run(['kubectl','delete','pod','--all','-n',service_name,'--grace-period=0','--force','--ignore-not-found'], check=False, capture_output=True, text=True)
            # Extra sweep: delete all built-in resources regardless of label
            subprocess.run(['kubectl','delete','all','--all','-n',service_name,'--ignore-not-found','--wait=false'], check=False, capture_output=True, text=True)
            subprocess.run(['kubectl','delete','pvc','--all','-n',service_name,'--ignore-not-found','--wait=false'], check=False, capture_output=True, text=True)
        except Exception:
            pass

        # 3) Delete namespace (remove finalizers if stuck terminating)
        try:
            subprocess.run(['kubectl', 'delete', 'namespace', service_name], check=True)
        except subprocess.CalledProcessError:
            # remove finalizers
            try:
                # fetch namespace json
                ns_json = subprocess.run(['kubectl','get','ns',service_name,'-o','json'], capture_output=True, text=True, check=True)
                data = json.loads(ns_json.stdout)
                if 'spec' in data and isinstance(data.get('spec'), dict):
                    data['spec'].pop('finalizers', None)
                # write temp file
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
                tmp.write(json.dumps(data).encode('utf-8'))
                tmp.close()
                subprocess.run(['kubectl','replace','--raw',f'/api/v1/namespaces/{service_name}/finalize','-f',tmp.name], check=False)
            except Exception:
                pass
        
        # 4) Delete service folder from local Repo B
        repo_b_path = os.path.join(REPO_B_SERVICES_PATH, service_name)
        if os.path.exists(repo_b_path):
            shutil.rmtree(repo_b_path)
            # If local Repo B is a git repo, commit and push
            try:
                repo_b_root = os.path.dirname(REPO_B_SERVICES_PATH)
                if os.path.isdir(os.path.join(repo_b_root, '.git')):
                    subprocess.run(['git','add','-A'], cwd=repo_b_root, check=False)
                    subprocess.run(['git','config','user.email','dev-portal@local'], cwd=repo_b_root, check=False)
                    subprocess.run(['git','config','user.name','Dev Portal'], cwd=repo_b_root, check=False)
                    subprocess.run(['git','commit','-m',f'chore: remove service {service_name}'], cwd=repo_b_root, check=False)
                    subprocess.run(['git','push','origin','main'], cwd=repo_b_root, check=False)
            except Exception:
                pass

        # 5) Delete service folder from remote Repo B (fallback to DEFAULT_REPO_B_URL when DB missing)
        try:
            # find service in DB to get repo_b_url
            services = service_manager.get_services()
            svc = next((s for s in services if s.get('name') == service_name), None)
            repo_b_url = (svc or {}).get('metadata', {}).get('repo_b_url', '') if svc else ''
            if not repo_b_url:
                repo_b_url = DEFAULT_REPO_B_URL
            if repo_b_url:
                # Use GitHub Contents API to delete files in services/<service_name>/
                def _parse_repo(url: str):
                    try:
                        u = urlparse(url)
                        parts = [p for p in u.path.strip('/').split('/') if p]
                        owner, repo = parts[0], parts[1]
                        if repo.endswith('.git'):
                            repo = repo[:-4]
                        return owner, repo
                    except Exception:
                        return None, None
                owner, repo = _parse_repo(repo_b_url)
                if owner and repo:
                    # Use default token for deletion since no token is passed from frontend
                    token_to_use = MANIFESTS_REPO_TOKEN
                    if token_to_use:
                        headers = {
                            'Accept': 'application/vnd.github+json',
                            'Authorization': f'token {token_to_use}'
                        }
                    else:
                        headers = {'Accept': 'application/vnd.github+json'}
                    import base64
                    def _get_sha(path_in_repo: str):
                        r = requests.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path_in_repo}", headers=headers)
                        if r.status_code == 200:
                            j = r.json()
                            if isinstance(j, dict):
                                return j.get('sha')
                        return None
                    def _delete_file(path_in_repo: str, message: str):
                        sha = _get_sha(path_in_repo)
                        if not sha:
                            return
                        requests.delete(
                            f"https://api.github.com/repos/{owner}/{repo}/contents/{path_in_repo}",
                            headers=headers,
                            json={'message': message, 'sha': sha, 'branch': 'main'}
                        )
                    # Known files under k8s to remove
                    files_to_delete = [
                        f"services/{service_name}/k8s/deployment.yaml",
                        f"services/{service_name}/k8s/service.yaml",
                        f"services/{service_name}/k8s/configmap.yaml",
                        f"services/{service_name}/k8s/hpa.yaml",
                        f"services/{service_name}/k8s/ingress.yaml",
                        f"services/{service_name}/k8s/ingress-gateway.yaml",
                        f"services/{service_name}/k8s/namespace.yaml",
                        f"services/{service_name}/k8s/secret.yaml",
                        f"services/{service_name}/k8s/argocd-application.yaml",
                    ]
                    for p in files_to_delete:
                        try:
                            _delete_file(p, f"remove service {service_name}")
                        except Exception:
                            pass
        except Exception:
            pass
        
        # 6) Delete from database (if exists)
        try:
            service_manager.delete_service(service_name)
        except Exception:
            pass
        
        return jsonify({'message': f'Service {service_name} deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/sync', methods=['POST'])
def sync_services():
    """Sync services from Repo B folder structure to database"""
    try:
        repo_b_path = REPO_B_SERVICES_PATH
        synced_count = 0
        
        if not os.path.exists(repo_b_path):
            return jsonify({'error': 'Repo B services directory not found'}), 404
        
        # Get all service directories
        service_dirs = [d for d in os.listdir(repo_b_path) 
                       if os.path.isdir(os.path.join(repo_b_path, d)) and d.startswith('demo-v')]
        
        for service_name in service_dirs:
            service_path = os.path.join(repo_b_path, service_name)
            k8s_path = os.path.join(service_path, 'k8s')
            
            if not os.path.exists(k8s_path):
                continue
            
            # Read service information
            service_info = read_service_info(service_name, k8s_path)
            
            # Check if service already exists in database
            existing_services = service_manager.get_services()
            if not any(s['name'] == service_name for s in existing_services):
                # Add to database - parse from YAML files
                if service_manager.add_service_from_yaml(service_name, k8s_path, ''):
                    synced_count += 1
        
        return jsonify({
            'message': f'Synced {synced_count} services from Repo B',
            'synced_count': synced_count
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/restart', methods=['POST'])
def restart_service(service_name):
    """Restart a service"""
    try:
        # Restart deployment
        subprocess.run(['kubectl', 'rollout', 'restart', 'deployment', service_name, '-n', service_name], 
                      check=True)
        
        return jsonify({'message': f'Service {service_name} restarted successfully'})
        
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'Failed to restart service: {e.stderr}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/logs')
def get_service_logs(service_name):
    """Get service logs"""
    try:
        # Get pods for the service
        result = subprocess.run(['kubectl', 'get', 'pods', '-n', service_name, 
                               '-l', f'app={service_name}', '-o', 'json'], 
                               capture_output=True, text=True, check=True)
        pods = json.loads(result.stdout)
        
        if not pods['items']:
            return jsonify({'error': 'No pods found'}), 404
        
        # Get logs from first pod
        pod_name = pods['items'][0]['metadata']['name']
        logs_result = subprocess.run(['kubectl', 'logs', pod_name, '-n', service_name, '--tail=100'], 
                                    capture_output=True, text=True, check=True)
        
        return jsonify({'logs': logs_result.stdout})
        
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'Failed to get logs: {e.stderr}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/details')
def get_service_details(service_name):
    """Get detailed service information"""
    try:
        # Get deployment details
        deploy_result = subprocess.run(['kubectl', 'get', 'deployment', service_name, 
                                      '-n', service_name, '-o', 'json'], 
                                      capture_output=True, text=True, check=True)
        deployment = json.loads(deploy_result.stdout)
        
        # Get service details
        svc_result = subprocess.run(['kubectl', 'get', 'service', f'{service_name}-service', 
                                   '-n', service_name, '-o', 'json'], 
                                   capture_output=True, text=True, check=True)
        service_info = json.loads(svc_result.stdout)
        
        # Get pods
        pods_result = subprocess.run(['kubectl', 'get', 'pods', '-n', service_name, 
                                    '-l', f'app={service_name}', '-o', 'json'], 
                                    capture_output=True, text=True, check=True)
        pods = json.loads(pods_result.stdout)
        
        return jsonify({
            'deployment': deployment,
            'service': service_info,
            'pods': pods
        })
        
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'Failed to get service details: {e.stderr}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create_service', methods=['POST'])
def create_service():
    try:
        # Get form data
        github_token = request.form.get('github_token', '').strip()
        # manifests_token is now optional - use config default if not provided
        manifests_token = request.form.get('manifests_token', '').strip() or MANIFESTS_REPO_TOKEN
        service_name = request.form.get('service_name')
        description = request.form.get('description')
        repo_url = request.form.get('repo_url', '').strip()
        repo_b_url = request.form.get('repo_b_url', '').strip()
        namespace = request.form.get('namespace', '').strip()
        repo_b_path = request.form.get('repo_b_path', '').strip()
        image_tag_mode = request.form.get('image_tag_mode', 'latest').strip()
        
        # Validate GitHub token
        if not github_token:
            return jsonify({'error': 'GitHub token is required'}), 400
        
        # Test GitHub token validity
        try:
            headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github+json'}
            test_response = requests.get('https://api.github.com/user', headers=headers)
            if test_response.status_code != 200:
                return jsonify({'error': 'Invalid GitHub token. Please check your token and try again.'}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to validate GitHub token: {str(e)}'}), 400
        
        # Kubernetes configuration
        replicas = request.form.get('replicas', '3')
        min_replicas = request.form.get('min_replicas', '2')
        max_replicas = request.form.get('max_replicas', '10')
        cpu_request = request.form.get('cpu_request', '100m')
        cpu_limit = request.form.get('cpu_limit', '200m')
        memory_request = request.form.get('memory_request', '128Mi')
        memory_limit = request.form.get('memory_limit', '256Mi')
        
        # Validate input
        if not service_name:
            return jsonify({'error': 'Service name is required'}), 400
        if not repo_url:
            return jsonify({'error': 'GitHub repo URL is required'}), 400
        # If Repo B URL not provided, use default
        if not repo_b_url:
            repo_b_url = DEFAULT_REPO_B_URL
        if not namespace:
            namespace = service_name
        if not repo_b_path:
            repo_b_path = f"services/{service_name}/k8s"
        
        # Get port from auto-detection
        repo_analysis = analyze_repository_structure(repo_url, github_token)
        if not repo_analysis.get('success'):
            print(f"⚠️ Repo analysis failed: {repo_analysis.get('error')}")
            # Fallback defaults for Python/Flask
            repo_analysis = {
                'success': True,
                'language': 'python',
                'framework': 'flask',
                'port': '5000'
            }
        
        detected_port = repo_analysis.get('port', '5000')
        print(f"🔍 Auto-detected port: {detected_port}")
        
        # Create service data
        service_data = {
            'service_name': service_name,
            'description': description,
            'port': detected_port,
            'replicas': replicas,
            'min_replicas': min_replicas,
            'max_replicas': max_replicas,
            'cpu_request': cpu_request,
            'cpu_limit': cpu_limit,
            'memory_request': memory_request,
            'memory_limit': memory_limit,
            'created_at': datetime.now().isoformat()
        }
        
        # Create GitHub webhook for the repository
        webhook_result = create_github_webhook(repo_url, github_token, WEBHOOK_URL)
        if webhook_result['success']:
            print(f"✅ Webhook created for {service_name}: {webhook_result.get('webhook_id')}")
        else:
            print(f"⚠️ Warning: Failed to create webhook for {service_name}: {webhook_result.get('error')}")
            # Continue with service creation even if webhook fails

        # Ensure secrets exist BEFORE adding CI/CD (to avoid race condition)
        try:
            print("Setting repository secrets BEFORE adding CI/CD...")
            print(f"Repository URL: {repo_url}")
            print(f"GitHub token: {'SET' if github_token else 'NOT SET'}")
            print(f"Manifests token: {'SET' if manifests_token else 'NOT SET'}")
            secrets_result = ensure_repo_secrets(repo_url, github_token, manifests_token, service_name)
            print(f"Secrets result: {secrets_result}")
            if not secrets_result:
                print("⚠️ Warning: Failed to set repository secrets. CI/CD may fail on first run.")
            else:
                print("✅ Repository secrets set successfully")
        except Exception as e:
            print(f"⚠️ Warning: Could not set repository secrets: {e}")
            # Continue anyway - secrets might be set already

        # Add CI/CD and Dockerfile directly to GitHub using API (idempotent)
        try:
            print(f"🧩 Adding CI/CD + Dockerfile to repo: {repo_url}")

            dockerfile_content = generate_dockerfile_from_analysis(repo_analysis)
            cicd_content = generate_cicd_pipeline(repo_analysis, service_name)

            # Only add Dockerfile and a single CI/CD workflow (ci-cd.yml)
            files_to_add = {
                'Dockerfile': dockerfile_content,
                '.github/workflows/ci-cd.yml': cicd_content
            }

            add_files_result = add_files_to_repository(repo_url, github_token, files_to_add)
            if not add_files_result.get('success'):
                print(f"❌ Failed to add CI/CD files: {add_files_result.get('error')}")
                return jsonify({
                    'success': False,
                    'error': f"Failed to add CI/CD files: {add_files_result.get('error')}"
                }), 500
            else:
                print(f"✅ CI/CD files added successfully: {add_files_result.get('added_files')}")
        except Exception as ensure_err:
            print(f"❌ Error adding CI/CD files: {ensure_err}")
            return jsonify({
                'success': False,
                'error': f"Error adding CI/CD files: {ensure_err}"
            }), 500
        
        # After Repo A ok → update Repo B manifests
        repo_b_res = generate_repo_b(service_data, repo_url, repo_b_url, repo_b_path, namespace, image_tag_mode, github_token)
        if not repo_b_res['success']:
            return jsonify({'success': False, 'error': f"Repo B update failed: {repo_b_res['error']}"}), 500
        
        # Save to database - use form data to populate all collections
        # ArgoCD plugin will later read from MongoDB and create YAML files
        print(f"DEBUG: Creating service {service_name} with form data")
        
        # Extract repo name from repo_url for webhook mapping
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(repo_url)
            repo_path = parsed_url.path.strip('/')
            if repo_path.endswith('.git'):
                repo_path = repo_path[:-4]
            repo_name = repo_path.split('/')[-1] if '/' in repo_path else repo_path
        except:
            repo_name = service_name  # Fallback to service_name
        
        # Override repo_b_path to use UI service name for consistency
        repo_b_path = f"services/{service_name}/k8s"
        print(f"🔧 Using repo_b_path: {repo_b_path} (based on UI service name: {service_name})")
        
        db_service_data = {
            'name': service_name,
            'repo_name': repo_name,  # Add repo_name for webhook mapping
            'namespace': namespace,
            'port': int(detected_port),
            'description': description,
            'repo_url': repo_url,
            'replicas': int(replicas),
            'min_replicas': int(min_replicas),
            'max_replicas': int(max_replicas),
            'cpu_request': cpu_request,
            'cpu_limit': cpu_limit,
            'memory_request': memory_request,
            'memory_limit': memory_limit,
            'metadata': {
                'created_by': 'portal',
                'template': 'repo_a_template',
                'repo_b_url': repo_b_url,
                'repo_b_path': repo_b_path
            }
        }
        result = service_manager.add_service_complete(db_service_data)
        print(f"DEBUG: add_service_complete result: {result}")
            
        response_data = {
                'success': True,
                'message': f'Service "{service_name}" created successfully!',
                'repo_url': repo_url,
                'clone_url': repo_url,
                'repo_b_url': repo_b_url,
                'repo_b_path': repo_b_path
        }

        # Attach files added info if available
        try:
            if 'add_files_result' in locals() and add_files_result:
                response_data['files_added'] = add_files_result.get('added_files', [])
                response_data['files_added_count'] = len(add_files_result.get('added_files', []))
        except Exception:
            pass
        
        # Secrets were already set before adding CI/CD, no need to set again

        # Add webhook information to response
        if webhook_result['success']:
            response_data['webhook'] = {
                'created': True,
                'webhook_id': webhook_result.get('webhook_id'),
                'webhook_url': webhook_result.get('webhook_url')
            }
        else:
            response_data['webhook'] = {
                'created': False,
                'error': webhook_result.get('error')
            }
        
        return jsonify(response_data)
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

def analyze_repository_structure(repo_url, github_token):
    """Analyze repository to detect technology stack"""
    try:
        # Extract owner and repo name from URL
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        import re
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return {'success': False, 'error': 'Invalid GitHub repository URL'}
        
        owner = match.group(1)
        repo_name = match.group(2)
        
        # Get repository contents
        headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github+json'}
        contents_url = f'https://api.github.com/repos/{owner}/{repo_name}/contents'
        
        response = requests.get(contents_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return {'success': False, 'error': f'Failed to access repository: {response.status_code}'}
        
        files = response.json()
        file_names = [file['name'] for file in files if file['type'] == 'file']
        
        # Detect technology stack
        analysis = {
            'success': True,
            'language': 'unknown',
            'framework': 'unknown',
            'port': '8000',
            'dependencies': [],
            'has_dockerfile': False,
            'has_cicd': False,
            'has_k8s': False
        }
        
        # Check for Python
        if 'requirements.txt' in file_names:
            analysis['language'] = 'python'
            analysis['dependencies'].append('requirements.txt')
            
            # Check for Flask
            if any('app.py' in name or 'main.py' in name for name in file_names):
                if 'app.py' in file_names:
                    analysis['framework'] = 'flask'
                    analysis['port'] = '5000'
                elif 'main.py' in file_names:
                    analysis['framework'] = 'fastapi'
                    analysis['port'] = '8000'
                
                # Try to detect actual port from code
                try:
                    for file_info in files:
                        if file_info['name'] in ['app.py', 'main.py', 'server.py']:
                            file_url = file_info['download_url']
                            file_response = requests.get(file_url, headers=headers, timeout=10)
                            if file_response.status_code == 200:
                                content = file_response.text
                                # Look for port patterns
                                import re
                                port_patterns = [
                                    r'port\s*=\s*(\d+)',
                                    r'PORT\s*=\s*(\d+)',
                                    r'port=(\d+)',
                                    r'PORT=(\d+)',
                                    r'\.run\([^)]*port\s*=\s*(\d+)',
                                    r'uvicorn\.run\([^)]*port\s*=\s*(\d+)',
                                    r'host="[^"]*",\s*port=(\d+)',
                                    r'listen\((\d+)\)',
                                    r':(\d+)\)'
                                ]
                                for pattern in port_patterns:
                                    match = re.search(pattern, content, re.IGNORECASE)
                                    if match:
                                        detected_port = match.group(1)
                                        if detected_port and detected_port != '0':
                                            analysis['port'] = detected_port
                                            print(f"Detected port {detected_port} from {file_info['name']}")
                                            break
                                if 'port' in analysis and analysis['port'] != '5000':
                                    break
                except Exception as e:
                    print(f"Error detecting port from code: {e}")
        
        # Check for Node.js
        elif 'package.json' in file_names:
            analysis['language'] = 'nodejs'
            analysis['framework'] = 'express'
            analysis['port'] = '3000'
            analysis['dependencies'].append('package.json')
        
        # Check for Java
        elif 'pom.xml' in file_names:
            analysis['language'] = 'java'
            analysis['framework'] = 'spring'
            analysis['port'] = '8080'
            analysis['dependencies'].append('pom.xml')
        
        # Check for existing files
        analysis['has_dockerfile'] = 'Dockerfile' in file_names
        analysis['has_cicd'] = '.github' in [f['name'] for f in files if f['type'] == 'dir']
        analysis['has_k8s'] = 'k8s' in [f['name'] for f in files if f['type'] == 'dir']
        
        return analysis
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def _read_template_from_repo_a(relative_path: str) -> str:
    """Read a template file from templates_src/repo_a_template. Returns empty string if missing."""
    try:
        base_dir = os.path.join(os.getcwd(), 'templates_src', 'repo_a_template')
        template_path = os.path.join(base_dir, *relative_path.split('/'))
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as _:
        pass
    return ''

def generate_dockerfile_from_analysis(repo_analysis):
    """Generate Dockerfile based on technology stack"""
    if repo_analysis['language'] == 'python':
        if repo_analysis['framework'] == 'flask':
            return f"""FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Expose port
EXPOSE {repo_analysis['port']}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:{repo_analysis['port']}/api/health || exit 1

# Run application
CMD ["python", "app.py"]"""
        
        elif repo_analysis['framework'] == 'fastapi':
            return f"""FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE {repo_analysis['port']}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:{repo_analysis['port']}/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{repo_analysis['port']}"]"""
    
    elif repo_analysis['language'] == 'nodejs':
        return f"""FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN if [ -f package-lock.json ]; then \\
        npm ci --omit=dev; \\
    else \\
        npm install --omit=dev; \\
    fi

# Copy application code
COPY . .

# Create non-root user
RUN addgroup -g 1001 -S nodejs
RUN adduser -S nodejs -u 1001
USER nodejs

# Expose port
EXPOSE {repo_analysis['port']}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:{repo_analysis['port']}/health || exit 1

# Run application
CMD ["npm", "start"]"""
    
    # Default fallback
    return f"""FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE {repo_analysis['port']}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:{repo_analysis['port']}/health || exit 1

# Run application
CMD ["python", "main.py"]"""

def generate_cicd_pipeline(repo_analysis, service_name):
    """Return CI/CD pipeline content. Prefer template from templates_src/repo_a_template/.github/workflows/ci-cd.yml."""
    templ = _read_template_from_repo_a('.github/workflows/ci-cd.yml')
    if templ:
        return templ
    # Fallback minimal workflow
    return (
        "name: Deploy to Kubernetes\n\n"
        "on:\n  push:\n    branches: [main]\n\n"
        "jobs:\n  build-and-deploy:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v3\n"
        "      - name: Build Docker image\n        run: |\n          docker build -t ${{ github.repository }}:${{ github.sha }} .\n\n"
        "      - name: Push to registry\n        run: |\n          docker tag ${{ github.repository }}:${{ github.sha }} ghcr.io/${{ github.repository }}:${{ github.sha }}\n          docker push ghcr.io/${{ github.repository }}:${{ github.sha }}\n\n"
        "      - name: Update K8s manifests\n        run: |\n          sed -i \"s|image: .*|image: ghcr.io/${{ github.repository }}:${{ github.sha }}|g\" k8s/deployment.yaml\n\n"
        "      - name: Commit and push changes\n        run: |\n          git config --local user.email \"action@github.com\"\n          git config --local user.name \"GitHub Action\"\n          git add k8s/\n          git commit -m \"Update image tag to ${{ github.sha }}\" || exit 0\n          git push\n"
    )

def generate_k8s_manifests(service_name, namespace, port, replicas, min_replicas, max_replicas, cpu_request, cpu_limit, memory_request, memory_limit):
    """Generate K8s manifests from template"""
    # This will use the existing template system
    return {
        'k8s/namespace.yaml': f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    name: {namespace}
    app: {service_name}""",
        
        'k8s/deployment.yaml': f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service_name}
  namespace: {namespace}
  labels:
    app: {service_name}
    version: v1.0.0
spec:
  replicas: {replicas}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  selector:
    matchLabels:
      app: {service_name}
  template:
    metadata:
      labels:
        app: {service_name}
        version: v1.0.0
    spec:
      containers:
      - name: {service_name}
        image: ghcr.io/ductri09072004/{service_name}:latest
        imagePullPolicy: Always
        ports:
        - containerPort: {port}
          name: http
        resources:
          requests:
            memory: "{memory_request}"
            cpu: "{cpu_request}"
          limits:
            memory: "{memory_limit}"
            cpu: "{cpu_limit}"
        livenessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: {port}
          initialDelaySeconds: 5
          periodSeconds: 5""",
        
        'k8s/service.yaml': f"""apiVersion: v1
kind: Service
metadata:
  name: {service_name}-service
  namespace: {namespace}
  labels:
    app: {service_name}
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: {port}
    protocol: TCP
    name: http
  selector:
    app: {service_name}""",
        
        'k8s/hpa.yaml': f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {service_name}-hpa
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {service_name}
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70"""
    }

def add_files_to_repository(repo_url, github_token, files):
    """Add files to repository using GitHub API"""
    try:
        # Extract owner and repo name from URL
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        import re
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return {'success': False, 'error': 'Invalid GitHub repository URL'}
        
        owner = match.group(1)
        repo_name = match.group(2)
        
        headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github+json'}

        # Determine default branch to target
        repo_api_url = f'https://api.github.com/repos/{owner}/{repo_name}'
        repo_info_resp = requests.get(repo_api_url, headers=headers, timeout=30)
        target_branch = 'main'
        if repo_info_resp.status_code == 200:
            target_branch = repo_info_resp.json().get('default_branch', 'main') or 'main'
        
        added_files = []
        failed_files = []
        
        for file_path, content in files.items():
            try:
                # Encode content to base64
                import base64
                content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                
                # Create file via GitHub API
                create_url = f'https://api.github.com/repos/{owner}/{repo_name}/contents/{file_path}'
                data = {
                    'message': f'Add {file_path} for deployment',
                    'content': content_b64,
                    'branch': target_branch
                }
                
                response = requests.put(create_url, headers=headers, json=data, timeout=30)
                if response.status_code in [200, 201]:
                    added_files.append(file_path)
                    print(f"✅ Added {file_path} to repository")
                else:
                    error_msg = f"Failed to create {file_path}: {response.status_code} {response.text}"
                    if response.status_code == 422:
                        # File might already exist, try to update it
                        try:
                            # Get existing file SHA
                            get_url = f'https://api.github.com/repos/{owner}/{repo_name}/contents/{file_path}'
                            get_response = requests.get(get_url, headers=headers, params={'ref': target_branch}, timeout=30)
                            if get_response.status_code == 200:
                                existing_file = get_response.json()
                                data['sha'] = existing_file['sha']
                                
                                update_response = requests.put(create_url, headers=headers, json=data, timeout=30)
                                if update_response.status_code in [200, 201]:
                                    added_files.append(file_path)
                                    print(f"✅ Updated {file_path} in repository")
                                else:
                                    failed_files.append(f"{file_path}: {update_response.status_code} {update_response.text}")
                            else:
                                failed_files.append(f"{file_path}: {response.status_code} {response.text}")
                        except Exception as update_error:
                            failed_files.append(f"{file_path}: {str(update_error)}")
                    else:
                        failed_files.append(f"{file_path}: {response.status_code} {response.text}")
                        print(f"❌ {error_msg}")
                        
            except Exception as file_error:
                failed_files.append(f"{file_path}: {str(file_error)}")
                print(f"❌ Error adding {file_path}: {file_error}")
        
        if failed_files:
            return {
                'success': False, 
                'error': f'Failed to add some files: {", ".join(failed_files)}',
                'added_files': added_files,
                'failed_files': failed_files
            }
        else:
            return {
                'success': True,
                'added_files': added_files,
                'message': f'Successfully added {len(added_files)} files to repository'
            }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def create_github_webhook(repo_url, github_token, webhook_url):
    """Create GitHub webhook for the repository"""
    try:
        # Extract owner and repo name from URL
        # Support both https://github.com/owner/repo and https://github.com/owner/repo.git
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        # Parse URL to get owner and repo name
        import re
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return {'success': False, 'error': 'Invalid GitHub repository URL'}
        
        owner = match.group(1)
        repo_name = match.group(2)
        
        # GitHub API endpoint for creating webhook
        api_url = f'https://api.github.com/repos/{owner}/{repo_name}/hooks'
        
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }
        
        # Webhook configuration
        webhook_data = {
            'name': 'web',
            'active': True,
            'events': ['push'],  # Only listen to push events
            'config': {
                'url': webhook_url,
                'content_type': 'form'  # GitHub sends webhook as form data
            }
        }
        
        print(f"Creating webhook for {owner}/{repo_name} with URL: {webhook_url}")
        
        response = requests.post(api_url, headers=headers, json=webhook_data, timeout=30)
        
        if response.status_code == 201:
            webhook_info = response.json()
            print(f"✅ Webhook created successfully: {webhook_info.get('id')}")
            return {
                'success': True, 
                'webhook_id': webhook_info.get('id'),
                'webhook_url': webhook_info.get('config', {}).get('url')
            }
        else:
            error_msg = f"Failed to create webhook: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail.get('message', 'Unknown error')}"
            except:
                error_msg += f" - {response.text}"
            
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}
            
    except Exception as e:
        error_msg = f"Exception while creating webhook: {str(e)}"
        print(f"❌ {error_msg}")
        return {'success': False, 'error': error_msg}

def generate_repository(service_data, repo_url, github_token=None):
    """Generate repository from E:\\Study\\demo_fiss1 template and push to provided GitHub repo URL"""
    try:
        service_name = service_data['service_name']
        
        # Create temporary directory for repository
        import tempfile
        repo_dir = tempfile.mkdtemp(prefix=f'{service_name}_')
        
        # Copy template from local templates_src (cloned once for speed)
        template_src = TEMPLATE_A_PATH
        if not os.path.isdir(template_src):
            return {'success': False, 'error': f'Template source not found: {template_src}'}

        # Clean target dir if previously generated
        for name in os.listdir(repo_dir):
            path = os.path.join(repo_dir, name)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception:
                pass

        shutil.copytree(template_src, repo_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git', '__pycache__', '.venv', 'venv', '.pytest_cache'))

        # Replace placeholders in all files
        namespace = service_name  # Use service name as namespace
        port = service_data['port']
        repl = {
            '{SERVICE_NAME}': service_name,
            '{NAMESPACE}': namespace,
            '{PORT}': port,
        }
        
        for root, _, files in os.walk(repo_dir):
            for file in files:
                if not file.endswith(('.py', '.md', '.yml', '.yaml', '.txt', 'Dockerfile')):
                    continue
                p = os.path.join(root, file)
                try:
                    with open(p, 'r', encoding='utf-8') as rf:
                        content = rf.read()
                    for k, v in repl.items():
                        content = content.replace(k, v)
                    with open(p, 'w', encoding='utf-8') as wf:
                        wf.write(content)
                except Exception:
                    pass

        # Initialize git repository (compatible with older git)
        proc = subprocess.run(['git', 'init', '-b', 'main'], cwd=repo_dir)
        if proc.returncode != 0:
            subprocess.run(['git', 'init'], cwd=repo_dir, check=True)
            subprocess.run(['git', 'checkout', '-b', 'main'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'add', '--all'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=repo_dir, check=True)
        st = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_dir, capture_output=True, text=True, check=True)
        if st.stdout.strip():
            subprocess.run(['git', 'commit', '-m', 'Initial commit generated by Dev Portal'], cwd=repo_dir, check=True)

        # Prepare remote URL (embed token if available)
        remote = repo_url
        token_to_use = github_token or GITHUB_TOKEN
        if token_to_use and '://' in repo_url:
            parsed = urlparse(repo_url)
            # Insert token as basic auth in URL: https://TOKEN@github.com/owner/repo.git
            remote = f"{parsed.scheme}://{token_to_use}@{parsed.netloc}{parsed.path}"

        # Set remote and push
        subprocess.run(['git', 'remote', 'remove', 'origin'], cwd=repo_dir, check=False)
        subprocess.run(['git', 'remote', 'add', 'origin', remote], cwd=repo_dir, check=True)
        # align local main with remote/main to avoid non-fast-forward
        subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=repo_dir, check=False)
        subprocess.run(['git', 'checkout', '-B', 'main', 'origin/main'], cwd=repo_dir, check=False)
        push_proc = subprocess.run(['git', 'push', '-u', 'origin', 'main'], cwd=repo_dir, capture_output=True, text=True)
        if push_proc.returncode != 0:
            err = push_proc.stderr or ''
            refusing_workflow = 'refusing to allow a Personal Access Token to create or update workflow' in err
            if refusing_workflow:
                # Remove workflow file and retry push as fallback when PAT lacks 'workflow' scope
                wf_path = os.path.join(repo_dir, '.github', 'workflows', 'ci-cd.yml')
                try:
                    if os.path.exists(wf_path):
                        os.remove(wf_path)
                        subprocess.run(['git', 'add', '--all'], cwd=repo_dir, check=True)
                        subprocess.run(['git', 'commit', '-m', 'chore: remove workflow due to missing PAT workflow scope'], cwd=repo_dir, check=False)
                        retry_proc = subprocess.run(['git', 'push', '-u', 'origin', 'main'], cwd=repo_dir, capture_output=True, text=True)
                        if retry_proc.returncode != 0:
                            return {
                                'success': False,
                                'error': f"Failed to push (after removing workflow): {retry_proc.stderr}",
                                'repo_url': repo_url,
                                'clone_url': repo_url
                            }
                    else:
                        return {
                            'success': False,
                            'error': f"Failed to push to remote: {err}",
                            'repo_url': repo_url,
                            'clone_url': repo_url
                        }
                except Exception as e:
                    return {
                        'success': False,
                        'error': f"Push failed and cleanup errored: {e}",
                        'repo_url': repo_url,
                        'clone_url': repo_url
                    }
            else:
                return {
                    'success': False,
                    'error': f"Failed to push to remote: {err}",
                    'repo_url': repo_url,
                    'clone_url': repo_url
                }

        # Ensure secrets exist for this repository (GHCR_TOKEN, MANIFESTS_REPO_TOKEN)
        try:
            ensure_repo_secrets(repo_url, github_token, None)  # Use default from config
        except Exception:
            pass

        # Clean up temporary directory
        try:
            shutil.rmtree(repo_dir, ignore_errors=True)
        except Exception:
            pass
        
        return {
            'success': True,
            'repo_url': repo_url,
            'clone_url': repo_url
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def generate_app_py(repo_dir, service_data, namespace):
    """Generate Flask app.py from template with placeholders replaced"""
    service_name = service_data['service_name']
    port = service_data['port']
    
    # Copy template and replace placeholders
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_file = os.path.join(base_dir, 'templates_src', 'repo_a_template', 'app.py')
    
    if os.path.exists(template_file):
        # Read template
        with open(template_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace placeholders
        content = content.replace('{SERVICE_NAME}', service_name)
        content = content.replace('{NAMESPACE}', namespace)
        content = content.replace('{PORT}', port)
        
        # Write to repo
        with open(os.path.join(repo_dir, 'app.py'), 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        # Fallback to old method if template not found
        mock_data_type = service_data.get('mock_data_type', 'users')
        data_count = service_data.get('data_count', 10)
        endpoints = service_data.get('endpoints', ['/api/health', '/api/users'])
    
    # Generate mock data based on type
    if mock_data_type == 'users':
        mock_data = f'''MOCK_USERS = [
    {{"id": i, "name": f"User {{i}}", "email": f"user{{i}}@example.com", "age": random.randint(18, 65)}}
    for i in range(1, {data_count + 1})
]'''
        data_endpoint = '''@app.route('/api/users')
def get_users():
    return jsonify({
        "users": MOCK_USERS,
        "total": len(MOCK_USERS),
        "timestamp": datetime.datetime.now().isoformat()
    })'''
    elif mock_data_type == 'products':
        mock_data = f'''MOCK_PRODUCTS = [
    {{"id": i, "name": f"Product {{i}}", "price": round(random.uniform(10, 1000), 2), "category": random.choice(["Electronics", "Clothing", "Books"])}}
    for i in range(1, {data_count + 1})
]'''
        data_endpoint = '''@app.route('/api/products')
def get_products():
    return jsonify({
        "products": MOCK_PRODUCTS,
        "total": len(MOCK_PRODUCTS),
        "timestamp": datetime.datetime.now().isoformat()
    })'''
    else:  # orders
        mock_data = f'''MOCK_ORDERS = [
    {{"id": i, "user_id": random.randint(1, 50), "product_id": random.randint(1, 100), "amount": round(random.uniform(10, 500), 2), "status": random.choice(["pending", "completed", "cancelled"])}}
    for i in range(1, {data_count + 1})
]'''
        data_endpoint = '''@app.route('/api/orders')
def get_orders():
    return jsonify({
        "orders": MOCK_ORDERS,
        "total": len(MOCK_ORDERS),
        "timestamp": datetime.datetime.now().isoformat()
    })'''
    
    app_content = f'''from flask import Flask, jsonify
import random
import datetime

app = Flask(__name__)

# Mock data
{mock_data}

@app.route('/')
def home():
    return jsonify({{
        "service": "{service_name}",
        "description": "{service_data['description']}",
        "version": "1.0.0",
        "endpoints": {endpoints}
    }})

{data_endpoint}

@app.route('/api/health')
def health():
    return jsonify({{
        "status": "healthy",
        "service": "{service_name}",
        "timestamp": datetime.datetime.now().isoformat()
    }})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port={port}, debug=True)
'''
    
    with open(os.path.join(repo_dir, 'app.py'), 'w', encoding='utf-8') as f:
        f.write(app_content)

def generate_requirements_txt(repo_dir):
    """Generate requirements.txt"""
    requirements = '''Flask==2.3.3
requests==2.31.0
'''
    with open(os.path.join(repo_dir, 'requirements.txt'), 'w') as f:
        f.write(requirements)

def generate_dockerfile(repo_dir, service_data):
    """Generate Dockerfile"""
    port = service_data['port']
    dockerfile_content = f'''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

CMD ["python", "app.py"]
'''
    with open(os.path.join(repo_dir, 'Dockerfile'), 'w') as f:
        f.write(dockerfile_content)

def generate_readme(repo_dir, service_data):
    """Generate README.md"""
    service_name = service_data['service_name']
    description = service_data['description']
    port = service_data['port']
    endpoints = service_data['endpoints']
    
    readme_content = f'''# {service_name}

{description}

## Quick Start

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

The API will be available at `http://localhost:{port}`

### Docker
```bash
# Build image
docker build -t {service_name} .

# Run container
docker run -p {port}:{port} {service_name}
```

## API Endpoints

{chr(10).join([f"- `GET {endpoint}`" for endpoint in endpoints])}
- `GET /api/health` - Health check

## Development

This service was generated using Dev Portal.

## License

MIT
'''
    with open(os.path.join(repo_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme_content)

def generate_github_workflow(repo_dir, service_data):
    """Generate GitHub Actions workflow"""
    service_name = service_data['service_name']
    
    workflow_content = f'''name: CI/CD Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -c "import app; print('App imports successfully')"

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
    - uses: actions/checkout@v4
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{{{ github.actor }}}}
        password: ${{{{ secrets.GHCR_TOKEN }}}}
    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ghcr.io/${{{{ github.repository_owner }}}}/{service_name}:latest
'''
    
    os.makedirs(os.path.join(repo_dir, '.github', 'workflows'), exist_ok=True)
    with open(os.path.join(repo_dir, '.github', 'workflows', 'ci-cd.yml'), 'w') as f:
        f.write(workflow_content)


def update_service_config(service_name: str, config_data: dict, github_token: str):
    """Update service configuration in repository"""
    try:
        # Repository details
        owner, repo = 'ductri09072004', 'demo_fiss1_B'
        service_path = f"services/{service_name}/k8s"
        
        # Prepare remote URL with token
        remote = f"https://{github_token}@github.com/{owner}/{repo}.git"
        
        # Create temp directory
        tmpdir = tempfile.mkdtemp(prefix='update_service_')
        clone_dir = os.path.join(tmpdir, 'repo')
        
        # Clone repository
        clone_proc = subprocess.run(['git', 'clone', remote, clone_dir], capture_output=True, text=True)
        if clone_proc.returncode != 0:
            return {'success': False, 'error': f'Failed to clone repository: {clone_proc.stderr}'}
        
        # Update to latest main
        subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=clone_dir, check=False)
        subprocess.run(['git', 'checkout', '-B', 'main', 'origin/main'], cwd=clone_dir, check=False)
        
        # Update deployment.yaml
        deployment_path = os.path.join(clone_dir, service_path, 'deployment.yaml')
        if os.path.exists(deployment_path):
            with open(deployment_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Update replicas
            content = re.sub(r'replicas:\s*\d+', f'replicas: {config_data["replicas"]}', content)
            
            # Update resources
            resource_pattern = r'resources:\s*\n\s*requests:\s*\n\s*memory:\s*"[^"]*"\s*\n\s*cpu:\s*"[^"]*"\s*\n\s*limits:\s*\n\s*memory:\s*"[^"]*"\s*\n\s*cpu:\s*"[^"]*"'
            new_resources = f'''resources:
            requests:
              memory: "{config_data["memory_request"]}"
              cpu: "{config_data["cpu_request"]}"
            limits:
              memory: "{config_data["memory_limit"]}"
              cpu: "{config_data["cpu_limit"]}"'''
            
            content = re.sub(resource_pattern, new_resources, content, flags=re.MULTILINE | re.DOTALL)
            
            # Update description in metadata
            content = re.sub(r'description:\s*"[^"]*"', f'description: "{config_data["description"]}"', content)
            
            with open(deployment_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        # Update configmap.yaml (port excluded as it cannot be changed)
        configmap_path = os.path.join(clone_dir, service_path, 'configmap.yaml')
        if os.path.exists(configmap_path):
            # Note: PORT is not updated to prevent service connectivity issues
            pass
        
        # Update hpa.yaml
        hpa_path = os.path.join(clone_dir, service_path, 'hpa.yaml')
        if os.path.exists(hpa_path):
            with open(hpa_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Update min/max replicas
            content = re.sub(r'minReplicas:\s*\d+', f'minReplicas: {config_data["min_replicas"]}', content)
            content = re.sub(r'maxReplicas:\s*\d+', f'maxReplicas: {config_data["max_replicas"]}', content)
            
            with open(hpa_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        # Commit and push changes
        subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
        
        # Check if there are changes
        st = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
        if st.stdout.strip():
            subprocess.run(['git', 'commit', '-m', f'Update configuration for {service_name}'], cwd=clone_dir, check=True)
            push_proc = subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir, capture_output=True, text=True)
            if push_proc.returncode != 0:
                return {'success': False, 'error': f'Failed to push changes: {push_proc.stderr}'}
        
        # Clean up
        shutil.rmtree(tmpdir, ignore_errors=True)
        
        return {
            'success': True,
            'details': {
                'service_name': service_name,
                'updated_files': ['deployment.yaml', 'hpa.yaml'],
                'repository': f'https://github.com/{owner}/{repo}',
                'note': 'Port configuration is protected and cannot be changed'
            }
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def generate_repo_b(service_data, repo_a_url: str, repo_b_url: str, repo_b_path: str, namespace: str, image_tag_mode: str, github_token: str = None):
    """Prepare Repo B manifests from template and push to Repo B URL."""
    try:
        service_name = service_data['service_name']
        container_port = service_data.get('port')
        if not container_port:
            return {'success': False, 'error': 'Port is required in service_data'}
        service_port = '80'
        port = container_port  # For template replacement
        health_path = '/api/health'
        domain = 'example.local'
        base_path = '/api'
        replicas = service_data.get('replicas', '3')
        min_replicas = service_data.get('min_replicas', '2')
        max_replicas = service_data.get('max_replicas', '10')
        cpu_request = service_data.get('cpu_request', '100m')
        cpu_limit = service_data.get('cpu_limit', '200m')
        memory_request = service_data.get('memory_request', '128Mi')
        memory_limit = service_data.get('memory_limit', '256Mi')

        # Parse Repo A URL → owner/repo
        parsed = urlparse(repo_a_url)
        path = parsed.path.lstrip('/')
        if path.endswith('.git'):
            path = path[:-4]
        parts = path.split('/')
        if len(parts) < 2:
            return {'success': False, 'error': f'Invalid Repo A URL: {repo_a_url}'}
        gh_owner, repo_a_name = parts[0], parts[1]
        
        # Set repo_url for template replacement
        repo_url = repo_a_url

        image_tag = 'latest' if image_tag_mode == 'latest' else f"{int(time.time())}"
        timestamp = str(int(time.time()))

        # Create temp dir
        tmpdir = tempfile.mkdtemp(prefix='repo_b_')
        clone_dir = os.path.join(tmpdir, 'repo')
        os.makedirs(clone_dir, exist_ok=True)

        # Build remote URL (embed token if available)
        remote = repo_b_url if repo_b_url.endswith('.git') else repo_b_url + '.git'
        # Always use MANIFESTS_REPO_TOKEN for Repo B access
        token_to_use = MANIFESTS_REPO_TOKEN
        if token_to_use and '://' in repo_b_url:
            parsed_b = urlparse(repo_b_url)
            path_git = parsed_b.path if parsed_b.path.endswith('.git') else parsed_b.path + '.git'
            remote = f"{parsed_b.scheme}://{token_to_use}@{parsed_b.netloc}{path_git}"

        # Check if we can use git commands or need to use GitHub API
        if has_git_command() and not is_railway_environment():
            # Use git commands for local development
            clone_proc = subprocess.run(['git', 'clone', remote, clone_dir], capture_output=True, text=True)
            if clone_proc.returncode != 0:
                return {'success': False, 'error': f'Clone Repo B failed: {clone_proc.stderr}'}

            # Ensure we are on latest main
            subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=clone_dir, check=False)
            subprocess.run(['git', 'checkout', '-B', 'main', 'origin/main'], cwd=clone_dir, check=False)
        else:
            # Use GitHub API for Railway deployment
            print("Using GitHub API instead of git commands (Railway environment)")
            # We'll handle the push later using GitHub API

        # Prepare destination path and copy template manifests
        
        # Create services/{SERVICE_NAME}/k8s structure with YAML files
        # Use UI service name for folder structure
        if has_git_command() and not is_railway_environment():
            # Local development - use cloned directory
            service_dir = os.path.join(clone_dir, 'services', service_name)
        else:
            # Railway deployment - create temporary directory
            service_dir = os.path.join(tmpdir, 'services', service_name)
            print(f"DEBUG: Creating service directory: {service_dir}")
        
        k8s_dir = os.path.join(service_dir, 'k8s')
        os.makedirs(k8s_dir, exist_ok=True)
        print(f"DEBUG: Created k8s directory: {k8s_dir}")
        
        # Copy template manifests and replace placeholders
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        k8s_template_dir = os.path.join(template_dir, 'k8s')
        
        # List of YAML files to create
        yaml_files = [
            'deployment.yaml',
            'service.yaml', 
            'configmap.yaml',
            'hpa.yaml',
            'ingress.yaml',
            'ingress-gateway.yaml',
            'namespace.yaml',
            'secret.yaml'
        ]
        
        # Check if we have local templates or need to use inline templates
        use_local_templates = os.path.exists(k8s_template_dir)
        
        for yaml_file in yaml_files:
            dst_file = os.path.join(k8s_dir, yaml_file)
            
            if use_local_templates:
                # Use local template files
                src_file = os.path.join(k8s_template_dir, yaml_file)
                if os.path.exists(src_file):
                    # Read template content
                    with open(src_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                else:
                    continue
            else:
                # Create inline template content for Railway
                content = _create_inline_template(yaml_file, service_name, namespace, port, replicas, min_replicas, max_replicas, cpu_request, cpu_limit, memory_request, memory_limit, gh_owner, repo_a_name, image_tag)
            
            # Replace placeholders (for both local and inline templates)
            content = content.replace('{SERVICE_NAME}', service_name)
            content = content.replace('{NAMESPACE}', namespace)
            content = content.replace('{PORT}', str(port))
            content = content.replace('{REPLICAS}', str(replicas))
            content = content.replace('{MIN_REPLICAS}', str(min_replicas))
            content = content.replace('{MAX_REPLICAS}', str(max_replicas))
            content = content.replace('{CPU_REQUEST}', cpu_request)
            content = content.replace('{CPU_LIMIT}', cpu_limit)
            content = content.replace('{MEMORY_REQUEST}', memory_request)
            content = content.replace('{MEMORY_LIMIT}', memory_limit)
            content = content.replace('{REPO_URL}', repo_url)
            content = content.replace('{IMAGE_TAG}', image_tag)
            
            # Write customized content
            with open(dst_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"DEBUG: Created {yaml_file} at {dst_file}")
            print(f"Created {yaml_file} for {service_name}")
        
        # Auto-configure Prometheus
        try:
            # Use provided port from service_data
            service_port = int(service_data.get('port'))
            if not service_port:
                return {'success': False, 'error': 'Port is required in service_data'}
            
            # Add Prometheus scrape job
            prometheus_config_added = add_prometheus_scrape_job(service_name, service_port)
            
            # Store results for return
            prometheus_result = "Prometheus configured" if prometheus_config_added else "Prometheus config failed"
            
        except Exception as e:
            prometheus_result = f"Prometheus error: {str(e)}"

        # Create ArgoCD Application pointing to services/{SERVICE_NAME}/k8s
        if has_git_command() and not is_railway_environment():
            # Local development - use cloned directory
            apps_dir = os.path.join(clone_dir, 'apps')
            print(f"DEBUG: Creating apps directory: {apps_dir}")
        else:
            # Railway deployment - use temporary directory
            apps_dir = os.path.join(tmpdir, 'apps')
            print(f"DEBUG: Creating apps directory: {apps_dir}")
        
        os.makedirs(apps_dir, exist_ok=True)
        app_file = os.path.join(apps_dir, f'{service_name}-application.yaml')
        
        # Create ArgoCD Application content pointing to YAML files
        app_content = f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {service_name}
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: {repo_b_url.replace('.git', '')}
    targetRevision: HEAD
    path: services/{service_name}/k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: {namespace}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - PrunePropagationPolicy=foreground
    - PruneLast=true
    - RespectIgnoreDifferences=true
    - ServerSideApply=true
    retry:
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
      limit: 5
  revisionHistoryLimit: 3
"""
        
        with open(app_file, 'w', encoding='utf-8') as f:
            f.write(app_content)

        # Commit and push all changes to Repo B
        if has_git_command() and not is_railway_environment():
            # Use git commands for local development
            subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
            subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
            subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
            st = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
            if st.stdout.strip():
                subprocess.run(['git', 'commit', '-m', f'Add service {service_name} with YAML manifests'], cwd=clone_dir, check=True)
            push_proc = subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir, capture_output=True, text=True)
            if push_proc.returncode != 0:
                return {'success': False, 'error': push_proc.stderr}
        else:
            # Use GitHub API for Railway deployment
            print("Pushing files using GitHub API...")
            
            # Collect all files to push
            files_to_push = {}
            
            # Walk through the service directory and collect all files
            service_source_dir = os.path.join(tmpdir, 'services', repo_a_name)
            print(f"DEBUG: Looking for files in {service_source_dir}")
            print(f"DEBUG: Directory exists: {os.path.exists(service_source_dir)}")
            
            if os.path.exists(service_source_dir):
                for root, dirs, files in os.walk(service_source_dir):
                    print(f"DEBUG: Found {len(files)} files in {root}")
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, tmpdir)
                        print(f"DEBUG: Adding file {relative_path}")
                        
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        files_to_push[relative_path] = content
            else:
                print(f"DEBUG: Service directory {service_source_dir} does not exist!")
            
            # DO NOT add ArgoCD application file here - it will be created after CI/CD completes
            # This prevents ArgoCD from syncing before the image is built
            print("⚠️ Skipping ArgoCD application file - will be created after CI/CD completes")
            
            # Push using GitHub API
            # Use token from service data or fallback to config
            token_to_use = service_data.get('manifests_token') or MANIFESTS_REPO_TOKEN
            print(f"Using token for GitHub API: {token_to_use[:10] if token_to_use else 'None'}...")
            if not token_to_use:
                return {'success': False, 'error': 'MANIFESTS_REPO_TOKEN is required for pushing to Repo B'}
            
            push_result = push_files_to_github_api(
                repo_b_url, 
                files_to_push, 
                f'Add service {service_name} with YAML manifests',
                token_to_use
            )
            
            if not push_result['success']:
                return {'success': False, 'error': f'GitHub API push failed: {push_result["error"]}'}
            
            print(f"Successfully pushed files using GitHub API: {push_result.get('commit_sha', 'N/A')}")

        # DO NOT deploy ArgoCD Application here - it will be created after CI/CD completes
        # This prevents ArgoCD from syncing before the image is built
        print("⚠️ ArgoCD Application will be created after CI/CD completes")
        
        print(f"Service '{service_name}' created with YAML manifests in Repo B")
        
        # Schedule deletion of YAML files after ArgoCD sync (in background)
        import threading
        
        def delete_yaml_files_after_sync(service_name, repo_b_url):
            """Delete YAML files after ArgoCD has synced with new changes"""
            try:
                import time
                import tempfile
                import shutil
                import json
                
                # Track sync states to detect actual changes
                last_sync_status = None
                last_health_status = None
                last_revision = None
                sync_changed = False
                
                # Wait for ArgoCD to sync with intelligent checking
                max_wait_time = 300  # 5 minutes maximum
                check_interval = 30  # Check every 30 seconds
                waited_time = 0
                
                while waited_time < max_wait_time:
                    time.sleep(check_interval)
                    waited_time += check_interval
                    
                    try:
                        # Get detailed ArgoCD application status
                        argocd_result = subprocess.run(
                            ['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'json'],
                            capture_output=True, text=True, timeout=10
                        )
                        
                        if argocd_result.returncode == 0:
                            app_data = json.loads(argocd_result.stdout)
                            status = app_data.get('status', {})
                            
                            sync_status = status.get('sync', {}).get('status', 'Unknown')
                            health_status = status.get('health', {}).get('status', 'Unknown')
                            revision = status.get('sync', {}).get('revision', 'Unknown')
                            
                            # Check if sync status or revision has changed (indicating new sync)
                            if (last_sync_status and last_sync_status != sync_status) or \
                               (last_revision and last_revision != revision):
                                sync_changed = True
                                print(f"ArgoCD sync state changed: {last_sync_status} -> {sync_status}, revision: {last_revision} -> {revision}")
                            
                            last_sync_status = sync_status
                            last_health_status = health_status
                            last_revision = revision
                            
                            print(f"ArgoCD status for {service_name} (waited {waited_time}s): sync={sync_status}, health={health_status}, revision={revision}")
                            
                            # Only proceed if we've seen a sync change AND current status is Synced
                            # Allow Progressing health status for ingress loading
                            if sync_changed and sync_status == 'Synced' and health_status in ['Healthy', 'Progressing']:
                                # For Progressing health status (ingress loading), skip pod check and proceed
                                if health_status == 'Progressing':
                                    print(f"ArgoCD synced with new changes (ingress loading), deleting YAML files for {service_name}...")
                                    break
                                else:
                                    # For Healthy status, check if pods are running
                                    if is_railway_environment():
                                        # Skip pod check on Railway
                                        print(f"ArgoCD synced with new changes (Railway), deleting YAML files for {service_name}...")
                                        break
                                    else:
                                        pods_result = subprocess.run(['kubectl', 'get', 'pods', '-l', f'app={service_name}', '-n', service_name, '-o', 'jsonpath={.items[*].status.phase}'], 
                                                                   capture_output=True, text=True)
                                        pods_running = 'Running' in pods_result.stdout if pods_result.returncode == 0 else False
                                        
                                        if pods_running:
                                            print(f"ArgoCD synced with new changes and pods running for {service_name}, deleting YAML files...")
                                            break
                                        else:
                                            print(f"ArgoCD synced but pods not running yet for {service_name}...")
                            else:
                                # If no sync change detected yet, continue waiting
                                if not sync_changed:
                                    print(f"Waiting for ArgoCD to detect changes for {service_name}...")
                                else:
                                    if health_status == 'Progressing':
                                        print(f"ArgoCD sync changed but ingress still loading: sync={sync_status}, health={health_status}")
                                    else:
                                        print(f"ArgoCD sync changed but not ready: sync={sync_status}, health={health_status}")
                        else:
                            print(f"Failed to get ArgoCD application status: {argocd_result.stderr}")
                            
                    except Exception as kubectl_error:
                        print(f"Kubectl check failed: {kubectl_error}")
                
                # Final check after max wait time
                if waited_time >= max_wait_time:
                    print(f"ArgoCD sync timeout for {service_name} after {max_wait_time} seconds, proceeding anyway...")
                
                # Final comprehensive check before proceeding
                if is_railway_environment():
                    # On Railway, check ArgoCD status via API with retry logic
                    print(f"Railway environment: Checking ArgoCD status via API for {service_name}")
                    
                    # Retry logic for ArgoCD health check
                    max_health_retries = 5
                    health_retry_delay = 30  # 30 seconds between retries
                    
                    for health_attempt in range(max_health_retries):
                        argocd_status = _check_argocd_application_status(service_name)
                        if argocd_status:
                            sync_status = argocd_status.get('sync_status', 'Unknown')
                            health_status = argocd_status.get('health_status', 'Unknown')
                            print(f"ArgoCD status (attempt {health_attempt + 1}/{max_health_retries}): sync={sync_status}, health={health_status}")
                            print(f"  - Sync Status: {sync_status} ({'✅' if sync_status == 'Synced' else '❌'})")
                            print(f"  - Health Status: {health_status} ({'✅' if health_status == 'Healthy' else '⏳' if health_status == 'Progressing' else '❌'})")
                            
                            # Only proceed if both sync and health are ready
                            # Progressing means still deploying, not ready yet
                            if sync_status == 'Synced' and health_status == 'Healthy':
                                print(f"✅ ArgoCD application {service_name} is ready (sync={sync_status}, health={health_status})")
                                argocd_final = True
                                pods_final = True
                                break
                            elif sync_status == 'Synced' and health_status == 'Progressing':
                                print(f"⏳ ArgoCD application {service_name} is still deploying (sync={sync_status}, health={health_status})")
                                print(f"⏳ Waiting for deployment to complete...")
                                if health_attempt < max_health_retries - 1:
                                    print(f"⏳ Waiting {health_retry_delay}s before retry...")
                                    time.sleep(health_retry_delay)
                                else:
                                    print(f"⚠️ ArgoCD application {service_name} still deploying after {max_health_retries} attempts")
                                    print(f"⏳ Proceeding anyway to avoid infinite wait...")
                                    argocd_final = True  # Proceed anyway to avoid infinite wait
                                    pods_final = True
                                    break
                            else:
                                # Other statuses (Unknown, Degraded, etc.)
                                if health_attempt < max_health_retries - 1:
                                    print(f"⚠️ ArgoCD application {service_name} not ready yet (sync={sync_status}, health={health_status})")
                                    print(f"⏳ Waiting {health_retry_delay}s before retry...")
                                    time.sleep(health_retry_delay)
                                else:
                                    print(f"⚠️ ArgoCD application {service_name} still not ready after {max_health_retries} attempts")
                                    print(f"⏳ Proceeding anyway to avoid infinite wait...")
                                    argocd_final = True  # Proceed anyway to avoid infinite wait
                                    pods_final = True
                        else:
                            if health_attempt < max_health_retries - 1:
                                print(f"⚠️ Could not get ArgoCD status for {service_name}, retrying...")
                                time.sleep(health_retry_delay)
                            else:
                                print(f"⚠️ Could not get ArgoCD status for {service_name} after {max_health_retries} attempts, proceeding anyway")
                                argocd_final = True  # Proceed anyway on Railway
                                pods_final = True
                else:
                    final_argocd_result = subprocess.run(['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'jsonpath={.status.sync.status}'], 
                                                       capture_output=True, text=True)
                    final_pods_result = subprocess.run(['kubectl', 'get', 'pods', '-l', f'app={service_name}', '-n', service_name, '-o', 'jsonpath={.items[*].status.phase}'], 
                                                     capture_output=True, text=True)
                    
                    argocd_final = final_argocd_result.returncode == 0 and final_argocd_result.stdout.strip() == 'Synced'
                    pods_final = 'Running' in final_pods_result.stdout if final_pods_result.returncode == 0 else False
                
                if argocd_final and pods_final:
                    # ArgoCD has synced, safe to delete YAML files
                    print(f"ArgoCD synced successfully for {service_name}, deleting YAML files...")
                    
                    try:
                        # Delete YAML files from Repo B
                        yaml_files_to_delete = [
                            'deployment.yaml',
                            'service.yaml', 
                            'configmap.yaml',
                            'hpa.yaml',
                            'ingress.yaml',
                            'ingress-gateway.yaml',
                            'namespace.yaml',
                            'secret.yaml',
                            'argocd-application.yaml'
                        ]
                        
                        # Delete YAML files using GitHub API instead of git clone
                        if is_railway_environment():
                            print(f"Using GitHub API to delete YAML files for {service_name}")
                            # Use GitHub API to delete files
                            _delete_yaml_files_via_github_api(service_name, repo_b_url, yaml_files_to_delete)
                            return  # Exit early for Railway environment
                        else:
                            # Use git commands for local development
                            temp_dir = tempfile.gettempdir()
                            clone_dir = os.path.join(temp_dir, f'repo_b_{service_name}_delete_{int(time.time())}')
                        
                        # Remove existing directory if it exists
                        if os.path.exists(clone_dir):
                            shutil.rmtree(clone_dir)
                        
                        print(f"Cloning repository to: {clone_dir}")
                        clone_proc = subprocess.run(['git', 'clone', repo_b_url, clone_dir], 
                                                  capture_output=True, text=True, timeout=60)
                        
                        if clone_proc.returncode != 0:
                            print(f"Failed to clone repository: {clone_proc.stderr}")
                            return
                        
                        # Check if service directory exists
                        service_path = f"services/{repo_a_name}/k8s"
                        full_service_path = os.path.join(clone_dir, service_path)
                        
                        if not os.path.exists(full_service_path):
                            print(f"Service directory not found: {service_path}")
                            return
                        
                        # Delete each YAML file
                        deleted_files = []
                        for yaml_file in yaml_files_to_delete:
                            file_path = os.path.join(full_service_path, yaml_file)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                deleted_files.append(yaml_file)
                                print(f"Deleted {yaml_file}")
                        
                        # Also delete the ArgoCD Application file under apps/
                        apps_file = os.path.join(clone_dir, 'apps', f'{service_name}-application.yaml')
                        if os.path.exists(apps_file):
                            os.remove(apps_file)
                            deleted_files.append(f'apps/{service_name}-application.yaml')
                            print(f"Deleted apps/{service_name}-application.yaml")
                        
                        if not deleted_files:
                            print("No YAML files found to delete")
                            return
                        
                        # Remove empty directories
                        remaining_files = os.listdir(full_service_path)
                        if not remaining_files:
                            os.rmdir(full_service_path)
                            print(f"Deleted empty k8s directory")
                        
                        # Check if services directory is empty
                        service_dir = os.path.join(clone_dir, 'services', repo_a_name)
                        if os.path.exists(service_dir) and not os.listdir(service_dir):
                            os.rmdir(service_dir)
                            print(f"Deleted empty service directory")
                        
                        # Commit and push deletion
                        subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
                        subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
                        subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
                        
                        # Check if there are changes
                        st = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
                        if st.stdout.strip():
                            commit_proc = subprocess.run(['git', 'commit', '-m', f'Clean up YAML files for {service_name} after ArgoCD sync'], 
                                                       cwd=clone_dir, capture_output=True, text=True)
                            
                            if commit_proc.returncode == 0:
                                push_proc = subprocess.run(['git', 'push', 'origin', 'main'], 
                                                        cwd=clone_dir, capture_output=True, text=True)
                                
                                if push_proc.returncode == 0:
                                    print(f"✅ Successfully cleaned up {len(deleted_files)} YAML files for {service_name}")
                                else:
                                    print(f"❌ Failed to push changes: {push_proc.stderr}")
                            else:
                                print(f"❌ Failed to commit changes: {commit_proc.stderr}")
                        else:
                            print("No changes to commit")
                        
                        # Cleanup temp directory
                        shutil.rmtree(clone_dir)
                        print(f"Cleaned up temp directory")
                        
                    except Exception as cleanup_error:
                        print(f"❌ Error during YAML cleanup: {cleanup_error}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"ArgoCD sync not completed for {service_name}, keeping YAML files")
                    
            except Exception as e:
                print(f"Error in delete_yaml_files_after_sync: {e}")
        
        # Start background thread to delete YAML files
        # NOTE: Disabled because ArgoCD Application is now created by CI/CD pipeline
        # The CI/CD pipeline handles the complete flow including ArgoCD sync
        # delete_thread = threading.Thread(target=delete_yaml_files_after_sync, args=(service_name, repo_b_url), daemon=True)
        # delete_thread.start()
        print("ℹ️ Skipping YAML deletion - CI/CD pipeline handles ArgoCD deployment")

        return {
            'success': True,
            'service_name': service_name,
            'monitoring': {
                'prometheus': prometheus_result
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/api/port-forward/start', methods=['POST'])
def start_port_forward_endpoint():
    """Start port-forward manually"""
    try:
        success = start_port_forward()
        if success:
            return jsonify({'message': 'Port-forward started successfully'})
        else:
            return jsonify({'error': 'Failed to start port-forward'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/port-forward/stop', methods=['POST'])
def stop_port_forward_endpoint():
    """Stop port-forward manually"""
    try:
        stop_port_forward()
        return jsonify({'message': 'Port-forward stopped successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/port-forward/status', methods=['GET'])
def port_forward_status():
    """Check port-forward status"""
    try:
        global port_forward_process
        if port_forward_process and port_forward_process.poll() is None:
            return jsonify({'status': 'running', 'message': 'Port-forward is active'})
        else:
            return jsonify({'status': 'stopped', 'message': 'Port-forward is not running'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/service/recreate-yaml/<service_name>', methods=['POST'])
def recreate_yaml_from_mongo(service_name):
    """Recreate YAML files from MongoDB data when Repo A code changes"""
    try:
        # Get service data from MongoDB
        service_data = service_manager.get_service_data(service_name)
        if not service_data:
            return {'success': False, 'error': f'Service {service_name} not found in MongoDB'}
        
        # Extract required data for generate_repo_b
        repo_a_url = service_data.get('repo_url', f'https://github.com/ductri09072004/{service_name}.git')
        repo_b_url = service_data.get('metadata', {}).get('repo_b_url', 'https://github.com/ductri09072004/demo_fiss1_B.git')
        repo_b_path = service_data.get('argocd_application', {}).get('path', f'services/{service_name}/k8s')
        namespace = service_data.get('namespace', service_name)
        
        # Prepare service_data in the format expected by generate_repo_b
        formatted_service_data = {
            'service_name': service_name,
            'port': service_data.get('port', 5001),
            'replicas': service_data.get('replicas', 3),
            'min_replicas': service_data.get('min_replicas', 2),
            'max_replicas': service_data.get('max_replicas', 10),
            'cpu_request': service_data.get('cpu_request', '100m'),
            'cpu_limit': service_data.get('cpu_limit', '200m'),
            'memory_request': service_data.get('memory_request', '128Mi'),
            'memory_limit': service_data.get('memory_limit', '256Mi'),
            'manifests_token': MANIFESTS_REPO_TOKEN  # Add token for GitHub API
        }
        
        # Get actual image tag from service data or generate from timestamp
        image_tag = service_data.get('metadata', {}).get('image_tag')
        if not image_tag:
            # Generate tag from current timestamp if not available
            import time
            image_tag = f"main-{int(time.time())}"
        
        # Use the existing generate_repo_b function
        result = generate_repo_b(
            formatted_service_data, 
            repo_a_url, 
            repo_b_url, 
            repo_b_path, 
            namespace, 
            image_tag  # Use actual image tag
        )
        
        if result['success']:
            # Schedule deletion of YAML files after ArgoCD sync (in background)
            import threading
            
            return {
                'success': True,
                'message': f'YAML files recreated for {service_name} from MongoDB data',
                'service_name': service_name,
                'details': {
                    'repo_a_url': repo_a_url,
                    'repo_b_url': repo_b_url,
                    'namespace': namespace,
                    'note': 'ArgoCD will automatically sync the new YAML files and they will be deleted after sync'
                }
            }
        else:
            return {'success': False, 'error': result.get('error', 'Failed to recreate YAML files')}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/api/service/update-from-repo-a/<service_name>', methods=['POST'])
def update_service_from_repo_a(service_name):
    """Update service when Repo A code changes - triggers YAML recreation"""
    try:
        # First recreate YAML files from MongoDB
        recreate_response = recreate_yaml_from_mongo(service_name)
        
        # Handle the response properly
        if hasattr(recreate_response, 'get_json'):
            recreate_data = recreate_response.get_json()
            success = recreate_data.get('success', False)
        else:
            recreate_data = {'error': 'Invalid response format'}
            success = False
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Service {service_name} updated from Repo A changes',
                'service_name': service_name,
                'yaml_recreation': recreate_data,
                'next_steps': [
                    'YAML files have been recreated in Repo B',
                    'ArgoCD will automatically detect changes',
                    'New image will be deployed to Kubernetes',
                    'YAML files will be cleaned up after deployment'
                ]
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to update service {service_name}',
                'service_name': service_name,
                'error': recreate_data.get('error', 'Unknown error')
            }), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/service/update-image-tag/<service_name>', methods=['POST'])
def update_service_image_tag(service_name):
    """Update service image tag from CI/CD pipeline"""
    try:
        data = request.get_json()
        image_tag = data.get('image_tag') or data.get('tag')
        
        if not image_tag:
            return jsonify({'error': 'image_tag is required'}), 400
        
        # Update MongoDB with new image tag
        service_manager.mongo_ops.db.services.update_one(
            {'name': service_name},
            {'$set': {'metadata.image_tag': image_tag, 'updated_at': datetime.utcnow().isoformat()}}
        )
        
        # Log the update
        service_manager.mongo_ops.db.service_events.insert_one({
            'service_name': service_name,
            'event_type': 'image_tag_updated',
            'event_data': {'image_tag': image_tag},
            'timestamp': datetime.utcnow().isoformat()
        })
        
        return jsonify({
            'success': True,
            'message': f'Image tag updated for {service_name}',
            'service_name': service_name,
            'image_tag': image_tag
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/service/get-image-tag/<service_name>', methods=['GET'])
def get_service_image_tag(service_name):
    """Get current image tag for service"""
    try:
        service_data = service_manager.get_service_data(service_name)
        if not service_data:
            return jsonify({'error': f'Service {service_name} not found'}), 404
        
        image_tag = service_data.get('metadata', {}).get('image_tag', 'latest')
        
        return jsonify({
            'service_name': service_name,
            'image_tag': image_tag,
            'image_url': f"ghcr.io/ductri09072004/{service_name}:{image_tag}"
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-simple', methods=['POST'])
def test_simple():
    """Simple test endpoint without MongoDB"""
    try:
        print("Simple test called")
        
        payload = request.get_json()
        print(f"Payload received: {payload}")
        
        return jsonify({
            'success': True,
            'message': 'Simple test successful',
            'received_data': payload
        })
        
    except Exception as e:
        print(f"Simple test error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug-headers', methods=['GET', 'POST'])
def debug_headers():
    """Debug endpoint to check request headers and content type"""
    try:
        debug_info = {
            'method': request.method,
            'content_type': request.content_type,
            'headers': dict(request.headers),
            'is_json': request.is_json,
            'content_length': request.content_length,
            'raw_data': request.get_data(as_text=True)[:500] if request.get_data() else None
        }
        
        if request.is_json:
            debug_info['json_data'] = request.get_json()
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/service/deploy-existing', methods=['POST'])
def deploy_from_existing_repository():
    """Deploy service from existing GitHub repository"""
    try:
        data = request.get_json()
        
        # Required fields
        repo_url = data.get('repo_url', '').strip()
        service_name = data.get('service_name', '').strip()
        github_token = data.get('github_token', '').strip()
        
        if not repo_url:
            return jsonify({'error': 'Repository URL is required'}), 400
        if not service_name:
            return jsonify({'error': 'Service name is required'}), 400
        if not github_token:
            return jsonify({'error': 'GitHub token is required'}), 400
        
        # Optional fields with defaults
        port = data.get('port', '8000')
        replicas = data.get('replicas', '3')
        min_replicas = data.get('min_replicas', '2')
        max_replicas = data.get('max_replicas', '10')
        cpu_request = data.get('cpu_request', '100m')
        cpu_limit = data.get('cpu_limit', '200m')
        memory_request = data.get('memory_request', '128Mi')
        memory_limit = data.get('memory_limit', '256Mi')
        repo_b_url = data.get('repo_b_url', DEFAULT_REPO_B_URL)
        namespace = data.get('namespace', service_name)
        
        # Extract repo name from repo_url for consistency
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(repo_url)
            repo_path = parsed_url.path.strip('/')
            if repo_path.endswith('.git'):
                repo_path = repo_path[:-4]
            repo_name = repo_path.split('/')[-1] if '/' in repo_path else repo_path
        except:
            repo_name = service_name  # Fallback to service_name
        
        print(f"🔧 Using repo_name: {repo_name} (extracted from GitHub URL)")
        
        # Validate GitHub token
        try:
            headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github+json'}
            test_response = requests.get('https://api.github.com/user', headers=headers)
            if test_response.status_code != 200:
                return jsonify({'error': 'Invalid GitHub token. Please check your token and try again.'}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to validate GitHub token: {str(e)}'}), 400
        
        # Analyze repository to detect technology stack
        print(f"🔍 Analyzing repository: {repo_url}")
        repo_analysis = analyze_repository_structure(repo_url, github_token)
        
        if not repo_analysis['success']:
            return jsonify({'error': f"Failed to analyze repository: {repo_analysis['error']}"}), 400
        
        print(f"✅ Detected: {repo_analysis['language']} {repo_analysis['framework']} application")
        print(f"✅ Port: {repo_analysis['port']}")
        print(f"✅ Dependencies: {repo_analysis['dependencies']}")
        
        # Create webhook for the repository
        webhook_result = create_github_webhook(repo_url, github_token, WEBHOOK_URL)
        webhook_created = webhook_result.get('success', False)
        
        # Generate Dockerfile based on detected technology
        dockerfile_content = generate_dockerfile_from_analysis(repo_analysis)
        
        # Generate CI/CD pipeline
        cicd_content = generate_cicd_pipeline(repo_analysis, service_name)
        
        # Generate K8s manifests
        k8s_manifests = generate_k8s_manifests(service_name, namespace, port, replicas, min_replicas, max_replicas, cpu_request, cpu_limit, memory_request, memory_limit)
        
        # Create service data for database
        service_data = {
            'service_name': service_name,
            'description': f"Deployed from existing repository: {repo_url}",
            'port': port,
            'replicas': replicas,
            'min_replicas': min_replicas,
            'max_replicas': max_replicas,
            'cpu_request': cpu_request,
            'cpu_limit': cpu_limit,
            'memory_request': memory_request,
            'memory_limit': memory_limit,
            'created_at': datetime.now().isoformat()
        }
        
        # Add files to repository (Dockerfile + single CI/CD workflow)
        print(f"📝 Adding files to repository: {repo_url}")
        files_to_add = {
            'Dockerfile': dockerfile_content,
            '.github/workflows/ci-cd.yml': cicd_content
        }
        
        add_files_result = add_files_to_repository(repo_url, github_token, files_to_add)
        if not add_files_result['success']:
            print(f"❌ Failed to add files to repository: {add_files_result['error']}")
            return jsonify({
                'success': False,
                'error': f"Failed to add files to repository: {add_files_result['error']}"
            }), 500
        
        print(f"✅ Successfully added files: {add_files_result.get('added_files', [])}")
        
        # Generate Kubernetes manifests in Repo B
        # Use UI service name for folder structure
        repo_b_path = f"services/{service_name}/k8s"
        repo_b_res = generate_repo_b(service_data, repo_url, repo_b_url, repo_b_path, namespace, 'latest', github_token)
        
        if not repo_b_res['success']:
            return jsonify({
                'success': False,
                'error': f"Failed to generate Kubernetes manifests: {repo_b_res['error']}"
            }), 500
        
        # Save to database
        db_service_data = {
            'name': service_name,
            'namespace': namespace,
            'port': int(port),
            'description': service_data['description'],
            'repo_url': repo_url,
            'replicas': int(replicas),
            'min_replicas': int(min_replicas),
            'max_replicas': int(max_replicas),
            'cpu_request': cpu_request,
            'cpu_limit': cpu_limit,
            'memory_request': memory_request,
            'memory_limit': memory_limit,
            'metadata': {
                'created_by': 'portal',
                'deployment_mode': 'existing-repo',
                'repo_b_url': repo_b_url,
                'repo_b_path': repo_b_path,
                'technology_stack': repo_analysis
            }
        }
        
        db_result = service_manager.add_service_complete(db_service_data)
        
        # Generate YAML templates in MongoDB
        yaml_generation_success = service_manager.generate_yaml_from_mongo(service_name)
        
        response_data = {
            'success': True,
            'message': f'Service "{service_name}" deployed from existing repository!',
            'service_name': service_name,
            'repo_url': repo_url,
            'repo_b_url': repo_b_url,
            'repo_b_path': repo_b_path,
            'namespace': namespace,
            'yaml_generation_success': yaml_generation_success,
            'technology_stack': repo_analysis,
            'files_added': add_files_result.get('added_files', []),
            'files_added_count': len(add_files_result.get('added_files', []))
        }
        
        # Add webhook information to response
        if webhook_created:
            response_data['webhook'] = {
                'created': True,
                'webhook_id': webhook_result.get('webhook_id'),
                'webhook_url': webhook_result.get('webhook_url')
            }
        else:
            response_data['webhook'] = {
                'created': False,
                'error': webhook_result.get('error')
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

@app.route('/api/webhook/check/<path:repo_url>', methods=['GET'])
def check_webhook(repo_url):
    """Check existing webhooks for a repository"""
    try:
        github_token = request.headers.get('Authorization', '').replace('token ', '')
        if not github_token:
            return jsonify({'error': 'GitHub token required in Authorization header'}), 400
        
        # Extract owner and repo name from URL
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        import re
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return jsonify({'error': 'Invalid GitHub repository URL'}), 400
        
        owner = match.group(1)
        repo_name = match.group(2)
        
        # GitHub API endpoint for listing webhooks
        api_url = f'https://api.github.com/repos/{owner}/{repo_name}/hooks'
        
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(api_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            webhooks = response.json()
            return jsonify({
                'success': True,
                'repository': f'{owner}/{repo_name}',
                'webhook_count': len(webhooks),
                'webhooks': webhooks
            })
        else:
            error_msg = f"Failed to fetch webhooks: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail.get('message', 'Unknown error')}"
            except:
                error_msg += f" - {response.text}"
            
            return jsonify({'success': False, 'error': error_msg}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/github/webhook-debug', methods=['POST'])
def github_webhook_debug():
    """Debug version of GitHub webhook - simplified"""
    try:
        print("Debug webhook called")
        
        # Parse webhook payload
        payload = request.get_json()
        print(f"Payload: {payload}")
        
        if not payload:
            return jsonify({'error': 'No payload received'}), 400
        
        # Extract repository information
        repo_name = payload.get('repository', {}).get('name')
        if not repo_name:
            return jsonify({'error': 'Repository name not found'}), 400
        
        print(f"Processing webhook for repo: {repo_name}")
        
        # Test MongoDB connection first
        try:
            service_data = service_manager.get_service_data(repo_name)
            if not service_data:
                print(f"Service {repo_name} not found in MongoDB")
                return jsonify({
                    'success': False,
                    'message': f'Service {repo_name} not found in database',
                    'service_name': repo_name
                }), 404
            
            print(f"Service {repo_name} found in MongoDB")
            
            # Simple success response
            return jsonify({
                'success': True,
                'message': f'Debug webhook processed for {repo_name}',
                'service_name': repo_name,
                'service_found': True
            })
            
        except Exception as mongo_error:
            print(f"MongoDB error: {mongo_error}")
            return jsonify({
                'success': False,
                'message': f'MongoDB error: {str(mongo_error)}',
                'service_name': repo_name
            }), 500
        
    except Exception as e:
        print(f"Debug webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Global lock để tránh conflict khi nhiều service cùng tạo
import threading
webhook_lock = threading.Lock()

@app.route('/api/github/webhook', methods=['POST'])
def github_webhook():
    """Handle GitHub webhook for Repo A changes - Simplified version"""
    try:
        print("GitHub webhook called")
        print(f"Content-Type: {request.content_type}")
        print(f"Headers: {dict(request.headers)}")
        
        # Parse webhook payload - handle different content types
        payload = None
        if request.is_json:
            payload = request.get_json()
        elif request.content_type == 'application/x-www-form-urlencoded':
            # GitHub sends webhook as form data with 'payload' field
            form_data = request.form
            if 'payload' in form_data:
                try:
                    import json
                    payload = json.loads(form_data['payload'])
                    print(f"Parsed payload from form data")
                except Exception as e:
                    print(f"Failed to parse form payload: {e}")
                    return jsonify({'error': 'Invalid form payload'}), 400
            else:
                print("No 'payload' field in form data")
                return jsonify({'error': 'No payload field in form data'}), 400
        else:
            # Try to parse as JSON from raw data
            try:
                import json
                payload = json.loads(request.get_data(as_text=True))
            except Exception as e:
                print(f"Failed to parse JSON: {e}")
                return jsonify({'error': 'Invalid JSON payload'}), 400
        
        print(f"Payload: {payload}")
        
        if not payload:
            return jsonify({'error': 'No payload received'}), 400
        
        event_type = request.headers.get('X-GitHub-Event')
        print(f"Event type: {event_type}")
        
        if event_type == 'push':
            # Extract repository information
            repo_name = payload.get('repository', {}).get('name')
            if not repo_name:
                return jsonify({'error': 'Repository name not found'}), 400
                
            branch = payload.get('ref', '').split('/')[-1]  # Extract branch from refs/heads/main
            print(f"Processing push to {repo_name} on branch {branch}")
            
            # Only process main/master branch pushes
            if branch in ['main', 'master']:
                # Extract commit info
                commit_sha = payload.get('head_commit', {}).get('id')
                if not commit_sha:
                    return jsonify({'error': 'Commit SHA not found'}), 400
                    
                commit_short = commit_sha[:7]
                image_tag = f"main-{commit_short}"
                
                print(f"Processing webhook: {repo_name} pushed to {branch} (commit: {commit_short})")
                
                # Check if service exists in MongoDB by repo_name
                try:
                    # First try to find by repo_name (for webhook mapping)
                    service_data = service_manager.mongo_ops.db.services.find_one({'repo_name': repo_name})
                    if not service_data:
                        # Fallback: try to find by name (for backward compatibility)
                        service_data = service_manager.get_service_data(repo_name)
                        if not service_data:
                            print(f"Service with repo_name {repo_name} not found in MongoDB")
                            return jsonify({
                                'success': False,
                                'message': f'Service with repo_name {repo_name} not found in database',
                                'repo_name': repo_name
                            }), 404
                    
                    # Get the actual service_name from the found service
                    actual_service_name = service_data.get('name', repo_name)
                    print(f"Found service: {actual_service_name} (repo_name: {repo_name})")
                    
                    print(f"Service {repo_name} found in MongoDB")
                    
                    # Update image tag in MongoDB
                    service_manager.mongo_ops.db.services.update_one(
                        {'name': actual_service_name},  # Use actual service name
                        {'$set': {
                            'metadata.image_tag': image_tag,
                            'metadata.last_commit': commit_sha,
                            'updated_at': datetime.utcnow().isoformat()
                        }}
                    )
                    print(f"Updated image tag to {image_tag} for {actual_service_name}")
                    
                    # Log the event
                    service_manager.mongo_ops.db.service_events.insert_one({
                        'service_name': actual_service_name,  # Use actual service name
                        'event_type': 'github_push',
                        'event_data': {
                            'repo_name': repo_name,
                            'commit_sha': commit_sha,
                            'image_tag': image_tag,
                            'branch': branch,
                            'repository': payload.get('repository', {}).get('full_name', '')
                        },
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    print(f"Logged event for {actual_service_name} (repo: {repo_name})")
                    
                    # Generate YAML templates from MongoDB data
                    try:
                        print(f"Generating YAML templates from MongoDB for {actual_service_name}...")
                        yaml_generation_success = service_manager.generate_yaml_from_mongo(actual_service_name)
                        print(f"YAML generation result: {yaml_generation_success}")
                        
                        if yaml_generation_success:
                            print(f"YAML templates generated successfully for {repo_name}")
                            # Materialize YAML files into Repo B so ArgoCD can sync
                            try:
                                print(f"Materializing YAML files to Repo B for {repo_name}...")
                                materialize_response = recreate_yaml_from_mongo(repo_name)
                                if isinstance(materialize_response, dict):
                                    print(f"Materialize result: success={materialize_response.get('success')} error={materialize_response.get('error')}")
                                else:
                                    print("Materialize response not dictionary format")
                            except Exception as mat_err:
                                print(f"Materialize YAML failed for {repo_name}: {mat_err}")
                        else:
                            print(f"Failed to generate YAML templates for {repo_name}")
                            
                    except Exception as e:
                        print(f"YAML generation failed for {repo_name}: {e}")
                        import traceback
                        traceback.print_exc()
                        yaml_generation_success = False
                    
                    print(f"Webhook processing completed for {repo_name}")
                    
                    return jsonify({
                        'success': True,
                        'message': f'Webhook processed for {repo_name}',
                        'service_name': repo_name,
                        'image_tag': image_tag,
                        'yaml_generation_success': yaml_generation_success
                    })
                    
                except Exception as mongo_error:
                    print(f"MongoDB error: {mongo_error}")
                    return jsonify({
                        'success': False,
                        'message': f'MongoDB error: {str(mongo_error)}',
                        'service_name': repo_name
                    }), 500
            else:
                return jsonify({'message': f'Branch {branch} not processed (only main/master)'}), 200
        else:
            return jsonify({'message': f'Event type {event_type} not processed'}), 200
        
    except Exception as e:
        print(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def verify_github_signature(payload, signature):
    """Verify GitHub webhook signature"""
    try:
        import hmac
        import hashlib
        
        webhook_secret = os.getenv('GITHUB_WEBHOOK_SECRET', 'your-secret-here')
        
        if not webhook_secret or webhook_secret == 'your-secret-here':
            print("⚠️ GitHub webhook secret not configured, skipping verification")
            return True  # Skip verification in development
        
        expected_signature = 'sha256=' + hmac.new(
            webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        print(f"❌ Signature verification error: {e}")
        return False

@app.route('/api/services/webhook-ready', methods=['GET'])
def get_webhook_ready_services():
    """Get list of services that can receive webhooks"""
    try:
        services = service_manager.mongo_ops.db.services.find({}, {
            'name': 1,
            'repo_url': 1,
            'metadata.image_tag': 1,
            'metadata.last_commit': 1,
            'updated_at': 1
        })
        
        webhook_services = []
        for service in services:
            webhook_services.append({
                'name': service['name'],
                'repo_url': service.get('repo_url'),
                'current_image_tag': service.get('metadata', {}).get('image_tag', 'latest'),
                'last_commit': service.get('metadata', {}).get('last_commit'),
                'updated_at': service.get('updated_at'),
                'webhook_url': f"https://auto-tool.up.railway.app/api/github/webhook"
            })
        
        return jsonify({
            'success': True,
            'total_services': len(webhook_services),
            'services': webhook_services
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/yaml-templates', methods=['GET'])
def get_service_yaml_templates(service_name):
    """Get YAML templates for a service"""
    try:
        templates = service_manager.get_yaml_templates_for_service(service_name)
        return jsonify({
            'success': True,
            'service_name': service_name,
            'templates': templates
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/generate-yaml', methods=['POST'])
def generate_service_yaml(service_name):
    """Generate YAML templates from MongoDB data for a service"""
    try:
        result = service_manager.generate_yaml_from_mongo(service_name)
        if result:
            return jsonify({
                'success': True,
                'message': f'YAML templates generated for {service_name}',
                'service_name': service_name
            })
        else:
            return jsonify({'error': f'Failed to generate YAML templates for {service_name}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services/<service_name>/delete-yaml-templates', methods=['DELETE'])
def delete_service_yaml_templates(service_name):
    """Delete YAML templates for a service"""
    try:
        deleted_count = service_manager.delete_yaml_templates_for_service(service_name)
        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} YAML templates for {service_name}',
            'service_name': service_name,
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
