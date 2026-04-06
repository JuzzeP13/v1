"""
TISH SEARCH v4 — Multi-Agent Site Analyzer
Запуск: python server.py → http://localhost:5000

Новое в v4:
  - Постоянная БД (SQLite) — уже проверенные домены не перепроверяются
  - Очередь городов — добавляй несколько и они обрабатываются по очереди
  - Настройки прямо в интерфейсе (MAX_LARGE, MAX_NICHE, PARALLEL_SHOTS)
  - Исправлены пустые оценки дизайна и UX
  - Один общий Excel-файл который пополняется
  - Аутентификация и профили пользователей
  - Поддержка светлой/тёмной темы
  - Мультиязычность (RU/EN)
  - Поиск по соцсетям (YouTube, Instagram, X)
"""

import asyncio
import base64
import json
import os
import random
import re
import sqlite3
import threading
import time
import requests as req
import openpyxl
from functools import wraps
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from playwright.async_api import async_playwright
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, render_template, send_file, jsonify, session, request, flash, redirect, url_for
from flask_socketio import SocketIO

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# ──────────────────────────────────────────────
# ИМПОРТ НОВЫХ МОДУЛЕЙ
# ──────────────────────────────────────────────
from config import Config
from models import User, get_db, init_extended_db
from auth import auth_bp, login_required, get_current_user, login_user, logout_user, init_auth
from security import security_middleware, add_security_headers, is_likely_bot
from social_search import search_social_media
from i18n import get_i18n, set_language, _

# ──────────────────────────────────────────────
# ПУТИ
# ──────────────────────────────────────────────
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "images").mkdir(exist_ok=True)
DB_PATH     = Path("tish_data.db")
EXCEL_PATH  = REPORTS_DIR / "tish_results.xlsx"   # единый файл

# ──────────────────────────────────────────────
# ДЕФОЛТНЫЕ НАСТРОЙКИ (меняются через UI)
# ──────────────────────────────────────────────
settings = {
    "ollama_url":    "http://localhost:11434",
    "vision_model":  "llava:latest",  # LLaVA быстрее для скриншотов
    "max_large":     30,
    "max_niche":     30,
    "max_per_query": 3,
    "parallel":      5,  # Оптимизировано для 20+ пользователей (было 8)
    "page_timeout":  8000,
}

CAPTCHA_SIGNALS = [
    "checkcaptcha","captcha","robot","blocked","access denied",
    "403 forbidden","cloudflare","just a moment","attention required",
    "verifying you","ddos-guard","checking your browser",
    "please verify", "security check", "are you human",
    "challenge", "reCAPTCHA", "hCaptcha",
    "protection", "denuvo", "suspicious activity",
    "ip banned", "too many requests", "429",
    "rate limit", "temporarily unavailable",
]
# ──────────────────────────────────────────────
# АДАПТИВНАЯ ФИЛЬТРАЦИЯ ПО ГОРОДУ
# ──────────────────────────────────────────────
# Крупные города - можно жесткую фильтрацию
BIG_CITIES = {"москва", "санкт-петербург", "спб", "св", "екатеринбург", "новосибирск", 
              "казань", "краснодар", "омск", "челябинск"}

# Режимы фильтрации
FILTER_MODES = {
    "STRICT": {  # Жесткая - для больших городов
        "search_multiplier": 5,  # Ищем результатов
        "check_spam_keywords": True,
        "check_suspicious_patterns": True,
        "check_domain_quality": True,
    },
    "NORMAL": {  # Обычная - для средних
        "search_multiplier": 10,
        "check_spam_keywords": False,  # Выключаем спам-ключворды
        "check_suspicious_patterns": False,  # Выключаем подозрительные паттерны
        "check_domain_quality": True,
    },
    "LENIENT": {  # Щадящая - для маленьких городов
        "search_multiplier": 20,
        "check_spam_keywords": False,
        "check_suspicious_patterns": False,
        "check_domain_quality": False,  # Берем почти всё
    },
}

def get_filter_mode(city: str) -> str:
    """Определяет режим фильтрации на основе города"""
    city_lower = city.lower().strip()
    
    # Проверяем крупный ли город
    if city_lower in BIG_CITIES or len(city_lower) < 4:
        return "STRICT"
    elif len(city_lower) > 15:
        return "NORMAL"  # Необычно длинное название
    else:
        return "NORMAL"  # По умолчанию нормальный

SKIP_DOMAINS = [
    # Wiki и словари
    "wiktionary.org","kartaslov.ru","wikipedia.org","support.google.com",
    
    # Видео и потоковое
    "youtube.com","rutube.ru","vimeo.com","dailymotion.com",
    
    # Социальные сети
    "vk.com","ok.ru","t.me","telegram.me","instagram.com",
    "facebook.com","twitter.com","x.com","tiktok.com","snapchat.com",
    
    # Облачные сервисы
    "digitalocean.ru","2gis.ru",
    
    # Маркетплейсы и магазины (кроме avito - он для услуг)
    "yandex.ru/maps","google.com/maps","zoom.earth",
    "amazon.com","ebay.com","aliexpress.com","ozon.ru","wildberries.ru",
    
    # Карты и навигация
    "yandex.ru/maps","google.com/maps","waze.com","tripadvisor.ru",
    
    # Агрегаторы отзывов
    "otzovik.com","2gis.ru","zoon.ru","flamp.ru","yell.ru",
    "market.yandex.ru","yandex.ru/internet",
    
    # Развлечение и досуг
    "kino.ru","kinopoisk.ru","imdb.com","letterboxd.com",
    "rotten tomatoes.com","metacritic.com",
    
    # Спортивные результаты
    "sports.ru","sport1.com","flashscore.com","espn.com",
    
    # Новостные агрегаторы
    "livejournal.com","blogger.com","wordpress.com","medium.com",
    
    # Форумы и обсуждения
    "forum","forums.","discuss","reddit.com","quora.com",
    "stack overflow.com","habr.com",
    
    # Блог-платформы
    "blogspot.com","tumblr.com","substack.com","patreon.com",
    
    # Тестирование и dev-сервисы
    "github.com","gitlab.com","bitbucket.org","npm.js.org",
    "pypi.org","crates.io","rubygems.org",
    
    # CDN и хостинг
    "cloudflare.com","akamai.com","fastly.com","cdn",
    
    # Платежные системы (опасные)
    "paypal.com","stripe.com","2checkout.com",
    
    # Казино и ставки (явные)
    "casino","betting","poker","slots","jackpot","forex",
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.from_object(Config)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", ping_timeout=60, ping_interval=25, max_http_buffer_size=10*1024*1024)

# ─────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ МНОГОЯЗЫЧНОСТИ
# ─────────────────────────────────────
i18n = get_i18n()
set_language('ru')  # Язык по умолчанию

# Добавляем функцию перевода в контекст шаблонов
@app.context_processor
def inject_i18n():
    return {
        '_': _,
        'set_language': set_language,
        'get_i18n': get_i18n,
        'current_language': i18n.get_language(),
        'available_languages': i18n.available_languages(),
        'config': Config
    }

app.register_blueprint(auth_bp)

@app.before_request
def _before_request_security():
    security_middleware()
    # Обработка переключения языка
    lang = request.args.get('lang')
    if lang:
        set_language(lang)
        session['language'] = lang

@app.after_request
def _after_request_security(response):
    return add_security_headers(response)

# ──────────────────────────────────────────────
# СОСТОЯНИЕ
# ──────────────────────────────────────────────
state = {
    "running":     False,
    "stop":        False,
    "city":        "",
    "phase":       "idle",
    "found_urls":  [],
    "results":     [],
    "current_url": "",
    "skipped":     0,
    "elapsed_sec": 0,
    "start_time":  None,
    "report_file": str(EXCEL_PATH),
    # очередь городов
    "queue":       [],   # список строк
    "queue_done":  [],   # уже обработанные
}

# Блокировка для предотвращения одновременного запуска задач
# Для 20+ пользователей
state_lock = threading.Lock()


# ──────────────────────────────────────────────
# SQLite — постоянное хранилище проверенных доменов
# ──────────────────────────────────────────────
def db_init():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                domain   TEXT PRIMARY KEY,
                url      TEXT,
                city     TEXT,
                type     TEXT,
                category TEXT,
                design   TEXT,
                ux       TEXT,
                design_score INTEGER DEFAULT 0,
                ux_score INTEGER DEFAULT 0,
                checked_at TEXT,
                rating   INTEGER DEFAULT 0,
                needs_redesign BOOLEAN DEFAULT 1
            )
        """)
        
        # Миграция: добавляем недостающие колонки если нужно
        cursor = con.execute("PRAGMA table_info(sites)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if "design_score" not in columns:
            print("[MIGRATION] Добавляю колонку design_score...")
            con.execute("ALTER TABLE sites ADD COLUMN design_score INTEGER DEFAULT 0")
        
        if "ux_score" not in columns:
            print("[MIGRATION] Добавляю колонку ux_score...")
            con.execute("ALTER TABLE sites ADD COLUMN ux_score INTEGER DEFAULT 0")
        
        if "rating" not in columns:
            print("[MIGRATION] Добавляю колонку rating...")
            con.execute("ALTER TABLE sites ADD COLUMN rating INTEGER DEFAULT 0")
        
        if "category" not in columns:
            print("[MIGRATION] Добавляю колонку category...")
            con.execute("ALTER TABLE sites ADD COLUMN category TEXT DEFAULT 'Другое'")
        
        if "needs_redesign" not in columns:
            print("[MIGRATION] Добавляю колонку needs_redesign...")
            con.execute("ALTER TABLE sites ADD COLUMN needs_redesign BOOLEAN DEFAULT 1")
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS examples (
                id       INTEGER PRIMARY KEY,
                url      TEXT,
                design   TEXT,
                ux       TEXT,
                is_good  BOOLEAN,
                reason   TEXT,
                added_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS product_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                query TEXT,
                city TEXT,
                category TEXT,
                found_at TEXT,
                analyzed_at TEXT,
                UNIQUE(url, query, city)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS social_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT,
                description TEXT,
                username TEXT,
                city TEXT,
                query TEXT,
                found_at TEXT,
                analyzed_at TEXT,
                design_score INTEGER,
                ux_score INTEGER,
                design_text TEXT,
                ux_text TEXT,
                UNIQUE(url, platform)
            )
        """)
        con.commit()
        print("[DB] Инициализация завершена ✓")

def check_ollama_models():
    """Проверяет доступные модели в Ollama"""
    try:
        r = req.get(f"{settings['ollama_url']}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        model_names = [m["name"] for m in models]
        print(f"[DEBUG] Доступные модели в Ollama: {model_names}")
        
        if settings["vision_model"] not in model_names:
            print(f"[WARNING] Модель '{settings['vision_model']}' НЕ найдена!")
            print(f"[INFO] Доступные модели: {', '.join(model_names)}")
            return False
        else:
            print(f"[OK] Модель '{settings['vision_model']}' найдена ✓")
            return True
    except Exception as e:
        print(f"[ERROR] Не удалось проверить модели: {e}")
        return False

def db_has_domain(domain: str) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        r = con.execute("SELECT 1 FROM sites WHERE domain=?", (domain,)).fetchone()
        return r is not None

def db_save(city: str, results: list):
    """Сохраняет ТОЛЬКО сайты с плохим дизайном/UX (нуждающиеся в переделке)"""
    now = datetime.now().isoformat()
    print(f"[DEBUG db_save] Попытка сохранить {len(results)} результатов для города '{city}'")
    saved_count = 0
    skipped_count = 0
    
    with sqlite3.connect(DB_PATH) as con:
        for r in results:
            if r["design"].startswith("Пропущено"):
                print(f"[DEBUG db_save] Пропущен: {r['url']} (design начинается с 'Пропущено')")
                skipped_count += 1
                continue
            
            design_score = r.get("design_score", 5)
            ux_score = r.get("ux_score", 5)
            
            # КЛЮЧЕВОЙ ФИЛЬТР: сохраняем только сайты с плохим дизайном ИЛИ UX
            # Нас интересуют сайты для переделки!
            needs_redesign = design_score <= 5 or ux_score <= 5
            
            if not needs_redesign:
                print(f"[DEBUG db_save] ⏭ Пропущен (хороший дизайн): {get_domain(r['url'])} "
                      f"[Дизайн: {design_score}/10, UX: {ux_score}/10]")
                skipped_count += 1
                continue
            
            try:
                category = r.get("category", "Другое")
                domain = get_domain(r["url"])
                
                con.execute("""
                    INSERT OR REPLACE INTO sites
                    (domain, url, city, type, category, design, ux, design_score, ux_score, checked_at, needs_redesign)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (domain, r["url"], city, r["type"], category, r["design"], r["ux"], 
                      design_score, ux_score, now, 1))
                
                saved_count += 1
                emoji = "🔴" if design_score <= 3 or ux_score <= 3 else "🟠"  # критичные vs обычные плохие
                print(f"[DEBUG db_save] {emoji} Сохранён: {domain} "
                      f"[Дизайн: {design_score}/10, UX: {ux_score}/10] - НУЖНА ПЕРЕДЕЛКА!")
            except Exception as e:
                print(f"[DEBUG db_save] ✗ ОШИБКА при сохранении {r['url']}: {e}")
        
        con.commit()
    
    print(f"[DEBUG db_save] Итого для города '{city}': "
          f"сохранено {saved_count} (нуждаются в переделке) | "
          f"пропущено {skipped_count} (уже хороший дизайн)")

def db_all() -> list:
    with sqlite3.connect(DB_PATH) as con:
        # Сортируем так, чтобы сайты с плохим дизайном (нуждающиеся в переделке) были в начале
        rows = con.execute("""
            SELECT url,city,type,category,design,ux,checked_at,design_score,ux_score,needs_redesign 
            FROM sites 
            ORDER BY needs_redesign DESC, design_score ASC, ux_score ASC, checked_at DESC
        """).fetchall()
    return [{"url":r[0],"city":r[1],"type":r[2],"category":r[3],"design":r[4],"ux":r[5],"checked_at":r[6],
             "design_score":r[7],"ux_score":r[8],"needs_redesign":bool(r[9])} for r in rows]

def db_stats():
    with sqlite3.connect(DB_PATH) as con:
        total  = con.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        cities = con.execute("SELECT COUNT(DISTINCT city) FROM sites").fetchone()[0]
        needs_redesign = con.execute("SELECT COUNT(*) FROM sites WHERE needs_redesign=1").fetchone()[0]
        critical = con.execute("SELECT COUNT(*) FROM sites WHERE (design_score <= 3 OR ux_score <= 3)").fetchone()[0]
    return {
        "total": total, 
        "cities": cities,
        "needs_redesign": needs_redesign,  # Сайты с плохим дизайном/UX
        "critical": critical  # Сайты с критичным дизайном/UX (дизайн или UX <= 3)
    }

def db_save_scores(domain: str, design_score: int, ux_score: int):
    """Сохранить оценки дизайна и UX (0-10)"""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE sites SET design_score=?, ux_score=? WHERE domain=?",
            (design_score, ux_score, domain)
        )
        con.commit()

def db_get_examples(is_good: bool) -> list:
    """Получить примеры хороших (True) или плохих (False) дизайнов"""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT url, design, ux FROM examples WHERE is_good=? ORDER BY added_at DESC LIMIT 3",
            (is_good,)
        ).fetchall()
    return [{"url": r[0], "design": r[1], "ux": r[2]} for r in rows]

def db_save_example(url: str, design: str, ux: str, is_good: bool, reason: str = ""):
    """Сохранить результат как пример"""
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO examples (url, design, ux, is_good, reason, added_at) VALUES (?,?,?,?,?,?)",
            (url, design, ux, is_good, reason, now)
        )
        con.commit()

def db_rate_site(domain: str, rating: int):
    """Оценить сайт (1-5 звёзд)"""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE sites SET rating=? WHERE domain=?", (rating, domain))
        con.commit()


# ──────────────────────────────────────────────
# EXCEL — единый файл, пополняется
# ──────────────────────────────────────────────
def excel_rebuild():
    """Пересобирает Excel из всей БД. Сортирует сайты по критичности переделки."""
    rows = db_all()
    if not rows:
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TISH SEARCH — для переделки"

    hf = PatternFill("solid", fgColor="1E1E2E")
    critical_fill = PatternFill("solid", fgColor="FFE0E0")  # Красный для критичных
    bad_fill = PatternFill("solid", fgColor="FFF0E0")  # Оранжевый для плохих
    good_fill = PatternFill("solid", fgColor="E0F0FF")  # Голубой для хороших
    hfont  = Font(bold=True, color="FFFFFF", size=11)
    ufont  = Font(color="0563C1", underline="single", bold=True)
    thin   = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap   = Alignment(wrap_text=True, vertical="top")

    headers = ["#", "КРИТИЧНОСТЬ", "URL", "Город", "Тип", "Категория", "Дизайн (0-10)", "UX (0-10)", "Оценка дизайна", "Оценка UX", "Дата"]
    widths  = [4, 14, 42, 12, 10, 16, 10, 10, 40, 40, 12]

    ws.append([""] * 11)
    ws.merge_cells("A1:K1")
    tc = ws.cell(row=1, column=1)
    tc.value = f"🔴 TISH SEARCH — Сайты для переделки  |  {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    tc.font = Font(bold=True, size=13, color="FFFFFF")
    tc.alignment = Alignment(horizontal="center", vertical="center")
    tc.fill = PatternFill("solid", fgColor="CC0000")
    ws.row_dimensions[1].height = 32

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=2, column=col, value=h)
        c.font = hfont; c.fill = hf; c.border = border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[2].height = 28

    for i, r in enumerate(rows, 1):
        row  = i + 2
        design_score = r.get("design_score", 5)
        ux_score = r.get("ux_score", 5)
        needs_redesign = r.get("needs_redesign", False)
        
        # Определяем цвет строки по критичности
        if design_score <= 3 or ux_score <= 3:
            fill = critical_fill
            criticality = "🔴 КРИТИЧНАЯ"
        elif needs_redesign:
            fill = bad_fill
            criticality = "🟠 ПЛОХАЯ"
        else:
            fill = good_fill
            criticality = "✅ ОК"
        
        ws.cell(row=row, column=1, value=i).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=row, column=2, value=criticality).alignment = Alignment(horizontal="center", vertical="top")
        uc = ws.cell(row=row, column=3, value=r["url"])
        uc.font = ufont; uc.alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(row=row, column=4, value=r["city"]).alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(row=row, column=5, value=r["type"]).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=row, column=6, value=r.get("category", "Другое")).alignment = Alignment(horizontal="center", vertical="top")
        
        # Оценки числовые
        ws.cell(row=row, column=7, value=design_score if design_score > 0 else "—").alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=row, column=8, value=ux_score if ux_score > 0 else "—").alignment = Alignment(horizontal="center", vertical="top")
        
        # Описания оценок
        ws.cell(row=row, column=9, value=r["design"]).alignment = wrap
        ws.cell(row=row, column=10, value=r["ux"]).alignment = wrap
        ws.cell(row=row, column=11, value=r["checked_at"][:10] if r["checked_at"] else "").alignment = Alignment(vertical="top")
        
        for col in range(1, 12):
            c = ws.cell(row=row, column=col)
            c.border = border; c.fill = fill
        ws.row_dimensions[row].height = 80

    wb.save(str(EXCEL_PATH))


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def get_domain(url: str) -> str:
    try:
        h = urlparse(url).hostname or ""
        return h.removeprefix("www.")
    except:
        return url

def is_spam_content(title: str = "", description: str = "") -> bool:
    """Проверяет заголовок и описание на явные признаки спама"""
    content = (title + " " + description).lower()
    
    # Только явные признаки спама/фарма
    obvious_spam_keywords = [
        "casino", "betting", "poker", "jackpot",
        "viagra", "cialis", "pharmacy",
        "click here now", "limited offer now",
        "scam", "phishing",
        "xxx", "adult",
    ]
    
    return any(keyword in content for keyword in obvious_spam_keywords)

def is_junk_url(url: str) -> bool:
    u = url.lower()
    # ТОЛЬКО явно мусорные паттерны (социалки, маркетплейсы, облако)
    absolute_junk = SKIP_DOMAINS + [
        # Только самые очевидные социальки и видео
        "instagram.com", "tiktok.com", "facebook.com", "twitter.com",
        "x.com", "linkedin.com", "youtube", "rutube",
        
        # Только очевидные маркетплейсы
        "amazon", "ebay", "aliexpress", "ozon", "wildberries",
        
        # Только явно облачные платформы
        "blogger.com", "wordpress.com", "wix.com",
    ]
    return any(s in u for s in absolute_junk)

def is_quality_domain(url: str) -> bool:
    """Проверяет очень мягко - только очевидный мусор"""
    u = url.lower()
    domain = get_domain(url)
    
    # ТОЛЬКО очень очевидный мусор отклоняем
    obvious_bad = [
        len(domain) < 3,  # Слишком короткий
        len(domain) > 150,  # Слишком длинный  
        domain.startswith("10."),  # IP адреса
        domain.count(".") > 5,  # Слишком много точек (мусорные поддомены)
    ]
    
    return not any(obvious_bad)

def is_professional_domain(url: str) -> bool:
    """МАКСИМАЛЬНО мягкая проверка - принимаем почти всё"""
    u = url.lower()
    domain = get_domain(url)
    
    # Только ЯВНЫЕ спам-домены отклоняем
    obvious_spam = [
        "casino" in u,
        "poker" in u,
    ]
    
    # Все остальное принимаем
    return not any(obvious_spam)

def has_suspicious_url_pattern(url: str) -> bool:
    """Проверяет URL на явно подозрительные паттерны (очень щадящая)"""
    u = url.lower()
    
    # Только самые явные красные флаги
    obvious_suspicious = [
        # Явные редиректы и шортены
        "bit.ly", "tinyurl", "short.link", "rebrand.ly",
        "bit.do", "ow.ly", "goo.gl", "shortened.link",
        
        # Очень длинные URL с параметрами (явный мусор)
        (len(url) > 250 and "?" in url),  # Очень длинный URL с параметрами
    ]
    
    for pattern in obvious_suspicious:
        if isinstance(pattern, bool):
            if pattern:
                return True
        elif isinstance(pattern, str) and pattern in u:
            return True
    
    return False

def is_captcha_page(title: str, cur_url: str) -> bool:
    return any(s in (title + cur_url).lower() for s in CAPTCHA_SIGNALS)


# ──────────────────────────────────────────────
# EMIT
# ──────────────────────────────────────────────
def emit_status(msg, level="info"):
    socketio.emit("status", {"msg": msg, "level": level})

def emit_state():
    s = state["elapsed_sec"]
    socketio.emit("state", {
        "phase":       state["phase"],
        "city":        state["city"],
        "found":       len(state["found_urls"]),
        "analyzed":    len(state["results"]),
        "total":       len(state["found_urls"]),
        "current_url": state["current_url"],
        "skipped":     state["skipped"],
        "elapsed":     f"{s//60}м {s%60:02d}с",
        "running":     state["running"],
        "stopped":     state["stop"],
        "queue":       state["queue"],
        "queue_done":  state["queue_done"],
        "db_stats":    db_stats(),
    })


# ──────────────────────────────────────────────
# ТАЙМЕР
# ──────────────────────────────────────────────
def _timer():
    while True:
        time.sleep(1)
        if state["running"] and state["start_time"]:
            state["elapsed_sec"] = int(time.time() - state["start_time"])
            s = state["elapsed_sec"]
            socketio.emit("tick", {"elapsed": f"{s//60}м {s%60:02d}с"})

threading.Thread(target=_timer, daemon=True).start()


# ──────────────────────────────────────────────
# OLLAMA — ИСПРАВЛЕННЫЙ vision
# ──────────────────────────────────────────────
def call_vision(prompt: str, image_b64: str) -> str:
    payload = {
        "model": settings["vision_model"],
        "messages": [{
            "role":    "user",
            "content": prompt,
            "images":  [image_b64]
        }],
        "stream": False,
        "options": {
            "temperature": 0.3,  # немного повышен для более критичной оценки
            "num_predict": 800,  # увеличено с 600 для полного анализа
            "top_k": 40,
            "top_p": 0.9,
        }
    }
    try:
        emit_status(f"  🤖 Анализирую с {settings['vision_model']}...", "info")
        
        r = req.post(
            f"{settings['ollama_url']}/api/chat",
            json=payload, timeout=180
        )
        r.raise_for_status()
        
        resp = r.json()
        print(f"[DEBUG] API ответ: {resp}")  # Логирование для отладки
        
        if "message" in resp:
            msg = resp["message"]
            # Сначала ищем обычный контент
            content = msg.get("content", "").strip()
            
            # Если контент пуст, проверяем поле "thinking" (для qwen3-vl)
            if not content and "thinking" in msg:
                content = msg.get("thinking", "").strip()
            
            if content:
                print(f"[DEBUG] Получен ответ: {content[:200]}")
                return content
        
        print(f"[DEBUG] Неожиданный формат ответа: {resp}")
        emit_status(f"⚠ Модель ответила пустым ответом", "warn")
        return "Нет ответа от модели"
        
    except req.exceptions.Timeout:
        msg = f"Timeout: модель долго обрабатывает. Проверь модель {settings['vision_model']}"
        print(f"[DEBUG] {msg}")
        emit_status(msg, "error")
        return msg
    except req.exceptions.ConnectionError as e:
        msg = f"Нет соединения с Ollama по адресу {settings['ollama_url']}"
        print(f"[DEBUG] {msg}: {e}")
        emit_status(msg, "error")
        return msg
    except Exception as e:
        msg = f"Ошибка анализа: {str(e)[:100]}"
        print(f"[DEBUG] {msg}")
        emit_status(msg, "error")
        return msg


# ──────────────────────────────────────────────
# ПЕРЕПРОВЕРКА БД
# ──────────────────────────────────────────────
def get_db_sites_for_recheck(limit: int = 10) -> list:
    """Получает сайты из БД для перепроверки"""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT domain, url, city, category, type FROM sites ORDER BY RANDOM() LIMIT ?",
            (limit,)
        ).fetchall()
    return [{"domain": r[0], "url": r[1], "city": r[2], "category": r[3], "type": r[4]} for r in rows]

def recheck_db_sites(limit: int = 10):
    """Перепроверяет сайты из БД с переанализом"""
    # Блокировка чтобы SQLite не блокировался
    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен!", "warn")
        state["running"] = False
        return
    
    try:
        state.update({
            "phase":       "rechecking",
            "city":        f"🔄 Перепроверка ({limit} сайтов)",
            "found_urls":  [],
            "results":     [],
            "current_url": "",
            "skipped":     0,
            "running":     True,
            "stop":        False,
            "start_time":  time.time(),
        "elapsed_sec": 0,
    })
    
    emit_status(f"🔄 Получаю {limit} случайных сайтов из БД для перепроверки...", "info")
    db_sites = get_db_sites_for_recheck(limit)
    
    if not db_sites:
        emit_status(f"❌ В БД нет сайтов для перепроверки", "error")
        state["running"] = False
        state["phase"] = "idle"
        emit_state()
        return
    
    emit_status(f"🔄 Перепроверка {len(db_sites)} сайтов из БД...", "info")
    emit_state()
    
    # 1. Скриншоты
    state["phase"] = "rechecking_screenshots"
    emit_status(f"📸 Делаю скриншоты {len(db_sites)} сайтов...", "info")
    emit_state()
    shots = take_screenshots([s["url"] for s in db_sites])
    ok = sum(1 for b, _ in shots.values() if b)
    skip = len(db_sites) - ok
    state["skipped"] += skip
    emit_status(f"✅ Скриншоты: {ok} ОК | {skip} пропущено", "success")
    
    if state["stop"]:
        state["running"] = False
        state["phase"] = "idle"
        emit_state()
        return
    
    # 2. AI-анализ
    state["phase"] = "rechecking_analysis"
    emit_status(f"🤖 Переанализ {len(db_sites)} сайтов...", "info")
    emit_state()
    recheck_results = []
    
    for idx, site in enumerate(db_sites, 1):
        if state["stop"]:
            break
        
        url = site["url"]
        state["current_url"] = url
        emit_state()
        
        b64, status = shots.get(url, (None, "not_found"))
        if b64:
            result = analyze_site(url, site["type"], site["category"], b64, idx, len(db_sites))
            design_score = result.get("design_score", 5)
            ux_score = result.get("ux_score", 5)
            needs_redesign = design_score <= 5 or ux_score <= 5  # Сайт нуждается в переделке?
            
            recheck_results.append({
                "domain": site["domain"],
                "url": url,
                "city": site["city"],
                "category": site["category"],
                "type": site["type"],
                "design": result["design"],
                "ux": result["ux"],
                "design_score": design_score,
                "ux_score": ux_score,
                "needs_redesign": needs_redesign
            })
        else:
            reason = "капча" if status == "captcha" else "недоступен"
            emit_status(f"[{idx}/{len(db_sites)}] ⏭ {get_domain(url)} — {reason}", "warn")
            state["skipped"] += 1
        
        emit_state()
    
    # 3. Обновление в БД
    if recheck_results:
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as con:
            for r in recheck_results:
                con.execute("""
                    UPDATE sites 
                    SET design=?, ux=?, design_score=?, ux_score=?, needs_redesign=?, checked_at=?
                    WHERE domain=?
                """, (r["design"], r["ux"], r["design_score"], r["ux_score"], 
                      r["needs_redesign"], now, r["domain"]))
            con.commit()
        
        excel_rebuild()
        emit_status(f"✅ Переанализировано и обновлено: {len(recheck_results)} сайтов", "success")
    
    state.update({
        "running": False,
        "phase": "done",
        "city": "",
        "current_url": "",
    })
    
    s = state["elapsed_sec"]
    emit_status(
        f"✅ Перепроверка завершена за {s//60}м {s%60:02d}с | "
        f"Переанализировано: {len(recheck_results)} | Пропущено: {state['skipped']}",
        "success"
    )
    emit_state()
    finally:
        analysis_lock.release()


# ──────────────────────────────────────────────
# ПОИСК
# ──────────────────────────────────────────────
def search_urls(queries_with_categories: list, city: str, label: str, exclude_domains: set = None, skip_db_check: bool = False, force_mode: str = None) -> list:
    """
    Поиск с адаптивной фильтрацией в зависимости от города
    queries_with_categories: список кортежей (query, category) или просто список строк запросов
    city: название города (используется для определения режима фильтрации)
    skip_db_check: если True, не пропускает домены которые уже в БД (для переанализа)
    force_mode: если указан, переопределяет автоматический выбор режима (STRICT/NORMAL/LENIENT)
    Возвращает список словарей {"url": url, "category": category}
    """
    found        = []
    seen_domains = set(exclude_domains or [])
    seen_urls    = set()
    mpq = settings["max_per_query"]
    
    # ОПРЕДЕЛЯЕМ РЕЖИМ ФИЛЬТРАЦИИ ДЛЯ ЭТОГО ГОРОДА
    filter_mode = force_mode or get_filter_mode(city)
    mode_config = FILTER_MODES[filter_mode]
    search_mult = mode_config["search_multiplier"]
    check_spam = mode_config["check_spam_keywords"]
    check_suspicious = mode_config["check_suspicious_patterns"]
    check_quality = mode_config["check_domain_quality"]
    
    emit_status(f"🔍 Режим фильтрации для {city}: {filter_mode} (ищем x{search_mult} результатов)", "info")
    
    # Нормализуем входные данные
    normalized_queries = []
    for item in queries_with_categories:
        if isinstance(item, tuple):
            query, category = item
            normalized_queries.append((query, category))
        else:
            # Если просто строка запроса
            normalized_queries.append((item, "Другое"))
    
    def search_one_query(q: str, category: str):
        """Поиск одного запроса с адаптивной фильтрацией"""
        local_found = []
        
        try:
            with DDGS() as ddgs:
                # Ищем согласно режиму
                results = list(ddgs.text(q, max_results=mpq * search_mult))
                count = 0
                checked = 0
                
                for r in results:
                    url = r.get("href", "")
                    if not url.startswith("http"):
                        continue
                    
                    # Жесткая проверка на очевидный мусор (всегда)
                    if is_junk_url(url):
                        continue
                    
                    # Проверка на качество домена (зависит от режима)
                    if check_quality and not is_quality_domain(url):
                        continue
                    
                    # Проверка на профессиональность
                    if not is_professional_domain(url):
                        continue
                    
                    # Проверка на подозрительные паттерны (зависит от режима)
                    if check_suspicious and has_suspicious_url_pattern(url):
                        continue
                    
                    # Проверка на спам-контент (зависит от режима)
                    if check_spam:
                        title = r.get("title", "")
                        body = r.get("body", "")
                        if is_spam_content(title, body):
                            continue
                    
                    # Проверка на дубликаты
                    if url in seen_urls:
                        continue
                    
                    domain = get_domain(url)
                    if domain in seen_domains:
                        continue
                    
                    # Пропускаем уже проверенные домены из БД (кроме переанализа)
                    if not skip_db_check and db_has_domain(domain):
                        continue
                    
                    seen_urls.add(url)
                    seen_domains.add(domain)
                    local_found.append({"url": url, "category": category})
                    count += 1
                    checked += 1
                    if count >= mpq:
                        break
                
                # Логирование поиска
                if count > 0:
                    emit_status(f"[{label}] «{q}» → {count} URL ({category}) | режим {filter_mode}")
                elif len(results) > 0:
                    emit_status(f"[{label}] «{q}» → 0 URL (отфильтровано все {len(results)} результатов)", "warn")
        
        except Exception as e:
            err_str = str(e).lower()
            if "no results" in err_str or "request" in err_str:
                pass
            else:
                emit_status(f"[{label}] ⚠ Ошибка «{q}»: {str(e)[:50]}", "warn")
        
        return local_found

    try:
        import concurrent.futures
        # Параллельный поиск до 3 запросов одновременно
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(search_one_query, q, cat): (q, cat) for q, cat in normalized_queries}
            for future in concurrent.futures.as_completed(futures):
                if state["stop"]:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    local_results = future.result(timeout=30)
                    found.extend(local_results)
                    emit_state()
                except Exception as e:
                    print(f"[ERROR] Batch error: {e}")
                
                time.sleep(0.3)
    except Exception as e:
        emit_status(f"[{label}] Параллельный поиск ошибка: {e}", "error")
        # Fallback на последовательный поиск
        for q, cat in normalized_queries:
            if state["stop"]:
                break
            found.extend(search_one_query(q, cat))
            time.sleep(0.5)
    
    return found


def get_large_queries(city):
    """Поиск крупных, официальных сайтов с высоким качеством"""
    return [
        # Муниципальная власть
        (f"администрация {city} ru официальный сайт", "Государство"),
        (f"мэрия {city} официальный веб-сайт", "Государство"),
        (f"правительство {city} область портал", "Государство"),
        (f"город {city} официальный портал", "Государство"),
        
        # Медицина (региональные учреждения)
        (f"министерство здравоохранения {city}", "Медицина"),
        (f"областная больница {city} сайт", "Медицина"),
        (f"университетская клиника {city}", "Медицина"),
        
        # Образование (вузы высокого уровня)
        (f"федеральный университет {city}", "Образование"),
        (f"государственный университет {city} официальный", "Образование"),
        (f"национальный исследовательский университет {city}", "Образование"),
        (f"технический университет {city}", "Образование"),
        
        # Крупный бизнес
        (f"торгово-промышленная палата {city}", "Бизнес"),
        (f"бизнес центр {city} официальный", "Бизнес"),
        (f"промышленный парк {city}", "Бизнес"),
        
        # СМИ
        (f"телевизионный канал {city} официальный", "СМИ"),
        (f"главное управление информации {city}", "СМИ"),
        (f"региональное телевидение {city}", "СМИ"),
        
        # Культура и спорт (крупные)
        (f"областной театр драмы {city}", "Культура"),
        (f"музей изобразительных искусств {city}", "Культура"),
        (f"центральный стадион {city}", "Спорт"),
        (f"ледовый дворец {city} официальный", "Спорт"),
    ]

def get_niche_queries(city):
    """Поиск нишевых, но качественных сайтов компаний и сервисов"""
    return [
        # IT и цифровые услуги
        (f"веб-студия {city} дизайн сайтов", "IT/Digital"),
        (f"it компания {city} разработка", "IT/Digital"),
        (f"digital агентство {city} реклама", "IT/Digital"),
        (f"компания {city} веб-разработка", "IT/Digital"),
        (f"студия веб дизайна {city}", "IT/Digital"),
        (f"seo {city} оптимизация", "IT/Digital"),
        
        # Профессиональные услуги
        (f"юридическая фирма {city} консультация", "Услуги/Консалт"),
        (f"бухгалтерское бюро {city}", "Услуги/Консалт"),
        (f"аудиторская компания {city}", "Услуги/Консалт"),
        (f"архитектурное бюро {city}", "Услуги/Консалт"),
        
        # Бизнес услуги (качественные)
        (f"консалтинг {city} бизнес", "Услуги/Консалт"),
        (f"маркетинговое агентство {city} реклама", "Маркетинг"),
        (f"рекламное агентство {city} дизайн", "Маркетинг"),
        (f"pr агентство {city} официальный", "Маркетинг"),
        
        # Образование (профессиональное)
        (f"учебный центр {city} обучение", "Образование"),
        (f"школа иностранных языков {city}", "Образование"),
        (f"курсы программирования {city}", "Образование"),
        (f"школа мастерства {city}", "Образование"),
        
        # Услуги красоты (премиум)
        (f"премиум салон красоты {city}", "Красота/СПА"),
        (f"spa центр {city} официальный", "Красота/СПА"),
        (f"студия красоты {city}", "Красота/СПА"),
        
        # Общепит
        (f"гостиница {city} официальный сайт", "Гостинично-ресторанный"),
        (f"отель {city} бронирование", "Гостинично-ресторанный"),
        (f"ресторан {city} высокая кухня", "Гостинично-ресторанный"),
        (f"кафе {city} премиум", "Гостинично-ресторанный"),
        (f"барбершоп {city}", "Гостинично-ресторанный"),
        
        # Строительство и недвижимость
        (f"застройщик {city} новостройки", "Недвижимость"),
        (f"строительная компания {city}", "Недвижимость"),
        (f"агентство недвижимости {city}", "Недвижимость"),
        (f"риэлтерская компания {city}", "Недвижимость"),
        
        # Производство/промышленность
        (f"производство {city} компания", "Производство"),
        (f"завод {city} официальный", "Производство"),
        (f"предприятие {city} информация", "Производство"),
    ]


# ──────────────────────────────────────────────
# СКРИНШОТЫ
# ──────────────────────────────────────────────
async def screenshot_one(pw, url: str):
    safe = re.sub(r'[^\w]', '_', url)[:80]
    path = SCREENSHOT_DIR / f"{safe}.png"
    browser = None
    try:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=random.choice(USER_AGENTS),
            locale="ru-RU",
            extra_http_headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            }
        )
        page = await ctx.new_page()
        # Блокируем медиа-контент для ускорения загрузки
        await page.route(
            "**/*.{mp4,webm,ogg,mp3,wav,woff,woff2,ttf,otf,gif}",
            lambda r: r.abort()
        )
        # Сокращённый таймаут и быстрая загрузка
        await page.goto(url, timeout=settings["page_timeout"], wait_until="domcontentloaded")
        # Уменьшена задержка для рендеринга (было 800-1500)
        await page.wait_for_timeout(random.randint(300, 800))
        title = await page.title()
        if is_captcha_page(title, page.url):
            await browser.close()
            return url, None, "captcha"
        await page.screenshot(path=str(path), full_page=False)
        await browser.close()
        with open(path, "rb") as f:
            return url, base64.b64encode(f.read()).decode(), "ok"
    except Exception as e:
        try:
            if browser: await browser.close()
        except: pass
        return url, None, str(e)[:60]

async def _batch_async(urls):
    results = {}
    par = settings["parallel"]
    async with async_playwright() as pw:
        for i in range(0, len(urls), par):
            if state["stop"]:
                break
            batch = urls[i:i+par]
            done  = await asyncio.gather(*[screenshot_one(pw, u) for u in batch])
            for url, b64, status in done:
                results[url] = (b64, status)
                icon = "✅" if b64 else ("⚠" if status == "captcha" else "❌")
                emit_status(f"  {icon} {get_domain(url)}")
    return results

def take_screenshots(urls):
    return asyncio.run(_batch_async(urls))


# ──────────────────────────────────────────────
# ПАРСИНГ ОТВЕТА МОДЕЛИ
# ──────────────────────────────────────────────
def parse_vision_response(raw: str):
    """
    Парсит ответ в формате:
    DESIGN: [оценка 0-10] описание...
    UX: [оценка 0-10] описание...
    Возвращает (design_text, ux_text, design_score, ux_score).
    """
    raw = raw.strip()
    print(f"[DEBUG PARSE] Исходный ответ:\n{raw}\n")

    design_text = ""
    ux_text = ""
    design_score = 5  # дефолт если не парсится
    ux_score = 5

    # Попытка 1 — ищем DESIGN: ... UX: ...
    design_match = re.search(r'DESIGN\s*[:\-]?\s*(.+?)(?=UX\s*[:\-]|$)', raw, re.DOTALL | re.IGNORECASE)
    ux_match = re.search(r'UX\s*[:\-]?\s*(.+?)$', raw, re.DOTALL | re.IGNORECASE)
    
    if design_match:
        design_text = design_match.group(1).strip()
    if ux_match:
        ux_text = ux_match.group(1).strip()

    # Парсим численные оценки (формат "3/10" или "3 из 10")
    def extract_score(text):
        """Вытаскивает оценку из текста вида '3/10' или '3 из 10'"""
        match = re.search(r'(\d+)\s*(?:/|из)\s*10', text)
        if match:
            score = int(match.group(1))
            return min(10, max(0, score))  # клеим 0-10
        return None

    # Парсим оценки
    design_score_parsed = extract_score(design_text)
    ux_score_parsed = extract_score(ux_text)
    
    if design_score_parsed is not None:
        design_score = design_score_parsed
    if ux_score_parsed is not None:
        ux_score = ux_score_parsed

    # Удаляем оценку из текста
    design_text = re.sub(r'^\d+\s*(?:/|из)\s*10\s*', '', design_text).strip()
    ux_text = re.sub(r'^\d+\s*(?:/|из)\s*10\s*', '', ux_text).strip()

    # Попытка 2 — если не удалось парсить, делим по новой строке
    if not design_text or not ux_text:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        if len(lines) >= 2:
            design_text = design_text or '\n'.join(lines[:-1])
            ux_text = ux_text or lines[-1]

    # Fallback — если совсем ничего не получилось
    if not design_text:
        design_text = raw[:300] if raw else "Не удалось проанализировать"
    if not ux_text:
        ux_text = (raw[300:600] if len(raw) > 300 else raw) or "Не удалось проанализировать"

    # Убираем спецсимволы в начале
    design_text = re.sub(r'^[\*\-\#\s]+', '', design_text).strip()
    ux_text = re.sub(r'^[\*\-\#\s]+', '', ux_text).strip()

    print(f"[DEBUG PARSE] Парсированные результаты:")
    print(f"  DESIGN: {design_score}/10 - {design_text[:150]}...")
    print(f"  UX: {ux_score}/10 - {ux_text[:150]}...")

    return design_text[:500], ux_text[:500], design_score, ux_score  # Ограничиваем длину


# ──────────────────────────────────────────────
# АНАЛИЗ ОДНОГО САЙТА
# ──────────────────────────────────────────────
def analyze_site(url: str, site_type: str, category: str, b64: str, idx: int, total: int) -> dict:
    emit_status(f"[{idx}/{total}] 🔍 {get_domain(url)} [{category}]", "info")

    # Получаем примеры для контекста
    good_examples = db_get_examples(True)
    bad_examples = db_get_examples(False)
    
    examples_text = ""
    if good_examples:
        examples_text += "\n\nХОРОШИЕ ПРИМЕРЫ:\n"
        for eg in good_examples:
            examples_text += f"- {eg['url']}: Дизайн — {eg['design'][:100]}... UX — {eg['ux'][:100]}...\n"
    if bad_examples:
        examples_text += "\nПЛОХИЕ ПРИМЕРЫ:\n"
        for eg in bad_examples:
            examples_text += f"- {eg['url']}: Дизайн — {eg['design'][:100]}... UX — {eg['ux'][:100]}...\n"

    prompt = (
        f"Ты ЖЕСТКИЙ профессиональный критик веб-дизайна с 15+ летним опытом. На скриншоте сайт: {url}\n"
        "Твоя задача — дать ЧЕСТНУЮ, ТРЕБОВАТЕЛЬНУЮ оценку. Не льсти посредственным сайтам!\n\n"
        
        "╔══ КРАСНЫЕ ФЛАГИ ПЛОХОГО ДИЗАЙНА (ищи эти косяки) ══╗\n"
        "🚩 Flash-like мигающие элементы или громкая анимация\n"
        "🚩 Шрифты меньше 14px или без проекта для основного текста\n"
        "🚩 Цвета: неконтрастные, неживые, выбитые из палитры\n"
        "🚩 Огромные блоки текста без отступов (более 80 символов в строке)\n"
        "🚩 Рваная иерархия — нельзя понять что важное, что нет\n"
        "🚩 Скучный однообразный дизайн без микроэлементов\n"
        "🚩 Устаревший/веб 1.0 дизайн (громоздкие кнопки, старые иконки)\n"
        "🚩 Нарушения доступности: очень бледный текст, отсутствие контраста\n"
        "🚩 Неправильное использование белого пространства (прижато к краям)\n"
        "🚩 Масса рекламных блоков или pop-ups портящих эстетику\n\n"
        
        "╔══ КРИТЕРИИ СОВРЕМЕННОГО ДИЗАЙНА 2024-2026 ══╗\n"
        "✅ Минимализм с функциональностью (не просто пусто)\n"
        "✅ Типография: 16-18px основной текст, четкая иерархия\n"
        "✅ Цветовая палитра: 2-3 основных цвета + нейтральные фоны\n"
        "✅ Микроинтерации: плавные переходы, правильная обратная связь\n"
        "✅ Адаптивный дизайн: смотрится хорошо на всех размерах\n"
        "✅ Светлый чистый интерфейс с ясной навигацией\n"
        "✅ Конкретная типография (Montserrat, Inter, Roboto правильно использованы)\n"
        "✅ Правильные CTA кнопки: заметные, яркие, с правильным контрастом\n"
        "✅ Иерархия: главное выделено размером, цветом, позицией\n\n"
        
        "КРИТЕРИИ ДИЗАЙНА:\n"
        "1. ТИПОГРАФИЯ: шрифты, размеры, четкость, иерархия\n"
        "2. КОЛОР: актуальная палитра 2024-2026 или серьёз устаревшая?\n"
        "3. ИЕРАРХИЯ: легко ли найти главное?\n"
        "4. КОНТРАСТ: текст читаем или микроскопический?\n"
        "5. СОВРЕМЕННОСТЬ: это выглядит свежо или как 2010?\n\n"
        
        "КРИТЕРИИ UX:\n"
        "1. НАВИГАЦИЯ: интуитивна ли? Где главное меню?\n"
        "2. ЧИТАЕМОСТЬ: удобно ли читать? Длинные ли строки?\n"
        "3. CTA: видны ли кнопки действия? Понятно ли что делать?\n"
        "4. АДАПТИВНОСТЬ: этот дизайн мобильный? На телефоне читаем?\n"
        "5. ИНТЕРАКТИВНОСТЬ: есть ли обратная связь при клике?\n\n"
        
        "ФОРМАТ ОТВЕТА (СТРОГО!):\n\n"
        "ДИЗАЙН: [оценка 0-10] [коротко плюсы (максимум 2), потом минусы (минимум 3-4, будь жестче!)]\n"
        "UX: [оценка 0-10] [коротко плюсы (максимум 2), потом минусы (минимум 3-4)]\n\n"
        "Например:\n"
        "ДИЗАЙН: 3/10 Плюсы: чистый, минималистичный. Минусы: очень устаревший дизайн 2000х годов, микроскопический шрифт 12px, ужасный контраст, нет иерархии\n"
        "UX: 2/10 Плюсы: быстро загружается. Минусы: непонятная навигация, нет кнопок действия, текст сливается с фоном, совсем не мобильный\n\n"
        "🔥 ГЛАВНОЕ: Если дизайн выглядит плохо или устаревший — ГОВОРИ ЧТО ВЫГЛЯДИТ ПЛОХО!\n"
        "Давай честные оценки! Не льсти посредственности! Если плохо - ставь 0-5 баллов!\n"
        "Отвечай ТОЛЬКО на русском языке." + examples_text
    )

    raw = call_vision(prompt, b64)
    design, ux, design_score, ux_score = parse_vision_response(raw)

    # Fallback если ответ не парсится правильно
    if design.startswith("Нет ответа") or design.startswith("Ошибка"):
        design = raw[:300] if raw else "Не удалось проанализировать дизайн"
        design_score = 5  # дефолт
    if ux.startswith("Нет"):
        ux = raw[300:600] if len(raw) > 300 else "Не удалось проанализировать UX"
        ux_score = 5  # дефолт

    return {
        "url":           url,
        "type":          site_type,
        "category":      category,
        "design":        design,
        "ux":            ux,
        "design_score":  design_score,
        "ux_score":      ux_score,
        "index":         idx,
    }


# ──────────────────────────────────────────────
# ПАЙПЛАЙН ДЛЯ ОДНОГО ГОРОДА
# ──────────────────────────────────────────────
def process_city(city: str, is_recheck: bool = False):
    state.update({
        "city":        city,
        "found_urls":  [],
        "results":     [],
        "current_url": "",
        "skipped":     0,
        "phase":       "searching",
        "start_time":  time.time(),
        "elapsed_sec": 0,
    })
    
    prefix = "🔄 " if is_recheck else "🏙 "
    goal_msg = f"{prefix}Повторный анализ «{city}»" if is_recheck else f"{prefix}Начинаю «{city}» | Цель: до {settings['max_large']+settings['max_niche']} сайтов"
    emit_status(goal_msg, "info")
    emit_state()

    # 1. Поиск крупных сайтов
    emit_status(f"📦 Агент 2: крупные сайты (до {settings['max_large']})...", "info")
    large = search_urls(get_large_queries(city), city, "А2", exclude_domains=set(), skip_db_check=is_recheck)[:settings["max_large"]]
    state["found_urls"] += [s["url"] for s in large]
    emit_status(f"✅ Крупных новых: {len(large)}", "success")
    
    # АДАПТИВНАЯ ЛОГИКА: если крупных сайтов мало - переключаемся на более мягкий режим для нишевых
    adapt_mode = None
    if len(large) < settings["max_large"] // 2:  # Если нашли менее половины ожидаемого
        emit_status(f"📊 Недостаточно крупных сайтов ({len(large)}/{settings['max_large']//2}), переключаемся на LENIENT для нишевых", "warn")
        adapt_mode = "LENIENT"

    if not state["stop"]:
        emit_status(f"🔬 Агент 3: нишевые сайты (до {settings['max_niche']})...", "info")
        ld = {get_domain(u["url"]) for u in large}
        niche = search_urls(get_niche_queries(city), city, "А3", exclude_domains=ld, skip_db_check=is_recheck, force_mode=adapt_mode)[:settings["max_niche"]]
        state["found_urls"] += [s["url"] for s in niche]
        emit_status(f"✅ Нишевых новых: {len(niche)}", "success")
    else:
        niche = []

    all_sites = (
        [{"url": s["url"], "type": "Крупный", "category": s["category"]} for s in large] +
        [{"url": s["url"], "type": "Нишевый", "category": s["category"]} for s in niche]
    )
    emit_state()

    if not all_sites:
        emit_status(f"⚠ Новых сайтов для «{city}» не найдено (возможно все уже в БД)", "warn")
        return

    if state["stop"]:
        return

    # 2. Скриншоты
    state["phase"] = "analyzing"
    total = len(all_sites)
    emit_status(f"📸 Скриншоты {total} сайтов...", "info")
    emit_state()

    shots = take_screenshots([s["url"] for s in all_sites])
    ok  = sum(1 for b, _ in shots.values() if b)
    skip = total - ok
    state["skipped"] += skip
    emit_status(f"✅ Скриншоты: {ok} ОК | {skip} пропущено", "success")

    if state["stop"]:
        return

    # 3. AI-анализ
    emit_status(f"🤖 AI-анализ {total} сайтов...", "info")
    for idx, site in enumerate(all_sites, 1):
        if state["stop"]:
            break
        url  = site["url"]
        state["current_url"] = url
        emit_state()

        b64, status = shots.get(url, (None, "not_found"))
        if b64:
            result = analyze_site(url, site["type"], site["category"], b64, idx, total)
        else:
            reason = "капча" if status == "captcha" else "недоступен"
            emit_status(f"[{idx}/{total}] ⏭ {get_domain(url)} — {reason}", "warn")
            result = {"url": url, "type": site["type"], "category": site["category"],
                      "design": f"Пропущено: {reason}",
                      "ux":     f"Пропущено: {reason}", "index": idx}
            state["skipped"] += 1

        state["results"].append(result)
        socketio.emit("result", result)
        emit_state()

    # 4. Сохранение в БД и Excel
    valid = [r for r in state["results"] if not r["design"].startswith("Пропущено")]
    print(f"[DEBUG process_city] Всего результатов: {len(state['results'])}")
    print(f"[DEBUG process_city] Валидных для сохранения: {len(valid)}")
    for i, r in enumerate(state["results"]):
        starts_with_skip = r["design"].startswith("Пропущено")
        print(f"[DEBUG process_city] [{i}] {get_domain(r['url'])} | design='{r['design'][:40]}...' | пропущен={starts_with_skip}")
    
    if valid:
        db_save(city, valid)
        excel_rebuild()
        emit_status(f"💾 Сохранено в БД: {len(valid)} сайтов", "success")
        socketio.emit("done", {"city": city, "count": len(valid)})
    else:
        print(f"[DEBUG process_city] ВНИМАНИЕ: Нет валидных результатов для сохранения!")
        emit_status(f"⚠️ Нет валидных результатов для сохранения (может быть ошибка анализа)", "warn")

    s = state["elapsed_sec"]
    emit_status(
        f"✅ «{city}» завершён за {s//60}м {s%60:02d}с | "
        f"Проанализировано: {len(valid)} | Пропущено: {state['skipped']}",
        "success"
    )


# ──────────────────────────────────────────────
# ГЛАВНЫЙ ПАЙПЛАЙН — обрабатывает очередь
# ──────────────────────────────────────────────
# Глобальная блокировка чтобы SQLite не блокировался
analysis_lock = threading.Lock()

def run_queue():
    # Проверяем что нет другого анализа
    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен! Дождитесь завершения.", "warn")
        state["running"] = False
        return
    
    try:
        state["running"] = True
        state["stop"]    = False

        # Отслеживаем активность
        if 'user_id' in session:
            track_user_activity(session['user_id'], session.get('username', 'user'), 'Running queue')

        emit_state()

        while state["queue"] and not state["stop"]:
            city = state["queue"].pop(0)
            state["queue_done"].append(city)
            emit_state()
            try:
                process_city(city, is_recheck=False)
            except Exception as e:
                emit_status(f"❌ Ошибка при обработке «{city}»: {e}", "error")

        state.update({
            "running": False, "phase": "done",
            "city": "", "current_url": "",
        })
        if not state["stop"]:
            st = db_stats()
            emit_status(
                f"🎉 Очередь завершена! Всего в БД: {st['total']} сайтов из {st['cities']} городов",
                "success"
            )
        else:
            emit_status("⛔ Очередь остановлена.", "warn")
        emit_state()
    finally:
        analysis_lock.release()


# ──────────────────────────────────────────────
# FLASK ROUTES
# ──────────────────────────────────────────────
@app.route("/")
def index():
    """Главная — если авторизован, то dashboard, иначе login"""
    if 'user_id' in session:
        return render_template("index.html", current_user=get_current_user())
    return redirect(url_for('auth.login'))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html", current_user=get_current_user())

@app.route("/subscription")
@login_required
def subscription():
    """Страница управления подпиской"""
    return render_template("subscription.html", current_user=get_current_user())

# ──────────────────────────────────────────────
# ADMIN PANEL
# ──────────────────────────────────────────────
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'TISH_TEAM_SEARCH')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '0192837456_TICH_TEAM_SEARCH')

# Хранилище онлайн пользователей (в памяти)
# {user_id: {'username': ..., 'last_seen': timestamp, 'task': ...}}
online_users_store = {}
ws_connections_count = 0
ONLINE_USERS_TIMEOUT = 300  # 5 минут неактивности = оффлайн

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

import psutil

@app.route("/admin")
def admin_panel():
    """Админ-панель с проверкой логина/пароля"""
    # Проверяем авторизацию админа
    if not session.get('admin_authenticated'):
        return render_template("admin_login.html")
    
    # Собираем статистику
    from models import User, get_db
    
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
    online = get_online_users()
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
    db_path = Path("tish_data.db")
    db_size_mb = round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0
    db_size_percent = min(100, db_size_mb * 2)  # Примерно, assuming 50MB max
    
    # Активные задачи
    active_tasks = 1 if state.get('running') else 0
    
    return render_template("admin.html",
                         current_user={'username': ADMIN_USERNAME},
                         online_count=len(online),
                         total_users=total_users,
                         active_tasks=active_tasks,
                         cpu_percent=cpu_percent,
                         cpu_cores=cpu_cores,
                         ram_used=ram_used_mb,
                         ram_total=ram_total_mb,
                         ram_percent=ram_percent,
                         ws_connections=ws_connections_count,
                         ws_percent=min(100, ws_connections_count * 2),
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
        return render_template("admin_login.html", error=None)
    
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

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session.clear()  # Очищаем старую сессию
        session['admin_authenticated'] = True
        session['admin_user'] = username
        session.permanent = True  # Сессия сохраняется
        track_user_activity(0, ADMIN_USERNAME, 'Admin Panel')
        
        print(f"[ADMIN] ✅ Успешный вход: {username}")
        print(f"[ADMIN] Session ID: {session.sid if hasattr(session, 'sid') else 'N/A'}")

        if request.is_json:
            return jsonify({'success': True, 'redirect': '/admin'})
        return redirect('/admin')
    else:
        print(f"[ADMIN] ❌ Неверный вход: username='{username}'")
        if request.is_json:
            return jsonify({'error': 'invalid_credentials'}), 401
        return render_template("admin_login.html", error="Неверный логин или пароль")

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
        'online_count': len(get_online_users()),
        'active_tasks': 1 if state.get('running') else 0,
        'cpu_percent': psutil.cpu_percent(interval=0.1),
        'ram_percent': psutil.virtual_memory().percent,
        'ws_connections': ws_connections_count,
    })

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
    path = Path("translations") / f"{lang}.json"
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

# ──────────────────────────────────────────────
# SOCKET.IO AUTH HELPER
# ──────────────────────────────────────────────
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

        from models import User
        user = User.get_by_id(session['user_id'])
        if not user:
            emit_status("⚠ Пользователь не найден", "error")
            return

        # АДМИН: Без ограничений!
        if user.main_site_id or user.username == ADMIN_USERNAME:
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
    global ws_connections_count
    ws_connections_count += 1
    
    # Отслеживаем пользователя если авторизован
    if 'user_id' in session:
        track_user_activity(session['user_id'], session.get('username', 'unknown'))
    elif session.get('admin_authenticated'):
        track_user_activity(0, ADMIN_USERNAME, 'Admin Panel')
    
    emit_state()
    # Отправляем список доступных моделей
    try:
        r = req.get(f"{settings['ollama_url']}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        model_names = [m["name"] for m in models]
        socketio.emit("models_available", {"models": model_names})
        print(f"[OK] Отправлены модели клиенту: {model_names}")
    except Exception as e:
        print(f"[ERROR] Не удалось получить модели: {e}")
        socketio.emit("models_available", {"models": []})

@socketio.on("disconnect")
def on_disconnect():
    global ws_connections_count
    ws_connections_count = max(0, ws_connections_count - 1)

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
        if state["running"]:
            emit_status("Уже работает!", "warn"); return
        if not state["queue"]:
            emit_status("Очередь пустая — добавь города!", "warn"); return
        state["queue_done"] = []
        state["running"] = True  # Блокируем сразу
    threading.Thread(target=run_queue, daemon=True).start()

@socketio.on("stop_scan")
@socket_login_required
def on_stop():
    if state["running"]:
        state["stop"] = True
        emit_status("⛔ Остановка...", "warn")

# ──────────────────────────────────────────────
# СОЦИАЛЬНЫЕ СЕТИ — обработчики
# ──────────────────────────────────────────────
@socketio.on("start_social_search")
@socket_login_required
@socket_subscription_required
def on_social_search(data):
    """Запуск поиска по соцсетям"""
    if state["running"]:
        emit_status("Уже работает!", "warn"); return
    
    query = data.get("query", "")
    city = data.get("city", "")
    platforms = data.get("platforms", [])
    
    if not query:
        emit_status("❌ Не указан поисковый запрос!", "error"); return
    
    emit_status(f"🔍 Начинаю поиск по соцсетям: «{query}»", "info")
    if city:
        emit_status(f"📍 Город: {city}", "info")
    emit_status(f"📱 Платформы: {', '.join(platforms)}", "info")
    
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
    
    emit_state()
    
    # Запускаем в отдельном потоке
    threading.Thread(
        target=process_social_search,
        args=(query, city, platforms),
        daemon=True
    ).start()

@socketio.on("stop_social_search")
@socket_login_required
def on_stop_social():
    """Остановка поиска по соцсетям"""
    if state["running"]:
        state["stop"] = True
        emit_status("⛔ Остановка поиска по соцсетям...", "warn")

# ──────────────────────────────────────────────
# ТОВАРЫ/УСЛУГИ — обработчики
# ──────────────────────────────────────────────
@socketio.on("start_product_search")
@socket_login_required
@socket_subscription_required
def on_product_search(data):
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
    if state["running"]:
        state["stop"] = True
        emit_status("⛔ Остановка поиска товаров/услуг...", "warn")

def generate_synonyms(query):
    """Генерирует расширенный набор синонимов и коммерческих хвостов для запроса."""
    synonym_map = {
        "кроссовки": ["кеды", "сникеры", "спортивная обувь", "обувной магазин"],
        "ремонт": ["ремонт под ключ", "мастер", "сервис", "восстановление", "обслуживание"],
        "доставка": ["курьер", "служба доставки", "доставка на дом", "экспресс доставка"],
        "кафе": ["ресторан", "кофейня", "бистро", "еда на заказ"],
        "отель": ["гостиница", "апартаменты", "мини-отель", "хостел"],
        "автосервис": ["сто", "ремонт авто", "автомастерская", "сервис авто"],
        "парикмахерская": ["салон красоты", "барбершоп", "стилист", "мастер красоты"],
        "магазин": ["бутик", "маркет", "интернет-магазин", "торговая точка"],
        "аптека": ["лекарства", "фармация", "медикаменты", "аптечный пункт"],
        "стройматериалы": ["строительные материалы", "стройбаза", "товары для ремонта"],
    }
    commercial_modifiers = [
        "купить", "заказать", "цена", "стоимость", "услуги", "официальный сайт",
        "контакты", "каталог", "отзывы", "с доставкой", "рядом", "в наличии"
    ]
    
    query_lower = query.lower().strip()
    synonyms = [query.strip()]
    
    for key, syns in synonym_map.items():
        if key in query_lower:
            synonyms.extend(syns)
            break
    
    expanded = []
    for item in synonyms:
        item = item.strip()
        if not item:
            continue
        expanded.append(item)
        for modifier in commercial_modifiers:
            expanded.append(f"{item} {modifier}")
    
    return list(dict.fromkeys(expanded))[:20]

def build_product_search_queries(query: str, city: str, synonyms: list[str]) -> list[str]:
    """Строит расширенный пул поисковых запросов для товаров/услуг."""
    city_part = city.strip() if city else ""
    templates = [
        "{term}",
        "{term} {city}",
        "{term} {city} официальный сайт",
        "{term} {city} каталог",
        "{term} {city} купить",
        "{term} {city} цена",
        "{term} {city} услуги",
        "{term} {city} отзывы",
        "{term} {city} контакты",
        "{term} {city} доставка",
        "site:2gis.ru {term} {city}",
        "site:yandex.ru/maps {term} {city}",
        "site:avito.ru {term} {city}",
        "site:flamp.ru {term} {city}",
    ]
    queries = []
    for term in synonyms or [query]:
        for template in templates:
            rendered = template.format(term=term, city=city_part).strip()
            rendered = re.sub(r"\s+", " ", rendered).strip()
            if rendered:
                queries.append(rendered)
    return list(dict.fromkeys(queries))[:40]

def is_low_quality_product_result(url: str, title: str = "", description: str = "") -> bool:
    """Отсекает мусорные страницы для товаров/услуг."""
    haystack = f"{url} {title} {description}".lower()
    blocked = [
        "login", "signup", "register", "/cart", "/checkout", "/privacy", "/terms",
        "youtube.com", "rutube.ru", "tiktok.com", "instagram.com", "facebook.com",
        "wikipedia.org", "yandex.ru/video", "google.com/search"
    ]
    return any(item in haystack for item in blocked)

def categorize_product(title: str, description: str) -> str:
    """Автоматически определяет категорию товара/услуги по заголовку и описанию"""
    text = (title + " " + description).lower()
    
    # Категории
    categories = {
        "Еда": ["доставка еды", "ресторан", "кафе", "пицца", "суши", "роллы", "бургеры", 
                "курьерская доставка", "заказ еды", "питание", "продукты", "магазин продуктов",
                "пекарня", "кондитерская", "кофейня", "бар", "столовая", "фастфуд", "шаурма"],
        
        "Одежда": ["одежда", "обувь", "кроссовки", "кеды", "ботинки", "туфли", 
                   "магазин одежды", "брендовая одежда", "одежда оптом", "одежда для детей",
                   "спортивная одежда", "верхняя одежда", "нижнее белье", "носки", "колготки",
                   "сумки", "рюкзаки", "кошельки", "аксессуары", "часы", "очки", "украшения"],
        
        "Электроника": ["телефон", "смартфон", "ноутбук", "компьютер", "планшет", 
                        "телевизор", "наушники", "колонки", "камера", "фотоаппарат",
                        "игровая приставка", "playstation", "xbox", "nintendo",
                        "бытовая техника", "холодильник", "стиральная машина", "микроволновка"],
        
        "Дом и сад": ["мебель", "диван", "кровать", "стол", "стул", "шкаф", "кухня",
                      "ремонт квартир", "отделка", "строительство", "загородный дом",
                      "дача", "участок", "ландшафтный дизайн", "сад", "огород",
                      "сантехника", "электрика", "окна", "двери", "пол", "потолок"],
        
        "Авто": ["автомобиль", "машина", "авто", "запчасти", "автосервис", "СТО",
                 "шиномонтаж", "мойка", "автосалон", "прокат авто", "аренда авто",
                 "мотоцикл", "скутер", "велосипед", "грузовик", "прицеп"],
        
        "Красота": ["салон красоты", "парикмахерская", "барбершоп", "маникюр", "педикюр",
                    "косметолог", "массаж", "спа", "эпиляция", "тату", "пирсинг",
                    "косметика", "парфюмерия", "уход за кожей", "макияж"],
        
        "Здоровье": ["медицинский центр", "клиника", "больница", "поликлиника", "врач",
                     "стоматология", "аптека", "лекарства", "витамины", "БАД",
                     "оптика", "очки", "линзы", "слуховой аппарат", "медицинское оборудование"],
        
        "Образование": ["курсы", "обучение", "школа", "репетитор", "языковая школа",
                        "онлайн курсы", "программирование", "дизайн", "маркетинг",
                        "английский язык", "математика", "физика", "химия", "биология",
                        "подготовка к ЕГЭ", "подготовка к ОГЭ", "детский сад", "няня"],
        
        "Услуги": ["юрист", "адвокат", "нотариус", "бухгалтер", "аудитор",
                   "оценка недвижимости", "оценка авто", "независимая экспертиза",
                   "клининг", "уборка", "химчистка", "прачечная",
                   "грузоперевозки", "переезд", "такси", "трансфер",
                   "фотограф", "видеограф", "организация праздников", "свадьба",
                   "ремонт техники", "ремонт обуви", "ремонт одежды", "ателье"],
        
        "Бизнес": ["бизнес", "инвестиции", "франшиза", "готовый бизнес", "продажа бизнеса",
                   "аренда офиса", "офис", "коворкинг", "бизнес центр",
                   "бухгалтерское обслуживание", "аутсорсинг", "консалтинг",
                   "реклама", "маркетинг", "продвижение", "SEO", "SMM", "контекстная реклама"],
    }
    
    # Определяем категорию
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in text:
                return category
    
    return "Другое"

PRODUCTS_EXCEL_PATH = REPORTS_DIR / "products_results.xlsx"

def save_products_to_excel(results: list):
    """Сохраняет результаты поиска товаров/услуг в ОДИН Excel файл в папке reports"""
    if not results:
        return
    
    filepath = PRODUCTS_EXCEL_PATH
    
    # Если файл существует - загружаем его, иначе создаём новый
    try:
        wb = openpyxl.load_workbook(str(filepath))
        if "TovaryUslugi" in wb.sheetnames:
            ws = wb["TovaryUslugi"]
        else:
            ws = wb.active
            ws.title = "TovaryUslugi"
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TovaryUslugi"
        
        # Стили
        hf = PatternFill("solid", fgColor="1E1E2E")
        hfont = Font(bold=True, color="FFFFFF", size="11")
        
        # Заголовки
        headers = ["#", "Категория", "URL", "Название", "Описание", "Запрос", "Город", "Дата"]
        widths = [4, 14, 45, 30, 40, 20, 15, 12]
        
        # Заголовок таблицы
        ws.append([""] * len(headers))
        ws.merge_cells(f"A1:{chr(64+len(headers))}1")
        tc = ws.cell(row=1, column=1)
        tc.value = f"🛍️ TISH SEARCH — Товары/Услуги"
        tc.font = Font(bold=True, size=13, color="FFFFFF")
        tc.alignment = Alignment(horizontal="center", vertical="center")
        tc.fill = PatternFill("solid", fgColor="CC0000")
        ws.row_dimensions[1].height = 32
        
        # Заголовки столбцов
        for col, (h, w) in enumerate(zip(headers, widths), 1):
            c = ws.cell(row=2, column=col, value=h)
            c.font = hfont
            c.fill = hf
            c.border = Border(left=Side(style="thin", color="CCCCCC"), right=Side(style="thin", color="CCCCCC"), top=Side(style="thin", color="CCCCCC"), bottom=Side(style="thin", color="CCCCCC"))
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[c.column_letter].width = w
        ws.row_dimensions[2].height = 28
    
    # Определяем цвет для категории
    fill_colors = {
        "Еда": "FFE8D6",
        "Одежда": "E8D6FF",
        "Электроника": "D6E8FF",
        "Дом и сад": "D6FFE8",
        "Авто": "FFE8E8",
        "Красота": "FFE8F0",
        "Здоровье": "E8FFE8",
        "Образование": "FFF0D6",
        "Услуги": "F0E8FF",
        "Бизнес": "FFF8D6",
        "Другое": "F0F0F0",
    }
    
    # Стили для данных
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")
    ufont = Font(color="0563C1", underline="single", bold=True)
    
    # Получаем текущее количество строк (начиная с 3, т.к. 1-2 это заголовки)
    start_row = ws.max_row + 1
    
    # Добавляем новые данные
    for i, result in enumerate(results, 1):
        row = start_row + i - 1
        category = result.get("category", categorize_product(result.get("title", ""), result.get("description", "")))
        
        ws.cell(row=row, column=1, value=row - 2).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=2, value=category).alignment = Alignment(horizontal="center")
        
        uc = ws.cell(row=row, column=3, value=result.get("url", ""))
        uc.font = ufont
        uc.alignment = Alignment(vertical="top", wrap_text=True)
        
        ws.cell(row=row, column=4, value=result.get("title", "")).alignment = wrap
        ws.cell(row=row, column=5, value=result.get("description", "")).alignment = wrap
        ws.cell(row=row, column=6, value=result.get("query", "")).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=7, value=result.get("city", "")).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=8, value=result.get("found_at", "")[:10] if result.get("found_at") else datetime.now().strftime("%Y-%m-%d")).alignment = Alignment(horizontal="center")
        
        # Применяем границы и цвет строки в зависимости от категории
        fill = PatternFill("solid", fgColor=fill_colors.get(category, "F0F0F0"))
        for col in range(1, 9):
            c = ws.cell(row=row, column=col)
            c.border = border
            c.fill = fill
        
        ws.row_dimensions[row].height = 60
    
    wb.save(str(filepath))
    emit_status(f"📊 Excel сохранён: {filepath.name} (всего {ws.max_row - 2} записей)", "success")
    return filepath

def process_product_search(query, city, max_results, synonyms):
    """Обработка поиска товаров/услуг"""
    # Блокировка чтобы SQLite не блокировался
    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен!", "warn")
        state["running"] = False
        return
    
    try:
        all_results = []
        seen_urls = set()
        search_queries = build_product_search_queries(query, city, synonyms)

        emit_status(f"🔍 Начинаю поиск товаров/услуг. Поисковых вариаций: {len(search_queries)}", "info")
    
    try:
        with DDGS() as ddgs:
            for i, search_query in enumerate(search_queries, 1):
                if state["stop"]:
                    emit_status("⛔ Поиск остановлен пользователем", "warn")
                    break
                
                emit_status(f"🔍 [{i}/{len(search_queries)}] Ищу «{search_query}»...", "info")
                try:
                    results = list(ddgs.text(search_query, max_results=max(10, min(max_results * 2, 50))))
                except Exception as e:
                    emit_status(f"⚠️ Ошибка поиска «{search_query}»: {str(e)[:50]}", "warn")
                    continue
                
                emit_status(f"  📊 Найдено {len(results)} результатов по запросу", "info")
                found_count = 0
                
                for r in results:
                    url = (r.get("href", "") or "").strip()
                    title = (r.get("title", "") or "").strip()
                    desc = (r.get("body", "") or "").strip()
                    
                    if not url.startswith("http"):
                        continue
                    if is_junk_url(url) or is_low_quality_product_result(url, title, desc):
                        continue
                    
                    domain = get_domain(url)
                    if domain in ["avito.ru", "cian.ru", "hh.ru"] and url.count("/") <= 3:
                        continue
                    
                    normalized_key = f"{domain}|{title[:80].lower()}"
                    if url in seen_urls or normalized_key in seen_urls:
                        continue
                    
                    seen_urls.add(url)
                    seen_urls.add(normalized_key)
                    state["found_urls"].append(url)
                    all_results.append({
                        "url": url,
                        "title": title,
                        "description": desc,
                        "query": search_query,
                        "city": city,
                        "found_at": datetime.now().isoformat()
                    })
                    found_count += 1
                    
                    if len(all_results) >= max_results:
                        break
                
                emit_status(f"  ✅ По запросу найдено {found_count} подходящих URL", "success")
                
                if len(all_results) >= max_results:
                    emit_status(f"✅ Достигнут лимит результатов ({max_results})", "success")
                    break
                
                time.sleep(0.5)
    except Exception as e:
        emit_status(f"❌ Критическая ошибка поиска товаров/услуг: {str(e)[:100]}", "error")
    
    if all_results:
        print(f"[DEBUG] Сохраняю {len(all_results)} результатов...")
        
        # Сохраняем результаты в БД
        now = datetime.now().isoformat()
        try:
            with sqlite3.connect(DB_PATH) as con:
                saved_count = 0
                updated_count = 0
                for result in all_results:
                    category = categorize_product(result.get("title", ""), result.get("description", ""))
                    cursor = con.execute("""
                        INSERT INTO product_results (url, title, description, query, city, category, found_at, analyzed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(url, query, city) DO UPDATE SET
                            title=excluded.title,
                            description=excluded.description,
                            category=excluded.category,
                            analyzed_at=excluded.analyzed_at
                    """, (
                        result.get("url", ""),
                        result.get("title", ""),
                        result.get("description", ""),
                        result.get("query", ""),
                        result.get("city", ""),
                        category,
                        result.get("found_at", now),
                        now
                    ))
                    if cursor.rowcount == 1:
                        saved_count += 1
                    else:
                        updated_count += 1
                
                con.commit()
                print(f"[DEBUG] Product DB sync: inserted={saved_count}, updated={updated_count}")
        except Exception as e:
            print(f"[ERROR] Ошибка при сохранении в БД: {e}")
            emit_status(f"❌ Ошибка при сохранении в БД: {e}", "error")
        
        # Сохраняем в Excel
        try:
            filepath = save_products_to_excel(all_results)
            print(f"[DEBUG] Excel сохранён: {filepath}")
            emit_status(f"📊 Excel сохранён: {filepath}", "success")
        except Exception as e:
            print(f"[ERROR] Ошибка при сохранении Excel: {e}")
            emit_status(f"❌ Ошибка при сохранении Excel: {e}", "error")
        
        # Отправляем результаты клиенту
        for idx, result in enumerate(all_results, 1):
            category = categorize_product(result.get("title", ""), result.get("description", ""))
            socketio.emit("result", {
                "url": result.get("url", ""),
                "type": "Товары/Услуги",
                "category": category,
                "design": result.get("description", "")[:200] or "Описание отсутствует",
                "ux": result.get("title", "")[:200] or "Заголовок отсутствует",
                "index": idx
            })
            state["results"].append(result)
            emit_state()
        
        emit_status(f"✅ Поиск завершён! Найдено {len(all_results)} результатов. Сохранено в БД и Excel.", "success")
    else:
        emit_status("⚠️ Ничего не найдено", "warn")
    
    # Сбрасываем состояние
    print(f"[DEBUG] Сброс состояния...")
    state["running"] = False
    state["phase"] = "done"
    state["city"] = ""
    state["current_url"] = ""
    emit_state()
    print(f"[DEBUG] Состояние сброшено")
    finally:
        analysis_lock.release()

def process_social_search(query, city, platforms):
    """Обработка поиска по соцсетям с AI анализом"""
    # Блокировка чтобы SQLite не блокировался
    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен!", "warn")
        state["running"] = False
        return
    
    try:
        from social_search import search_social_media, analyze_social_profile

        all_results = []

        # 1. ПОИСК профилей
        for platform in platforms:
            if state["stop"]:
                break

            emit_status(f"🔍 Ищу на {platform}...", "info")
        results = search_social_media(query, platform, city)
        
        if results:
            emit_status(f"✅ Найдено {len(results)} результатов на {platform}", "success")
            all_results.extend(results)
        else:
            emit_status(f"⚠️ На {platform} ничего не найдено", "warn")
    
    if all_results:
        # 2. AI АНАЛИЗ каждого профиля
        emit_status(f"🤖 Запускаю AI анализ {len(all_results)} профилей...", "info")
        analyzed_results = []
        
        for idx, result in enumerate(all_results, 1):
            if state["stop"]:
                break
            
            url = result.get("url", "")
            platform = result.get("platform", "")
            
            try:
                # Делаем скриншот профиля
                emit_status(f"📸 Скриншот {idx}/{len(all_results)}: {url[:50]}...", "info")
                state["current_url"] = url
                emit_state()
                
                screenshot_b64 = None
                try:
                    screenshot_b64 = take_screenshot(url)
                except Exception as e:
                    print(f"[Screenshot Error] {url}: {e}")
                
                # Анализируем профиль
                if screenshot_b64:
                    emit_status(f"🧠 Анализирую профиль {idx}/{len(all_results)}: {platform}", "info")
                    analysis = analyze_social_profile(platform, url, screenshot_b64)
                    
                    if "error" not in analysis:
                        result["design_score"] = analysis.get("design_score", 5)
                        result["ux_score"] = analysis.get("ux_score", 5)
                        result["design_text"] = analysis.get("design_text", "")
                        result["ux_text"] = analysis.get("ux_text", "")
                        emit_status(f"✅ Анализ {idx}/{len(all_results)}: Дизайн {result['design_score']}/10, UX {result['ux_score']}/10", "success")
                    else:
                        result["design_score"] = 5
                        result["ux_score"] = 5
                        result["design_text"] = f"Ошибка анализа: {analysis.get('error', '')}"
                        result["ux_text"] = ""
                        emit_status(f"⚠️ Ошибка анализа {idx}/{len(all_results)}", "warn")
                else:
                    # Нет скриншота - сохраняем без оценок
                    result["design_score"] = 5
                    result["ux_score"] = 5
                    result["design_text"] = "Не удалось взять скриншот"
                    result["ux_text"] = ""
                
                analyzed_results.append(result)
                
            except Exception as e:
                print(f"[Social Analysis Error] {url}: {e}")
                result["design_score"] = 5
                result["ux_score"] = 5
                result["design_text"] = f"Ошибка: {str(e)[:100]}"
                result["ux_text"] = ""
                analyzed_results.append(result)
        
        all_results = analyzed_results
        
        # 3. СОХРАНЯЕМ в БД
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as con:
            inserted_count = 0
            for result in all_results:
                try:
                    cursor = con.execute("""
                        INSERT INTO social_results 
                        (url, platform, title, description, username, city, query, found_at, analyzed_at, design_score, ux_score, design_text, ux_text)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        result.get("url", ""),
                        result.get("platform", ""),
                        result.get("title", ""),
                        result.get("description", ""),
                        result.get("username", result.get("channel_id", "")),
                        city,
                        result.get("query", query),
                        result.get("found_at", now),
                        now,
                        result.get("design_score", 5),
                        result.get("ux_score", 5),
                        result.get("design_text", ""),
                        result.get("ux_text", "")
                    ))
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    # Дубликат - обновляем запись
                    con.execute("""
                        UPDATE social_results 
                        SET title=?, description=?, username=?, city=?, query=?, analyzed_at=?,
                            design_score=?, ux_score=?, design_text=?, ux_text=?
                        WHERE url=? AND platform=?
                    """, (
                        result.get("title", ""),
                        result.get("description", ""),
                        result.get("username", result.get("channel_id", "")),
                        city,
                        result.get("query", query),
                        now,
                        result.get("design_score", 5),
                        result.get("ux_score", 5),
                        result.get("design_text", ""),
                        result.get("ux_text", ""),
                        result.get("url", ""),
                        result.get("platform", "")
                    ))
                    inserted_count += 1
            
            con.commit()
        emit_status(f"💾 Social DB sync: {inserted_count} записей обработано", "success")
        
        # 4. СОХРАНЯЕМ в Excel
        save_social_to_excel(all_results)
        emit_status(f"📊 Экспорт в Excel завершён", "success")
        
        # 5. ОТПРАВЛЯЕМ результаты клиенту
        for idx, result in enumerate(all_results, 1):
            socketio.emit("result", {
                "url": result.get("url", ""),
                "type": "Соцсеть",
                "category": result.get("platform", "social"),
                "design": f"Дизайн: {result.get('design_score', 5)}/10",
                "ux": f"UX: {result.get('ux_score', 5)}/10",
                "design_text": result.get("design_text", "")[:200],
                "ux_text": result.get("ux_text", "")[:200],
                "index": idx
            })
            state["results"].append(result)
            state["found_urls"].append(result.get("url", ""))
            emit_state()
        
        emit_status(f"✅ Поиск завершён! Найдено {len(all_results)} результатов. Сохранено в БД + Excel.", "success")
    else:
        emit_status("⚠️ Ничего не найдено", "warn")

    state.update({
        "running": False,
        "phase": "done",
        "city": "",
        "current_url": "",
    })
    emit_state()
    finally:
        analysis_lock.release()

SOCIAL_EXCEL_PATH = REPORTS_DIR / "social_results.xlsx"

def save_social_to_excel(results: list):
    """Сохраняет результаты поиска по соцсетям в ОДИН Excel файл"""
    if not results:
        return
    
    filepath = SOCIAL_EXCEL_PATH
    
    try:
        wb = openpyxl.load_workbook(str(filepath))
        if "SocialMedia" in wb.sheetnames:
            ws = wb["SocialMedia"]
        else:
            ws = wb.active
            ws.title = "SocialMedia"
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SocialMedia"
        
        hf = PatternFill("solid", fgColor="1E1E2E")
        hfont = Font(bold=True, color="FFFFFF", size="11")
        
        headers = ["#", "Платформа", "URL", "Название", "Описание", "Username/ID", "Дизайн", "UX", "Отримечание", "Город", "Запрос", "Дата"]
        widths = [4, 12, 45, 30, 40, 20, 8, 8, 25, 15, 20, 12]
        
        ws.append([""] * len(headers))
        ws.merge_cells(f"A1:{chr(64+len(headers))}1")
        tc = ws.cell(row=1, column=1)
        tc.value = f"📱 TISH SEARCH — Социальные сети"
        tc.font = Font(bold=True, size=13, color="FFFFFF")
        tc.alignment = Alignment(horizontal="center", vertical="center")
        tc.fill = PatternFill("solid", fgColor="CC0000")
        ws.row_dimensions[1].height = 32
        
        for col, (h, w) in enumerate(zip(headers, widths), 1):
            c = ws.cell(row=2, column=col, value=h)
            c.font = hfont
            c.fill = hf
            c.border = Border(left=Side(style="thin", color="CCCCCC"), right=Side(style="thin", color="CCCCCC"), top=Side(style="thin", color="CCCCCC"), bottom=Side(style="thin", color="CCCCCC"))
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[c.column_letter].width = w
        ws.row_dimensions[2].height = 28
    
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")
    ufont = Font(color="0563C1", underline="single", bold=True)
    
    platform_colors = {
        "youtube": "FFD6D6",
        "instagram": "FFE8F0",
        "twitter": "D6E8FF",
        "vk": "D6D6FF",
        "telegram": "D6F0FF",
        "tiktok": "F0D6FF",
        "other": "F0F0F0",
    }
    
    start_row = ws.max_row + 1
    
    for i, result in enumerate(results, 1):
        row = start_row + i - 1
        platform = result.get("platform", "other")
        
        ws.cell(row=row, column=1, value=row - 2).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=2, value=platform.upper()).alignment = Alignment(horizontal="center")
        
        uc = ws.cell(row=row, column=3, value=result.get("url", ""))
        uc.font = ufont
        uc.alignment = Alignment(vertical="top", wrap_text=True)
        
        ws.cell(row=row, column=4, value=result.get("title", "")).alignment = wrap
        ws.cell(row=row, column=5, value=result.get("description", "")).alignment = wrap
        ws.cell(row=row, column=6, value=result.get("username", result.get("channel_id", ""))).alignment = Alignment(horizontal="center")
        
        # AI ОЦЕНКИ
        design_score = result.get("design_score", 5)
        ux_score = result.get("ux_score", 5)
        ws.cell(row=row, column=7, value=design_score).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=8, value=ux_score).alignment = Alignment(horizontal="center")
        
        # Примечания (design_text/ux_text)
        notes = f"Дизайн: {result.get('design_text', '')[:50]}... UX: {result.get('ux_text', '')[:50]}..."
        ws.cell(row=row, column=9, value=notes).alignment = wrap
        
        ws.cell(row=row, column=10, value=result.get("city", "")).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=11, value=result.get("query", "")).alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=12, value=result.get("found_at", "")[:10] if result.get("found_at") else datetime.now().strftime("%Y-%m-%d")).alignment = Alignment(horizontal="center")
        
        fill = PatternFill("solid", fgColor=platform_colors.get(platform, "F0F0F0"))
        for col in range(1, 13):
            c = ws.cell(row=row, column=col)
            c.border = border
            c.fill = fill
        
        ws.row_dimensions[row].height = 60
    
    try:
        wb.save(str(filepath))
        emit_status(f"📊 Social Excel сохранён: {filepath.name} (всего {ws.max_row - 2} записей)", "success")
        return filepath
    except PermissionError:
        emit_status("⚠️ Файл Excel открыт в другой программе. Сохранение пропущено.", "warn")
        return None
    except Exception as e:
        emit_status(f"❌ Ошибка сохранения Excel: {e}", "error")
        return None

@socketio.on("recheck_db")
@socket_login_required
@socket_subscription_required
def on_recheck_db(data):
    """Перепроверка сайтов из БД"""
    if state["running"]:
        emit_status("Уже работает!", "warn"); return
    
    limit = int(data.get("limit", 10))
    if limit < 1:
        limit = 10
    if limit > 100:
        limit = 100  # максимум 100 сайтов за раз
    
    state["running"] = True
    state["stop"] = False
    emit_state()
    threading.Thread(target=recheck_db_sites, args=(limit,), daemon=True).start()

@socketio.on("update_settings")
@socket_login_required
def on_settings(data):
    for k in ["max_large","max_niche","max_per_query","parallel","page_timeout"]:
        if k in data:
            try:
                settings[k] = int(data[k])
            except: pass
    if "vision_model" in data:
        settings["vision_model"] = data["vision_model"].strip()
    emit_status(f"⚙ Настройки обновлены: до {settings['max_large']+settings['max_niche']} сайтов на город", "success")
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
    """Сохранить оценки дизайна и UX (0-10)"""
    domain = data.get("domain", "")
    design_score = int(data.get("design_score", 0))
    ux_score = int(data.get("ux_score", 0))
    
    if not domain:
        return
    
    # Валидация
    design_score = max(0, min(10, design_score))
    ux_score = max(0, min(10, ux_score))
    
    try:
        db_save_scores(domain, design_score, ux_score)
        excel_rebuild()
        emit_status(f"⭐ Оценки сохранены: дизайн {design_score}/10, UX {ux_score}/10", "success")
    except Exception as e:
        emit_status(f"❌ Ошибка при сохранении оценок: {e}", "error")

@socketio.on("add_manual_example")
@socket_login_required
def on_add_manual_example(data):
    """Добавить пример вручную"""
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
        # Перезагружаем примеры у клиента
        socketio.emit("reload_examples", {})
    except Exception as e:
        emit_status(f"❌ Ошибка при добавлении примера: {e}", "error")

if __name__ == "__main__":
    db_init()
    init_auth()
    print("=" * 60)
    print("🚀 TISH SEARCH v4: http://localhost:5000")
    print("=" * 60)
    print(f"Ollama URL: {settings['ollama_url']}")
    print(f"Vision модель: {settings['vision_model']}")
    print()
    
    # Проверяем модель перед запуском
    if check_ollama_models():
        print("✅ Готово к запуску!")
    else:
        print("❌ ВНИМАНИЕ: Модель недоступна!")
        print("   Проверь Ollama и установленные модели")
        print("   Команда: ollama list")
    
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
