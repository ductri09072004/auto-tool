# PowerShell script to test Railway mode with real data
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   RAILWAY MODE TESTING WITH REAL DATA" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Set environment variables for current session
$env:RAILWAY_ENVIRONMENT = "1"
$env:GATEWAY_BASE_URL = "http://127.0.0.1:5005"

Write-Host "`n✅ Environment variables set for current session:" -ForegroundColor Green
Write-Host "   RAILWAY_ENVIRONMENT=1" -ForegroundColor Yellow
Write-Host "   GATEWAY_BASE_URL=http://127.0.0.1:5005" -ForegroundColor Yellow

Write-Host "`n📋 Testing steps:" -ForegroundColor Cyan
Write-Host "1. Make sure aemo-v6 is running on port 5001" -ForegroundColor White
Write-Host "2. Start Mock Gateway: python gateway_mock.py" -ForegroundColor White
Write-Host "3. Start Dev Portal: python app.py" -ForegroundColor White

Write-Host "`n🔗 Test URLs:" -ForegroundColor Cyan
Write-Host "   Gateway health: http://127.0.0.1:5005/health" -ForegroundColor Yellow
Write-Host "   Service health: http://127.0.0.1:5005/api/aemo-v6/api/health" -ForegroundColor Yellow
Write-Host "   Dev Portal: http://127.0.0.1:5000" -ForegroundColor Yellow

Write-Host "`n🧪 Quick test commands:" -ForegroundColor Cyan
Write-Host "   # Test gateway health" -ForegroundColor Gray
Write-Host "   Invoke-RestMethod -Uri 'http://127.0.0.1:5005/health'" -ForegroundColor Gray
Write-Host ""
Write-Host "   # Test service health (real psutil data)" -ForegroundColor Gray
Write-Host "   Invoke-RestMethod -Uri 'http://127.0.0.1:5005/api/aemo-v6/api/health'" -ForegroundColor Gray
Write-Host ""
Write-Host "   # Test Dev Portal API" -ForegroundColor Gray
Write-Host "   Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/services'" -ForegroundColor Gray

Write-Host "`n🎯 Expected result:" -ForegroundColor Cyan
Write-Host "   Service Details should show real CPU/Memory usage from psutil!" -ForegroundColor Green

Write-Host "`nPress any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
