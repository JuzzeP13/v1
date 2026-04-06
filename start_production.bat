@echo off
chcp 65001 >nul
title TISH SEARCH v4 - PRODUCTION MODE
cls

echo ╔══════════════════════════════════════════════════════════╗
echo ║                                                          ║
echo ║       TISH SEARCH v4 - PRODUCTION SERVER                 ║
echo ║                                                          ║
echo ║      Waitress WSGI Server (Production Ready)             ║
echo ║                                                          ║
echo ══════════════════════════════════════════════════════════╝
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.9+
    pause
    exit /b 1
)

echo ✅ Python найден
python --version
echo.

REM Проверяем наличие Waitress
python -c "import waitress" >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Waitress не установлен. Устанавливаю...
    pip install waitress
    if errorlevel 1 (
        echo ❌ Ошибка установки Waitress!
        pause
        exit /b 1
    )
)
echo ✅ Waitress найден
echo.

REM Проверяем наличие .env
if not exist .env (
    echo ❌ Файл .env не найден!
    echo Скопируйте .env.example в .env и настройте переменные
    pause
    exit /b 1
)
echo ✅ .env найден
echo.

REM Загружаем переменные окружения из .env
echo 🔧 Загрузка настроек из .env...
for /f "tokens=1,* delims==" %%a in (.env) do (
    set %%a=%%b
)
echo ✅ Настройки загружены
echo.

REM Показываем конфигурацию
echo ═══════════════════════════════════════════════════════
echo 📋 КОНФИГУРАЦИЯ:
echo    Database: %DATABASE_URL%
echo    Ollama: %OLLAMA_URL%
echo    Vision: %VISION_MODEL%
echo    Workers: %MAX_WORKERS%
echo ═══════════════════════════════════════════════════════
echo.

echo ╔══════════════════════════════════════════════════════════╗
echo ║                                                          ║
echo            🚀 ЗАПУСК PRODUCTION СЕРВЕРА...                ║
echo                                                           ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo 📡 Сервер будет доступен по адресу: http://0.0.0.0:5000
echo 🔐 Admin Panel: http://0.0.0.0:5000/admin
echo.
echo 💡 Для остановки нажмите Ctrl+C в этом окне
echo.
echo ──────────────────────────────────────────────────────────
echo.

REM Запускаем production сервер через waitress
python -m waitress --listen=0.0.0.0:5000 --threads=%MAX_WORKERS% server:app

pause
