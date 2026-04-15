@echo off
setlocal EnableExtensions
chcp 65001 >nul
title TISH SEARCH v4 - Production Mode
cls

echo ============================================================
echo   TISH SEARCH v4 - Production Mode (Waitress)
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

REM 2) .env
if not exist .env (
    echo [ERROR] .env file not found.
    echo Create it from .env.example and fill required values.
    pause
    exit /b 1
)
echo [OK] .env found.
echo.

REM 3) Auto-update from git (safe mode)
echo [INFO] Checking git auto-update...
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN] Git is not installed. Skipping auto-update.
) else (
    git rev-parse --is-inside-work-tree >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Current folder is not a git repository. Skipping auto-update.
    ) else (
        set "GIT_DIRTY="
        for /f %%i in ('git status --porcelain 2^>nul') do set "GIT_DIRTY=1"

        if defined GIT_DIRTY (
            echo [WARN] Local changes detected. Skipping auto-update to avoid conflicts.
        ) else (
            git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
            if errorlevel 1 (
                echo [WARN] Upstream branch is not configured. Skipping auto-update.
            ) else (
                echo [INFO] Pulling latest changes...
                git pull --ff-only
                if errorlevel 1 (
                    echo [WARN] Git auto-update failed. Continuing with current code.
                ) else (
                    echo [OK] Repository is up to date.
                )
            )
        )
    )
)
echo.

REM 4) pip + dependencies
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] pip is missing. Installing via ensurepip...
    python -m ensurepip --upgrade >nul 2>&1
)

echo [INFO] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies are ready.
echo.

REM 5) Playwright browser
echo [INFO] Checking Playwright Chromium...
if not exist "%USERPROFILE%\\AppData\\Local\\ms-playwright\\chromium-*" (
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

REM 6) Ollama binary
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

REM 7) Ollama server
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

REM 8) Vision model (always llava)
echo [INFO] Checking llava model...
python -c "import requests,sys; r=requests.get('http://localhost:11434/api/tags',timeout=10); models=r.json().get('models', []); names=[(m.get('name','') or '').lower() for m in models]; has_llava=any(('llava' in n) for n in names); sys.exit(0 if has_llava else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] LLaVA not found. Pulling llava:latest...
    ollama pull llava:latest
    if errorlevel 1 (
        echo [ERROR] Failed to pull llava model.
        pause
        exit /b 1
    )
) else (
    echo [OK] LLaVA model found.
)
echo.

REM 9) Load .env values into current shell (for MAX_WORKERS)
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    set "%%A=%%B"
)
if not defined MAX_WORKERS set "MAX_WORKERS=4"

REM 10) Initialize app resources
echo [INFO] Running app initialization...
python -m modules.system.python.init_app
if errorlevel 1 (
    echo [WARN] Initialization returned warnings. Continuing...
)
echo.

echo ============================================================
echo   Starting production server (Waitress)
echo   URL: http://0.0.0.0:5000
echo   Admin: http://0.0.0.0:5000/admin
echo   Press Ctrl+C to stop
echo ============================================================
echo.

python -m waitress --listen=0.0.0.0:5000 --threads=%MAX_WORKERS% modules.main.python.app:app
pause
