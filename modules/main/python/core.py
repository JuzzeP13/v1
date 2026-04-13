"""
TISH SEARCH v4 — Multi-Agent Site Analyzer
Запуск: python -m modules.main.python.server → http://localhost:5000

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
from modules.common.python.config import Config
from modules.auth.python.models import User, get_db, init_extended_db
from modules.auth.python.auth import auth_bp, login_required, get_current_user, login_user, logout_user, init_auth
from modules.auth.python.security import security_middleware, add_security_headers, is_likely_bot
from modules.chat.python.social_search import search_social_media
from modules.common.python.i18n import get_i18n, set_language, _

# ──────────────────────────────────────────────
# ПУТИ
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
STATIC_DIR = PROJECT_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "images").mkdir(exist_ok=True)
TEMPLATES_DIR = PROJECT_ROOT / "templates"
DB_PATH     = PROJECT_ROOT / "tish_data.db"
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

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
    template_folder=str(TEMPLATES_DIR),
)
app.config.from_object(Config)
app.config["JSON_AS_ASCII"] = False
if hasattr(app, "json"):
    app.json.ensure_ascii = False
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
    content_type = response.headers.get('Content-Type', '')
    ct_lower = content_type.lower()
    if ct_lower.startswith('text/html') and 'charset=' not in ct_lower:
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    elif ct_lower.startswith('application/json') and 'charset=' not in ct_lower:
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
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
    "active_sid":  None,
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
        product_columns = {row[1] for row in con.execute("PRAGMA table_info(product_results)").fetchall()}
        product_migrations = {
            "match_level": "ALTER TABLE product_results ADD COLUMN match_level TEXT DEFAULT 'partial'",
            "rank_score": "ALTER TABLE product_results ADD COLUMN rank_score REAL DEFAULT 0",
            "tags": "ALTER TABLE product_results ADD COLUMN tags TEXT",
            "related_terms": "ALTER TABLE product_results ADD COLUMN related_terms TEXT",
            "search_tokens": "ALTER TABLE product_results ADD COLUMN search_tokens TEXT",
            "source_level": "ALTER TABLE product_results ADD COLUMN source_level TEXT DEFAULT 'partial'",
        }
        for column_name, sql in product_migrations.items():
            if column_name not in product_columns:
                print(f"[MIGRATION] Добавляю колонку product_results.{column_name}...")
                con.execute(sql)
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_results_rank ON product_results(rank_score DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_results_match_level ON product_results(match_level)")
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
        con.execute("""
            CREATE TABLE IF NOT EXISTS youtube_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                channel_id TEXT,
                channel_title TEXT,
                channel_url TEXT,
                subscriber_count INTEGER,
                views INTEGER,
                duration REAL,
                viral_score REAL,
                score REAL,
                query TEXT,
                found_at TEXT,
                analyzed_at TEXT,
                thumbnail_score REAL,
                thumbnail_quality TEXT,
                clickbait_probability TEXT,
                emotion_score REAL
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
    socketio.emit("status", {"msg": msg, "level": level}, room=state.get("active_sid"))

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
    }, room=state.get("active_sid"))


# ──────────────────────────────────────────────
# ТАЙМЕР
# ──────────────────────────────────────────────
def _timer():
    while True:
        time.sleep(1)
        if state["running"] and state["start_time"]:
            state["elapsed_sec"] = int(time.time() - state["start_time"])
            s = state["elapsed_sec"]
            socketio.emit("tick", {"elapsed": f"{s//60}м {s%60:02d}с"}, room=state.get("active_sid"))

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
