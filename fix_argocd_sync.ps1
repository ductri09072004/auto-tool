# Script khắc phục ArgoCD không tự động cập nhật
# Chạy script này khi service không tự động cập nhật sau khi code thay đổi

param(
    [Parameter(Mandatory=$true)]
    [string]$ServiceName,
    
    [string]$Namespace = "default"
)

Write-Host "=== Khắc phục ArgoCD Sync cho $ServiceName ===" -ForegroundColor Cyan

# 1. Kiểm tra trạng thái ArgoCD Application
Write-Host "1. Kiểm tra ArgoCD Application..." -ForegroundColor Yellow
$app = kubectl get application $ServiceName -o json 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Không tìm thấy ArgoCD Application: $ServiceName" -ForegroundColor Red
    Write-Host "Các Application có sẵn:" -ForegroundColor Yellow
    kubectl get applications
    exit 1
}

# 2. Force sync ArgoCD Application
Write-Host "2. Force sync ArgoCD Application..." -ForegroundColor Yellow
kubectl patch application $ServiceName -p '{"operation":{"sync":{"syncOptions":["CreateNamespace=true","PrunePropagationPolicy=foreground","PruneLast=true"]}}}' --type merge
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ ArgoCD Application đã được force sync" -ForegroundColor Green
} else {
    Write-Host "❌ Lỗi khi force sync ArgoCD Application" -ForegroundColor Red
}

# 3. Restart Deployment để force pull image mới
Write-Host "3. Restart Deployment để force pull image mới..." -ForegroundColor Yellow
kubectl rollout restart deployment/$ServiceName -n $Namespace
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Deployment đã được restart" -ForegroundColor Green
} else {
    Write-Host "❌ Lỗi khi restart Deployment" -ForegroundColor Red
}

# 4. Kiểm tra trạng thái rollout
Write-Host "4. Kiểm tra trạng thái rollout..." -ForegroundColor Yellow
kubectl rollout status deployment/$ServiceName -n $Namespace --timeout=300s
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Rollout hoàn thành thành công" -ForegroundColor Green
} else {
    Write-Host "❌ Rollout không hoàn thành trong thời gian quy định" -ForegroundColor Red
}

# 5. Kiểm tra pods
Write-Host "5. Kiểm tra pods..." -ForegroundColor Yellow
kubectl get pods -n $Namespace -l app=$ServiceName
kubectl describe pods -n $Namespace -l app=$ServiceName | Select-String -Pattern "Image:|Events:"

# 6. Kiểm tra image hiện tại
Write-Host "6. Kiểm tra image hiện tại..." -ForegroundColor Yellow
kubectl get deployment $ServiceName -n $Namespace -o jsonpath='{.spec.template.spec.containers[0].image}'
Write-Host ""

Write-Host "=== Hoàn thành ===" -ForegroundColor Green
Write-Host "Nếu vẫn không cập nhật, thử các lệnh sau:" -ForegroundColor Yellow
Write-Host "1. kubectl delete pods -n $Namespace -l app=$ServiceName" -ForegroundColor Cyan
Write-Host "2. kubectl get events -n $Namespace --sort-by='.lastTimestamp'" -ForegroundColor Cyan
Write-Host "3. Kiểm tra ArgoCD UI: kubectl port-forward svc/argocd-server -n argocd 8080:80" -ForegroundColor Cyan
