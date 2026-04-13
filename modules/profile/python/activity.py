"""Online user activity tracking for profile/admin sections."""

import os
import time
import threading

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'TISH_TEAM_SEARCH')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '0192837456_TICH_TEAM_SEARCH')

online_users_store = {}
ws_connections_count = 0
ONLINE_USERS_TIMEOUT = 300
def track_user_activity(user_id, username, task=None):
    """Отслеживание активности пользователя"""
    online_users_store[user_id] = {
        'username': username,
        'last_seen': time.time(),
        'task': task or ''
    }

def get_online_users(timeout=None):
    """Получить пользователей онлайн (активны за последние timeout секунд)"""
    if timeout is None:
        timeout = ONLINE_USERS_TIMEOUT
    now = time.time()
    # Удаляем устаревшие записи (очистка утечки памяти)
    stale_users = [uid for uid, data in online_users_store.items() 
                   if now - data['last_seen'] > timeout]
    for uid in stale_users:
        del online_users_store[uid]
    
    return {uid: data for uid, data in online_users_store.items() 
            if now - data['last_seen'] < timeout}

def cleanup_online_store():
    """Периодическая очистка хранилища онлайн пользователей"""
    while True:
        time.sleep(60)  # Каждую минуту
        try:
            get_online_users()  # Это автоматически удалит stale записи
        except Exception as e:
            print(f"[CLEANUP] Error: {e}")

# Запускаем фоновую очистку
import threading
cleanup_thread = threading.Thread(target=cleanup_online_store, daemon=True)
cleanup_thread.start()
print("[CLEANUP] Фоновая очистка online_users_store запущена")

