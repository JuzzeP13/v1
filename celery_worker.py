"""
TISH SEARCH v4 - Celery Worker Configuration
Фоновые задачи для обработки анализов
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

# Redis URL для Celery
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Создаём Celery приложение
celery_app = Celery(
    'tish_search',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['celery_worker']
)

# Конфигурация Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 час максимум на задачу
    task_soft_time_limit=3000,  # 50 минут мягкий лимит
    worker_prefetch_multiplier=1,  # Не брать задачи заранее
    worker_max_tasks_per_child=100,  # Перезапуск worker после 100 задач (очистка памяти)
)

# Периодические задачи
celery_app.conf.beat_schedule = {
    # Очистка устаревших онлайн пользователей каждый час
    'cleanup-online-users': {
        'task': 'celery_worker.cleanup_online_users',
        'schedule': crontab(minute=0),  # Каждый час
    },
    # Синхронизация с главным сайтом каждые 10 минут
    'sync-main-site': {
        'task': 'celery_worker.sync_with_main_site',
        'schedule': crontab(minute='*/10'),  # Каждые 10 минут
    },
    # Очистка временных файлов каждый день в 3 ночи
    'cleanup-temp-files': {
        'task': 'celery_worker.cleanup_temp_files',
        'schedule': crontab(hour=3, minute=0),  # Каждый день в 3:00
    },
}


# ──────────────────────────────────────────────
# TASKS
# ──────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3)
def analyze_city_task(self, city: str, user_id: int = None):
    """Фоновая задача анализа города"""
    try:
        from server import process_city, state, track_user_activity
        
        # Обновляем состояние
        state["running"] = True
        state["city"] = city
        
        # Отслеживаем пользователя
        if user_id:
            from models import User
            user = User.get_by_id(user_id)
            if user:
                track_user_activity(user_id, user.username, f'Анализ: {city}')
        
        # Запускаем анализ
        process_city(city, is_recheck=False)
        
        return {
            'status': 'completed',
            'city': city,
            'user_id': user_id
        }
        
    except Exception as exc:
        # Retry logic
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def cleanup_online_users():
    """Очистка устаревших записей онлайн пользователей"""
    try:
        from server import get_online_users
        online = get_online_users()
        print(f"[CELERY] Online users: {len(online)}")
        return len(online)
    except Exception as e:
        print(f"[CELERY] Error cleaning up: {e}")
        return 0


@celery_app.task
def sync_with_main_site():
    """Синхронизация с главным сайтом"""
    try:
        from main_site_integration import sync_all_users_periodically
        print("[CELERY] Syncing with main site...")
        # Запускаем однократную синхронизацию
        # (полная синхронизация уже работает в отдельном потоке)
        return {'status': 'synced'}
    except Exception as e:
        print(f"[CELERY] Error syncing: {e}")
        return {'status': 'error', 'message': str(e)}


@celery_app.task
def cleanup_temp_files():
    """Очистка временных файлов"""
    try:
        import os
        from pathlib import Path
        
        temp_dirs = [
            Path('screenshots'),
            Path('uploads'),
        ]
        
        cleaned = 0
        for temp_dir in temp_dirs:
            if temp_dir.exists():
                for file in temp_dir.iterdir():
                    if file.is_file():
                        # Удаляем файлы старше 7 дней
                        import time
                        if time.time() - file.stat().st_mtime > 7 * 24 * 60 * 60:
                            file.unlink()
                            cleaned += 1
        
        print(f"[CELERY] Cleaned {cleaned} temp files")
        return {'cleaned': cleaned}
    except Exception as e:
        print(f"[CELERY] Error cleaning temp files: {e}")
        return {'status': 'error', 'message': str(e)}


@celery_app.task
def analyze_screenshot_task(self, url: str, user_id: int = None):
    """Фоновая задача анализа скриншота"""
    try:
        from server import take_screenshots, analyze_site, track_user_activity
        
        # Делаем скриншот
        screenshots = take_screenshots([url])
        b64, status = screenshots.get(url, (None, 'error'))
        
        if not b64:
            return {'status': 'error', 'reason': status}
        
        # Анализируем
        result = analyze_site(url, 'Крупный', 'Другое', b64, 1, 1)
        
        # Отслеживаем пользователя
        if user_id:
            from models import User
            user = User.get_by_id(user_id)
            if user:
                track_user_activity(user_id, user.username, f'Анализ скриншота: {url}')
        
        return {
            'status': 'completed',
            'url': url,
            'design_score': result.get('design_score', 5),
            'ux_score': result.get('ux_score', 5)
        }
        
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
