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
ARGOCD_WEBHOOK_URL = os.getenv('ARGOCD_WEBHOOK_URL', 'https://auto-tool.up.railway.app/api/webhook')

# ArgoCD API Configuration
# Note: Use https:// for ngrok URLs, ArgoCD automatically redirects HTTP to HTTPS
ARGOCD_SERVER_URL = os.getenv('ARGOCD_SERVER_URL', 'https://d2ecc2dba7cc.ngrok-free.app')
ARGOCD_TOKEN = os.getenv('ARGOCD_TOKEN', '')
ARGOCD_ADMIN_PASSWORD = os.getenv('ARGOCD_ADMIN_PASSWORD', 'IG42zHWiFya1XbaR')

# Debug logging for tokens
print(f"MANIFESTS_REPO_TOKEN: {'SET' if MANIFESTS_REPO_TOKEN else 'NOT SET'}")
print(f"GITHUB_TOKEN: {'SET' if GITHUB_TOKEN else 'NOT SET'}")
print(f"GHCR_TOKEN: {'SET' if GHCR_TOKEN else 'NOT SET'}")

# Dashboard token - can be set for read-only operations
DASHBOARD_TOKEN = os.getenv('DASHBOARD_TOKEN', '')

# Token Usage:
# - GITHUB_TOKEN: For general GitHub API operations (create repos, push code)
# - GHCR_TOKEN: For GitHub Container Registry (push Docker images)
# - MANIFESTS_REPO_TOKEN: For Repository B operations (push K8s manifests)
# - ARGOCD_WEBHOOK_URL: For ArgoCD webhook trigger (immediate sync)
# - DASHBOARD_TOKEN: For dashboard read-only operations (view services list)

# Monitoring Configuration
PROMETHEUS_URL = "http://localhost:9090"
GRAFANA_URL = "http://localhost:3000"
GRAFANA_USER = "admin"
GRAFANA_PASS = "admin123"

# Default Repository Configuration
GITHUB_ORG = os.getenv('GITHUB_ORG', 'your_organization')
DEFAULT_REPO_B_URL = os.getenv('DEFAULT_REPO_B_URL', 'https://github.com/ductri09072004/demo_fiss1_B')

# Webhook Configuration
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://auto-tool.up.railway.app/api/github/webhook')

# Template Paths - Use relative paths for cross-platform compatibility
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# For Railway deployment, use environment variables or fallback to local paths
TEMPLATE_A_PATH = os.getenv('TEMPLATE_A_PATH', os.path.join(BASE_DIR, "templates_src", "repo_a_template"))
TEMPLATE_B_PATH = os.getenv('TEMPLATE_B_PATH', os.path.join(BASE_DIR, "templates_src", "repo_b_template", "k8s"))
FALLBACK_TEMPLATE_B = os.getenv('FALLBACK_TEMPLATE_B', os.path.join(BASE_DIR, "..", "demo_fiss1_B", "k8s"))

# Repository B Paths
REPO_B_SERVICES_PATH = os.getenv('REPO_B_SERVICES_PATH', os.path.join(BASE_DIR, "..", "demo_fiss1_B", "services"))

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
    },
    'ARGOCD_WEBHOOK_URL': {
        'description': 'ArgoCD webhook URL for immediate sync',
        'usage': ['Trigger immediate ArgoCD sync', 'Bypass auto-sync delay', 'Force deployment update']
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
