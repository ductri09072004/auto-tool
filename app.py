from flask import Flask, render_template, request, jsonify, redirect, url_for
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
from config import GITHUB_TOKEN, GHCR_TOKEN, MANIFESTS_REPO_TOKEN, DASHBOARD_TOKEN

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
    if public is None:
        raise RuntimeError("PyNaCl is required to encrypt GitHub secrets. Please install pynacl.")
    pk = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder().encode(encrypted).decode("utf-8")

def ensure_repo_secrets(repo_url: str, github_token: str = None) -> bool:
    """Ensure GHCR_TOKEN and MANIFESTS_REPO_TOKEN exist in repo secrets."""
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
        headers = {
            'Authorization': f'token {token_to_use}',
            'Accept': 'application/vnd.github+json'
        }

        # Fetch public key
        pk_resp = requests.get(f"{base}/public-key", headers=headers)
        if pk_resp.status_code != 200:
            print(f"Failed to get public key: {pk_resp.status_code} {pk_resp.text}")
            return False
        pk_json = pk_resp.json()
        repo_public_key = pk_json.get('key')
        key_id = pk_json.get('key_id')
        if not repo_public_key or not key_id:
            return False

        # Encrypt and upsert secrets
        token_to_use_for_secrets = github_token or GHCR_TOKEN
        updates = {
            'GHCR_TOKEN': token_to_use_for_secrets,
            'MANIFESTS_REPO_TOKEN': token_to_use_for_secrets
        }
        for name, value in updates.items():
            if not value:
                continue
            encrypted_value = _encrypt_secret(repo_public_key, value)
            put_resp = requests.put(
                f"{base}/{name}",
                headers={**headers, 'Content-Type': 'application/json'},
                json={'encrypted_value': encrypted_value, 'key_id': key_id}
            )
            if put_resp.status_code not in [201, 204]:
                print(f"Failed to set secret {name}: {put_resp.status_code} {put_resp.text}")
                return False
        return True
    except Exception as e:
        print(f"ensure_repo_secrets error: {e}")
        return False

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

@app.route('/dashboard')
def dashboard():
    return render_template('service_dashboard.html')

# Service Management API Endpoints
@app.route('/api/services', methods=['GET'])
def get_services():
    """Get list of services from MongoDB, enrich with K8s + health metrics."""
    try:
        services = []

        db_services = service_manager.get_services() or []
        default_repo_url = DEFAULT_REPO_B_URL

        for svc in db_services:
            service_name = svc.get('name') or svc.get('service_name')
            if not service_name:
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
                subprocess.run(['kubectl', 'get', 'namespace', service_name], capture_output=True, text=True, check=True)
                deploy_result = subprocess.run(['kubectl', 'get', 'deployment', service_name, '-n', service_name, '-o', 'json'], capture_output=True, text=True, check=True)
                deployment = json.loads(deploy_result.stdout)

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
                except Exception as e:
                    print(f"Warning: Could not get health metrics for {service_name}: {e}")

                try:
                    argocd_result = subprocess.run(['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'json'], capture_output=True, text=True, check=True)
                    argocd_app = json.loads(argocd_result.stdout)
                    health_status = argocd_app['status'].get('health', {}).get('status', 'Unknown')
                    sync_status = argocd_app['status'].get('sync', {}).get('status', 'Unknown')
                except subprocess.CalledProcessError:
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

        services.sort(key=lambda x: x['name'])
        return jsonify({'services': services})

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
        repo_b_path = f"E:\\Study\\demo_fiss1_B\\services\\{service_name}"
        if os.path.exists(repo_b_path):
            shutil.rmtree(repo_b_path)
            # If local Repo B is a git repo, commit and push
            try:
                repo_b_root = "E:\\Study\\demo_fiss1_B"
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
        repo_b_path = "E:\\Study\\demo_fiss1_B\\services"
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
        service_name = request.form.get('service_name')
        description = request.form.get('description')
        port = request.form.get('port', '')
        if not port:
            return jsonify({'error': 'Port is required'}), 400
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
        
        # Create service data
        service_data = {
            'service_name': service_name,
            'description': description,
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
        
        # Generate repository from existing template and push to provided repo URL (Repo A)
        result = generate_repository(service_data, repo_url, github_token)
        
        if result['success']:
            # After Repo A ok → update Repo B manifests
            repo_b_res = generate_repo_b(service_data, repo_url, repo_b_url, repo_b_path, namespace, image_tag_mode, github_token)
            if not repo_b_res['success']:
                return jsonify({'success': False, 'error': f"Repo B update failed: {repo_b_res['error']}"}), 500
            
            # Save to database - use form data to populate all collections
            # ArgoCD plugin will later read from MongoDB and create YAML files
            print(f"DEBUG: Creating service {service_name} with form data")
            
            db_service_data = {
                'name': service_name,
                'namespace': namespace,
                'port': int(port),
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
            
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" created successfully!',
                'repo_url': repo_url,
                'clone_url': repo_url,
                'repo_b_url': repo_b_url,
                'repo_b_path': repo_b_path
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create service'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

def generate_repository(service_data, repo_url, github_token=None):
    """Generate repository from E:\\Study\\demo_fiss1 template and push to provided GitHub repo URL"""
    try:
        service_name = service_data['service_name']
        
        # Create temporary directory for repository
        import tempfile
        repo_dir = tempfile.mkdtemp(prefix=f'{service_name}_')
        
        # Copy template from local templates_src (cloned once for speed)
        template_src = r"E:\\Study\\Auto_project_tool\\templates_src\\repo_a_template"
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
            ensure_repo_secrets(repo_url, github_token)
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
        token_to_use = github_token or MANIFESTS_REPO_TOKEN
        if token_to_use and '://' in repo_b_url:
            parsed_b = urlparse(repo_b_url)
            path_git = parsed_b.path if parsed_b.path.endswith('.git') else parsed_b.path + '.git'
            remote = f"{parsed_b.scheme}://{token_to_use}@{parsed_b.netloc}{path_git}"

        # Clone Repo B to get current history
        clone_proc = subprocess.run(['git', 'clone', remote, clone_dir], capture_output=True, text=True)
        if clone_proc.returncode != 0:
            return {'success': False, 'error': f'Clone Repo B failed: {clone_proc.stderr}'}

        # Ensure we are on latest main
        subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=clone_dir, check=False)
        subprocess.run(['git', 'checkout', '-B', 'main', 'origin/main'], cwd=clone_dir, check=False)

        # Prepare destination path and copy template manifests
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_b = os.path.join(base_dir, 'templates_src', 'repo_b_template', 'k8s')
        if not os.path.isdir(template_b):
            fallback = r"E:\\Study\\demo_fiss1_B\k8s"
            if os.path.isdir(fallback):
                template_b = fallback
            else:
                return {'success': False, 'error': f'Template B not found: {template_b}'}
        # Create services/{SERVICE_NAME}/k8s structure with YAML files
        service_dir = os.path.join(clone_dir, 'services', service_name)
        k8s_dir = os.path.join(service_dir, 'k8s')
        os.makedirs(k8s_dir, exist_ok=True)
        
        # Copy template manifests and replace placeholders
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        k8s_template_dir = os.path.join(template_dir, 'k8s')
        
        if os.path.exists(k8s_template_dir):
            # List of YAML files to copy and customize
            yaml_files = [
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
            
            for yaml_file in yaml_files:
                src_file = os.path.join(k8s_template_dir, yaml_file)
                if os.path.exists(src_file):
                    dst_file = os.path.join(k8s_dir, yaml_file)
                    
                    # Read template content
                    with open(src_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Replace placeholders
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
        apps_dir = os.path.join(clone_dir, 'apps')
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
        subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
        st = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
        if st.stdout.strip():
            subprocess.run(['git', 'commit', '-m', f'Add service {service_name} with YAML manifests'], cwd=clone_dir, check=True)
        push_proc = subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir, capture_output=True, text=True)
        if push_proc.returncode != 0:
            return {'success': False, 'error': push_proc.stderr}

        # Auto-deploy ArgoCD Application after successful push
        try:
            subprocess.run(['kubectl', 'apply', '-f', app_file], check=True, capture_output=True)
            print(f"ArgoCD Application '{service_name}' deployed successfully")
        except subprocess.CalledProcessError as e:
            print(f"ArgoCD Application deploy failed: {e.stderr.decode()}")
            # Continue anyway - user can apply manually
        
        print(f"Service '{service_name}' created with YAML manifests in Repo B")
        
        # Schedule deletion of YAML files after ArgoCD sync (in background)
        import threading
        
        def delete_yaml_files_after_sync(service_name, repo_b_url):
            """Delete YAML files after ArgoCD has synced"""
            try:
                import time
                import tempfile
                import shutil
                
                # Wait for ArgoCD to sync with intelligent checking
                max_wait_time = 300  # 5 minutes maximum
                check_interval = 30  # Check every 30 seconds
                waited_time = 0
                
                while waited_time < max_wait_time:
                    time.sleep(check_interval)
                    waited_time += check_interval
                    
                    # Check multiple status indicators
                    all_good = True
                    
                    # 1. Check ArgoCD sync status
                    argocd_result = subprocess.run(['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'jsonpath={.status.sync.status}'], 
                                                 capture_output=True, text=True)
                    argocd_synced = argocd_result.returncode == 0 and argocd_result.stdout.strip() == 'Synced'
                    
                    # 2. Check if pods are running
                    pods_result = subprocess.run(['kubectl', 'get', 'pods', '-l', f'app={service_name}', '-n', service_name, '-o', 'jsonpath={.items[*].status.phase}'], 
                                               capture_output=True, text=True)
                    pods_running = 'Running' in pods_result.stdout if pods_result.returncode == 0 else False
                    
                    # 3. Check if deployment is ready
                    deployment_result = subprocess.run(['kubectl', 'get', 'deployment', service_name, '-n', service_name, '-o', 'jsonpath={.status.readyReplicas}'], 
                                                     capture_output=True, text=True)
                    deployment_ready = deployment_result.returncode == 0 and deployment_result.stdout.strip().isdigit() and int(deployment_result.stdout.strip()) > 0
                    
                    print(f"Status check for {service_name} (waited {waited_time}s):")
                    print(f"   - ArgoCD Synced: {'YES' if argocd_synced else 'NO'}")
                    print(f"   - Pods Running: {'YES' if pods_running else 'NO'}")
                    print(f"   - Deployment Ready: {'YES' if deployment_ready else 'NO'}")
                    
                    # All checks must pass
                    if argocd_synced and pods_running and deployment_ready:
                        print(f"All checks passed for {service_name} after {waited_time} seconds")
                        break
                    else:
                        print(f"Still waiting for {service_name} to be fully ready...")
                
                # Final check after max wait time
                if waited_time >= max_wait_time:
                    print(f"ArgoCD sync timeout for {service_name} after {max_wait_time} seconds, proceeding anyway...")
                
                # Final comprehensive check before proceeding
                final_argocd_result = subprocess.run(['kubectl', 'get', 'application', service_name, '-n', 'argocd', '-o', 'jsonpath={.status.sync.status}'], 
                                                   capture_output=True, text=True)
                final_pods_result = subprocess.run(['kubectl', 'get', 'pods', '-l', f'app={service_name}', '-n', service_name, '-o', 'jsonpath={.items[*].status.phase}'], 
                                                 capture_output=True, text=True)
                
                argocd_final = final_argocd_result.returncode == 0 and final_argocd_result.stdout.strip() == 'Synced'
                pods_final = 'Running' in final_pods_result.stdout if final_pods_result.returncode == 0 else False
                
                if argocd_final and pods_final:
                    # ArgoCD has synced, safe to delete YAML files
                    print(f"ArgoCD synced successfully for {service_name}, deleting YAML files...")
                    
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
                    
                    # Clone repo again for deletion
                    temp_dir = tempfile.gettempdir()
                    clone_dir = os.path.join(temp_dir, f'repo_b_{service_name}_delete')
                    subprocess.run(['git', 'clone', repo_b_url, clone_dir], check=True)
                    
                    # Delete each YAML file
                    for yaml_file in yaml_files_to_delete:
                        file_path = os.path.join(clone_dir, 'services', service_name, 'k8s', yaml_file)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            print(f"Deleted {yaml_file}")
                    
                    # Remove the entire k8s directory if empty
                    k8s_dir = os.path.join(clone_dir, 'services', service_name, 'k8s')
                    if os.path.exists(k8s_dir) and not os.listdir(k8s_dir):
                        os.rmdir(k8s_dir)
                        print(f"Deleted empty k8s directory")
                    
                    # Remove services directory if empty
                    service_dir = os.path.join(clone_dir, 'services', service_name)
                    if os.path.exists(service_dir) and not os.listdir(service_dir):
                        os.rmdir(service_dir)
                        print(f"Deleted empty service directory")
                    
                    # Commit and push deletion
                    subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
                    subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
                    subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
                    
                    st = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
                    if st.stdout.strip():
                        subprocess.run(['git', 'commit', '-m', f'Clean up YAML files for {service_name} after ArgoCD sync'], cwd=clone_dir, check=True)
                        subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir, check=True)
                        print(f"Cleaned up YAML files for {service_name}")
                    
                    # Cleanup temp directory
                    shutil.rmtree(clone_dir)
                else:
                    print(f"ArgoCD sync not completed for {service_name}, keeping YAML files")
                    
            except Exception as e:
                print(f"Error in delete_yaml_files_after_sync: {e}")
        
        # Start background thread to delete YAML files
        delete_thread = threading.Thread(target=delete_yaml_files_after_sync, args=(service_name, repo_b_url), daemon=True)
        delete_thread.start()

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
            return jsonify({'error': f'Service {service_name} not found in MongoDB'}), 404
        
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
            'memory_limit': service_data.get('memory_limit', '256Mi')
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
            
            def delete_yaml_files_after_sync(service_name, repo_b_url):
                """Delete YAML files after ArgoCD has synced"""
                try:
                    import time
                    start_time = time.time()
                    print(f"Starting background thread to monitor ArgoCD sync for {service_name}")
                    
                    while time.time() - start_time < 300:  # Wait up to 5 minutes
                        try:
                            # Check ArgoCD sync status
                            import requests
                            argocd_response = requests.get(
                                f"https://argocd-server/api/v1/applications/{service_name}",
                                timeout=10
                            )
                            
                            if argocd_response.status_code == 200:
                                argocd_data = argocd_response.json()
                                sync_status = argocd_data.get('status', {}).get('sync', {}).get('status')
                                
                                if sync_status == 'Synced':
                                    # Check if pods are running
                                    import subprocess
                                    kubectl_cmd = ['kubectl', 'get', 'pods', '-n', service_name, '-o', 'json']
                                    kubectl_result = subprocess.run(kubectl_cmd, capture_output=True, text=True)
                                    
                                    if kubectl_result.returncode == 0:
                                        import json
                                        pods_data = json.loads(kubectl_result.stdout)
                                        pods = pods_data.get('items', [])
                                        
                                        if pods:
                                            running_pods = [pod for pod in pods if pod.get('status', {}).get('phase') == 'Running']
                                            if len(running_pods) >= 1:  # At least 1 pod running
                                                print(f"ArgoCD synced and pods running for {service_name}, deleting YAML files...")
                                                
                                                # Delete YAML files from Repo B
                                                yaml_files_to_delete = [
                                                    'deployment.yaml',
                                                    'service.yaml', 
                                                    'configmap.yaml',
                                                    'hpa.yaml',
                                                    'ingress.yaml',
                                                    'ingress-gateway.yaml',
                                                    'secret.yaml',
                                                    'namespace.yaml',
                                                    'argocd-application.yaml'
                                                ]
                                                
                                                # Clone repo and delete files
                                                import tempfile
                                                import shutil
                                                tmpdir = tempfile.mkdtemp(prefix='delete_yaml_')
                                                clone_dir = os.path.join(tmpdir, 'repo')
                                                
                                                clone_proc = subprocess.run(['git', 'clone', repo_b_url, clone_dir], 
                                                                          capture_output=True, text=True)
                                                if clone_proc.returncode == 0:
                                                    service_path = f"services/{service_name}/k8s"
                                                    for yaml_file in yaml_files_to_delete:
                                                        file_path = os.path.join(clone_dir, service_path, yaml_file)
                                                        if os.path.exists(file_path):
                                                            os.remove(file_path)
                                                            print(f"Deleted {yaml_file}")
                                                    
                                                    # Commit and push changes
                                                    subprocess.run(['git', 'add', '.'], cwd=clone_dir)
                                                    subprocess.run(['git', 'commit', '-m', f'Delete YAML files after ArgoCD sync for {service_name}'], 
                                                                 cwd=clone_dir)
                                                    subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir)
                                                    
                                                    print(f"YAML files deleted successfully for {service_name}")
                                                
                                                # Cleanup
                                                shutil.rmtree(tmpdir)
                                                return
                            
                        except Exception as check_error:
                            print(f"Error checking ArgoCD status: {check_error}")
                        
                        time.sleep(30)  # Wait 30 seconds before next check
                    
                    print(f"ArgoCD sync timeout for {service_name}, keeping YAML files")
                    
                except Exception as e:
                    print(f"Error in delete_yaml_files_after_sync: {e}")
            
            # Start background thread to delete YAML files
            delete_thread = threading.Thread(target=delete_yaml_files_after_sync, args=(service_name, repo_b_url), daemon=True)
            delete_thread.start()
            
            return jsonify({
                'success': True,
                'message': f'YAML files recreated for {service_name} from MongoDB data',
                'service_name': service_name,
                'details': {
                    'repo_a_url': repo_a_url,
                    'repo_b_url': repo_b_url,
                    'namespace': namespace,
                    'note': 'ArgoCD will automatically sync the new YAML files and they will be deleted after sync'
                }
            })
        else:
            return jsonify({'error': result.get('error', 'Failed to recreate YAML files')}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/github/webhook', methods=['POST'])
def github_webhook():
    """Handle GitHub webhook for Repo A changes - Simplified version"""
    try:
        print("GitHub webhook called")
        
        # Parse webhook payload
        payload = request.get_json()
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
                
                # Check if service exists in MongoDB
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
                    
                    # Update image tag in MongoDB
                    service_manager.mongo_ops.db.services.update_one(
                        {'name': repo_name},
                        {'$set': {
                            'metadata.image_tag': image_tag,
                            'metadata.last_commit': commit_sha,
                            'updated_at': datetime.utcnow().isoformat()
                        }}
                    )
                    print(f"Updated image tag to {image_tag} for {repo_name}")
                    
                    # Log the event
                    service_manager.mongo_ops.db.service_events.insert_one({
                        'service_name': repo_name,
                        'event_type': 'github_push',
                        'event_data': {
                            'commit_sha': commit_sha,
                            'image_tag': image_tag,
                            'branch': branch,
                            'repository': payload.get('repository', {}).get('full_name', '')
                        },
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    print(f"Logged event for {repo_name}")
                    
                    # Trigger YAML recreation
                    try:
                        print(f"Starting YAML recreation for {repo_name}...")
                        recreate_response = recreate_yaml_from_mongo(repo_name)
                        
                        # Check if it's a successful response
                        if hasattr(recreate_response, 'get_json'):
                            response_data = recreate_response.get_json()
                            yaml_recreation_success = response_data.get('success', False)
                            print(f"YAML recreation result: {yaml_recreation_success}")
                        else:
                            yaml_recreation_success = False
                            print("YAML recreation returned invalid response format")
                            
                    except Exception as e:
                        print(f"YAML recreation failed for {repo_name}: {e}")
                        import traceback
                        traceback.print_exc()
                        yaml_recreation_success = False
                    
                    print(f"Webhook processing completed for {repo_name}")
                    
                    return jsonify({
                        'success': True,
                        'message': f'Webhook processed for {repo_name}',
                        'service_name': repo_name,
                        'image_tag': image_tag,
                        'yaml_recreation_success': yaml_recreation_success
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
                'webhook_url': f"http://localhost:3050/api/github/webhook"
            })
        
        return jsonify({
            'success': True,
            'total_services': len(webhook_services),
            'services': webhook_services
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 3050))
    app.run(debug=False, host='0.0.0.0', port=port)
