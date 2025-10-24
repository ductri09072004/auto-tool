# ArgoCD Setup Guide

## 🚀 Quick Setup

### 1. Local Development
```bash
# Start ArgoCD
chmod +x setup_argocd.sh
./setup_argocd.sh

# Start Dev Portal
python app.py
```

### 2. Railway Deployment
```bash
# Deploy to Railway
railway login
railway link
railway up
```

## 🔧 Configuration

### Environment Variables
```
ARGOCD_SERVER_URL=http://argocd:8080
ARGOCD_TOKEN=your-argocd-token
```

### URLs
- **Dev Portal**: `https://auto-tool.up.railway.app/`
- **ArgoCD**: `https://auto-tool.up.railway.app/argocd`
- **Dashboard**: `https://auto-tool.up.railway.app/dashboard`

## 🎯 Features

### Integrated Services
- ✅ **Dev Portal** - Create and manage services
- ✅ **ArgoCD** - Deploy and sync applications
- ✅ **Proxy** - Access ArgoCD through Dev Portal
- ✅ **API Integration** - Automatic ArgoCD application creation

### Workflow
1. **Create Service** → Dev Portal generates YAML
2. **ArgoCD API** → Automatically creates ArgoCD application
3. **Access ArgoCD** → Click "ArgoCD" link in Dev Portal
4. **Monitor** → View service status in ArgoCD UI
5. **Sync** → ArgoCD automatically syncs and deploys

## 🔑 Getting ArgoCD Token

### Method 1: ArgoCD UI
1. Login to ArgoCD UI
2. Click profile → Settings → Account → Tokens
3. Create new token with permissions:
   - `applications:create`
   - `applications:update`
   - `applications:delete`
   - `applications:get`

### Method 2: CLI
```bash
# Login to ArgoCD
argocd login localhost:8080

# Generate token
argocd account generate-token --account dev-portal
```

## 🚨 Troubleshooting

### ArgoCD not accessible
- Check if ArgoCD service is running
- Verify `ARGOCD_SERVER_URL` is correct
- Check Railway logs for errors

### Token issues
- Verify `ARGOCD_TOKEN` is set correctly
- Check token permissions
- Generate new token if expired

### Proxy errors
- Check ArgoCD service status
- Verify network connectivity
- Check Railway logs
