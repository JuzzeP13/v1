"""
TISH SEARCH v4 - Application Initialization Script
Запуск: python -m modules.system.python.init_app
"""

import os
import sys

def check_dependencies():
    """Проверка установленных зависимостей"""
    required = [
        'flask', 'flask_socketio', 'flask_login', 'flask_sqlalchemy',
        'flask_wtf', 'flask_mail', 'werkzeug', 'openpyxl', 'playwright',
        'requests', 'ddgs', 'duckduckgo_search', 'dotenv', 'bcrypt', 'email_validator',
        'PIL'
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Отсутствуют зависимости:")
        for pkg in missing:
            print(f"   - {pkg}")
        print("\nУстановите: pip install -r requirements.txt")
        return False
    
    print("✅ Все зависимости установлены")
    return True

def init_database():
    """Инициализация базы данных"""
    from modules.auth.python.models import init_extended_db
    init_extended_db()
    print("✅ База данных инициализирована")

def install_playwright():
    """Установка браузеров Playwright"""
    print("\n📦 Установка браузеров Playwright...")
    os.system("playwright install chromium")
    print("✅ Браузеры установлены")

def check_ollama():
    """Проверка доступности Ollama"""
    import requests
    from modules.common.python.config import Config
    
    try:
        r = requests.get(f"{Config.OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            print(f"✅ Ollama доступна: {len(models)} моделей")
            
            # Проверяем наличие vision модели
            vision_models = [m for m in models if 'qwen' in m['name'] or 'llava' in m['name']]
            if vision_models:
                print(f"   Vision модели: {', '.join(m['name'] for m in vision_models)}")
            else:
                print("   ⚠️ Нет vision моделей! Установите: ollama pull qwen3-vl")
            return True
        else:
            print(f"⚠️ Ollama вернула статус {r.status_code}")
            return False
    except requests.ConnectionError:
        print("❌ Ollama не доступна! Запустите: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки Ollama: {e}")
        return False

def create_upload_folder():
    """Создание папки для загрузок"""
    from modules.common.python.config import Config
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs('uploads/images', exist_ok=True)
    print("✅ Папки для загрузок созданы")

def create_static_folders():
    """Создание статических папок"""
    os.makedirs('static/images', exist_ok=True)
    print("✅ Статические папки созданы")

def main():
    """Основная функция инициализации"""
    print("=" * 60)
    print("  TISH SEARCH v4 - Инициализация")
    print("=" * 60)
    print()
    
    # 1. Проверка зависимостей
    print("[1/6] Проверка зависимостей...")
    if not check_dependencies():
        sys.exit(1)
    
    # 2. Инициализация БД
    print("\n[2/6] Инициализация базы данных...")
    init_database()
    
    # 3. Установка Playwright
    print("\n[3/6] Проверка Playwright...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch()
        print("✅ Playwright готов")
    except Exception:
        install_playwright()
    
    # 4. Проверка Ollama
    print("\n[4/6] Проверка Ollama...")
    check_ollama()
    
    # 5. Создание папок
    print("\n[5/6] Создание папок...")
    create_upload_folder()
    create_static_folders()
    
    # 6. Проверка конфигов
    print("\n[6/6] Проверка конфигурации...")
    from modules.common.python.config import Config
    if Config.SECRET_KEY == 'dev-secret-key-change-in-production':
        print("⚠️ ВНИМАНИЕ: Используйте уникальный SECRET_KEY в production!")
    else:
        print("✅ SECRET_KEY настроен")
    
    print("\n" + "=" * 60)
    print("  ✅ Инициализация завершена!")
    print("=" * 60)
    print("\n📝 Следующие шаги:")
    print("   1. Настройте .env файл (укажите реальные SMTP настройки)")
    print("   2. Установите vision модель: ollama pull qwen3-vl")
    print("   3. Запустите сервер: python -m modules.main.python.server")
    print("   4. Откройте: http://localhost:5000")
    print()

if __name__ == "__main__":
    main()
