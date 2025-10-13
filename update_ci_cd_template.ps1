# Script cập nhật CI/CD template để đảm bảo timestamp luôn thay đổi
# Điều này giúp ArgoCD detect được thay đổi và trigger rolling update

$templateFile = "E:\Study\Auto_project_tool\templates_src\repo_a_template\.github\workflows\ci-cd.yml"

Write-Host "=== Cập nhật CI/CD Template ===" -ForegroundColor Cyan

# Đọc nội dung hiện tại
$content = Get-Content $templateFile -Raw

# Thêm step để update timestamp trong deployment.yaml
$newStep = @"

    - name: Update deployment timestamp
      run: |
        cd manifests
        # Cập nhật timestamp annotation để force restart pods
        TIMESTAMP=`$(date +%s)
        sed -i "s|timestamp: \".*\"|timestamp: \"`$TIMESTAMP\"|g" k8s/deployment.yaml
        # Thêm annotation để force update
        sed -i "/timestamp: \"`$TIMESTAMP\"/a\        deployment.kubernetes.io/revision: \"`$TIMESTAMP\"" k8s/deployment.yaml
        echo "Updated timestamp to: `$TIMESTAMP"
"@

# Tìm vị trí để chèn step mới (sau step "Update image tag")
$insertPoint = $content.IndexOf("        echo ""Updated image tag to: latest""")
if ($insertPoint -gt 0) {
    $beforeInsert = $content.Substring(0, $insertPoint)
    $afterInsert = $content.Substring($insertPoint)
    
    # Tìm vị trí kết thúc của step hiện tại
    $stepEnd = $afterInsert.IndexOf("      ")
    if ($stepEnd -gt 0) {
        $newContent = $beforeInsert + $afterInsert.Substring(0, $stepEnd) + $newStep + $afterInsert.Substring($stepEnd)
    } else {
        $newContent = $beforeInsert + $newStep + $afterInsert
    }
} else {
    # Nếu không tìm thấy, thêm vào cuối file trước dòng cuối
    $newContent = $content -replace "(\s+)(- name: Update image tag)", "`$1$newStep`n`$1`$2"
}

# Ghi file mới
Set-Content -Path $templateFile -Value $newContent -Encoding UTF8

Write-Host "✅ Đã cập nhật CI/CD template" -ForegroundColor Green
Write-Host "Template mới sẽ:" -ForegroundColor Yellow
Write-Host "- Tự động cập nhật timestamp mỗi lần build" -ForegroundColor White
Write-Host "- Thêm deployment.kubernetes.io/revision annotation" -ForegroundColor White
Write-Host "- Force ArgoCD detect thay đổi và trigger rolling update" -ForegroundColor White

Write-Host "`n=== Cách sử dụng ===" -ForegroundColor Cyan
Write-Host "1. Tạo service mới từ Dev Portal" -ForegroundColor White
Write-Host "2. Khi code thay đổi, GitHub Actions sẽ tự động:" -ForegroundColor White
Write-Host "   - Build image mới với tag mới" -ForegroundColor White
Write-Host "   - Update timestamp trong deployment.yaml" -ForegroundColor White
Write-Host "   - ArgoCD sẽ tự động sync và restart pods" -ForegroundColor White
Write-Host "3. Nếu vẫn không tự động, chạy: .\fix_argocd_sync.ps1 -ServiceName <tên-service>" -ForegroundColor White
