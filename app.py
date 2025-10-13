from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import subprocess
import json
import requests
import shutil
from urllib.parse import urlparse
from datetime import datetime
import tempfile
import time

app = Flask(__name__)

# GitHub configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', 'your_github_token_here')

# Monitoring configuration
PROMETHEUS_URL = "http://localhost:9090"
GRAFANA_URL = "http://localhost:3000"
GRAFANA_USER = "admin"
GRAFANA_PASS = "admin123"
GITHUB_ORG = os.getenv('GITHUB_ORG', 'your_organization')
DEFAULT_REPO_B_URL = os.getenv('DEFAULT_REPO_B_URL', 'https://github.com/ductri09072004/demo_fiss1_B')

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

def import_grafana_dashboard(service_name, grafana_dir):
    """Import Grafana dashboard for new service"""
    try:
        # Read dashboard JSON
        dashboard_file = os.path.join(grafana_dir, 'dashboard.json')
        if not os.path.exists(dashboard_file):
            print(f"Dashboard file not found: {dashboard_file}")
            return False
            
        with open(dashboard_file, 'r', encoding='utf-8') as f:
            dashboard_data = json.load(f)
        
        # Delete existing dashboard if exists
        headers = {
            'Authorization': f'Basic {requests.auth._basic_auth_str(GRAFANA_USER, GRAFANA_PASS)}',
            'Content-Type': 'application/json'
        }
        
        delete_url = f"{GRAFANA_URL}/api/dashboards/uid/{service_name}"
        requests.delete(delete_url, headers=headers)
        
        # Import dashboard
        import_url = f"{GRAFANA_URL}/api/dashboards/db"
        import_response = requests.post(import_url, headers=headers, json=dashboard_data)
        
        return import_response.status_code in [200, 201]
        
    except Exception as e:
        print(f"Error importing Grafana dashboard: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_service', methods=['POST'])
def create_service():
    try:
        # Get form data
        service_name = request.form.get('service_name')
        description = request.form.get('description')
        port = request.form.get('port', '5000')
        mock_data_type = request.form.get('mock_data_type', 'users')
        data_count = request.form.get('data_count', '100')
        endpoints = request.form.getlist('endpoints')
        repo_url = request.form.get('repo_url', '').strip()
        repo_b_url = request.form.get('repo_b_url', '').strip()
        namespace = request.form.get('namespace', '').strip()
        repo_b_path = request.form.get('repo_b_path', '').strip()
        image_tag_mode = request.form.get('image_tag_mode', 'latest').strip()
        
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
            'mock_data_type': mock_data_type,
            'data_count': int(data_count),
            'endpoints': endpoints,
            'created_at': datetime.now().isoformat()
        }
        
        # Generate repository from existing template and push to provided repo URL (Repo A)
        result = generate_repository(service_data, repo_url)
        
        if result['success']:
            # After Repo A ok → update Repo B manifests
            repo_b_res = generate_repo_b(service_data, repo_url, repo_b_url, repo_b_path, namespace, image_tag_mode)
            if not repo_b_res['success']:
                return jsonify({'success': False, 'error': f"Repo B update failed: {repo_b_res['error']}"}), 500
            return jsonify({
                'success': True,
                'message': f'Service "{service_name}" created successfully!',
                'repo_url': result['repo_url'],
                'clone_url': result['clone_url'],
                'repo_b_url': repo_b_url,
                'repo_b_path': repo_b_path
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

def generate_repository(service_data, repo_url):
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
        repl = {
            '{SERVICE_NAME}': service_name,
            '{NAMESPACE}': namespace,
        }
        
        for root, _, files in os.walk(repo_dir):
            for file in files:
                if not file.endswith(('.py', '.md', '.yml', '.yaml', '.txt')):
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
        if GITHUB_TOKEN and '://' in repo_url:
            parsed = urlparse(repo_url)
            # Insert token as basic auth in URL: https://TOKEN@github.com/owner/repo.git
            remote = f"{parsed.scheme}://{GITHUB_TOKEN}@{parsed.netloc}{parsed.path}"

        # Set remote and push
        subprocess.run(['git', 'remote', 'remove', 'origin'], cwd=repo_dir, check=False)
        subprocess.run(['git', 'remote', 'add', 'origin', remote], cwd=repo_dir, check=True)
        # align local main with remote/main to avoid non-fast-forward
        subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=repo_dir, check=False)
        subprocess.run(['git', 'checkout', '-B', 'main', 'origin/main'], cwd=repo_dir, check=False)
        push_proc = subprocess.run(['git', 'push', '-u', 'origin', 'main'], cwd=repo_dir, capture_output=True, text=True)
        if push_proc.returncode != 0:
            return {
                'success': False,
                'error': f"Failed to push to remote: {push_proc.stderr}",
                'repo_url': repo_url,
                'clone_url': repo_url
            }

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
        
        # Write to repo
        with open(os.path.join(repo_dir, 'app.py'), 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        # Fallback to old method if template not found
        mock_data_type = service_data['mock_data_type']
        data_count = service_data['data_count']
        endpoints = service_data['endpoints']
    
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
        password: ${{{{ secrets.GITHUB_TOKEN }}}}
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


def generate_repo_b(service_data, repo_a_url: str, repo_b_url: str, repo_b_path: str, namespace: str, image_tag_mode: str):
    """Prepare Repo B manifests from template and push to Repo B URL."""
    try:
        service_name = service_data['service_name']
        container_port = service_data.get('port', '5000')
        service_port = '80'
        health_path = '/api/health'
        domain = 'example.local'
        base_path = '/api'
        min_replicas = '1'
        max_replicas = '3'

        # Parse Repo A URL → owner/repo
        parsed = urlparse(repo_a_url)
        path = parsed.path.lstrip('/')
        if path.endswith('.git'):
            path = path[:-4]
        parts = path.split('/')
        if len(parts) < 2:
            return {'success': False, 'error': f'Invalid Repo A URL: {repo_a_url}'}
        gh_owner, repo_a_name = parts[0], parts[1]

        image_tag = 'latest' if image_tag_mode == 'latest' else f"{int(time.time())}"
        timestamp = str(int(time.time()))

        # Create temp dir
        tmpdir = tempfile.mkdtemp(prefix='repo_b_')
        clone_dir = os.path.join(tmpdir, 'repo')
        os.makedirs(clone_dir, exist_ok=True)

        # Build remote URL (embed token if available)
        remote = repo_b_url if repo_b_url.endswith('.git') else repo_b_url + '.git'
        if GITHUB_TOKEN and '://' in repo_b_url:
            parsed_b = urlparse(repo_b_url)
            path_git = parsed_b.path if parsed_b.path.endswith('.git') else parsed_b.path + '.git'
            remote = f"{parsed_b.scheme}://{GITHUB_TOKEN}@{parsed_b.netloc}{path_git}"

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
            fallback = r"E:\\Study\\PJ_demo_fiss1_B\k8s"
            if os.path.isdir(fallback):
                template_b = fallback
            else:
                return {'success': False, 'error': f'Template B not found: {template_b}'}
        # Create services/{SERVICE_NAME}/k8s structure
        services_dir = os.path.join(clone_dir, 'services')
        service_dir = os.path.join(services_dir, service_name)
        target_path = os.path.join(service_dir, 'k8s')
        os.makedirs(target_path, exist_ok=True)
        shutil.copytree(template_b, target_path, dirs_exist_ok=True)

        # Replace placeholders in all files under target_path
        repl = {
            '{SERVICE_NAME}': service_name,
            '{NAMESPACE}': namespace,
            '{GH_OWNER}': gh_owner,
            '{REPO_A}': repo_a_name,
            '{IMAGE_TAG}': image_tag,
            '{CONTAINER_PORT}': str(container_port),
            '{SERVICE_PORT}': str(service_port),
            '{HEALTH_PATH}': health_path,
            '{DOMAIN}': domain,
            '{BASE_PATH}': base_path,
            '{MIN_REPLICAS}': str(min_replicas),
            '{MAX_REPLICAS}': str(max_replicas),
            '{TIMESTAMP}': timestamp,
        }

        for root, _, files in os.walk(target_path):
            for file in files:
                if not file.endswith(('.yaml', '.yml', '.py')):
                    continue
                p = os.path.join(root, file)
                with open(p, 'r', encoding='utf-8') as rf:
                    content = rf.read()
                for k, v in repl.items():
                    content = content.replace(k, v)
                with open(p, 'w', encoding='utf-8') as wf:
                    wf.write(content)

        # Create Grafana dashboard folder and files
        grafana_dir = os.path.join(service_dir, 'grafana')
        os.makedirs(grafana_dir, exist_ok=True)
        
        # Determine service port: prefer provided port, fallback to version-based rule
        try:
            provided_port = int(service_data.get('port')) if service_data.get('port') else None
        except Exception:
            provided_port = None
        if provided_port:
            service_port = provided_port
        else:
            if '-v' in service_name:
                try:
                    version_num = int(service_name.split('-v')[-1])
                    service_port = 5000 + version_num
                except:
                    service_port = 5001
            else:
                service_port = 5001
        
        # Create dashboard.json
        dashboard_content = f"""{{
  "dashboard": {{
    "id": null,
    "uid": "{service_name}",
    "title": "{service_name} API Dashboard",
    "tags": [
      "{service_name}",
      "flask",
      "api",
      "microservice"
    ],
    "style": "dark",
    "timezone": "browser",
    "panels": [
      {{
        "id": 1,
        "title": "API Requests & Memory",
        "type": "barchart",
        "targets": [
          {{
            "expr": "demo_fiss_memory_usage_bytes{{instance=\\"host.docker.internal:{service_port}\\"}} / 1024 / 1024",
            "legendFormat": "Memory Usage (MB)",
            "refId": "A"
          }},
          {{
            "expr": "demo_fiss_active_connections{{instance=\\"host.docker.internal:{service_port}\\"}}",
            "legendFormat": "Active Connections",
            "refId": "B"
          }}
        ],
        "gridPos": {{
          "h": 8,
          "w": 12,
          "x": 0,
          "y": 0
        }}
      }},
      {{
        "id": 2,
        "title": "Response Time & Performance",
        "type": "graph",
        "targets": [
          {{
            "expr": "demo_fiss_response_time_seconds{{instance=\\"host.docker.internal:{service_port}\\"}}",
            "legendFormat": "Response Time (s)",
            "refId": "A"
          }}
        ],
        "gridPos": {{
          "h": 8,
          "w": 12,
          "x": 12,
          "y": 0
        }}
      }},
      {{
        "id": 3,
        "title": "Service Status & Requests",
        "type": "barchart",
        "targets": [
          {{
            "expr": "up{{instance=\\"host.docker.internal:{service_port}\\"}}",
            "legendFormat": "{service_name} Status",
            "refId": "A"
          }},
          {{
            "expr": "demo_fiss_requests_total{{instance=\\"host.docker.internal:{service_port}\\"}}",
            "legendFormat": "Total Requests",
            "refId": "B"
          }}
        ],
        "gridPos": {{
          "h": 8,
          "w": 24,
          "x": 0,
          "y": 8
        }}
      }}
    ],
    "time": {{
      "from": "now-1h",
      "to": "now"
    }},
    "refresh": "5s",
    "schemaVersion": 27,
    "version": 0
  }}
}}"""
        
        dashboard_file = os.path.join(grafana_dir, 'dashboard.json')
        with open(dashboard_file, 'w', encoding='utf-8') as f:
            f.write(dashboard_content)
        
        # Create import_dashboard.ps1
        import_script_content = f'''# Script import dashboard cho {service_name}
param(
    [string]$GrafanaUrl = "http://localhost:3000",
    [string]$Username = "admin",
    [string]$Password = "{GRAFANA_PASS}"
)

Write-Host "=== Import Dashboard for {service_name} ===" -ForegroundColor Cyan

# Function để gọi Grafana API
function Invoke-GrafanaAPI {{
    param(
        [string]$Method,
        [string]$Endpoint,
        [string]$Body = $null
    )
    
    $base64Auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${{Username}}:${{Password}}"))
    $headers = @{{
        "Content-Type" = "application/json"
        "Authorization" = "Basic $base64Auth"
    }}
    
    $uri = "${{GrafanaUrl}}/api${{Endpoint}}"
    
    try {{
        if ($Body) {{
            $response = Invoke-RestMethod -Uri $uri -Method $Method -Headers $headers -Body $Body
        }} else {{
            $response = Invoke-RestMethod -Uri $uri -Method $Method -Headers $headers
        }}
        return $response
    }}
    catch {{
        Write-Host "API Error: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }}
}}

# Kiểm tra kết nối Grafana
Write-Host "Checking Grafana connection..." -ForegroundColor Yellow
$health = Invoke-GrafanaAPI -Method "GET" -Endpoint "/health"
if ($health) {{
    Write-Host "Grafana is running" -ForegroundColor Green
}} else {{
    Write-Host "Cannot connect to Grafana at $GrafanaUrl" -ForegroundColor Red
    exit 1
}}

# Đọc dashboard JSON
$dashboardFile = "dashboard.json"
Write-Host "Reading dashboard file: $dashboardFile" -ForegroundColor Yellow
if (-not (Test-Path $dashboardFile)) {{
    Write-Host "Dashboard file not found: $dashboardFile" -ForegroundColor Red
    exit 1
}}

$dashboardJson = Get-Content $dashboardFile -Raw
$dashboard = $dashboardJson | ConvertFrom-Json
$dashboardTitle = $dashboard.dashboard.title

# Import dashboard
Write-Host "Importing dashboard..." -ForegroundColor Yellow
$importBody = $dashboard | ConvertTo-Json -Depth 10
$result = Invoke-GrafanaAPI -Method "POST" -Endpoint "/dashboards/db" -Body $importBody

if ($result) {{
    Write-Host "Dashboard imported successfully!" -ForegroundColor Green
    Write-Host "Dashboard URL: ${{GrafanaUrl}}/d/$($result.uid)" -ForegroundColor Cyan
}} else {{
    Write-Host "Failed to import dashboard" -ForegroundColor Red
    exit 1
}}

Write-Host "Dashboard import completed for {service_name}!" -ForegroundColor Green'''
        
        import_script_file = os.path.join(grafana_dir, 'import_dashboard.ps1')
        with open(import_script_file, 'w', encoding='utf-8') as f:
            f.write(import_script_content)
        
        # Auto-configure Prometheus and import Grafana dashboard
        try:
            # Calculate port for service: prefer provided port, else 5000 + version
            try:
                provided_port = int(service_data.get('port')) if service_data.get('port') else None
            except Exception:
                provided_port = None
            if provided_port:
                service_port = provided_port
            else:
                if '-v' in service_name:
                    try:
                        version_num = int(service_name.split('-v')[-1])
                        service_port = 5000 + version_num
                    except:
                        service_port = 5001
                else:
                    service_port = 5001
            
            # Add Prometheus scrape job
            prometheus_config_added = add_prometheus_scrape_job(service_name, service_port)
            
            # Import Grafana dashboard
            grafana_dashboard_imported = import_grafana_dashboard(service_name, grafana_dir)
            
            # Store results for return
            prometheus_result = "✅ Prometheus configured" if prometheus_config_added else "❌ Prometheus config failed"
            grafana_result = "✅ Grafana dashboard imported" if grafana_dashboard_imported else "❌ Grafana import failed"
            
        except Exception as e:
            prometheus_result = f"❌ Prometheus error: {str(e)}"
            grafana_result = f"❌ Grafana error: {str(e)}"

        # Create ArgoCD Application
        apps_dir = os.path.join(clone_dir, 'apps')
        os.makedirs(apps_dir, exist_ok=True)
        app_file = os.path.join(apps_dir, f'{service_name}-application.yaml')
        
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

        # Commit and push manifests to Repo B first
        subprocess.run(['git', 'add', '--all'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.email', 'dev-portal@local'], cwd=clone_dir, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Dev Portal'], cwd=clone_dir, check=True)
        st = subprocess.run(['git', 'status', '--porcelain'], cwd=clone_dir, capture_output=True, text=True, check=True)
        if st.stdout.strip():
            subprocess.run(['git', 'commit', '-m', f'Add/Update manifests for {service_name}'], cwd=clone_dir, check=True)
        push_proc = subprocess.run(['git', 'push', 'origin', 'main'], cwd=clone_dir, capture_output=True, text=True)
        if push_proc.returncode != 0:
            return {'success': False, 'error': push_proc.stderr}

        # Auto-deploy ArgoCD Application after successful push
        try:
            subprocess.run(['kubectl', 'apply', '-f', app_file], check=True, capture_output=True)
            print(f"✅ ArgoCD Application '{service_name}' deployed successfully")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  ArgoCD Application deploy failed: {e.stderr.decode()}")
            # Continue anyway - user can apply manually

        return {
            'success': True,
            'service_name': service_name,
            'monitoring': {
                'prometheus': prometheus_result,
                'grafana': grafana_result,
                'dashboard_url': f"{GRAFANA_URL}/d/{service_name}"
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=3050)
