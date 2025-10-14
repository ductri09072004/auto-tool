# 🔑 GitHub Tokens Configuration

Auto Project Tool sử dụng 3 loại GitHub token khác nhau để thực hiện các tác vụ khác nhau:

## 📋 Token Types

### 1. **GITHUB_TOKEN** 
- **Mục đích**: Các thao tác GitHub API chung
- **Sử dụng**: 
  - Tạo repositories
  - Push code lên GitHub
  - Quản lý repository settings
  - Thêm GitHub secrets

### 2. **GHCR_TOKEN**
- **Mục đích**: GitHub Container Registry (GHCR)
- **Sử dụng**:
  - Push Docker images lên GHCR
  - Pull images từ GHCR
  - Quản lý packages

### 3. **MANIFESTS_REPO_TOKEN**
- **Mục đích**: Repository B (K8s Manifests)
- **Sử dụng**:
  - Push K8s manifests
  - Cập nhật deployment files
  - Quản lý ArgoCD applications

## ⚙️ Configuration

### Current Token (All 3 tokens use the same value):
```
GITHUB_TOKEN = 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
GHCR_TOKEN = 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
MANIFESTS_REPO_TOKEN = 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
```

### Environment Variables (Optional):
```bash
export GITHUB_TOKEN="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"
export GHCR_TOKEN="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"
export MANIFESTS_REPO_TOKEN="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"
```

## 🧪 Testing Tokens

### Run Token Test:
```bash
python test_tokens.py
```

### Manual Testing:
```python
from config import GITHUB_TOKEN, GHCR_TOKEN, MANIFESTS_REPO_TOKEN
import requests

# Test GITHUB_TOKEN
headers = {'Authorization': f'token {GITHUB_TOKEN}'}
response = requests.get('https://api.github.com/user', headers=headers)
print(f"GitHub API: {response.status_code}")

# Test GHCR_TOKEN
response = requests.get('https://api.github.com/user/packages', headers=headers)
print(f"GHCR API: {response.status_code}")

# Test MANIFESTS_REPO_TOKEN
response = requests.get('https://api.github.com/user/repos', headers=headers)
print(f"Repos API: {response.status_code}")
```

## 🔄 Token Flow in Auto Project Tool

### 1. **Service Creation Flow:**
```
User Input → GITHUB_TOKEN → Create Repo A → Push Code
                ↓
            GHCR_TOKEN → Add to GitHub Secrets
                ↓
            MANIFESTS_REPO_TOKEN → Push to Repo B
```

### 2. **CI/CD Pipeline:**
```
GitHub Actions → GHCR_TOKEN → Build & Push Docker Image
                    ↓
                MANIFESTS_REPO_TOKEN → Update K8s Manifests
```

### 3. **Repository Operations:**
```
GITHUB_TOKEN: Repository A (Django App)
MANIFESTS_REPO_TOKEN: Repository B (K8s Manifests)
GHCR_TOKEN: Docker Registry (Container Images)
```

## 🛠️ Token Permissions Required

### GITHUB_TOKEN Permissions:
- ✅ `repo` (Full control of private repositories)
- ✅ `write:packages` (Upload packages to GitHub Package Registry)
- ✅ `read:packages` (Download packages from GitHub Package Registry)
- ✅ `admin:org` (Full control of orgs and teams)

### GHCR_TOKEN Permissions:
- ✅ `write:packages` (Upload packages)
- ✅ `read:packages` (Download packages)
- ✅ `delete:packages` (Delete packages)

### MANIFESTS_REPO_TOKEN Permissions:
- ✅ `repo` (Full control of repositories)
- ✅ `workflow` (Update GitHub Action workflows)

## 🔧 Configuration Files

### `config.py`:
```python
# Token configuration
GITHUB_TOKEN = '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'
GHCR_TOKEN = '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'
MANIFESTS_REPO_TOKEN = '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'
```

### `app.py`:
```python
from config import GITHUB_TOKEN, GHCR_TOKEN, MANIFESTS_REPO_TOKEN

# Usage in functions
def generate_repository():
    # Uses GITHUB_TOKEN for repo operations
    pass

def generate_repo_b():
    # Uses MANIFESTS_REPO_TOKEN for manifests
    pass

def add_github_secrets():
    # Uses GITHUB_TOKEN to add GHCR_TOKEN and MANIFESTS_REPO_TOKEN as secrets
    pass
```

## 🚨 Security Notes

### Token Security:
- ✅ Tokens are stored in `config.py` (not in environment by default)
- ✅ Tokens are used for authentication only
- ✅ No token logging in production
- ✅ Tokens are embedded in Git URLs for authentication

### Best Practices:
- 🔒 Rotate tokens regularly
- 🔒 Use environment variables in production
- 🔒 Monitor token usage
- 🔒 Set appropriate expiration dates

## 📊 Monitoring Token Usage

### Check Token Usage:
```bash
# Test all tokens
python test_tokens.py

# Check specific token
python -c "from config import GITHUB_TOKEN; print('Token configured:', bool(GITHUB_TOKEN))"
```

### GitHub API Limits:
- **Authenticated requests**: 5,000 per hour
- **Search API**: 30 requests per minute
- **Core API**: 5,000 requests per hour

## 🎯 Usage Examples

### 1. Create Service with Tokens:
```python
# Auto Project Tool will:
# 1. Use GITHUB_TOKEN to create repository
# 2. Use GITHUB_TOKEN to add GHCR_TOKEN as secret
# 3. Use MANIFESTS_REPO_TOKEN to push manifests
```

### 2. CI/CD Pipeline:
```yaml
# GitHub Actions workflow uses:
# - GHCR_TOKEN for Docker registry
# - MANIFESTS_REPO_TOKEN for updating manifests
```

### 3. Repository Operations:
```python
# Repository A (Django App) → GITHUB_TOKEN
# Repository B (K8s Manifests) → MANIFESTS_REPO_TOKEN
# Docker Registry → GHCR_TOKEN
```

## 🔍 Troubleshooting

### Common Issues:

#### 1. **Token Invalid Error:**
```
❌ GITHUB_TOKEN: Invalid (Status: 401)
```
**Solution**: Check token validity and permissions

#### 2. **Repository Access Denied:**
```
❌ MANIFESTS_REPO_TOKEN: Invalid (Status: 403)
```
**Solution**: Ensure token has repository access

#### 3. **GHCR Access Denied:**
```
❌ GHCR_TOKEN: Invalid (Status: 403)
```
**Solution**: Check package permissions

### Debug Commands:
```bash
# Test token validity
curl -H "Authorization: token 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" https://api.github.com/user

# Check token scopes
curl -H "Authorization: token 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" https://api.github.com/user -I
```

## 📈 Token Performance

### Expected Response Times:
- **GitHub API**: 200-500ms
- **GHCR API**: 300-800ms
- **Repository Operations**: 1-3 seconds

### Rate Limiting:
- **5,000 requests/hour** per token
- **30 requests/minute** for search API
- **Automatic retry** with exponential backoff

---

**Generated by Auto Project Tool** 🚀
**Last Updated**: 2024-12-19
