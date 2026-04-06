"""
TISH SEARCH v4 - Production Server Launcher
Использует Flask-SocketIO server для поддержки WebSocket
Запуск: python run.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("  TISH SEARCH v4 - Production Server")
print("=" * 60)
print()

required_vars = ['SECRET_KEY']
missing_vars = [var for var in required_vars if not os.environ.get(var)]

if missing_vars:
    print("❌ Отсутствуют обязательные переменные окружения:")
    for var in missing_vars:
        print(f"   - {var}")
    sys.exit(1)

secret_key = os.environ.get('SECRET_KEY', '')
if secret_key in ['your-secret-key-change-this-in-production-min-32-chars', 'dev-secret-key-change-in-production']:
    print("⚠️ WARNING: Используйте уникальный SECRET_KEY!")
    print('   python -c "import secrets; print(secrets.token_hex(32))"')

print("📋 Конфигурация:")
print(f"   Database: {os.environ.get('DATABASE_URL', 'SQLite')}")
print(f"   Ollama: {os.environ.get('OLLAMA_URL', 'N/A')}")
print(f"   Vision: {os.environ.get('VISION_MODEL', 'llava:latest')}")
print()

try:
    from server import app, socketio
    print("✅ Приложение загружено")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    sys.exit(1)

try:
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))
    
    print(f"\n🚀 Запуск: http://{host}:{port}")
    print(f"🔐 Admin: http://{host}:{port}/admin")
    print("💡 Ctrl+C для остановки\n")
    
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    
except KeyboardInterrupt:
    print("\n👋 Остановлен")
except Exception as e:
    print(f"\n❌ Ошибка: {e}")
    sys.exit(1)
