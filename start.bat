@echo off
setlocal EnableExtensions
chcp 65001 >nul
title TISH SEARCH v4 - Auto Startup
cls

echo ============================================================
echo   TISH SEARCH v4 - Auto Startup
echo ============================================================
echo.

REM 1) Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo Install Python 3.11+ from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python:
python --version
echo.

REM 2) pip
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] pip is missing. Installing via ensurepip...
    python -m ensurepip --upgrade >nul 2>&1
)

REM 3) Install project dependencies (idempotent)
echo [INFO] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Python dependencies are ready.
echo.

REM 4) Playwright browser
echo [INFO] Checking Playwright Chromium...
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing Playwright Chromium...
    python -m playwright install chromium
    if errorlevel 1 (
        echo [ERROR] Failed to install Playwright Chromium.
        pause
        exit /b 1
    )
)
echo [OK] Playwright is ready.
echo.

REM 5) Ollama binary
echo [INFO] Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama is not installed. Trying auto-install via winget...
    winget --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] winget is not available. Install Ollama manually: https://ollama.ai
        pause
        exit /b 1
    )

    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERROR] Failed to auto-install Ollama.
        echo Install manually: https://ollama.ai
        pause
        exit /b 1
    )
)
echo [OK] Ollama found.
echo.

REM 6) Ollama server
echo [INFO] Checking Ollama server...
python -c "import requests,sys; sys.exit(0 if requests.get('http://localhost:11434/api/tags',timeout=5).status_code==200 else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama server is not running. Starting...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama server is running.
)
echo.

REM 7) Vision model (qwen3-vl or llava)
echo [INFO] Checking vision model...
python -c "import requests,sys; r=requests.get('http://localhost:11434/api/tags',timeout=10); models=r.json().get('models', []); vision=[m for m in models if 'qwen' in m.get('name','') or 'llava' in m.get('name','')]; sys.exit(0 if vision else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Vision model not found. Pulling qwen3-vl...
    ollama pull qwen3-vl
    if errorlevel 1 (
        echo [ERROR] Failed to pull vision model.
        pause
        exit /b 1
    )
) else (
    echo [OK] Vision model found.
)
echo.

REM 8) Initialize app resources (DB/folders/checks)
echo [INFO] Running app initialization...
python -m modules.system.python.init_app
if errorlevel 1 (
    echo [WARN] Initialization returned warnings. Continuing...
)
echo.

echo ============================================================
echo   Starting server: http://localhost:5000
echo   Press Ctrl+C to stop
echo ============================================================
echo.

python -m modules.main.python.server
pause
