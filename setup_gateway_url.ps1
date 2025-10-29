# PowerShell script to setup GATEWAY_BASE_URL for Railway environment
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   GATEWAY_BASE_URL SETUP GUIDE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n📋 GATEWAY_BASE_URL Configuration:" -ForegroundColor Yellow
Write-Host "`n1. LOCAL TESTING (Railway mode simulation):" -ForegroundColor Green
Write-Host "   Set environment variable:" -ForegroundColor White
Write-Host "   `$env:GATEWAY_BASE_URL = 'http://127.0.0.1:5005'" -ForegroundColor Gray
Write-Host "   `$env:RAILWAY_ENVIRONMENT = '1'" -ForegroundColor Gray

Write-Host "`n2. RAILWAY PRODUCTION:" -ForegroundColor Green
Write-Host "   In Railway dashboard:" -ForegroundColor White
Write-Host "   - Go to your project" -ForegroundColor Gray
Write-Host "   - Click 'Variables' tab" -ForegroundColor Gray
Write-Host "   - Add: GATEWAY_BASE_URL = https://your-gateway.up.railway.app" -ForegroundColor Gray

Write-Host "`n3. NGROK TUNNEL (for local services):" -ForegroundColor Green
Write-Host "   If you want to expose local services:" -ForegroundColor White
Write-Host "   - Install ngrok: https://ngrok.com/download" -ForegroundColor Gray
Write-Host "   - Run: ngrok http 5005" -ForegroundColor Gray
Write-Host "   - Use HTTPS URL: https://abc123.ngrok-free.app" -ForegroundColor Gray

Write-Host "`n4. CLOUDFLARE TUNNEL (alternative):" -ForegroundColor Green
Write-Host "   - Install cloudflared" -ForegroundColor White
Write-Host "   - Run: cloudflared tunnel --url http://localhost:5005" -ForegroundColor Gray
Write-Host "   - Use provided HTTPS URL" -ForegroundColor Gray

Write-Host "`n🔧 Current Status:" -ForegroundColor Yellow
$currentGateway = $env:GATEWAY_BASE_URL
if ($currentGateway) {
    Write-Host "   GATEWAY_BASE_URL: $currentGateway" -ForegroundColor Green
} else {
    Write-Host "   GATEWAY_BASE_URL: NOT SET" -ForegroundColor Red
}

$currentRailway = $env:RAILWAY_ENVIRONMENT
if ($currentRailway) {
    Write-Host "   RAILWAY_ENVIRONMENT: $currentRailway" -ForegroundColor Green
} else {
    Write-Host "   RAILWAY_ENVIRONMENT: NOT SET" -ForegroundColor Red
}

Write-Host "`n🧪 Test Commands:" -ForegroundColor Yellow
Write-Host "   # Test health detection" -ForegroundColor Gray
Write-Host "   Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/test-health-detection'" -ForegroundColor Gray
Write-Host ""
Write-Host "   # Test specific service health" -ForegroundColor Gray
Write-Host "   Invoke-RestMethod -Uri 'http://127.0.0.1:5005/api/aemo-v6/api/health'" -ForegroundColor Gray

Write-Host "`n💡 Tips:" -ForegroundColor Yellow
Write-Host "   - Gateway must be running before setting GATEWAY_BASE_URL" -ForegroundColor White
Write-Host "   - Use HTTPS URLs for production (Railway/ngrok)" -ForegroundColor White
Write-Host "   - Test with /api/test-health-detection endpoint first" -ForegroundColor White

Write-Host "`nPress any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
