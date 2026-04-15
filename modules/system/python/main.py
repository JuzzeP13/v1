"""
РњСѓР»СЊС‚Рё-Р°РіРµРЅС‚РЅР°СЏ СЃРёСЃС‚РµРјР° Р°РЅР°Р»РёР·Р° СЃР°Р№С‚РѕРІ РіРѕСЂРѕРґР°
РЎС‚РµРє: Python + Ollama (llava:latest) + Playwright + openpyxl + ddgs

РЈСЃС‚Р°РЅРѕРІРєР°:
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

# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РљРћРќР¤РР“
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
OLLAMA_BASE  = "http://localhost:11434"
VISION_MODEL = "llava:latest"

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Р”РѕРјРµРЅС‹-РјСѓСЃРѕСЂ РєРѕС‚РѕСЂС‹Рµ РЅР°РґРѕ РѕС‚С„РёР»СЊС‚СЂРѕРІР°С‚СЊ
SKIP_DOMAINS = [
    "yandex.ru/checkcaptcha", "wiktionary.org", "kartaslov.ru",
    "support.google.com", "wikipedia.org", "youtube.com",
    "vk.com", "ok.ru", "rutube.ru/info", "digitalocean.ru",
    "yandex.ru/internet", "2gis.ru", "avito.ru"
]


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Р’Р«Р—РћР’ OLLAMA вЂ” С‚РµРєСЃС‚
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
        return f"РћС€РёР±РєР°: {e}"


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Р’Р«Р—РћР’ OLLAMA вЂ” vision (РёР·РѕР±СЂР°Р¶РµРЅРёРµ)
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def call_ollama_vision(prompt: str, image_b64: str) -> str:
    # Ollama vision: images РїРµСЂРµРґР°С‘С‚СЃСЏ РєР°Рє РѕС‚РґРµР»СЊРЅРѕРµ РїРѕР»Рµ, РќР• РІРЅСѓС‚СЂРё content
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [image_b64]   # <-- РїСЂР°РІРёР»СЊРЅС‹Р№ С„РѕСЂРјР°С‚ РґР»СЏ Ollama
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
        return f"РћС€РёР±РєР°: {e}"


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РџРћРРЎРљ РЎРђР™РўРћР’ С‡РµСЂРµР· DuckDuckGo
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
                    print(f"  Р—Р°РїСЂРѕСЃ В«{q}В» в†’ {count} URL")
                except Exception as e:
                    print(f"  Р—Р°РїСЂРѕСЃ В«{q}В» в†’ РѕС€РёР±РєР°: {e}")
    except Exception as e:
        print(f"  [DDGS error] {e}")
    return found


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РђР“Р•РќРў 2 вЂ” РєСЂСѓРїРЅС‹Рµ РїСЂРѕРµРєС‚С‹ РіРѕСЂРѕРґР°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def agent_2_large_projects(city: str) -> list:
    print(f"\n[РђРіРµРЅС‚ 2] РС‰Сѓ РєСЂСѓРїРЅС‹Рµ СЃР°Р№С‚С‹ РґР»СЏ: {city}")
    queries = [
        f"Р°РґРјРёРЅРёСЃС‚СЂР°С†РёСЏ {city} РѕС„РёС†РёР°Р»СЊРЅС‹Р№ СЃР°Р№С‚",
        f"РїРѕСЂС‚Р°Р» {city} РіРѕСЂРѕРґСЃРєРѕР№",
        f"РЅРѕРІРѕСЃС‚Рё {city} РјРµСЃС‚РЅС‹Р№ СЃР°Р№С‚",
        f"С‚РѕСЂРіРѕРІС‹Р№ С†РµРЅС‚СЂ {city} СЃР°Р№С‚",
        f"Р±РѕР»СЊРЅРёС†Р° {city} РѕС„РёС†РёР°Р»СЊРЅС‹Р№ СЃР°Р№С‚",
    ]
    urls = search_urls(queries, max_per_query=2)
    print(f"  [РђРіРµРЅС‚ 2] РС‚РѕРіРѕ: {len(urls)} в†’ {urls}")
    return urls[:6]


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РђР“Р•РќРў 3 вЂ” РЅРёС€РµРІС‹Рµ РїСЂРѕРµРєС‚С‹ РіРѕСЂРѕРґР°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def agent_3_niche_projects(city: str) -> list:
    print(f"\n[РђРіРµРЅС‚ 3] РС‰Сѓ РЅРёС€РµРІС‹Рµ СЃР°Р№С‚С‹ РґР»СЏ: {city}")
    queries = [
        f"РІРµР± СЃС‚СѓРґРёСЏ {city}",
        f"РґРёР·Р°Р№РЅ Р°РіРµРЅС‚СЃС‚РІРѕ {city} СЃР°Р№С‚",
        f"it РєРѕРјРїР°РЅРёСЏ {city} СЂР°Р·СЂР°Р±РѕС‚РєР°",
        f"СЂРµСЃС‚РѕСЂР°РЅ {city} РѕС„РёС†РёР°Р»СЊРЅС‹Р№ СЃР°Р№С‚",
        f"С„РёС‚РЅРµСЃ РєР»СѓР± {city} СЃР°Р№С‚",
    ]
    urls = search_urls(queries, max_per_query=2)
    print(f"  [РђРіРµРЅС‚ 3] РС‚РѕРіРѕ: {len(urls)} в†’ {urls}")
    return urls[:6]


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РЎРљР РРќРЁРћРў
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РђР“Р•РќРў 4 вЂ” Р°РЅР°Р»РёР· РґРёР·Р°Р№РЅР°
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def agent_4_design(url: str, image_b64: str) -> str:
    prompt = (
        f"РўС‹ СЌРєСЃРїРµСЂС‚ РїРѕ РІРµР±-РґРёР·Р°Р№РЅСѓ. РќР° СЃРєСЂРёРЅС€РѕС‚Рµ СЃР°Р№С‚ {url}. "
        "РћС†РµРЅРё: РІРёР·СѓР°Р»СЊРЅР°СЏ РёРµСЂР°СЂС…РёСЏ, С†РІРµС‚Р°, С‚РёРїРѕРіСЂР°С„РёРєР°, СЃРѕРІСЂРµРјРµРЅРЅРѕСЃС‚СЊ СЃС‚РёР»СЏ. "
        "РћС‚РІРµС‚ вЂ” 2-3 РїСЂРµРґР»РѕР¶РµРЅРёСЏ, РєРѕРЅРєСЂРµС‚РЅРѕ СѓРєР°Р¶Рё СЃРёР»СЊРЅС‹Рµ Рё СЃР»Р°Р±С‹Рµ СЃС‚РѕСЂРѕРЅС‹."
    )
    return call_ollama_vision(prompt, image_b64)


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РђР“Р•РќРў 4.5 вЂ” Р°РЅР°Р»РёР· UX
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def agent_45_ux(url: str, image_b64: str) -> str:
    prompt = (
        f"РўС‹ СЌРєСЃРїРµСЂС‚ РїРѕ UX. РќР° СЃРєСЂРёРЅС€РѕС‚Рµ СЃР°Р№С‚ {url}. "
        "РћС†РµРЅРё: РЅР°РІРёРіР°С†РёСЏ, С‡РёС‚Р°РµРјРѕСЃС‚СЊ, РЅР°Р»РёС‡РёРµ CTA, СЃС‚СЂСѓРєС‚СѓСЂР° СЃС‚СЂР°РЅРёС†С‹. "
        "РћС‚РІРµС‚ вЂ” 2-3 РїСЂРµРґР»РѕР¶РµРЅРёСЏ, С‡С‚Рѕ СѓРґРѕР±РЅРѕ Рё С‡С‚Рѕ РјРµС€Р°РµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ."
    )
    return call_ollama_vision(prompt, image_b64)


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РђР“Р•РќРў 5 вЂ” Excel-РѕС‚С‡С‘С‚
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def agent_5_excel(city: str, results: list, output_path: str):
    print(f"\n[РђРіРµРЅС‚ 5] РЎРѕР·РґР°СЋ Excel-РѕС‚С‡С‘С‚...")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"РђРЅР°Р»РёР· вЂ” {city}"

    header_fill = PatternFill("solid", fgColor="1E1E2E")
    large_fill  = PatternFill("solid", fgColor="E8F4FD")
    niche_fill  = PatternFill("solid", fgColor="E8F8F0")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    url_font    = Font(color="0563C1", underline="single", bold=True)
    thin        = Side(style="thin", color="CCCCCC")
    border      = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap        = Alignment(wrap_text=True, vertical="top")

    headers    = ["#", "URL / РЎР°Р№С‚", "РўРёРї", "РћС†РµРЅРєР° РґРёР·Р°Р№РЅР° (РђРіРµРЅС‚ 4)", "РћС†РµРЅРєР° UX (РђРіРµРЅС‚ 4.5)"]
    col_widths = [4, 42, 10, 50, 50]

    # Р—Р°РіРѕР»РѕРІРѕРє РґРѕРєСѓРјРµРЅС‚Р°
    ws.append([""] * 5)
    ws.merge_cells("A1:E1")
    tc = ws.cell(row=1, column=1)
    tc.value     = f"РђРЅР°Р»РёР· РІРµР±-РїСЂРѕРµРєС‚РѕРІ РіРѕСЂРѕРґР° {city}  |  {datetime.now().strftime('%d.%m.%Y')}"
    tc.font      = Font(bold=True, size=13, color="1E1E2E")
    tc.alignment = Alignment(horizontal="center", vertical="center")
    tc.fill      = PatternFill("solid", fgColor="F0F4FF")
    ws.row_dimensions[1].height = 32

    # РЁР°РїРєР° РєРѕР»РѕРЅРѕРє
    for col, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=2, column=col, value=h)
        c.font      = header_font
        c.fill      = header_fill
        c.border    = border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[2].height = 28

    # РЎС‚СЂРѕРєРё СЃ РґР°РЅРЅС‹РјРё
    for i, r in enumerate(results, 1):
        row  = i + 2
        fill = large_fill if r["type"] == "РљСЂСѓРїРЅС‹Р№" else niche_fill

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
    print(f"  [РђРіРµРЅС‚ 5] РЎРѕС…СЂР°РЅРµРЅРѕ: {output_path}")


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РћР РљР•РЎРўР РђРўРћР 
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async def run_pipeline(city: str):
    print(f"\n{'='*50}")
    print(f"  РЎРўРђР Рў | Р“РѕСЂРѕРґ: {city}")
    print(f"{'='*50}")

    large_urls = agent_2_large_projects(city)
    niche_urls = agent_3_niche_projects(city)

    all_sites = (
        [{"url": u, "type": "РљСЂСѓРїРЅС‹Р№"} for u in large_urls] +
        [{"url": u, "type": "РќРёС€РµРІС‹Р№"} for u in niche_urls]
    )

    if not all_sites:
        print("\n[!] РЎР°Р№С‚С‹ РЅРµ РЅР°Р№РґРµРЅС‹.")
        return

    results = []
    for site in all_sites:
        url = site["url"]
        print(f"\n--- РђРЅР°Р»РёР·РёСЂСѓСЋ: {url} ({site['type']}) ---")

        img_b64 = await take_screenshot(url)

        if img_b64:
            print(f"  [РђРіРµРЅС‚ 4]   РђРЅР°Р»РёР· РґРёР·Р°Р№РЅР°...")
            design = agent_4_design(url, img_b64)
            print(f"  [РђРіРµРЅС‚ 4.5] РђРЅР°Р»РёР· UX...")
            ux = agent_45_ux(url, img_b64)
        else:
            design = "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃС‚СЂР°РЅРёС†Сѓ РґР»СЏ Р°РЅР°Р»РёР·Р°."
            ux     = "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃС‚СЂР°РЅРёС†Сѓ РґР»СЏ Р°РЅР°Р»РёР·Р°."

        results.append({"url": url, "type": site["type"], "design": design, "ux": ux})

    output_file = f"РѕС‚С‡С‘С‚_{city}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    agent_5_excel(city, results, output_file)

    print(f"\n{'='*50}")
    print(f"  Р“РћРўРћР’Рћ! Р¤Р°Р№Р»: {output_file}")
    print(f"  РџСЂРѕР°РЅР°Р»РёР·РёСЂРѕРІР°РЅРѕ СЃР°Р№С‚РѕРІ: {len(results)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    city = input("Р’РІРµРґРёС‚Рµ РЅР°Р·РІР°РЅРёРµ РіРѕСЂРѕРґР°: ").strip() or "Р‘РµР»РіРѕСЂРѕРґ"
    asyncio.run(run_pipeline(city))

