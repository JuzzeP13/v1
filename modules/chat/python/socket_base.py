"""Socket.IO base handlers and command routing."""

from modules.main.python.core import *
from modules.main.python.analysis import run_queue, recover_stale_analysis_lock
from modules.chat.python.product_service import process_product_search, generate_synonyms
from modules.chat.python.media_service import process_social_search, process_youtube_trends, save_youtube_to_excel
from modules.profile.python import activity
def socket_login_required(f):
    """Декоратор для защиты Socket.IO обработчиков авторизацией"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            emit_status("⚠ Требуется авторизация. Войдите в систему.", "warn")
            return
        return f(*args, **kwargs)
    return decorated_function

def socket_subscription_required(f):
    """Декоратор для проверки активной подписки пользователя"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            emit_status("⚠ Требуется авторизация. Войдите в систему.", "warn")
            return

        from modules.auth.python.models import User
        user = User.get_by_id(session['user_id'])
        if not user:
            emit_status("⚠ Пользователь не найден", "error")
            return

        # АДМИН: Без ограничений!
        if user.main_site_id or user.username == activity.ADMIN_USERNAME:
            # Админ или пользователь с главного сайта - без ограничений
            return f(*args, **kwargs)

        # Проверка подписки
        if not user.has_active_subscription():
            emit_status("❌ Подписка истекла. Продлите для продолжения работы.", "error")
            return

        # Проверка лимитов
        can, msg = user.can_run_analysis()
        if not can:
            emit_status(f"❌ {msg}", "error")
            return

        return f(*args, **kwargs)
    return decorated_function

# ──────────────────────────────────────────────
# SOCKET.IO HANDLERS
# ──────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    activity.ws_connections_count += 1
    
    # Отслеживаем пользователя если авторизован
    if 'user_id' in session:
        activity.track_user_activity(session['user_id'], session.get('username', 'unknown'))
    elif session.get('admin_authenticated'):
        activity.track_user_activity(0, activity.ADMIN_USERNAME, 'Admin Panel')
    
    socketio.emit("state", {
        "phase":       state["phase"],
        "city":        state["city"],
        "found":       len(state["found_urls"]),
        "analyzed":    len(state["results"]),
        "total":       len(state["found_urls"]),
        "current_url": state["current_url"],
        "skipped":     state["skipped"],
        "elapsed":     f"{state['elapsed_sec']//60}м {state['elapsed_sec']%60:02d}с",
        "running":     state["running"],
        "stopped":     state["stop"],
        "queue":       state["queue"],
        "queue_done":  state["queue_done"],
        "db_stats":    db_stats(),
    }, room=request.sid)
    # Отправляем список доступных моделей
    try:
        r = req.get(f"{settings['ollama_url']}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        model_names = [m["name"] for m in models]
        socketio.emit("models_available", {"models": model_names}, room=request.sid)
        print(f"[OK] Отправлены модели клиенту: {model_names}")
    except Exception as e:
        print(f"[ERROR] Не удалось получить модели: {e}")
        socketio.emit("models_available", {"models": []}, room=request.sid)

@socketio.on("disconnect")
def on_disconnect():
    activity.ws_connections_count = max(0, activity.ws_connections_count - 1)

@socketio.on("add_city")
@socket_login_required
def on_add(data):
    city = data.get("city", "").strip()
    if not city:
        return
    if city not in state["queue"] and city not in state["queue_done"]:
        state["queue"].append(city)
        emit_status(f"➕ Добавлен в очередь: «{city}»", "info")
    else:
        emit_status(f"⚠ «{city}» уже в очереди или обработан", "warn")
    emit_state()

@socketio.on("reanalyze_city")
@socket_login_required
@socket_subscription_required
def on_reanalyze(data):
    """Повторный анализ города с возможностью большего кол-ва сайтов"""
    city = data.get("city", "").strip()
    if not city:
        return
    
    # Удаляем из очереди обработанных если там есть
    if city in state["queue_done"]:
        state["queue_done"].remove(city)
    
    # Удаляем из очереди если там есть
    if city in state["queue"]:
        state["queue"].remove(city)
    
    # Добавляем в конец очереди
    state["queue"].append(city)
    emit_status(f"🔄 Переанализ добавлен в очередь: «{city}»", "info")
    emit_state()

@socketio.on("remove_city")
@socket_login_required
def on_remove(data):
    city = data.get("city", "")
    if city in state["queue"]:
        state["queue"].remove(city)
        emit_state()

@socketio.on("start_queue")
@socket_login_required
@socket_subscription_required
def on_start():
    with state_lock:
        recover_stale_analysis_lock()
        if state["running"]:
            emit_status("Уже работает!", "warn"); return
        if not state["queue"]:
            emit_status("Очередь пустая — добавь города!", "warn"); return
        state["queue_done"] = []
        state["running"] = True  # Блокируем сразу
        state["active_sid"] = request.sid
    threading.Thread(
        target=run_queue,
        args=(session.get('user_id'), session.get('username', 'user')),
        daemon=True
    ).start()

@socketio.on("stop_scan")
@socket_login_required
def on_stop():
    if state["running"] and state.get("active_sid") == request.sid:
        state["stop"] = True
        emit_status("⛔ Остановка...", "warn")

# ──────────────────────────────────────────────
# СОЦИАЛЬНЫЕ СЕТИ — обработчики
# ──────────────────────────────────────────────
@socketio.on("start_social_search")
@socket_login_required
@socket_subscription_required
def on_social_search(data):
    recover_stale_analysis_lock()
    """Запуск поиска по соцсетям"""
    if state["running"]:
        emit_status("Уже работает!", "warn"); return
    
    query = data.get("query", "")
    city = data.get("city", "")
    platforms = data.get("platforms", [])
    try:
        max_results_per_platform = int(data.get("max_results", 10) or 10)
    except (TypeError, ValueError):
        max_results_per_platform = 10
    max_results_per_platform = max(1, min(100, max_results_per_platform))
    
    if not query:
        emit_status("❌ Не указан поисковый запрос!", "error"); return
    
    emit_status(f"🔍 Начинаю поиск по соцсетям: «{query}»", "info")
    if city:
        emit_status(f"📍 Город: {city}", "info")
    emit_status(f"📱 Платформы: {', '.join(platforms)}", "info")
    emit_status(f"🎯 Цель: {max_results_per_platform} новых профилей на платформу", "info")
    
    state["running"] = True
    state["stop"] = False
    state["phase"] = "searching"
    state["city"] = f"📱 {query}"
    state["found_urls"] = []
    state["results"] = []
    state["current_url"] = ""
    state["skipped"] = 0
    state["start_time"] = time.time()
    state["elapsed_sec"] = 0
    state["active_sid"] = request.sid
    
    emit_state()
    
    # Запускаем в отдельном потоке
    threading.Thread(
        target=process_social_search,
        args=(query, city, platforms, max_results_per_platform),
        daemon=True
    ).start()

@socketio.on("stop_social_search")
@socket_login_required
def on_stop_social():
    """Остановка поиска по соцсетям"""
    if state["running"] and state.get("active_sid") == request.sid:
        state["stop"] = True
        emit_status("⛔ Остановка поиска по соцсетям...", "warn")

# ──────────────────────────────────────────────
# YOUTUBE TRENDS (TubelQ-style) — обработчики
# ──────────────────────────────────────────────
@socketio.on("start_youtube_trends")
@socket_login_required
@socket_subscription_required
def on_youtube_trends(data):
    recover_stale_analysis_lock()
    """Запуск поиска трендовых YouTube видео"""
    if state["running"]:
        emit_status("Уже работает!", "warn"); return

    query = data.get("query", "")
    max_results = int(data.get("max_results", 50))
    filters = data.get("filters", {})

    if not query:
        emit_status("❌ Не указан поисковый запрос!", "error"); return

    emit_status(f"🎬 Поиск трендов YouTube: «{query}»", "info")
    emit_status(f"📊 Максимум результатов: {max_results}", "info")
    if filters:
        emit_status(f"🔧 Фильтры: {filters}", "info")

    state["running"] = True
    state["stop"] = False
    state["phase"] = "searching"
    state["city"] = f"🎬 YouTube: {query}"
    state["found_urls"] = []
    state["results"] = []
    state["current_url"] = ""
    state["skipped"] = 0
    state["start_time"] = time.time()
    state["elapsed_sec"] = 0
    state["active_sid"] = request.sid

    emit_state()

    threading.Thread(
        target=process_youtube_trends,
        args=(query, max_results, filters, request.sid),
        daemon=True
    ).start()

@socketio.on("stop_youtube_trends")
@socket_login_required
def on_stop_youtube_trends():
    """Остановка поиска YouTube трендов"""
    if state["running"] and state.get("active_sid") == request.sid:
        state["stop"] = True
        emit_status("⛔ Остановка поиска YouTube трендов...", "warn")

@socketio.on("save_youtube_to_excel")
@socket_login_required
def on_save_youtube_excel(data):
    """Сохранить YouTube тренды в Excel"""
    if state.get("active_sid") and state.get("active_sid") != request.sid:
        emit_status("⚠ Сохранение доступно только для владельца текущего анализа", "warn")
        socketio.emit("youtube_excel_error", {
            "error": "forbidden",
            "message": "Сохранение доступно только для владельца текущего анализа",
        }, room=request.sid)
        return

    quality_filter = data.get("quality_filter")  # 'good', 'bad', или None
    
    if not state["results"]:
        emit_status("❌ Нет результатов для сохранения!", "error")
        socketio.emit("youtube_excel_error", {
            "error": "no_results",
            "message": "Нет результатов для сохранения",
        }, room=request.sid)
        return
    
    emit_status(f"💾 Сохраняю {len(state['results'])} видео в Excel...", "info")
    save_result = save_youtube_to_excel(state["results"], thumbnail_quality_filter=quality_filter)

    if save_result.get("ok"):
        socketio.emit("youtube_excel_saved", {
            "saved_count": save_result.get("saved_count", 0),
            "images_added": save_result.get("images_added", 0),
            "quality_filter": quality_filter,
            "download_url": f"/download/youtube?ts={int(time.time())}",
        }, room=request.sid)
    else:
        socketio.emit("youtube_excel_error", {
            "error": save_result.get("error", "save_failed"),
            "message": save_result.get("message", "Не удалось сохранить Excel"),
            "saved_count": save_result.get("saved_count", 0),
            "images_added": save_result.get("images_added", 0),
        }, room=request.sid)

# ──────────────────────────────────────────────
# ТОВАРЫ/УСЛУГИ — обработчики
# ──────────────────────────────────────────────
@socketio.on("start_product_search")
@socket_login_required
@socket_subscription_required
def on_product_search(data):
    recover_stale_analysis_lock()
    """Запуск поиска товаров/услуг"""
    if state["running"]:
        emit_status("Уже работает!", "warn"); return
    
    query = data.get("query", "")
    city = data.get("city", "")
    max_results = int(data.get("max_results", 20))
    
    if not query:
        emit_status("❌ Не указан поисковый запрос!", "error"); return
    
    emit_status(f"🛍️ Начинаю поиск товаров/услуг: «{query}»", "info")
    if city:
        emit_status(f"📍 Регион: {city}", "info")
    emit_status(f"📊 Максимум результатов: {max_results}", "info")
    
    # Синонимы для товаров/услуг
    synonyms = generate_synonyms(query)
    emit_status(f"🔤 Синонимы: {', '.join(synonyms[:5])}...", "info")
    
    state["running"] = True
    state["stop"] = False
    state["phase"] = "searching"
    state["city"] = f"🛍️ {query}"
    state["found_urls"] = []
    state["results"] = []
    state["current_url"] = ""
    state["skipped"] = 0
    state["start_time"] = time.time()
    state["elapsed_sec"] = 0
    state["active_sid"] = request.sid
    
    emit_state()
    
    # Запускаем в отдельном потоке
    threading.Thread(
        target=process_product_search,
        args=(query, city, max_results, synonyms),
        daemon=True
    ).start()

@socketio.on("stop_product_search")
@socket_login_required
def on_stop_product():
    """Остановка поиска товаров/услуг"""
    if state["running"] and state.get("active_sid") == request.sid:
        state["stop"] = True
        emit_status("⛔ Остановка поиска товаров/услуг...", "warn")

