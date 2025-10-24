#!/bin/bash

# Setup ArgoCD script
echo "🚀 Setting up ArgoCD..."

# Install kubectl if not exists
if ! command -v kubectl &> /dev/null; then
    echo "Installing kubectl..."
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    chmod +x kubectl
    sudo mv kubectl /usr/local/bin/
fi

# Create namespace
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
echo "⏳ Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

# Get admin password
echo "🔑 ArgoCD admin password:"
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
echo ""

# Port forward ArgoCD
echo "🌐 Starting ArgoCD server..."
kubectl port-forward svc/argocd-server -n argocd 8080:80 &

echo "✅ ArgoCD setup complete!"
echo "🌐 ArgoCD UI: http://localhost:8080"
echo "👤 Username: admin"
echo "🔑 Password: (see above)"
