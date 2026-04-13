"""Main page routes."""

from modules.main.python.core import *
@app.route("/")
def index():
    """Главная — если авторизован, то dashboard, иначе login"""
    if 'user_id' in session:
        return render_template("main/index.html", current_user=get_current_user())
    return redirect(url_for('auth.login'))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("main/index.html", current_user=get_current_user())

@app.route("/subscription")
@login_required
def subscription():
    """Страница управления подпиской"""
    return render_template("main/subscription.html", current_user=get_current_user())

# ──────────────────────────────────────────────
# ADMIN PANEL
# ──────────────────────────────────────────────
