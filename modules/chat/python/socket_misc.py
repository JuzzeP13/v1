"""Socket.IO misc handlers (settings, recheck, examples, ratings)."""

from modules.main.python.core import *
from modules.main.python.analysis import recheck_db_sites, recover_stale_analysis_lock
from modules.chat.python.socket_base import socket_login_required, socket_subscription_required


@socketio.on("recheck_db")
@socket_login_required
@socket_subscription_required
def on_recheck_db(data):
    recover_stale_analysis_lock()
    """Перепроверка сайтов из БД"""
    if state["running"]:
        emit_status("Уже работает!", "warn")
        return

    limit = int(data.get("limit", 10))
    if limit < 1:
        limit = 10
    if limit > 100:
        limit = 100

    state["running"] = True
    state["stop"] = False
    emit_state()
    threading.Thread(target=recheck_db_sites, args=(limit,), daemon=True).start()


@socketio.on("update_settings")
@socket_login_required
def on_settings(data):
    limits = {
        "max_large": (5, 100),
        "max_niche": (5, 100),
        "max_per_query": (1, 10),
        "parallel": (1, 10),
        "page_timeout": (5000, 60000),
        "vision_timeout_sec": (60, 1200),
        "vision_num_predict": (64, 2000),
        "search_max_passes": (2, 10),
        "screenshot_wait_min_ms": (50, 5000),
        "screenshot_wait_max_ms": (50, 7000),
    }
    for k, (min_v, max_v) in limits.items():
        if k not in data:
            continue
        try:
            value = int(data[k])
            settings[k] = max(min_v, min(max_v, value))
        except Exception:
            pass
    if settings.get("screenshot_wait_max_ms", 0) < settings.get("screenshot_wait_min_ms", 0):
        settings["screenshot_wait_max_ms"] = settings["screenshot_wait_min_ms"]
    if "vision_model" in data:
        settings["vision_model"] = data["vision_model"].strip()
    log_event(
        "settings_updated_from_ui",
        settings={
            "max_large": settings.get("max_large"),
            "max_niche": settings.get("max_niche"),
            "max_per_query": settings.get("max_per_query"),
            "parallel": settings.get("parallel"),
            "page_timeout": settings.get("page_timeout"),
            "vision_timeout_sec": settings.get("vision_timeout_sec"),
            "vision_num_predict": settings.get("vision_num_predict"),
            "search_max_passes": settings.get("search_max_passes"),
            "screenshot_wait_min_ms": settings.get("screenshot_wait_min_ms"),
            "screenshot_wait_max_ms": settings.get("screenshot_wait_max_ms"),
            "vision_model": settings.get("vision_model"),
        },
    )
    emit_status(
        f"⚙ Настройки обновлены: до {settings['max_large'] + settings['max_niche']} сайтов на город",
        "success",
    )
    emit_state()


@socketio.on("clear_queue_done")
@socket_login_required
def on_clear_done():
    state["queue_done"] = []
    emit_state()


@socketio.on("save_example")
@socket_login_required
def on_save_example(data):
    url = data.get("url", "")
    design = data.get("design", "")
    ux = data.get("ux", "")
    is_good = data.get("is_good", True)
    reason = data.get("reason", "")

    try:
        db_save_example(url, design, ux, is_good, reason)
        emoji = "👍" if is_good else "👎"
        emit_status(f"{emoji} Пример сохранён: {get_domain(url)}", "success")
    except Exception as e:
        emit_status(f"❌ Ошибка при сохранении примера: {e}", "error")


@socketio.on("rate_site")
@socket_login_required
def on_rate_site(data):
    domain = data.get("domain", "")
    rating = int(data.get("rating", 0))
    if 1 <= rating <= 5:
        try:
            db_rate_site(domain, rating)
            emit_status(f"⭐ Оценка {rating}/5 для {domain}", "success")
        except Exception as e:
            emit_status(f"❌ Ошибка при оценке: {e}", "error")


@socketio.on("save_scores")
@socket_login_required
def on_save_scores(data):
    """Сохранить оценки дизайна и UX (0-10)."""
    domain = data.get("domain", "")
    design_score = int(data.get("design_score", 0))
    ux_score = int(data.get("ux_score", 0))

    if not domain:
        return

    design_score = max(0, min(10, design_score))
    ux_score = max(0, min(10, ux_score))

    try:
        db_save_scores(domain, design_score, ux_score)
        excel_rebuild()
        emit_status(
            f"⭐ Оценки сохранены: дизайн {design_score}/10, UX {ux_score}/10",
            "success",
        )
    except Exception as e:
        emit_status(f"❌ Ошибка при сохранении оценок: {e}", "error")


@socketio.on("add_manual_example")
@socket_login_required
def on_add_manual_example(data):
    """Добавить пример вручную."""
    url = data.get("url", "").strip()
    design = data.get("design", "").strip()
    ux = data.get("ux", "").strip()
    is_good = data.get("is_good", True)

    if not url or not design or not ux:
        emit_status("❌ Заполни все поля: URL, описание дизайна и UX", "error")
        return

    if not url.startswith("http"):
        url = "https://" + url

    try:
        db_save_example(url, design, ux, is_good, "Вручную добавлено")
        emoji = "👍" if is_good else "👎"
        emit_status(f"{emoji} Пример добавлен: {get_domain(url)}", "success")
        socketio.emit("reload_examples", {})
    except Exception as e:
        emit_status(f"❌ Ошибка при добавлении примера: {e}", "error")
