@echo off
chcp 65001 > nul

REM Set Python encoding environment variables
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONLEGACYWINDOWSFSENCODING=utf-8
set LANG=zh_TW.UTF-8
set LC_ALL=zh_TW.UTF-8

echo Starting MP3 to Text application...
echo Please wait a few seconds...
echo.

REM Start Flask application in background
start "" py -3.8 app.py

REM Wait for server to start
timeout /t 3 /nobreak > nul

REM Open browser
echo Opening web browser...
start http://localhost:5000

echo.
echo If browser does not open automatically, please visit: http://localhost:5000
echo Press any key to exit...
pause
