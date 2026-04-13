"""Download and API routes."""

from modules.main.python.core import *
from modules.chat.python.product_service import PRODUCTS_EXCEL_PATH
from modules.chat.python.media_service import SOCIAL_EXCEL_PATH, YOUTUBE_EXCEL_PATH
from modules.profile.python import activity
@app.route("/download")
def download():
    """Скачать базу данных сайтов"""
    if EXCEL_PATH.exists():
        return send_file(str(EXCEL_PATH), as_attachment=True, download_name="sites_results.xlsx")
    return "Файл пока пуст", 404

@app.route("/download/products")
def download_products():
    """Скачать базу данных товаров/услуг"""
    if PRODUCTS_EXCEL_PATH.exists():
        return send_file(str(PRODUCTS_EXCEL_PATH), as_attachment=True, download_name="products_results.xlsx")
    return "Файл пока пуст", 404

@app.route("/download/social")
def download_social():
    """Скачать базу данных соцсетей"""
    if SOCIAL_EXCEL_PATH.exists():
        return send_file(str(SOCIAL_EXCEL_PATH), as_attachment=True, download_name="social_results.xlsx")
    return "Файл пока пуст", 404

@app.route("/download/youtube")
def download_youtube():
    """Скачать результаты YouTube трендов"""
    if YOUTUBE_EXCEL_PATH.exists():
        return send_file(str(YOUTUBE_EXCEL_PATH), as_attachment=True, download_name="youtube_trends.xlsx")
    return "Файл пока пуст", 404

@app.route("/api/db")
def api_db():
    return jsonify(db_all())

@app.route("/api/stats")
def api_stats():
    return jsonify(db_stats())

@app.route("/api/db/count")
def api_db_count():
    """Возвращает количество сайтов в БД"""
    with sqlite3.connect(DB_PATH) as con:
        count = con.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    return jsonify({"count": count})

@app.route("/api/translations/<lang>")
def api_translations(lang):
    lang = (lang or "ru").lower()
    if lang not in {"ru", "en"}:
        lang = "ru"
    path = PROJECT_ROOT / "translations" / f"{lang}.json"
    if not path.exists():
        return jsonify({"error": "translation_not_found"}), 404
    try:
        with open(path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/models")
def api_models():
    try:
        r = req.get(f"{settings['ollama_url']}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        model_names = [m["name"] for m in models]
        return jsonify({"models": model_names})
    except Exception as e:
        return jsonify({"models": [], "error": str(e)}), 500

@app.route("/api/examples")
def api_examples():
    return jsonify({
        "good": db_get_examples(True),
        "bad": db_get_examples(False)
    })

@app.route("/api/examples/count")
def api_examples_count():
    with sqlite3.connect(DB_PATH) as con:
        good = con.execute("SELECT COUNT(*) FROM examples WHERE is_good=1").fetchone()[0]
        bad = con.execute("SELECT COUNT(*) FROM examples WHERE is_good=0").fetchone()[0]
    return jsonify({"good": good, "bad": bad})
