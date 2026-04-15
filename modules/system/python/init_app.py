"""
TISH SEARCH v4 - Скрипт инициализации приложения
Запуск: python -m modules.system.python.init_app
"""

import os
import subprocess
import sys

from modules.common.python.asyncio_compat import ensure_windows_proactor_event_loop


def check_dependencies() -> bool:
    """Проверка обязательных Python-зависимостей."""
    required = [
        "flask",
        "flask_socketio",
        "flask_login",
        "flask_sqlalchemy",
        "flask_wtf",
        "flask_mail",
        "werkzeug",
        "openpyxl",
        "playwright",
        "requests",
        "ddgs",
        "duckduckgo_search",
        "dotenv",
        "bcrypt",
        "email_validator",
        "PIL",
    ]

    missing = []
    for package in required:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        print("Отсутствуют зависимости:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nУстановите: pip install -r requirements.txt")
        return False

    print("Все зависимости установлены")
    return True


def init_database() -> None:
    """Инициализация таблиц SQLite."""
    from modules.auth.python.models import init_extended_db

    init_extended_db()
    print("База данных инициализирована")


def install_playwright() -> bool:
    """Установка браузера Chromium для Playwright."""
    print("\nУстановка Playwright Chromium...")
    result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    if result.returncode == 0:
        print("Playwright Chromium установлен")
        return True

    print("Не удалось установить Playwright Chromium")
    return False


def check_playwright_runtime() -> tuple[bool, str]:
    """Проверка запуска Playwright в отдельном процессе (без шумного traceback)."""
    probe = (
        "import asyncio,os;"
        "from playwright.sync_api import sync_playwright;"
        "os.name=='nt' and hasattr(asyncio,'WindowsProactorEventLoopPolicy') and "
        "asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy());"
        "p=sync_playwright().start();"
        "b=p.chromium.launch(headless=True);"
        "b.close();"
        "p.stop()"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, ""

    out = (result.stderr or result.stdout or "").strip()
    if out:
        return False, out.splitlines()[-1]
    return False, "неизвестная ошибка"


def is_vision_model_name(model_name: str) -> bool:
    """Определяет, является ли модель vision-моделью."""
    name = (model_name or "").strip().lower()
    if not name:
        return False

    # Поддержка основных семейств vision-моделей Ollama:
    # llava, qwen*-vl, deepseek-vl и т.п.
    return (
        "llava" in name
        or "-vl" in name
        or "vl-" in name
        or "vision" in name
    )


def check_ollama() -> bool:
    """Проверка доступности Ollama и vision-моделей."""
    import requests
    from modules.common.python.config import Config

    try:
        r = requests.get(f"{Config.OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            print(f"Ollama доступна: {len(models)} моделей")

            vision_models = [m for m in models if is_vision_model_name(m.get("name", ""))]
            if vision_models:
                print(f"Vision-модели: {', '.join(m['name'] for m in vision_models)}")
            else:
                print("⚠ Нет vision-моделей. Установите: ollama pull qwen3-vl")
            return True

        print(f"⚠ Ollama вернула статус {r.status_code}")
        return False
    except requests.ConnectionError:
        print("❌ Ollama недоступна. Запустите: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки Ollama: {e}")
        return False


def create_upload_folder() -> None:
    """Создание папок для загрузок."""
    from modules.common.python.config import Config

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs("uploads/images", exist_ok=True)
    print("Папки загрузок готовы")


def create_static_folders() -> None:
    """Создание папок static."""
    os.makedirs("static/images", exist_ok=True)
    print("Папки static готовы")


def main() -> None:
    """Основная процедура инициализации."""
    ensure_windows_proactor_event_loop()

    print("=" * 60)
    print("  TISH SEARCH v4 - Инициализация")
    print("=" * 60)
    print()

    print("[1/6] Проверка зависимостей...")
    if not check_dependencies():
        sys.exit(1)

    print("\n[2/6] Инициализация базы данных...")
    init_database()

    print("\n[3/6] Проверка Playwright...")
    ok, check_error = check_playwright_runtime()
    if ok:
        print("Playwright готов")
    else:
        print(f"⚠ Проверка запуска Playwright не прошла: {check_error}")
        if not install_playwright():
            print("⚠ Продолжаю без подтверждённого запуска Playwright")

    print("\n[4/6] Проверка Ollama...")
    check_ollama()

    print("\n[5/6] Создание папок...")
    create_upload_folder()
    create_static_folders()

    print("\n[6/6] Проверка конфигурации...")
    from modules.common.python.config import Config

    if Config.SECRET_KEY == "dev-secret-key-change-in-production":
        print("⚠ ВНИМАНИЕ: используйте уникальный SECRET_KEY в production")
    else:
        print("SECRET_KEY настроен")

    print("\n" + "=" * 60)
    print("  Инициализация завершена")
    print("=" * 60)
    print("\nСледующие шаги:")
    print("  1. Настройте .env с реальными SMTP-параметрами")
    print("  2. Установите vision-модель: ollama pull qwen3-vl")
    print("  3. Запустите сервер: python -m modules.main.python.server")
    print("  4. Откройте: http://localhost:5000")
    print()


if __name__ == "__main__":
    main()
