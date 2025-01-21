@echo off
chcp 65001 > nul

REM 設置 Python 編碼環境變量
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONLEGACYWINDOWSFSENCODING=utf-8
set LANG=zh_TW.UTF-8
set LC_ALL=zh_TW.UTF-8

REM 檢查虛擬環境
if not exist ".\venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    pause
    exit /b 1
)

REM 啟動虛擬環境
call .\venv\Scripts\activate.bat

REM 啟動應用程序
.\venv\Scripts\python.exe app.py

pause
