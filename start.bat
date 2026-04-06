@echo off
chcp 65001 >nul
title TISH SEARCH v4 - Multi-Agent Site Analyzer
cls

echo ╔══════════════════════════════════════════════════════════╗
echo ║                                                          ║
echo ║           TISH SEARCH v4 - Auto-Startup                  ║
echo ║                                                          ║
echo ║     Профессиональный инструмент для анализа сайтов       ║
echo ║                                                          ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.9+
    echo Скачайте с: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python найден
python --version
echo.

REM Проверяем наличие зависимостей
echo 📦 Проверка зависимостей...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Зависимости не установлены. Устанавливаю...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ Ошибка установки зависимостей!
        pause
        exit /b 1
    )
) else (
    echo ✅ Зависимости установлены
)
echo.

REM Проверяем Ollama
echo 🔍 Проверка Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo ❌ Ollama не найдена! Установите Ollama
    echo Скачайте с: https://ollama.ai
    pause
    exit /b 1
)

echo ✅ Ollama найдена
echo.

REM Проверяем, запущена ли Ollama
echo 🔄 Проверка сервера Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Сервер Ollama не запущен. Запускаю...
    start "" "ollama" "ollama" "serve"
    timeout /t 5 /nobreak >nul
) else (
    echo ✅ Сервер Ollama работает
)
echo.

REM Проверяем наличие vision-модели
echo 🤖 Проверка vision-модели...
python -c "import requests; r = requests.get('http://localhost:11434/api/tags'); models = r.json().get('models', []); vision = [m for m in models if 'qwen' in m['name'] or 'llava' in m['name']]; exit(0 if vision else 1)" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Vision-модель не найдена! Устанавливаю qwen3-vl...
    echo Это может занять несколько минут...
    ollama pull qwen3-vl
    if errorlevel 1 (
        echo ❌ Ошибка установки модели!
        pause
        exit /b 1
    )
) else (
    echo ✅ Vision-модель найдена
)
echo.

REM Инициализация БД
echo 💾 Инициализация базы данных...
python init_app.py
if errorlevel 1 (
    echo ⚠️ Предупреждение при инициализации (не критично)
)
echo.

echo ╔══════════════════════════════════════════════════════════╗
echo ║                                                          ║
echo ║           🚀 ЗАПУСК TISH SEARCH v4...                    ║
echo ║                                                          ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo 📡 Сервер будет доступен по адресу: http://localhost:5000
echo.
echo 💡 Для остановки нажмите Ctrl+C в этом окне
echo.
echo ──────────────────────────────────────────────────────────
echo.

REM Запускаем сервер
python server.py

pause