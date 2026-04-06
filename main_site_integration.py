"""
TISH SEARCH - Интеграция с главным сайтом (tishteam.space)
Проверка подписки и получение данных пользователя через API главного сайта
"""

import requests
import time
from functools import wraps
from datetime import datetime
from flask import request, session, redirect, url_for, flash, jsonify
from config import Config

# Настройки главного сайта
MAIN_SITE_URL = Config.MAIN_SITE_URL
MAIN_SITE_API_URL = Config.MAIN_SITE_API_URL

# Кеш для проверки токенов (в памяти)
# В продакшене использовать Redis
_token_cache = {}


def verify_user_with_main_site(api_token):
    """
    Проверяет токен пользователя через API главного сайта
    
    Args:
        api_token: API токен пользователя с главного сайта
    
    Returns:
        dict с данными пользователя или None
        {
            'id': 123,
            'username': 'user123',
            'email': 'user@example.com',
            'subscription_plan': 'pro',  # basic/pro/enterprise
            'priority': 2,  # 1=low, 2=normal, 3=high, 4=vip
            'subscription_expires': '2026-12-31T23:59:59',
            'is_active': True,
            'limits': {
                'max_cities_per_day': 10,
                'max_sites_per_city': 100,
                'max_parallel': 5,
            }
        }
    """
    global _token_cache
    
    # Проверяем кеш (валиден 5 минут)
    if api_token in _token_cache:
        cached = _token_cache[api_token]
        if time.time() - cached['timestamp'] < 300:  # 5 минут
            return cached['data']
        else:
            del _token_cache[api_token]
    
    try:
        # Запрос к API главного сайта
        response = requests.get(
            f"{MAIN_SITE_API_URL}/user/verify",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            user_data = response.json()
            
            # Кешируем результат
            _token_cache[api_token] = {
                'data': user_data,
                'timestamp': time.time()
            }
            
            return user_data
        else:
            print(f"[MAIN SITE] Ошибка верификации: {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        print("[MAIN SITE] Таймаут запроса к главному сайту")
        return None
    except requests.exceptions.ConnectionError:
        print("[MAIN SITE] Не удалось подключиться к главному сайту")
        return None
    except Exception as e:
        print(f"[MAIN SITE] Ошибка: {e}")
        return None


def sync_user_to_local_db(main_site_user_data):
    """
    Синхронизирует данные пользователя с локальной БД
    
    Args:
        main_site_user_data: данные пользователя с главного сайта
    
    Returns:
        User объект локальной БД
    """
    from models import User, get_db
    from werkzeug.security import generate_password_hash
    import secrets
    from datetime import datetime
    
    user_id = main_site_user_data['id']
    username = main_site_user_data.get('username', f"user_{user_id}")
    email = main_site_user_data.get('email', f"user_{user_id}@tishteam.space")
    subscription_plan = main_site_user_data.get('subscription_plan', 'basic')
    subscription_expires = main_site_user_data.get('subscription_expires')
    priority = main_site_user_data.get('priority', 2)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем, существует ли пользователь
    existing = cursor.execute(
        "SELECT id FROM users WHERE main_site_id = ?",
        (user_id,)
    ).fetchone()
    
    if existing:
        # Обновляем данные
        cursor.execute("""
            UPDATE users 
            SET subscription_plan = ?, 
                subscription_expires = ?,
                priority = ?,
                last_sync = ?,
                is_active = 1
            WHERE main_site_id = ?
        """, (subscription_plan, subscription_expires, priority, 
              datetime.now().isoformat(), user_id))
        conn.commit()
        
        user = User.get_by_main_site_id(user_id)
    else:
        # Создаём нового пользователя
        # Генерируем случайный пароль (пользователь входит через главный сайт)
        random_password = generate_password_hash(
            secrets.token_urlsafe(32), 
            method='pbkdf2:sha256', 
            salt_length=16
        )
        
        cursor.execute("""
            INSERT INTO users (
                username, email, password_hash, main_site_id, 
                subscription_plan, subscription_expires, priority,
                is_active, is_verified, theme, language,
                created_at, last_sync
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, 'dark', 'ru', ?, ?)
        """, (username, email, random_password, user_id,
              subscription_plan, subscription_expires, priority,
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
        
        user = User.get_by_main_site_id(user_id)
    
    conn.close()
    return user


def login_from_main_site(api_token):
    """
    Вход пользователя через токен главного сайта
    
    Args:
        api_token: API токен с главного сайта
    
    Returns:
        User объект или None
    """
    # 1. Проверяем токен через главный сайт
    main_site_user = verify_user_with_main_site(api_token)
    
    if not main_site_user:
        print("[AUTH] Неверный токен главного сайта")
        return None
    
    # 2. Синхронизируем с локальной БД
    local_user = sync_user_to_local_db(main_site_user)
    
    # 3. Авторизуем в локальной системе
    if local_user:
        from auth import login_user
        login_user(local_user, remember=True)
        print(f"[AUTH] Успешный вход через главный сайт: {local_user.username} (ID: {local_user.main_site_id})")
        return local_user
    
    return None


def require_main_site_auth(f):
    """
    Декоратор для проверки авторизации через главный сайт
    
    Проверяет:
    1. Токен в cookie/session
    2. Синхронизацию с главным сайтом
    3. Активность подписки
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Проверяем локальную сессию
        if 'user_id' in session:
            from models import User
            user = User.get_by_id(session['user_id'])
            
            if user and user.main_site_id:
                # Проверяем актуальность данных (раз в 10 минут)
                if not hasattr(user, 'last_sync') or not user.last_sync:
                    needs_refresh = True
                else:
                    try:
                        last_sync = datetime.fromisoformat(user.last_sync)
                        needs_refresh = (datetime.now() - last_sync).total_seconds() > 600
                    except:
                        needs_refresh = True
                
                # Обновляем данные с главного сайта если нужно
                if needs_refresh and user.main_site_api_token:
                    fresh_data = verify_user_with_main_site(user.main_site_api_token)
                    if fresh_data:
                        sync_user_to_local_db(fresh_data)
                    else:
                        # Токен невалиден - редирект на главный сайт
                        if request.is_json:
                            from flask import jsonify
                            return jsonify({'error': 'token_expired', 'redirect_to_main': True}), 401
                        flash('Сессия истекла. Войдите через главный сайт.', 'warning')
                        return redirect(f"{MAIN_SITE_URL}/auth/login?redirect={request.url}")
                
                return f(*args, **kwargs)
        
        # Проверяем токен в запросе (для API)
        api_token = request.headers.get('X-Main-Site-Token') or \
                    request.args.get('token') or \
                    request.cookies.get('main_site_token')
        
        if api_token:
            user = login_from_main_site(api_token)
            if user:
                return f(*args, **kwargs)
        
        # Нет авторизации - редирект на главный сайт
        if request.is_json:
            from flask import jsonify
            return jsonify({
                'error': 'not_authenticated',
                'redirect_to_main': True,
                'main_site_url': f"{MAIN_SITE_URL}/auth/login?redirect={request.url}"
            }), 401
        
        return redirect(f"{MAIN_SITE_URL}/auth/login?redirect={request.url}")
    
    return decorated_function


def get_user_priority(user_id):
    """
    Получает приоритетность пользователя
    
    Returns:
        int: 1=low, 2=normal, 3=high, 4=vip
    """
    from models import User
    user = User.get_by_id(user_id)
    
    if not user:
        return 1
    
    # Приоритет на основе подписки
    priority_map = {
        'basic': 1,
        'pro': 2,
        'enterprise': 3
    }
    
    # Если есть явный приоритет с главного сайта
    if hasattr(user, 'priority') and user.priority:
        return user.priority
    
    return priority_map.get(user.subscription_plan, 1)


def should_prioritize_queue(user_id):
    """
    Определяет, должен ли пользователь получить приоритет в очереди
    
    Returns:
        bool: True если пользователь приоритетный
    """
    priority = get_user_priority(user_id)
    return priority >= 3  # high или vip


# Фоновая задача для периодической синхронизации
def sync_all_users_periodically():
    """
    Периодически синхронизирует всех активных пользователей с главным сайтом
    Запускать в отдельном потоке каждые 10 минут
    """
    import threading
    from models import User, get_db
    from datetime import datetime
    
    def sync_loop():
        while True:
            try:
                conn = get_db()
                users = conn.execute(
                    "SELECT * FROM users WHERE main_site_id IS NOT NULL AND is_active = 1"
                ).fetchall()
                conn.close()
                
                for user_row in users:
                    user = User(user_row)
                    if user.main_site_api_token:
                        fresh_data = verify_user_with_main_site(user.main_site_api_token)
                        if fresh_data:
                            sync_user_to_local_db(fresh_data)
                            print(f"[SYNC] Синхронизирован: {user.username}")
                        else:
                            print(f"[SYNC] Ошибка синхронизации: {user.username}")
                
                # Ждём 10 минут
                time.sleep(600)
                
            except Exception as e:
                print(f"[SYNC] Ошибка в цикле синхронизации: {e}")
                time.sleep(60)  # Ждём минуту при ошибке
    
    thread = threading.Thread(target=sync_loop, daemon=True)
    thread.start()
    print("[SYNC] Запущена фоновая синхронизация с главным сайтом")
