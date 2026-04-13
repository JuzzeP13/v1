"""Admin routes and admin APIs."""

from modules.main.python.core import *
from modules.profile.python import activity

import psutil
import os
import shutil
import subprocess
import threading
from modules.auth.python.models import User, get_db

_git_update_lock = threading.Lock()
_git_install_lock = threading.Lock()
GITHUB_UPDATE_REPO_URL = os.environ.get("GITHUB_UPDATE_REPO_URL", "https://github.com/JuzzeP13/v1").strip()
GITHUB_UPDATE_REPO_URL = GITHUB_UPDATE_REPO_URL or "https://github.com/JuzzeP13/v1"
AUTO_INSTALL_GIT = os.environ.get("AUTO_INSTALL_GIT", "true").strip().lower() in {"1", "true", "yes", "on"}


def _discover_git_path() -> str:
    """Find git executable path in PATH or common install locations."""
    candidates = [shutil.which("git")]
    if os.name == "nt":
        candidates.extend([
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
        ])

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _run_install_command(command, timeout=600):
    """Run one installer command and capture output."""
    return subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _auto_install_git_if_needed():
    """
    Try to install git automatically when it is missing.
    Returns (installed_or_available, message).
    """
    existing = _discover_git_path()
    if existing:
        return True, f"Git найден: {existing}"

    if not AUTO_INSTALL_GIT:
        return False, "Git не найден и автоустановка отключена (AUTO_INSTALL_GIT=false)."

    if os.name != "nt":
        return False, "Автоустановка git поддерживается только на Windows."

    with _git_install_lock:
        # Repeat check: another request may have installed git while we waited for the lock.
        existing_after_lock = _discover_git_path()
        if existing_after_lock:
            return True, f"Git найден: {existing_after_lock}"

        install_attempts = []

        winget_path = shutil.which("winget")
        if winget_path:
            winget_cmd = [
                winget_path, "install", "--id", "Git.Git", "--exact",
                "--source", "winget", "--silent",
                "--accept-package-agreements", "--accept-source-agreements"
            ]
            try:
                result = _run_install_command(winget_cmd, timeout=900)
                install_attempts.append(("winget", result.returncode, result.stdout, result.stderr))
            except subprocess.TimeoutExpired:
                install_attempts.append(("winget", -1, "", "Timeout during winget install"))
            except Exception as exc:
                install_attempts.append(("winget", -1, "", str(exc)))

        choco_path = shutil.which("choco")
        if choco_path and not _discover_git_path():
            choco_cmd = [choco_path, "install", "git", "-y", "--no-progress"]
            try:
                result = _run_install_command(choco_cmd, timeout=900)
                install_attempts.append(("choco", result.returncode, result.stdout, result.stderr))
            except subprocess.TimeoutExpired:
                install_attempts.append(("choco", -1, "", "Timeout during choco install"))
            except Exception as exc:
                install_attempts.append(("choco", -1, "", str(exc)))

        installed_path = _discover_git_path()
        if installed_path:
            return True, f"Git успешно установлен/найден: {installed_path}"

        if not install_attempts:
            return False, (
                "Git не найден. Автоустановка недоступна: не найден ни winget, ни choco."
            )

        chunks = []
        for tool_name, code, out, err in install_attempts:
            out_short = (out or "").strip()[-600:]
            err_short = (err or "").strip()[-600:]
            joined = f"{tool_name} rc={code}"
            if out_short:
                joined += f"\n{out_short}"
            if err_short:
                joined += f"\n{err_short}"
            chunks.append(joined)

        return False, "Автоустановка git не удалась.\n" + "\n\n".join(chunks)


def _run_git_command(args, timeout=30, ensure_git=False):
    """Run git command in project root and return CompletedProcess."""
    git_executable = _discover_git_path()
    if not git_executable and ensure_git:
        ok, _ = _auto_install_git_if_needed()
        if ok:
            git_executable = _discover_git_path()

    if not git_executable:
        raise FileNotFoundError("git_not_installed")

    return subprocess.run(
        [git_executable, *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _join_git_output(result: subprocess.CompletedProcess) -> str:
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout and stderr:
        joined = f"{stdout}\n{stderr}"
    else:
        joined = stdout or stderr
    return joined[-4000:]


def _resolve_remote_branch(local_branch: str) -> str:
    """Resolve which branch should be used on remote update source."""
    candidates = []
    if local_branch:
        candidates.append(local_branch)
    for fallback in ("main", "master"):
        if fallback not in candidates:
            candidates.append(fallback)

    for branch in candidates:
        probe = _run_git_command(["ls-remote", "--heads", GITHUB_UPDATE_REPO_URL, branch], timeout=40)
        if probe.returncode == 0 and (probe.stdout or "").strip():
            return branch
    return ""


def _collect_git_status(fetch_remote: bool = False, ensure_git: bool = False) -> dict:
    """Collect local/remote git status for admin auto-update UI."""
    detected_git = _discover_git_path()
    install_message = ""
    if ensure_git and not detected_git:
        ok, install_message = _auto_install_git_if_needed()
        if ok:
            detected_git = _discover_git_path()

    status = {
        "repo_path": str(PROJECT_ROOT),
        "repo_url": GITHUB_UPDATE_REPO_URL,
        "git_installed": bool(detected_git),
        "git_path": detected_git,
        "git_auto_install": bool(ensure_git),
        "git_auto_install_message": install_message,
        "is_git_repo": (PROJECT_ROOT / ".git").exists(),
        "ready": False,
        "checked_remote": False,
        "branch": "",
        "target_branch": "",
        "local_commit": "",
        "remote_commit": "",
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "message": "",
    }

    if not status["git_installed"]:
        if install_message:
            status["message"] = install_message
        else:
            status["message"] = "Git не найден в PATH. Установите Git."
        return status

    if not status["is_git_repo"]:
        status["message"] = "Текущая папка не является git-репозиторием."
        return status

    try:
        branch_result = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        if branch_result.returncode != 0:
            status["message"] = _join_git_output(branch_result) or "Не удалось определить текущую ветку."
            return status
        status["branch"] = (branch_result.stdout or "").strip()

        local_result = _run_git_command(["rev-parse", "HEAD"])
        if local_result.returncode == 0:
            status["local_commit"] = (local_result.stdout or "").strip()

        dirty_result = _run_git_command(["status", "--porcelain"])
        if dirty_result.returncode == 0:
            status["dirty"] = bool((dirty_result.stdout or "").strip())

        status["target_branch"] = status["branch"]
        status["ready"] = True

        if fetch_remote:
            remote_branch = _resolve_remote_branch(status["branch"])
            if not remote_branch:
                status["ready"] = False
                status["message"] = (
                    f"Не удалось найти ветку {status['branch']} / main / master "
                    f"в {GITHUB_UPDATE_REPO_URL}."
                )
                return status

            status["target_branch"] = remote_branch
            fetch_result = _run_git_command(
                ["fetch", "--prune", GITHUB_UPDATE_REPO_URL, remote_branch],
                timeout=120,
            )
            if fetch_result.returncode != 0:
                status["ready"] = False
                status["message"] = _join_git_output(fetch_result) or "Не удалось выполнить git fetch."
                return status

            status["checked_remote"] = True

            remote_result = _run_git_command(["rev-parse", "FETCH_HEAD"])
            if remote_result.returncode == 0:
                status["remote_commit"] = (remote_result.stdout or "").strip()

            diff_result = _run_git_command(["rev-list", "--left-right", "--count", "HEAD...FETCH_HEAD"])
            if diff_result.returncode == 0:
                parts = (diff_result.stdout or "").strip().split()
                if len(parts) >= 2:
                    status["ahead"] = int(parts[0])
                    status["behind"] = int(parts[1])

        if status["dirty"]:
            status["message"] = "Есть локальные изменения (working tree dirty)."
        elif not status["checked_remote"]:
            status["message"] = "Локальный статус готов. Нажмите «Проверить обновления» для GitHub."
        elif status["behind"] > 0:
            status["message"] = f"Доступно обновление: {status['behind']} коммит(ов)."
        elif status["ahead"] > 0:
            status["message"] = "Локальная ветка опережает GitHub."
        else:
            status["message"] = "Локальная версия актуальна."

    except subprocess.TimeoutExpired:
        status["ready"] = False
        status["message"] = "Операция git превысила лимит времени."
    except FileNotFoundError:
        status["ready"] = False
        status["message"] = "Git не найден в PATH. Установите Git."
    except Exception as exc:
        status["ready"] = False
        status["message"] = f"Ошибка git: {exc}"

    return status


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


@app.route("/admin/api/github-update/status")
def admin_github_update_status():
    """Проверить статус обновлений из GitHub."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'unauthorized'}), 401

    refresh = (request.args.get("refresh") or "").lower() in {"1", "true", "yes"}
    status_data = _collect_git_status(fetch_remote=refresh, ensure_git=refresh)
    ok = status_data.get("ready", False)

    if ok:
        return jsonify({"success": True, "status": status_data})
    return jsonify({"success": False, "status": status_data}), 503


@app.route("/admin/api/github-update", methods=["POST"])
def admin_github_update():
    """Выполнить автообновление проекта через git pull --ff-only."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'unauthorized'}), 401

    if not _git_update_lock.acquire(blocking=False):
        return jsonify({
            "success": False,
            "error": "update_in_progress",
            "message": "Обновление уже выполняется. Попробуйте позже."
        }), 409

    try:
        before = _collect_git_status(fetch_remote=True, ensure_git=True)
        if not before.get("ready"):
            return jsonify({
                "success": False,
                "error": "git_status_failed",
                "message": before.get("message", "Не удалось получить статус git."),
                "status": before,
            }), 503

        if before.get("dirty"):
            return jsonify({
                "success": False,
                "error": "dirty_worktree",
                "message": "Обновление заблокировано: есть локальные изменения. Сделайте commit/stash.",
                "status": before,
            }), 409

        if not before.get("checked_remote"):
            return jsonify({
                "success": False,
                "error": "remote_check_failed",
                "message": "Не удалось проверить удалённый GitHub-репозиторий.",
                "status": before,
            }), 503

        if int(before.get("behind") or 0) <= 0:
            return jsonify({
                "success": True,
                "updated": False,
                "message": "Обновлений не найдено. У вас уже актуальная версия.",
                "status": before,
            })

        merge_result = _run_git_command(["merge", "--ff-only", "FETCH_HEAD"], timeout=180)
        merge_output = _join_git_output(merge_result)

        if merge_result.returncode != 0:
            failed_status = _collect_git_status(fetch_remote=False, ensure_git=False)
            return jsonify({
                "success": False,
                "error": "git_merge_failed",
                "message": "Не удалось применить обновление (git merge --ff-only FETCH_HEAD).",
                "pull_output": merge_output,
                "status": failed_status,
            }), 500

        after = _collect_git_status(fetch_remote=True, ensure_git=False)
        updated = before.get("local_commit") != after.get("local_commit")
        message = "Обновление успешно применено." if updated else "Команда выполнена, но коммит не изменился."

        return jsonify({
            "success": True,
            "updated": updated,
            "restart_required": bool(updated),
            "message": message,
            "pull_output": merge_output,
            "status": after,
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "timeout",
            "message": "Операция обновления превысила лимит времени."
        }), 504
    except Exception as exc:
        return jsonify({
            "success": False,
            "error": "unexpected_error",
            "message": f"Неожиданная ошибка обновления: {exc}"
        }), 500
    finally:
        _git_update_lock.release()
