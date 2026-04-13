"""Admin routes and admin APIs."""

from modules.main.python.core import *
from modules.profile.python import activity

import psutil
from modules.auth.python.models import User, get_db
@app.route("/admin")
def admin_panel():
    """Админ-панель с проверкой логина/пароля"""
    # Проверяем авторизацию админа
    if not session.get('admin_authenticated'):
        return render_template("admin/admin_login.html")
    
    # Собираем статистику
    from modules.auth.python.models import User, get_db
    
    # Все пользователи
    conn = get_db()
    all_users = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(DISTINCT city) FROM search_history 
                WHERE user_id = u.id AND date(created_at) = date('now')) as cities_today
        FROM users u 
        ORDER BY u.last_login DESC
    """).fetchall()
    
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db_sites = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    db_cities = conn.execute("SELECT COUNT(DISTINCT city) FROM sites").fetchone()[0]
    conn.close()
    
    # Онлайн пользователи
    online = activity.get_online_users()
    online_users_data = []
    
    for user_id, data in online.items():
        user = User.get_by_id(user_id)
        if user:
            limits = user.get_subscription_limits()
            user_data = dict(user.to_dict())
            user_data['is_online'] = True
            user_data['current_task'] = data.get('task', '')
            user_data['cities_today'] = user.get_usage_today()['cities_today']
            user_data['max_cities'] = limits['max_cities_per_day'] if limits['max_cities_per_day'] > 0 else '∞'
            online_users_data.append(user_data)
    
    # Добавляем оффлайн пользователей
    for user_row in all_users:
        user = User(user_row)
        if user.id not in online:
            user_data = dict(user.to_dict())
            user_data['is_online'] = False
            user_data['current_task'] = None
            limits = user.get_subscription_limits()
            user_data['cities_today'] = user.get_usage_today()['cities_today']
            user_data['max_cities'] = limits['max_cities_per_day'] if limits['max_cities_per_day'] > 0 else '∞'
            online_users_data.append(user_data)
    
    # Системная статистика
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_cores = psutil.cpu_count()
    ram = psutil.virtual_memory()
    ram_used_mb = int(ram.used / 1024 / 1024)
    ram_total_mb = int(ram.total / 1024 / 1024)
    ram_percent = ram.percent
    
    # Размер БД
    import os
    db_path = DB_PATH
    db_size_mb = round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0
    db_size_percent = min(100, db_size_mb * 2)  # Примерно, assuming 50MB max
    
    # Активные задачи
    active_tasks = 1 if state.get('running') else 0
    
    return render_template("admin/admin.html",
                         current_user={'username': activity.ADMIN_USERNAME},
                         online_count=len(online),
                         total_users=total_users,
                         active_tasks=active_tasks,
                         cpu_percent=cpu_percent,
                         cpu_cores=cpu_cores,
                         ram_used=ram_used_mb,
                         ram_total=ram_total_mb,
                         ram_percent=ram_percent,
                         ws_connections=activity.ws_connections_count,
                         ws_percent=min(100, activity.ws_connections_count * 2),
                         db_sites=db_sites,
                         db_cities=db_cities,
                         db_size_mb=db_size_mb,
                         db_size_percent=db_size_percent,
                         online_users=online_users_data,
                         all_users=online_users_data)

@app.route("/admin/login", methods=['GET', 'POST'])
def admin_login():
    """Вход в админ-панель"""
    if request.method == 'GET':
        return render_template("admin/admin_login.html", error=None)
    
    # POST - обработка входа
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    # Если форма пустая пробуем JSON
    if not username:
        json_data = request.get_json(silent=True)
        if json_data:
            username = json_data.get('username', '').strip()
            password = json_data.get('password', '').strip()

    print(f"[ADMIN] Попытка входа: username='{username}', password_len={len(password)}")

    if username == activity.ADMIN_USERNAME and password == activity.ADMIN_PASSWORD:
        session.clear()  # Очищаем старую сессию
        session['admin_authenticated'] = True
        session['admin_user'] = username
        session.permanent = True  # Сессия сохраняется
        activity.track_user_activity(0, activity.ADMIN_USERNAME, 'Admin Panel')
        
        print(f"[ADMIN] ✅ Успешный вход: {username}")
        print(f"[ADMIN] Session ID: {session.sid if hasattr(session, 'sid') else 'N/A'}")

        if request.is_json:
            return jsonify({'success': True, 'redirect': '/admin'})
        return redirect('/admin')
    else:
        print(f"[ADMIN] ❌ Неверный вход: username='{username}'")
        if request.is_json:
            return jsonify({'error': 'invalid_credentials'}), 401
        return render_template("admin/admin_login.html", error="Неверный логин или пароль")

@app.route("/admin/logout")
def admin_logout():
    """Выход из админ-панели"""
    session.pop('admin_authenticated', None)
    session.pop('admin_user', None)
    return redirect('/admin')

@app.route("/admin/api/set-priority", methods=['POST'])
def admin_set_priority():
    """Установить приоритет пользователя"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'unauthorized'}), 401
    
    data = request.get_json()
    user_id = data.get('user_id')
    priority = data.get('priority')
    
    if not user_id or not priority or priority < 1 or priority > 4:
        return jsonify({'error': 'invalid_data'}), 400
    
    conn = get_db()
    conn.execute("UPDATE users SET priority = ? WHERE id = ?", (priority, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route("/admin/api/ban-user", methods=['POST'])
def admin_ban_user():
    """Заблокировать пользователя"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'unauthorized'}), 401
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'invalid_data'}), 400
    
    conn = get_db()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route("/admin/api/stats")
def admin_api_stats():
    """API: получить статистику для админки"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'unauthorized'}), 401
    
    return jsonify({
        'online_count': len(activity.get_online_users()),
        'active_tasks': 1 if state.get('running') else 0,
        'cpu_percent': psutil.cpu_percent(interval=0.1),
        'ram_percent': psutil.virtual_memory().percent,
        'ws_connections': activity.ws_connections_count,
    })
