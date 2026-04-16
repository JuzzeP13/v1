@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title TISH SEARCH v4 - Auto Startup
cls

echo ============================================================
echo   TISH SEARCH v4 - Auto Startup
echo ============================================================
echo.
set "CHECK_UPDATE_ONLY="
if /I "%~1"=="--check-update" set "CHECK_UPDATE_ONLY=1"
if /I "%~1"=="check-update" set "CHECK_UPDATE_ONLY=1"
if defined CHECK_UPDATE_ONLY (
    echo [INFO] Mode: check-update only. Only git auto-update block will run.
    echo.
)

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

REM 3) Auto-update from git (safe mode)
echo [INFO] Checking git auto-update...
set "GIT_READY="
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;C:\Program Files (x86)\Git\cmd;C:\Program Files (x86)\Git\bin"
where git >nul 2>&1
if errorlevel 1 (
    if exist "C:\Program Files\Git\cmd\git.exe" (
        echo [OK] Git found in Program Files.
        set "GIT_READY=1"
    ) else (
        echo [INFO] Git is not installed. Trying auto-install via winget...
        winget --version >nul 2>&1
        if errorlevel 1 (
            echo [WARN] winget is not available. Skipping auto-update.
        ) else (
            winget install --id Git.Git --exact --source winget --silent --accept-package-agreements --accept-source-agreements
            if errorlevel 1 (
                echo [WARN] Failed to auto-install Git. Skipping auto-update.
            ) else (
                set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;C:\Program Files (x86)\Git\cmd;C:\Program Files (x86)\Git\bin"
                where git >nul 2>&1
                if errorlevel 1 (
                    echo [WARN] Git installed but not visible in current session. Restart terminal and rerun.
                ) else (
                    echo [OK] Git installed.
                    set "GIT_READY=1"
                )
            )
        )
    )
) else (
    set "GIT_READY=1"
)

if defined GIT_READY (
    if not exist ".git" (
        echo [WARN] .git folder is missing in "%CD%".
        echo [WARN] Auto-update works only in a cloned git repository.
        echo [WARN] If this folder was copied/archived, use: git clone ^<repo_url^>
        goto :after_git_update
    )
    git rev-parse --is-inside-work-tree >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Current folder "%CD%" is not a git repository. Skipping auto-update.
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
) else (
    echo [WARN] Git is unavailable. Auto-update skipped.
)
:after_git_update
echo.
if defined CHECK_UPDATE_ONLY (
    echo [INFO] Check-update mode finished.
    exit /b 0
)

REM 4) Install project dependencies (idempotent)
echo [INFO] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Python dependencies are ready.
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
set "OLLAMA_READY="
python -c "import requests,sys; sys.exit(0 if requests.get('http://localhost:11434/api/tags',timeout=5).status_code==200 else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama server is not running. Starting...
    start "" ollama serve
    for /l %%I in (1,1,10) do (
        if not defined OLLAMA_READY (
            timeout /t 3 /nobreak >nul
            python -c "import requests,sys; sys.exit(0 if requests.get('http://localhost:11434/api/tags',timeout=3).status_code==200 else 1)" >nul 2>&1
            if not errorlevel 1 set "OLLAMA_READY=1"
        )
    )
) else (
    set "OLLAMA_READY=1"
)

if defined OLLAMA_READY (
    echo [OK] Ollama server is running.
) else (
    echo [WARN] Ollama server did not start. Continuing without model pull.
)
echo.

REM 8) Vision model (always llava)
if not defined OLLAMA_READY (
    echo [WARN] Skipping llava check because Ollama server is unavailable.
) else (
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
)
echo.

REM 9) Initialize app resources (DB/folders/checks)
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
