"""
Мульти-агентная система анализа сайтов города
Стек: Python + Ollama (qwen3-vl) + Playwright + openpyxl + ddgs

Установка:
    pip install ddgs playwright requests openpyxl
    playwright install chromium
"""

import asyncio
import base64
import re
import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from playwright.async_api import async_playwright
from datetime import datetime
from pathlib import Path
from modules.common.python.asyncio_compat import ensure_windows_proactor_event_loop

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

ensure_windows_proactor_event_loop()

# ──────────────────────────────────────────────
# КОНФИГ
# ──────────────────────────────────────────────
OLLAMA_BASE  = "http://localhost:11434"
VISION_MODEL = "qwen3-vl"

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Домены-мусор которые надо отфильтровать
SKIP_DOMAINS = [
    "yandex.ru/checkcaptcha", "wiktionary.org", "kartaslov.ru",
    "support.google.com", "wikipedia.org", "youtube.com",
    "vk.com", "ok.ru", "rutube.ru/info", "digitalocean.ru",
    "yandex.ru/internet", "2gis.ru", "avito.ru"
]


# ──────────────────────────────────────────────
# ВЫЗОВ OLLAMA — текст
# ──────────────────────────────────────────────
def call_ollama_text(prompt: str) -> str:
    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3}
    }
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        print(f"  [Ollama text error] {e}")
        return f"Ошибка: {e}"


# ──────────────────────────────────────────────
# ВЫЗОВ OLLAMA — vision (изображение)
# ──────────────────────────────────────────────
def call_ollama_vision(prompt: str, image_b64: str) -> str:
    # Ollama vision: images передаётся как отдельное поле, НЕ внутри content
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [image_b64]   # <-- правильный формат для Ollama
        }],
        "stream": False,
        "options": {"temperature": 0.3}
    }
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        print(f"  [Ollama vision error] {e}")
        return f"Ошибка: {e}"


# ──────────────────────────────────────────────
# ПОИСК САЙТОВ через DuckDuckGo
# ──────────────────────────────────────────────
def search_urls(queries: list, max_per_query: int = 3) -> list:
    found = []
    seen = set()
    try:
        with DDGS() as ddgs:
            for q in queries:
                try:
                    results = list(ddgs.text(q, max_results=max_per_query * 2))
                    count = 0
                    for r in results:
                        url = r.get("href", "")
                        if not url.startswith("http"):
                            continue
                        if any(skip in url for skip in SKIP_DOMAINS):
                            continue
                        if url in seen:
                            continue
                        seen.add(url)
                        found.append(url)
                        count += 1
                        if count >= max_per_query:
                            break
                    print(f"  Запрос «{q}» → {count} URL")
                except Exception as e:
                    print(f"  Запрос «{q}» → ошибка: {e}")
    except Exception as e:
        print(f"  [DDGS error] {e}")
    return found


# ──────────────────────────────────────────────
# АГЕНТ 2 — крупные проекты города
# ──────────────────────────────────────────────
def agent_2_large_projects(city: str) -> list:
    print(f"\n[Агент 2] Ищу крупные сайты для: {city}")
    queries = [
        f"администрация {city} официальный сайт",
        f"портал {city} городской",
        f"новости {city} местный сайт",
        f"торговый центр {city} сайт",
        f"больница {city} официальный сайт",
    ]
    urls = search_urls(queries, max_per_query=2)
    print(f"  [Агент 2] Итого: {len(urls)} → {urls}")
    return urls[:6]


# ──────────────────────────────────────────────
# АГЕНТ 3 — нишевые проекты города
# ──────────────────────────────────────────────
def agent_3_niche_projects(city: str) -> list:
    print(f"\n[Агент 3] Ищу нишевые сайты для: {city}")
    queries = [
        f"веб студия {city}",
        f"дизайн агентство {city} сайт",
        f"it компания {city} разработка",
        f"ресторан {city} официальный сайт",
        f"фитнес клуб {city} сайт",
    ]
    urls = search_urls(queries, max_per_query=2)
    print(f"  [Агент 3] Итого: {len(urls)} → {urls}")
    return urls[:6]


# ──────────────────────────────────────────────
# СКРИНШОТ
# ──────────────────────────────────────────────
async def take_screenshot(url: str) -> str:
    safe_name = re.sub(r'[^\w]', '_', url)[:80]
    path = SCREENSHOT_DIR / f"{safe_name}.png"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
            )
            page = await ctx.new_page()
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.screenshot(path=str(path), full_page=False)
            await browser.close()

        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        print(f"  [Screenshot] OK: {url}")
        return b64
    except Exception as e:
        print(f"  [Screenshot] FAIL {url}: {e}")
        return None


# ──────────────────────────────────────────────
# АГЕНТ 4 — анализ дизайна
# ──────────────────────────────────────────────
def agent_4_design(url: str, image_b64: str) -> str:
    prompt = (
        f"Ты эксперт по веб-дизайну. На скриншоте сайт {url}. "
        "Оцени: визуальная иерархия, цвета, типографика, современность стиля. "
        "Ответ — 2-3 предложения, конкретно укажи сильные и слабые стороны."
    )
    return call_ollama_vision(prompt, image_b64)


# ──────────────────────────────────────────────
# АГЕНТ 4.5 — анализ UX
# ──────────────────────────────────────────────
def agent_45_ux(url: str, image_b64: str) -> str:
    prompt = (
        f"Ты эксперт по UX. На скриншоте сайт {url}. "
        "Оцени: навигация, читаемость, наличие CTA, структура страницы. "
        "Ответ — 2-3 предложения, что удобно и что мешает пользователю."
    )
    return call_ollama_vision(prompt, image_b64)


# ──────────────────────────────────────────────
# АГЕНТ 5 — Excel-отчёт
# ──────────────────────────────────────────────
def agent_5_excel(city: str, results: list, output_path: str):
    print(f"\n[Агент 5] Создаю Excel-отчёт...")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Анализ — {city}"

    header_fill = PatternFill("solid", fgColor="1E1E2E")
    large_fill  = PatternFill("solid", fgColor="E8F4FD")
    niche_fill  = PatternFill("solid", fgColor="E8F8F0")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    url_font    = Font(color="0563C1", underline="single", bold=True)
    thin        = Side(style="thin", color="CCCCCC")
    border      = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap        = Alignment(wrap_text=True, vertical="top")

    headers    = ["#", "URL / Сайт", "Тип", "Оценка дизайна (Агент 4)", "Оценка UX (Агент 4.5)"]
    col_widths = [4, 42, 10, 50, 50]

    # Заголовок документа
    ws.append([""] * 5)
    ws.merge_cells("A1:E1")
    tc = ws.cell(row=1, column=1)
    tc.value     = f"Анализ веб-проектов города {city}  |  {datetime.now().strftime('%d.%m.%Y')}"
    tc.font      = Font(bold=True, size=13, color="1E1E2E")
    tc.alignment = Alignment(horizontal="center", vertical="center")
    tc.fill      = PatternFill("solid", fgColor="F0F4FF")
    ws.row_dimensions[1].height = 32

    # Шапка колонок
    for col, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=2, column=col, value=h)
        c.font      = header_font
        c.fill      = header_fill
        c.border    = border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[2].height = 28

    # Строки с данными
    for i, r in enumerate(results, 1):
        row  = i + 2
        fill = large_fill if r["type"] == "Крупный" else niche_fill

        ws.cell(row=row, column=1, value=i).alignment = Alignment(horizontal="center", vertical="top")

        uc           = ws.cell(row=row, column=2, value=r["url"])
        uc.font      = url_font
        uc.alignment = Alignment(vertical="top", wrap_text=True)

        tc2           = ws.cell(row=row, column=3, value=r["type"])
        tc2.alignment = Alignment(horizontal="center", vertical="top")

        ws.cell(row=row, column=4, value=r["design"]).alignment = wrap
        ws.cell(row=row, column=5, value=r["ux"]).alignment     = wrap

        for col in range(1, 6):
            c        = ws.cell(row=row, column=col)
            c.border = border
            c.fill   = fill

        ws.row_dimensions[row].height = 90

    wb.save(output_path)
    print(f"  [Агент 5] Сохранено: {output_path}")


# ──────────────────────────────────────────────
# ОРКЕСТРАТОР
# ──────────────────────────────────────────────
async def run_pipeline(city: str):
    print(f"\n{'='*50}")
    print(f"  СТАРТ | Город: {city}")
    print(f"{'='*50}")

    large_urls = agent_2_large_projects(city)
    niche_urls = agent_3_niche_projects(city)

    all_sites = (
        [{"url": u, "type": "Крупный"} for u in large_urls] +
        [{"url": u, "type": "Нишевый"} for u in niche_urls]
    )

    if not all_sites:
        print("\n[!] Сайты не найдены.")
        return

    results = []
    for site in all_sites:
        url = site["url"]
        print(f"\n--- Анализирую: {url} ({site['type']}) ---")

        img_b64 = await take_screenshot(url)

        if img_b64:
            print(f"  [Агент 4]   Анализ дизайна...")
            design = agent_4_design(url, img_b64)
            print(f"  [Агент 4.5] Анализ UX...")
            ux = agent_45_ux(url, img_b64)
        else:
            design = "Не удалось загрузить страницу для анализа."
            ux     = "Не удалось загрузить страницу для анализа."

        results.append({"url": url, "type": site["type"], "design": design, "ux": ux})

    output_file = f"отчёт_{city}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    agent_5_excel(city, results, output_file)

    print(f"\n{'='*50}")
    print(f"  ГОТОВО! Файл: {output_file}")
    print(f"  Проанализировано сайтов: {len(results)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    city = input("Введите название города: ").strip() or "Белгород"
    asyncio.run(run_pipeline(city))
