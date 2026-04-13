"""
TISH SEARCH - Authentication & User Management Module
Регистрация, вход, восстановление пароля, профиль пользователя
"""

import secrets
import sqlite3
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from modules.auth.python.models import User, get_db, init_extended_db
from modules.auth.python.security import (
    validate_email, validate_username, validate_password,
    sanitize_input, generate_csrf_token, validate_csrf_token,
    suspicious_detector, log_security_event, rate_limiter
)
from modules.common.python.config import Config

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# ─── Helpers ───

def login_user(user, remember=False):
    """Вход пользователя"""
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['theme'] = user.theme
    session['language'] = user.language
    session['_csrf_token'] = generate_csrf_token()
    
    if remember:
        session.permanent = True
    
    # Обновляем last_login
    conn = get_db()
    conn.execute("UPDATE users SET last_login = ? WHERE id = ?", 
                 (datetime.now().isoformat(), user.id))
    conn.commit()
    conn.close()
    
    user.log_activity('login', request.remote_addr, request.user_agent.string[:200])

def logout_user():
    """Выход пользователя"""
    user_id = session.get('user_id')
    if user_id:
        user = User.get_by_id(user_id)
        if user:
            user.log_activity('logout', request.remote_addr)
    session.clear()

def login_required(f):
    """Декоратор для защиты маршрутов"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'login_required'}), 401
            flash('Пожалуйста, войдите для продолжения', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Получить текущего пользователя"""
    user_id = session.get('user_id')
    if user_id:
        return User.get_by_id(user_id)
    return None

def require_current_user():
    """Получить текущего пользователя или аварийно завершить запрос"""
    user = get_current_user()
    if not user:
        session.clear()
        if request.is_json:
            return None, (jsonify({'error': 'login_required'}), 401)
        flash('Сессия истекла, войдите снова', 'warning')
        return None, redirect(url_for('auth.login'))
    return user, None

# ─── Routes ───

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя"""
    if request.method == 'GET':
        return render_template('auth/register.html')
    
    # Rate limiting (увеличено для 20+ пользователей)
    ip = request.remote_addr
    if not rate_limiter.is_allowed(f"register_{ip}", 10, 3600):  # 10 регистраций в час (было 5)
        log_security_event('rate_limit_register', ip)
        return jsonify({'error': 'too_many_attempts'}), 429
    
    data = request.get_json() if request.is_json else request.form
    
    username = sanitize_input(data.get('username', '').strip())
    email = sanitize_input(data.get('email', '').strip().lower())
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    
    # Валидация
    errors = []
    
    if not validate_username(username):
        errors.append('Неверное имя пользователя (3-30 символов, только латиница, цифры, _ и -)')
    
    if not validate_email(email):
        errors.append('Неверный email адрес')
    
    if password != confirm_password:
        errors.append('Пароли не совпадают')
    
    valid, msg = validate_password(password)
    if not valid:
        errors.append(msg)
    
    # Проверка на существующих пользователей
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username = ? OR email = ?", 
                           (username, email)).fetchone()
    if existing:
        errors.append('Пользователь с таким именем или email уже существует')
    
    if errors:
        if request.is_json:
            return jsonify({'errors': errors}), 400
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('auth.register'))
    
    # Создаём пользователя
    user = User.create(username, email, password)
    if user:
        login_user(user)
        log_security_event('user_registered', ip, {'user_id': user.id})
        
        if request.is_json:
            return jsonify({'success': True, 'user': user.to_dict()})
        flash('Регистрация успешна!', 'success')
        return redirect(url_for('dashboard'))
    else:
        if request.is_json:
            return jsonify({'errors': ['Ошибка при регистрации']}), 500
        flash('Ошибка при регистрации', 'error')
        return redirect(url_for('auth.register'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Вход пользователя"""
    if request.method == 'GET':
        return render_template('auth/login.html')
    
    ip = request.remote_addr
    
    # Проверка на блокировку после множественных неудачных попыток
    if suspicious_detector.is_rate_limited(ip, 5):
        log_security_event('login_blocked', ip)
        if request.is_json:
            return jsonify({'error': 'account_locked', 'message': 'Слишком много попыток входа'}), 429
        flash('Слишком много неудачных попыток. Попробуйте позже.', 'error')
        return redirect(url_for('auth.login'))
    
    data = request.get_json() if request.is_json else request.form
    login_field = sanitize_input(data.get('login', '').strip())  # username или email
    password = data.get('password', '')
    remember = data.get('remember', False)
    
    # Находим пользователя
    user = None
    if '@' in login_field:
        user = User.get_by_email(login_field)
    else:
        user = User.get_by_username(login_field)
    
    if user and user.check_password(password):
        # Сбрасываем счётчик неудачных попыток
        conn = get_db()
        conn.execute("UPDATE users SET failed_login_attempts = 0 WHERE id = ?", (user.id,))
        conn.commit()
        conn.close()
        
        login_user(user, remember)
        log_security_event('login_success', ip, {'user_id': user.id})
        
        if request.is_json:
            return jsonify({'success': True, 'user': user.to_dict()})
        flash('С возвращением!', 'success')
        return redirect(url_for('dashboard'))
    else:
        # Записываем неудачную попытку
        attempts = suspicious_detector.record_failed_login(ip)
        log_security_event('login_failed', ip, {'login': login_field, 'attempts': attempts})
        
        if request.is_json:
            return jsonify({'error': 'invalid_credentials'}), 401
        flash('Неверные учётные данные', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    """Выход пользователя"""
    logout_user()
    if request.is_json:
        return jsonify({'success': True})
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Запрос на восстановление пароля"""
    if request.method == 'GET':
        return render_template('auth/forgot_password.html')
    
    email = sanitize_input(request.form.get('email', '').strip().lower())
    
    if not validate_email(email):
        flash('Неверный email адрес', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    user = User.get_by_email(email)
    if user:
        # Генерируем токен
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
        
        conn = get_db()
        conn.execute("""
            INSERT INTO password_resets (user_id, token, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (user.id, token, datetime.now().isoformat(), expires_at))
        conn.commit()
        conn.close()
        
        # В реальном приложении здесь была бы отправка email
        # Для демонстрации показываем ссылку
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        flash(f'Ссылка для сброса: {reset_url}', 'info')
        flash('В реальном приложении ссылка была бы отправлена на ваш email', 'info')
    else:
        # Не показываем, существует ли пользователь (безопасность)
        flash('Если email зарегистрирован, вы получите инструкцию по сбросу пароля', 'info')
    
    return redirect(url_for('auth.forgot_password'))

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Сброс пароля по токену"""
    conn = get_db()
    
    reset = conn.execute("""
        SELECT r.*, u.email FROM password_resets r
        JOIN users u ON r.user_id = u.id
        WHERE r.token = ? AND r.used = 0 AND r.expires_at > ?
    """, (token, datetime.now().isoformat())).fetchone()
    
    if not reset:
        flash('Ссылка для сброса недействительна или истекла', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'GET':
        return render_template('auth/reset_password.html', token=token)
    
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    valid, msg = validate_password(password)
    if not valid:
        flash(msg, 'error')
        return redirect(url_for('auth.reset_password', token=token))
    
    if password != confirm_password:
        flash('Пароли не совпадают', 'error')
        return redirect(url_for('auth.reset_password', token=token))
    
    # Обновляем пароль
    password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, reset['user_id']))
    conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset['id'],))
    conn.commit()
    conn.close()
    
    flash('Пароль успешно изменён', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Страница профиля"""
    user, error_response = require_current_user()
    if error_response:
        return error_response
    
    if request.method == 'GET':
        return render_template('profile/profile.html', user=user)
    
    # Обновление профиля
    data = request.get_json() if request.is_json else request.form
    
    theme = data.get('theme', user.theme)
    language = data.get('language', user.language)
    
    user.update_profile(theme=theme, language=language)
    session['theme'] = theme
    session['language'] = language
    
    if request.is_json:
        return jsonify({'success': True, 'user': user.to_dict()})
    flash('Профиль обновлён', 'success')
    return redirect(url_for('auth.profile'))

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Смена пароля"""
    user, error_response = require_current_user()
    if error_response:
        return error_response
    data = request.get_json() if request.is_json else request.form
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not user.check_password(current_password):
        if request.is_json:
            return jsonify({'error': 'invalid_current_password'}), 400
        flash('Текущий пароль неверен', 'error')
        return redirect(url_for('auth.profile'))
    
    valid, msg = validate_password(new_password)
    if not valid:
        if request.is_json:
            return jsonify({'error': msg}), 400
        flash(msg, 'error')
        return redirect(url_for('auth.profile'))
    
    # Обновляем пароль
    password_hash = generate_password_hash(new_password, method='pbkdf2:sha256', salt_length=16)
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user.id))
    conn.commit()
    conn.close()
    
    user.log_activity('password_changed', request.remote_addr)
    
    if request.is_json:
        return jsonify({'success': True})
    flash('Пароль изменён', 'success')
    return redirect(url_for('auth.profile'))

@auth_bp.route('/api/me')
@login_required
def api_current_user():
    """API: получить текущего пользователя"""
    user, error_response = require_current_user()
    if error_response:
        return error_response
    return jsonify(user.to_dict())

@auth_bp.route('/api/me/subscription')
@login_required
def api_subscription_info():
    """API: получить информацию о подписке"""
    user, error_response = require_current_user()
    if error_response:
        return error_response

    limits = user.get_subscription_limits()
    usage = user.get_usage_today()
    is_active = user.has_active_subscription()

    return jsonify({
        'plan': limits['name'],
        'plan_ru': limits['name_ru'],
        'is_active': is_active,
        'expires': user.subscription_expires,
        'limits': {
            'max_cities_per_day': limits['max_cities_per_day'],
            'max_sites_per_city': limits['max_sites_per_city'],
            'max_parallel': limits['max_parallel'],
            'can_export': limits['can_export'],
            'can_api': limits['can_api'],
        },
        'usage': usage,
        'remaining': {
            'cities_today': max(0, limits['max_cities_per_day'] - usage['cities_today']) if limits['max_cities_per_day'] > 0 else -1,
        }
    })

@auth_bp.route('/api/regenerate-api-key', methods=['POST'])
@login_required
def regenerate_api_key():
    """API: сгенерировать новый API ключ"""
    user, error_response = require_current_user()
    if error_response:
        return error_response
    api_key = secrets.token_urlsafe(32)

    conn = get_db()
    conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (api_key, user.id))
    conn.commit()
    conn.close()

    user.log_activity('api_key_regenerated', request.remote_addr)

    return jsonify({'api_key': api_key})

@auth_bp.route('/login-from-main-site', methods=['POST'])
def login_from_main_site():
    """Вход через токен главного сайта"""
    data = request.get_json()
    api_token = data.get('api_token') or data.get('token')
    
    if not api_token:
        return jsonify({'error': 'no_token'}), 400
    
    # Импортируем интеграцию
    try:
        from modules.integration.python.main_site_integration import login_from_main_site
        user = login_from_main_site(api_token)
        
        if user:
            return jsonify({
                'success': True,
                'user': user.to_dict(),
                'redirect': '/dashboard'
            })
        else:
            return jsonify({'error': 'invalid_token'}), 401
    except ImportError:
        return jsonify({'error': 'integration_not_configured'}), 500
    except Exception as e:
        return jsonify({'error': 'login_failed', 'message': str(e)}), 500

@auth_bp.route('/verify-token', methods=['POST'])
def verify_token_from_main_site():
    """Проверить токен главного сайта (без входа)"""
    data = request.get_json()
    api_token = data.get('api_token') or data.get('token')
    
    if not api_token:
        return jsonify({'error': 'no_token'}), 400
    
    try:
        from modules.integration.python.main_site_integration import verify_user_with_main_site
        user_data = verify_user_with_main_site(api_token)
        
        if user_data:
            return jsonify({
                'valid': True,
                'user': user_data
            })
        else:
            return jsonify({'valid': False, 'error': 'invalid_token'}), 401
    except Exception as e:
        return jsonify({'error': 'verification_failed', 'message': str(e)}), 500

# ─── Init ───

# Админ-аккаунт — пропуск без регистрации
ADMIN_USERNAME = 'TISH_TEAM_SEARCH'
ADMIN_EMAIL = 'admin@tishteam.space'
ADMIN_PASSWORD = '0192837456_TICH_TEAM_SEARCH'

def create_admin_account():
    """Создаёт или обновит админ-аккаунт для входа без регистрации"""
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()

    if existing:
        # Обновим пароль на всякий случай
        password_hash = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256', salt_length=16)
        conn.execute("UPDATE users SET password_hash = ?, is_active = 1, subscription_plan = 'enterprise' WHERE id = ?",
                     (password_hash, existing['id']))
        conn.commit()
        conn.close()
        print(f"[AUTH] ✅ Админ-аккаунт '{ADMIN_USERNAME}' обновлён")
    else:
        password_hash = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256', salt_length=16)
        now = datetime.now().isoformat()
        conn.execute("""
            INSERT INTO users (username, email, password_hash, is_active, is_verified, theme, language,
                               subscription_plan, subscription_expires, created_at, last_login)
            VALUES (?, ?, ?, 1, 1, 'dark', 'ru', 'enterprise', '2099-12-31T23:59:59', ?, ?)
        """, (ADMIN_USERNAME, ADMIN_EMAIL, password_hash, now, now))
        conn.commit()
        conn.close()
        print(f"[AUTH] ✅ Админ-аккаунт '{ADMIN_USERNAME}' создан")

def init_auth():
    """Инициализация модуля аутентификации"""
    init_extended_db()
    create_admin_account()
    
    # Запускаем фоновую синхронизацию с главным сайтом
    try:
        from modules.integration.python.main_site_integration import sync_all_users_periodically
        sync_all_users_periodically()
    except Exception as e:
        print(f"[AUTH] Не удалось запустить синхронизацию: {e}")
    
    print("[AUTH] Модуль аутентификации инициализирован ✓")
