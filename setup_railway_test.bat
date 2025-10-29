@echo off
echo ========================================
echo   RAILWAY MODE TESTING SETUP
echo ========================================

echo.
echo 1. Setting Railway environment variables...
setx RAILWAY_ENVIRONMENT 1
setx GATEWAY_BASE_URL http://127.0.0.1:5005

echo ✅ Environment variables set!
echo    RAILWAY_ENVIRONMENT=1
echo    GATEWAY_BASE_URL=http://127.0.0.1:5005

echo.
echo 2. Please restart your terminal/IDE to apply environment variables
echo.
echo 3. Then run these commands in separate terminals:
echo.
echo    Terminal 1 - Start aemo-v6 service:
echo    cd E:\Study\aemo-v6
echo    python app.py
echo.
echo    Terminal 2 - Start Mock Gateway:
echo    cd E:\Study\Auto_project_tool
echo    python gateway_mock.py
echo.
echo    Terminal 3 - Start Dev Portal:
echo    cd E:\Study\Auto_project_tool
echo    python app.py
echo.
echo 4. Test URLs:
echo    - Gateway health: http://127.0.0.1:5005/health
echo    - Service health: http://127.0.0.1:5005/api/aemo-v6/api/health
echo    - Dev Portal: http://127.0.0.1:5000
echo.
echo 5. Check real-time metrics in Service Details!
echo.
pause
