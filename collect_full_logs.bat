@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format \"yyyyMMdd_HHmmss\""') do set "TS=%%I"
set "LOG_FILE=logs\full_runtime_%TS%.log"

echo ============================================================
echo   TISH SEARCH v4 - Full Log Collector
echo ============================================================
echo [INFO] Runtime log: %LOG_FILE%
echo [INFO] Structured app log: logs\full_diagnostics.log
echo.

(
echo ===== TISH FULL DIAGNOSTICS SESSION =====
echo Start time: %DATE% %TIME%
echo Workdir: %CD%
echo.
echo --- Python ---
python --version 2^>^&1
python -m pip --version 2^>^&1
echo.
echo --- Ollama binary ---
where ollama 2^>^&1
ollama --version 2^>^&1
echo.
echo --- Ollama models ---
ollama list 2^>^&1
echo.
echo --- Ollama API /api/tags ---
python -c "import requests; print(requests.get('http://localhost:11434/api/tags', timeout=10).text)" 2^>^&1
echo.
echo ===== SERVER OUTPUT =====
) > "%LOG_FILE%"

echo [INFO] Starting server with unbuffered output...
echo [INFO] Press Ctrl+C to stop and finish log session.
echo.

python -u -m modules.main.python.server 1>>"%LOG_FILE%" 2>&1

(
echo.
echo ===== SESSION FINISHED =====
echo End time: %DATE% %TIME%
) >> "%LOG_FILE%"

echo [INFO] Done. Runtime log saved to: %LOG_FILE%
echo [INFO] Structured log saved to: logs\full_diagnostics.log
pause

