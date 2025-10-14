"""
Configuration file for Auto Project Tool
Contains GitHub tokens and other settings
"""

import os

# GitHub Tokens Configuration
# All tokens use the same value as requested
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GHCR_TOKEN = os.getenv('GHCR_TOKEN', '')
MANIFESTS_REPO_TOKEN = os.getenv('MANIFESTS_REPO_TOKEN', '')

# Dashboard token - can be set for read-only operations
DASHBOARD_TOKEN = os.getenv('DASHBOARD_TOKEN', '')

# Token Usage:
# - GITHUB_TOKEN: For general GitHub API operations (create repos, push code)
# - GHCR_TOKEN: For GitHub Container Registry (push Docker images)
# - MANIFESTS_REPO_TOKEN: For Repository B operations (push K8s manifests)
# - DASHBOARD_TOKEN: For dashboard read-only operations (view services list)

# Monitoring Configuration
PROMETHEUS_URL = "http://localhost:9090"
GRAFANA_URL = "http://localhost:3000"
GRAFANA_USER = "admin"
GRAFANA_PASS = "admin123"

# Default Repository Configuration
GITHUB_ORG = os.getenv('GITHUB_ORG', 'your_organization')
DEFAULT_REPO_B_URL = os.getenv('DEFAULT_REPO_B_URL', 'https://github.com/ductri09072004/demo_fiss1_B')

# Template Paths
TEMPLATE_A_PATH = r"E:\Study\Auto_project_tool\templates_src\repo_a_template"
TEMPLATE_B_PATH = r"E:\Study\Auto_project_tool\templates_src\repo_b_template\k8s"
FALLBACK_TEMPLATE_B = r"E:\Study\demo_fiss1_B\k8s"

# Repository B Paths
REPO_B_SERVICES_PATH = "E:\\Study\\demo_fiss1_B\\services"

# Token Validation
def validate_tokens():
    """Validate that all required tokens are configured"""
    tokens = {
        'GITHUB_TOKEN': GITHUB_TOKEN,
        'GHCR_TOKEN': GHCR_TOKEN,
        'MANIFESTS_REPO_TOKEN': MANIFESTS_REPO_TOKEN
    }
    
    missing_tokens = []
    for name, token in tokens.items():
        if not token:
            missing_tokens.append(name)
    
    if missing_tokens:
        print(f"⚠️ Warning: No default tokens configured: {', '.join(missing_tokens)}")
        print("💡 Tokens must be provided through the web interface form.")
        return False
    
    print("✅ All GitHub tokens configured")
    return True

# Token Information
TOKEN_INFO = {
    'GITHUB_TOKEN': {
        'description': 'General GitHub API operations',
        'usage': ['Create repositories', 'Push code', 'Manage repository settings']
    },
    'GHCR_TOKEN': {
        'description': 'GitHub Container Registry access',
        'usage': ['Push Docker images', 'Pull images', 'Manage packages']
    },
    'MANIFESTS_REPO_TOKEN': {
        'description': 'Repository B (Manifests) access',
        'usage': ['Push K8s manifests', 'Update deployment files', 'Manage ArgoCD applications']
    }
}

if __name__ == "__main__":
    print("🔧 Auto Project Tool Configuration")
    print("=" * 50)
    
    # Validate tokens
    validate_tokens()
    
    print("\n📋 Token Usage:")
    for token_name, info in TOKEN_INFO.items():
        print(f"\n🔑 {token_name}:")
        print(f"   Description: {info['description']}")
        print(f"   Usage: {', '.join(info['usage'])}")
    
    print(f"\n📁 Template Paths:")
    print(f"   Template A: {TEMPLATE_A_PATH}")
    print(f"   Template B: {TEMPLATE_B_PATH}")
    print(f"   Fallback B: {FALLBACK_TEMPLATE_B}")
    
    print(f"\n🌐 Monitoring:")
    print(f"   Prometheus: {PROMETHEUS_URL}")
    print(f"   Grafana: {GRAFANA_URL}")
