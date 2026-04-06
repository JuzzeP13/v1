"""
TISH SEARCH - Social Media Search Module
Поиск по YouTube, Instagram, X (Twitter) - отдельная категория поиска
"""

import re
import time
import json
import sqlite3
import requests
from datetime import datetime
from urllib.parse import quote, urlparse

# ─── Helpers ───

def extract_domain(url):
    """Извлечь домен из URL"""
    try:
        parsed = urlparse(url)
        return parsed.netloc.replace('www.', '')
    except:
        return url

def is_valid_social_url(url, platform):
    """Проверить, валидный ли URL социальной сети"""
    platform_domains = {
        "youtube": ["youtube.com", "youtu.be", "m.youtube.com"],
        "instagram": ["instagram.com", "www.instagram.com"],
        "twitter": ["twitter.com", "x.com", "mobile.twitter.com"]
    }
    
    domain = extract_domain(url).lower()
    allowed = platform_domains.get(platform, [])
    return any(d in domain for d in allowed)

def normalize_social_url(url, platform):
    """Нормализует URL профиля/канала, убирая служебные хвосты."""
    url = (url or "").strip()
    if not url:
        return ""
    
    url = url.split("?")[0].split("#")[0].rstrip("/")
    
    if platform == "youtube":
        match = re.search(r"(https?://(?:www\.)?youtube\.com/(?:channel/[a-zA-Z0-9_-]+|@[\w.-]+|user/[a-zA-Z0-9_-]+))", url)
        if match:
            return match.group(1)
        match = re.search(r"(https?://youtu\.be/[a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
    elif platform == "instagram":
        match = re.search(r"(https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.-]+)", url)
        if match:
            username = extract_instagram_username(match.group(1))
            if username:
                return f"https://www.instagram.com/{username}"
    elif platform == "twitter":
        match = re.search(r"(https?://(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+)", url)
        if match:
            username = extract_twitter_username(match.group(1))
            if username:
                return f"https://x.com/{username}"
    
    return url

def is_low_quality_social_result(url, title="", description=""):
    """Отсекает страницы логина, посты, reels, видео и прочий шум."""
    haystack = f"{url} {title} {description}".lower()
    blocked_fragments = [
        "/status/", "/reel/", "/reels/", "/p/", "/tv/", "/shorts/", "/watch", "/video/",
        "login", "signup", "sign in", "explore", "hashtag", "search", "privacy", "terms",
        "accounts/login", "intent/tweet", "share?", "playlist?", "results?"
    ]
    return any(fragment in haystack for fragment in blocked_fragments)

def build_social_queries(query, platform, city=None):
    """Строит расширенный набор поисковых запросов по платформе."""
    base = [query.strip()]
    if city:
        base.extend([
            f"{query} {city}",
            f"{query} {city} официальный",
            f"{query} {city} отзывы",
            f"{query} {city} контакты",
        ])
    
    platform_modifiers = {
        "youtube": ["канал", "ютуб", "youtube channel", "обзор", "видео"],
        "instagram": ["instagram", "инстаграм", "профиль", "аккаунт", "official"],
        "twitter": ["x", "twitter", "твиттер", "аккаунт", "official"],
    }
    site_prefix = {
        "youtube": "site:youtube.com",
        "instagram": "site:instagram.com",
        "twitter": "(site:x.com OR site:twitter.com)",
    }[platform]
    
    queries = []
    modifiers = platform_modifiers.get(platform, [])
    for item in base:
        queries.append(f"{site_prefix} {item}".strip())
        for modifier in modifiers:
            queries.append(f"{site_prefix} {item} {modifier}".strip())
    
    # Убираем дубли, сохраняя порядок
    return list(dict.fromkeys(q for q in queries if q.strip()))

# ─── YouTube Search ───

def search_youtube_channels(query, max_results=10, city=None):
    """
    Поиск YouTube каналов по запросу.
    Возвращает список каналов с метаданными.
    """
    results = []
    seen = set()
    print(f"[YouTube] Начинаю поиск: query='{query}', city='{city}', max_results={max_results}")
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for search_query in build_social_queries(query, "youtube", city):
                if len(results) >= max_results:
                    break
                
                print(f"[YouTube] Запрос: {search_query}")
                raw_results = list(ddgs.text(search_query, max_results=max_results * 3))
                print(f"[YouTube] Найдено сырых результатов: {len(raw_results)}")
                
                for r in raw_results:
                    url = normalize_social_url(r.get("href", ""), "youtube")
                    if not url or url in seen:
                        continue
                    if not is_valid_social_url(url, "youtube") or is_low_quality_social_result(url, r.get("title", ""), r.get("body", "")):
                        continue
                    
                    channel_id = extract_youtube_channel_id(url)
                    if not channel_id:
                        continue
                    
                    results.append({
                        "url": url,
                        "title": r.get("title", ""),
                        "description": r.get("body", ""),
                        "channel_id": channel_id,
                        "platform": "youtube",
                        "query": search_query,
                        "found_at": datetime.now().isoformat()
                    })
                    seen.add(url)
                    print(f"[YouTube] Добавлен результат: {url}")
                    
                    if len(results) >= max_results:
                        break
    except Exception as e:
        print(f"[YouTube Search Error] {e}")
    
    print(f"[YouTube] Итого результатов: {len(results)}")
    return results

def extract_youtube_channel_id(url):
    """Извлечь ID канала из URL"""
    # /channel/UCxxxxx
    match = re.search(r'/channel/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # /@username
    match = re.search(r'/@([a-zA-Z0-9_-]+)', url)
    if match:
        return f"@{match.group(1)}"
    
    # /user/username
    match = re.search(r'/user/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    return None

def analyze_youtube_channel(channel_id):
    """
    Анализ YouTube канала (требует YouTube Data API)
    Для базового анализа используем скриншот и AI
    """
    # В полной версии здесь будет интеграция с YouTube Data API
    # Для демонстрации возвращаем структуру
    return {
        'channel_id': channel_id,
        'subscribers': None,  # Требуется API
        'total_views': None,
        'video_count': None,
        'description': None,
        'thumbnail': None,
    }

# ─── Instagram Search ───

def search_instagram_profiles(query, max_results=10, city=None):
    """
    Поиск Instagram профилей по запросу.
    """
    results = []
    seen = set()
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for search_query in build_social_queries(query, "instagram", city):
                if len(results) >= max_results:
                    break
                
                raw_results = list(ddgs.text(search_query, max_results=max_results * 3))
                for r in raw_results:
                    url = normalize_social_url(r.get("href", ""), "instagram")
                    if not url or url in seen:
                        continue
                    if not is_valid_social_url(url, "instagram") or is_low_quality_social_result(url, r.get("title", ""), r.get("body", "")):
                        continue
                    
                    username = extract_instagram_username(url)
                    if not username:
                        continue
                    
                    results.append({
                        "url": url,
                        "title": r.get("title", ""),
                        "description": r.get("body", ""),
                        "username": username,
                        "platform": "instagram",
                        "query": search_query,
                        "found_at": datetime.now().isoformat()
                    })
                    seen.add(url)
                    
                    if len(results) >= max_results:
                        break
    except Exception as e:
        print(f"[Instagram Search Error] {e}")
    
    return results

def extract_instagram_username(url):
    """Извлечь username из Instagram URL"""
    match = re.search(r'instagram\.com/([a-zA-Z0-9_.-]+)', url)
    if match:
        username = match.group(1)
        # Исключаем служебные пути
        if username not in ['p', 'tv', 'reel', 'stories', 'explore', 'accounts']:
            return username
    return None

# ─── Twitter/X Search ───

def search_twitter_accounts(query, max_results=10, city=None):
    """
    Поиск аккаунтов X (Twitter) по запросу.
    """
    results = []
    seen = set()
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for search_query in build_social_queries(query, "twitter", city):
                if len(results) >= max_results:
                    break
                
                raw_results = list(ddgs.text(search_query, max_results=max_results * 3))
                for r in raw_results:
                    url = normalize_social_url(r.get("href", ""), "twitter")
                    if not url or url in seen:
                        continue
                    if not is_valid_social_url(url, "twitter") or is_low_quality_social_result(url, r.get("title", ""), r.get("body", "")):
                        continue
                    
                    username = extract_twitter_username(url)
                    if not username:
                        continue
                    
                    results.append({
                        "url": url,
                        "title": r.get("title", ""),
                        "description": r.get("body", ""),
                        "username": username,
                        "platform": "twitter",
                        "query": search_query,
                        "found_at": datetime.now().isoformat()
                    })
                    seen.add(url)
                    
                    if len(results) >= max_results:
                        break
    except Exception as e:
        print(f"[Twitter Search Error] {e}")
    
    return results

def extract_twitter_username(url):
    """Извлечь username из Twitter/X URL"""
    match = re.search(r'(?:twitter|x)\.com/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

# ─── Social Media Analysis ───

def analyze_social_profile(platform, url, screenshot_b64=None):
    """
    Анализ профиля социальной сети через AI
    """
    from config import Config
    import base64
    import requests as req
    
    # Формируем промпт для анализа
    if platform == 'youtube':
        prompt = (
            f"Ты эксперт по анализу YouTube каналов. Проанализируй скриншот канала: {url}\n\n"
            "Оцени:\n"
            "1. ДИЗАЙН канала (баннер, аватар, оформление)\n"
            "2. UX (навигация, описание, плейлисты)\n\n"
            "ФОРМАТ ОТВЕТА:\n"
            "DESIGN: [оценка 0-10] [описание]\n"
            "UX: [оценка 0-10] [описание]"
        )
    elif platform == 'instagram':
        prompt = (
            f"Ты эксперт по анализу Instagram профилей. Проанализируй скриншот: {url}\n\n"
            "Оцени:\n"
            "1. ДИЗАЙН (аватар, highlights, лента)\n"
            "2. UX (био, навигация, вовлечённость)\n\n"
            "ФОРМАТ ОТВЕТА:\n"
            "DESIGN: [оценка 0-10] [описание]\n"
            "UX: [оценка 0-10] [описание]"
        )
    elif platform == 'twitter':
        prompt = (
            f"Ты эксперт по анализу X (Twitter) профилей. Проанализируй скриншот: {url}\n\n"
            "Оцени:\n"
            "1. ДИЗАЙН (баннер, аватар, оформление)\n"
            "2. UX (био, закреплённые твиты, навигация)\n\n"
            "ФОРМАТ ОТВЕТА:\n"
            "DESIGN: [оценка 0-10] [описание]\n"
            "UX: [оценка 0-10] [описание]"
        )
    else:
        return {'error': 'Unknown platform'}
    
    # Вызываем AI для анализа
    if screenshot_b64:
        payload = {
            "model": Config.VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [screenshot_b64]
            }],
            "stream": False,
            "options": {"temperature": 0.3}
        }
        
        try:
            r = req.post(f"{Config.OLLAMA_URL}/api/chat", json=payload, timeout=180)
            r.raise_for_status()
            response = r.json()
            content = response.get("message", {}).get("content", "")
            
            # Парсим ответ
            return parse_social_analysis_response(content)
        except Exception as e:
            return {'error': str(e)}
    
    return {'error': 'No screenshot provided'}

def parse_social_analysis_response(raw):
    """Парсинг ответа AI анализа соцсетей"""
    raw = raw.strip()
    
    design_score = 5
    ux_score = 5
    design_text = ""
    ux_text = ""
    
    # Ищем DESIGN: ...
    design_match = re.search(r'DESIGN\s*[:\-]?\s*(.+?)(?=UX\s*[:\-]|$)', raw, re.DOTALL | re.IGNORECASE)
    ux_match = re.search(r'UX\s*[:\-]?\s*(.+?)$', raw, re.DOTALL | re.IGNORECASE)
    
    if design_match:
        design_text = design_match.group(1).strip()
    if ux_match:
        ux_text = ux_match.group(1).strip()
    
    # Извлекаем оценки
    def extract_score(text):
        match = re.search(r'(\d+)\s*(?:/|из)\s*10', text)
        if match:
            return min(10, max(0, int(match.group(1))))
        return None
    
    design_score_parsed = extract_score(design_text)
    ux_score_parsed = extract_score(ux_text)
    
    if design_score_parsed is not None:
        design_score = design_score_parsed
    if ux_score_parsed is not None:
        ux_score = ux_score_parsed
    
    # Удаляем оценки из текста
    design_text = re.sub(r'^\d+\s*(?:/|из)\s*10\s*', '', design_text).strip()
    ux_text = re.sub(r'^\d+\s*(?:/|из)\s*10\s*', '', ux_text).strip()
    
    return {
        'design_score': design_score,
        'ux_score': ux_score,
        'design_text': design_text[:500],
        'ux_text': ux_text[:500],
        'raw_response': raw[:1000]
    }

# ─── Main Search Function ───

def search_social_media(query, platform, city=None, max_results=10):
    """
    Главная функция поиска по социальным сетям
    
    Args:
        query: поисковый запрос
        platform: 'youtube', 'instagram', 'twitter'
        city: город (опционально)
        max_results: максимум результатов
    
    Returns:
        Список найденных профилей
    """
    print(f"[Social Search] Начинаю поиск: platform='{platform}', query='{query}', city='{city}'")
    
    if platform == 'youtube':
        results = search_youtube_channels(query, max_results, city)
    elif platform == 'instagram':
        results = search_instagram_profiles(query, max_results, city)
    elif platform == 'twitter':
        results = search_twitter_accounts(query, max_results, city)
    else:
        print(f"[Social Search] Неизвестная платформа: {platform}")
        return []
    
    print(f"[Social Search] {platform}: найдено {len(results)} профилей")
    return results

# ─── Database Functions ───
# ПРИМЕЧАНИЕ: Функции save_social_result() и get_social_results() были использованы ранее
# но теперь результаты сохраняются напрямую в server.py функцией process_social_search()
# для обеспечения консистентности с таблицей social_results в БД

# ─── CLI Test ───

if __name__ == "__main__":
    print("Testing Social Media Search...")
    
    # Тест поиска YouTube
    print("\n[YouTube] Поиск каналов про веб-дизайн...")
    yt_results = search_youtube_channels("web design", max_results=5)
    for r in yt_results:
        print(f"  - {r.get('title', 'N/A')}: {r.get('url', 'N/A')}")
    
    # Тест поиска Instagram
    print("\n[Instagram] Поиск профилей про дизайн...")
    ig_results = search_instagram_profiles("web design studio", max_results=5)
    for r in ig_results:
        print(f"  - {r.get('title', 'N/A')}: {r.get('url', 'N/A')}")
    
    # Тест поиска Twitter
    print("\n[Twitter] Поиск аккаунтов про дизайн...")
    tw_results = search_twitter_accounts("web designer", max_results=5)
    for r in tw_results:
        print(f"  - {r.get('title', 'N/A')}: {r.get('url', 'N/A')}")
    
    print("\n✓ Тест завершён!")
