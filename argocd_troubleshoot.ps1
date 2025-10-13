# Script tổng hợp khắc phục tất cả vấn đề ArgoCD sync
# Sử dụng khi services không tự động cập nhật sau khi code thay đổi

param(
    [string]$ServiceName = "",
    [switch]$AllServices = $false,
    [switch]$CheckOnly = $false
)

Write-Host "=== ArgoCD Troubleshooting Tool ===" -ForegroundColor Cyan

if ($AllServices) {
    Write-Host "🔍 Kiểm tra tất cả services..." -ForegroundColor Yellow
    
    # Lấy danh sách tất cả applications
    $apps = kubectl get applications -o json | ConvertFrom-Json
    foreach ($app in $apps.items) {
        $name = $app.metadata.name
        $status = $app.status.sync.status
        $health = $app.status.health.status
        
        Write-Host "Service: $name | Sync: $status | Health: $health" -ForegroundColor $(if($status -eq "Synced" -and $health -eq "Healthy") {"Green"} else {"Red"})
        
        if (-not $CheckOnly) {
            Write-Host "  → Force syncing $name..." -ForegroundColor Yellow
            kubectl patch application $name -p '{"operation":{"sync":{"syncOptions":["CreateNamespace=true","PrunePropagationPolicy=foreground","PruneLast=true"]}}}' --type merge | Out-Null
        }
    }
} elseif ($ServiceName) {
    Write-Host "🔍 Kiểm tra service: $ServiceName" -ForegroundColor Yellow
    
    # Kiểm tra ArgoCD Application
    $app = kubectl get application $ServiceName -o json 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Không tìm thấy ArgoCD Application: $ServiceName" -ForegroundColor Red
        Write-Host "Các Application có sẵn:" -ForegroundColor Yellow
        kubectl get applications
        exit 1
    }
    
    $appObj = $app | ConvertFrom-Json
    $syncStatus = $appObj.status.sync.status
    $healthStatus = $appObj.status.health.status
    
    Write-Host "Sync Status: $syncStatus" -ForegroundColor $(if($syncStatus -eq "Synced") {"Green"} else {"Red"})
    Write-Host "Health Status: $healthStatus" -ForegroundColor $(if($healthStatus -eq "Healthy") {"Green"} else {"Red"})
    
    if (-not $CheckOnly) {
        # Force sync
        Write-Host "🔄 Force syncing $ServiceName..." -ForegroundColor Yellow
        kubectl patch application $ServiceName -p '{"operation":{"sync":{"syncOptions":["CreateNamespace=true","PrunePropagationPolicy=foreground","PruneLast=true"]}}}' --type merge
        
        # Restart deployment
        Write-Host "🔄 Restarting deployment..." -ForegroundColor Yellow
        kubectl rollout restart deployment/$ServiceName -n $ServiceName
        
        # Kiểm tra rollout status
        Write-Host "⏳ Waiting for rollout to complete..." -ForegroundColor Yellow
        kubectl rollout status deployment/$ServiceName -n $ServiceName --timeout=300s
    }
} else {
    Write-Host "❌ Vui lòng chỉ định ServiceName hoặc sử dụng -AllServices" -ForegroundColor Red
    Write-Host "Cách sử dụng:" -ForegroundColor Yellow
    Write-Host "  .\argocd_troubleshoot.ps1 -ServiceName demo-v42" -ForegroundColor White
    Write-Host "  .\argocd_troubleshoot.ps1 -AllServices" -ForegroundColor White
    Write-Host "  .\argocd_troubleshoot.ps1 -ServiceName demo-v42 -CheckOnly" -ForegroundColor White
    exit 1
}

# Kiểm tra pods và events
Write-Host "`n🔍 Kiểm tra pods và events..." -ForegroundColor Yellow
if ($ServiceName) {
    $namespace = $ServiceName
} else {
    $namespace = "default"
}

kubectl get pods -n $namespace -l app=$ServiceName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n📊 Pod details:" -ForegroundColor Cyan
    kubectl describe pods -n $namespace -l app=$ServiceName | Select-String -Pattern "Image:|Events:|Status:"
}

Write-Host "`n📋 Recent events:" -ForegroundColor Cyan
kubectl get events -n $namespace --sort-by='.lastTimestamp' | Select-Object -Last 10

# Kiểm tra image hiện tại
Write-Host "`n🖼️ Current image:" -ForegroundColor Cyan
if ($ServiceName) {
    kubectl get deployment $ServiceName -n $ServiceName -o jsonpath='{.spec.template.spec.containers[0].image}' 2>$null
    Write-Host ""
}

Write-Host "`n=== Kết quả ===" -ForegroundColor Green
if ($CheckOnly) {
    Write-Host "✅ Chỉ kiểm tra trạng thái, không thực hiện thay đổi" -ForegroundColor Green
} else {
    Write-Host "✅ Đã thực hiện các bước khắc phục:" -ForegroundColor Green
    Write-Host "  - Force sync ArgoCD Application" -ForegroundColor White
    Write-Host "  - Restart Deployment" -ForegroundColor White
    Write-Host "  - Kiểm tra rollout status" -ForegroundColor White
}

Write-Host "`n💡 Nếu vẫn có vấn đề, thử:" -ForegroundColor Yellow
Write-Host "1. kubectl delete pods -n $namespace -l app=$ServiceName" -ForegroundColor White
Write-Host "2. Kiểm tra ArgoCD UI: kubectl port-forward svc/argocd-server -n argocd 8080:80" -ForegroundColor White
Write-Host "3. Kiểm tra GitHub Actions logs" -ForegroundColor White
Write-Host "4. Kiểm tra image có tồn tại trên GHCR không" -ForegroundColor White
