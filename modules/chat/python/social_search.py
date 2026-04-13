"""
TISH SEARCH - Social Media Search Module
РџРѕРёСЃРє РїРѕ YouTube, Instagram, X (Twitter) - РѕС‚РґРµР»СЊРЅР°СЏ РєР°С‚РµРіРѕСЂРёСЏ РїРѕРёСЃРєР°
"""

import re
import time
import json
import html as html_lib
import sqlite3
import requests
import logging
import builtins
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from logging.handlers import RotatingFileHandler
from urllib.parse import quote, urlparse

def _setup_social_logger():
    logger = logging.getLogger("tish")
    if logger.handlers:
        return logger

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / "server_runtime.log"

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        str(log_path), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


LOGGER = _setup_social_logger()
_BUILTIN_PRINT = builtins.print


def print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    try:
        message = sep.join(str(a) for a in args)
    except Exception:
        message = " ".join(repr(a) for a in args)
    line = (message + ("" if end == "\n" else end)).rstrip()
    if line:
        LOGGER.info(line)
    _BUILTIN_PRINT(*args, **kwargs)

# в”Ђв”Ђв”Ђ Helpers в”Ђв”Ђв”Ђ

def extract_domain(url):
    """РР·РІР»РµС‡СЊ РґРѕРјРµРЅ РёР· URL"""
    try:
        parsed = urlparse(url)
        return parsed.netloc.replace('www.', '')
    except:
        return url

def is_valid_social_url(url, platform):
    """РџСЂРѕРІРµСЂРёС‚СЊ, РІР°Р»РёРґРЅС‹Р№ Р»Рё URL СЃРѕС†РёР°Р»СЊРЅРѕР№ СЃРµС‚Рё"""
    platform_domains = {
        "youtube": ["youtube.com", "youtu.be", "m.youtube.com"],
        "instagram": ["instagram.com", "www.instagram.com"],
        "twitter": ["twitter.com", "x.com", "mobile.twitter.com"]
    }
    
    domain = extract_domain(url).lower()
    allowed = platform_domains.get(platform, [])
    return any(d in domain for d in allowed)

def normalize_social_url(url, platform):
    """РќРѕСЂРјР°Р»РёР·СѓРµС‚ URL РїСЂРѕС„РёР»СЏ/РєР°РЅР°Р»Р°, СѓР±РёСЂР°СЏ СЃР»СѓР¶РµР±РЅС‹Рµ С…РІРѕСЃС‚С‹."""
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


def get_existing_social_urls(platform):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ URL РїРѕ РїР»Р°С‚С„РѕСЂРјРµ, РєРѕС‚РѕСЂС‹Рµ СѓР¶Рµ СЃРѕС…СЂР°РЅРµРЅС‹ РІ social_results."""
    db_path = Path(__file__).resolve().parents[3] / "tish_data.db"
    existing = set()
    try:
        with sqlite3.connect(str(db_path)) as con:
            rows = con.execute(
                "SELECT url FROM social_results WHERE platform=?",
                (platform,)
            ).fetchall()
        for row in rows:
            raw_url = (row[0] if row else "") or ""
            normalized = normalize_social_url(raw_url, platform)
            if normalized:
                existing.add(normalized)
            elif raw_url:
                existing.add(raw_url)
    except Exception as e:
        print(f"[Social Search] РћС€РёР±РєР° С‡С‚РµРЅРёСЏ social_results ({platform}): {e}")
    return existing


def get_existing_youtube_trend_video_ids():
    """Возвращает ID видео, уже сохранённые в youtube_results."""
    db_path = Path(__file__).resolve().parents[3] / "tish_data.db"
    existing = set()
    try:
        with sqlite3.connect(str(db_path)) as con:
            rows = con.execute("SELECT video_id FROM youtube_results").fetchall()
        for row in rows:
            value = ((row[0] if row else "") or "").strip()
            if value:
                existing.add(value)
    except Exception as e:
        # Таблица может отсутствовать на старой БД до первого db_init().
        print(f"[YouTube Trends] Не удалось прочитать youtube_results: {e}")
    return existing

def is_low_quality_social_result(url, title="", description=""):
    """РћС‚СЃРµРєР°РµС‚ СЃС‚СЂР°РЅРёС†С‹ Р»РѕРіРёРЅР°, РїРѕСЃС‚С‹, reels, РІРёРґРµРѕ Рё РїСЂРѕС‡РёР№ С€СѓРј."""
    haystack = f"{url} {title} {description}".lower()
    blocked_fragments = [
        "/status/", "/reel/", "/reels/", "/p/", "/tv/", "/shorts/", "/watch", "/video/",
        "login", "signup", "sign in", "explore", "hashtag", "search", "privacy", "terms",
        "accounts/login", "intent/tweet", "share?", "playlist?", "results?"
    ]
    return any(fragment in haystack for fragment in blocked_fragments)

def build_social_queries(query, platform, city=None):
    """РЎС‚СЂРѕРёС‚ СЂР°СЃС€РёСЂРµРЅРЅС‹Р№ РЅР°Р±РѕСЂ РїРѕРёСЃРєРѕРІС‹С… Р·Р°РїСЂРѕСЃРѕРІ РїРѕ РїР»Р°С‚С„РѕСЂРјРµ."""
    base = [query.strip()]
    if city:
        base.extend([
            f"{query} {city}",
            f"{query} {city} РѕС„РёС†РёР°Р»СЊРЅС‹Р№",
            f"{query} {city} РѕС‚Р·С‹РІС‹",
            f"{query} {city} РєРѕРЅС‚Р°РєС‚С‹",
        ])
    
    platform_modifiers = {
        "youtube": ["РєР°РЅР°Р»", "СЋС‚СѓР±", "youtube channel", "РѕР±Р·РѕСЂ", "РІРёРґРµРѕ"],
        "instagram": ["instagram", "РёРЅСЃС‚Р°РіСЂР°Рј", "РїСЂРѕС„РёР»СЊ", "Р°РєРєР°СѓРЅС‚", "official"],
        "twitter": ["x", "twitter", "С‚РІРёС‚С‚РµСЂ", "Р°РєРєР°СѓРЅС‚", "official"],
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
    
    # РЈР±РёСЂР°РµРј РґСѓР±Р»Рё, СЃРѕС…СЂР°РЅСЏСЏ РїРѕСЂСЏРґРѕРє
    return list(dict.fromkeys(q for q in queries if q.strip()))

# в”Ђв”Ђв”Ђ YouTube Trend Search (TubelQ-style) в”Ђв”Ђв”Ђ

def _prepare_youtube_trend_candidate(
    candidate,
    search_query,
    duration_min,
    duration_max,
    subs_filter_active,
    subs_min,
    subs_max,
    channel_subs_cache,
    channel_subs_cache_lock,
):
    """РџРѕРґРіРѕС‚Р°РІР»РёРІР°РµС‚ РєР°РЅРґРёРґР°С‚Р° РІ С‚СЂРµРЅРґС‹ (РјРµС‚Р°РґР°РЅРЅС‹Рµ + С„РёР»СЊС‚СЂС‹), Р±РµР·РѕРїР°СЃРЅРѕ РґР»СЏ Р·Р°РїСѓСЃРєР° РІ РїРѕС‚РѕРєР°С…."""
    title = candidate.get("title", "")
    description = candidate.get("description", "")
    url = candidate.get("url", "")
    video_id = candidate.get("video_id", "")

    try:
        video_meta = get_youtube_video_metadata(video_id, description)

        duration = video_meta.get("duration")
        if duration and (duration < duration_min or duration > duration_max):
            return {"status": "skip_duration", "title": title}

        subscriber_count = video_meta.get("subscriber_count")
        channel_key = video_meta.get("channel_id") or video_meta.get("channel_url")

        # РЈС‚РѕС‡РЅСЏРµРј РїРѕРґРїРёСЃС‡РёРєРѕРІ РєР°РЅР°Р»Р° РѕС‚РґРµР»СЊРЅС‹Рј Р·Р°РїСЂРѕСЃРѕРј, РµСЃР»Рё Р·РЅР°С‡РµРЅРёРµ РЅРµ РїРѕРїР°РґР°РµС‚ РІ С„РёР»СЊС‚СЂ.
        needs_subs_recheck = (
            subs_filter_active and channel_key and (
                subscriber_count is None or
                subscriber_count < subs_min or
                subscriber_count > subs_max
            )
        )

        if needs_subs_recheck:
            verified_subs = get_cached_channel_subscriber_count(
                channel_id=video_meta.get("channel_id"),
                channel_url=video_meta.get("channel_url"),
                cache=channel_subs_cache,
                cache_lock=channel_subs_cache_lock
            )
            if verified_subs is not None:
                subscriber_count = verified_subs
                video_meta["subscriber_count"] = verified_subs
            elif (
                subscriber_count is not None and
                subscriber_count < 1000 and
                subs_min >= 5000
            ):
                # Р—РЅР°С‡РµРЅРёРµ РїРѕС…РѕР¶Рµ РЅР° СѓСЃРµС‡С‘РЅРЅРѕРµ (РЅР°РїСЂРёРјРµСЂ 47 РІРјРµСЃС‚Рѕ 47k), РЅРµ РѕС‚Р±СЂР°СЃС‹РІР°РµРј Р¶С‘СЃС‚РєРѕ.
                subscriber_count = None
                video_meta["subscriber_count"] = None

        if subscriber_count is not None and (subscriber_count < subs_min or subscriber_count > subs_max):
            return {"status": "skip_subscribers", "title": title, "subscriber_count": subscriber_count}

        views = video_meta.get("views", 0)
        viral_score = calculate_viral_score(views, duration) if duration else 0
        total_score = calculate_total_score(views, viral_score, title)

        video_data = {
            "url": url,
            "video_id": video_id,
            "title": title,
            "description": description,
            "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "channel_id": video_meta.get("channel_id"),
            "channel_url": video_meta.get("channel_url"),
            "channel_title": video_meta.get("channel_title"),
            "subscriber_count": subscriber_count,
            "views": views,
            "duration": duration,
            "viral_score": viral_score,
            "score": total_score,
            "platform": "youtube",
            "query": search_query,
            "found_at": datetime.now().isoformat(),
        }
        return {"status": "ok", "video": video_data}
    except Exception as e:
        return {"status": "error", "title": title, "error": str(e)}


def search_youtube_trends(query, max_results=50, filters=None, return_stats=False):
    """
    РџРѕРёСЃРє С‚СЂРµРЅРґРѕРІС‹С… YouTube РІРёРґРµРѕ Р°РЅР°Р»РѕРіРёС‡РЅРѕ TubelQ v6.0.
    РЈСЃРєРѕСЂРµРЅРЅР°СЏ РІРµСЂСЃРёСЏ: РїР°СЂР°Р»Р»РµР»СЊРЅР°СЏ РѕР±СЂР°Р±РѕС‚РєР° РєР°РЅРґРёРґР°С‚РѕРІ Рё РјРµС‚Р°РґР°РЅРЅС‹С….
    """
    filters = filters or {}
    results = []
    unknown_subs_candidates = []
    seen = set()
    seen_video_ids = set()
    seen_channels = set()
    channel_subs_cache = {}
    channel_subs_cache_lock = threading.Lock()
    existing_video_ids = get_existing_youtube_trend_video_ids()
    stats = {
        "target": max_results,
        "found": 0,
        "existing_in_db": len(existing_video_ids),
        "query_errors": 0,
        "skipped_existing_db": 0,
        "skipped_duplicate_url": 0,
        "skipped_duplicate_channel": 0,
        "skipped_irrelevant": 0,
        "skipped_duration": 0,
        "skipped_subscribers": 0,
        "metadata_errors": 0,
        "fallback_unknown_subs_added": 0,
    }

    def _to_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    duration_min = _to_int(filters.get("duration_min", 0), 0)
    duration_max = _to_int(filters.get("duration_max", 999), 999)
    subs_min = _to_int(filters.get("subs_min", 0), 0)
    subs_max = _to_int(filters.get("subs_max", 10_000_000), 10_000_000)
    tag = filters.get("tag", "").strip()
    language = (filters.get("language", "EN") or "EN").upper()
    metadata_workers = max(4, min(24, _to_int(filters.get("parallel_requests", 12), 12)))
    search_retries = max(1, min(2, _to_int(filters.get("search_retries", 1), 1)))
    query_has_cyrillic = bool(re.search(r"[Р°-СЏС‘]", (query or "").lower()))

    if duration_max < duration_min:
        duration_min, duration_max = duration_max, duration_min
    if subs_max < subs_min:
        subs_min, subs_max = subs_max, subs_min

    if language == "EN" and query_has_cyrillic:
        language = "RU"
        print("[YouTube Trends] РћР±РЅР°СЂСѓР¶РµРЅР° РєРёСЂРёР»Р»РёС†Р° РІ Р·Р°РїСЂРѕСЃРµ вЂ” РїРµСЂРµРєР»СЋС‡Р°СЋ СЏР·С‹Рє РїРѕРёСЃРєР° РЅР° RU.")

    print(f"[YouTube Trends] РџРѕРёСЃРє: query='{query}', max={max_results}, lang={language}")
    print(f"[YouTube Trends] Р¤РёР»СЊС‚СЂС‹: duration={duration_min}-{duration_max}min, subs={subs_min}-{subs_max}")
    print(f"[YouTube Trends] РџР°СЂР°Р»Р»РµР»СЊРЅС‹С… Р·Р°РїСЂРѕСЃРѕРІ РјРµС‚Р°РґР°РЅРЅС‹С…: {metadata_workers}")
    print(f"[YouTube Trends] РџРѕРІС‚РѕСЂРѕРІ РїРѕРёСЃРєРѕРІРѕРіРѕ Р·Р°РїСЂРѕСЃР°: {search_retries}")
    if existing_video_ids:
        print(f"[YouTube Trends] В БД уже есть {len(existing_video_ids)} видео — они будут пропущены")

    subs_filter_active = subs_min > 0 or subs_max < 10_000_000
    query_lower = (query or "").lower()

    # РЎС‚СЂРѕРёРј РїРѕРёСЃРєРѕРІС‹Рµ Р·Р°РїСЂРѕСЃС‹ СЃ СѓС‡С‘С‚РѕРј СЏР·С‹РєР°.
    search_queries = []
    if language == "RU":
        search_queries.extend([f"{query}", f"{query} СЃРјРѕС‚СЂРµС‚СЊ", f"{query} РІРёРґРµРѕ"])
        if "РєСЂРёРїС‚" in query_lower:
            search_queries.extend([f"{query} РєСЂРёРїС‚РѕРІР°Р»СЋС‚Р°", f"{query} Р±РёС‚РєРѕРёРЅ", f"{query} РѕР±Р·РѕСЂ СЂС‹РЅРєР°"])
    else:
        search_queries.extend([f"{query}", f"{query} viral", f"{query} trending"])
        if "crypto" in query_lower or "bitcoin" in query_lower:
            search_queries.extend([f"{query} market analysis", f"{query} altcoins"])
    if tag:
        search_queries.append(f"{query} {tag}")
    search_queries = list(dict.fromkeys(q.strip() for q in search_queries if q.strip()))

    from ddgs import DDGS
    pass_multipliers = [2, 4, 6, 8, 10]

    with ThreadPoolExecutor(max_workers=metadata_workers) as metadata_pool:
        zero_passes = 0
        for pass_idx, pass_mult in enumerate(pass_multipliers, 1):
            if len(results) >= max_results:
                break

            pass_added = 0
            print(
                f"[YouTube Trends] Проход {pass_idx}/{len(pass_multipliers)} | "
                f"Собрано {len(results)}/{max_results} | x{pass_mult}"
            )

            for search_query in search_queries:
                if len(results) >= max_results:
                    break

                site_query = f"site:youtube.com/watch {search_query}"
                if "РєСЂРёРїС‚" in query_lower or "crypto" in query_lower:
                    site_query += " -crypttv -С‚СЂРµР№Р»РµСЂ -С„РёР»СЊРј -movie -mortal -kombat -official video"
                print(f"[YouTube Trends] Р—Р°РїСЂРѕСЃ: {site_query}")

                raw_results = []
                fetch_limit = max(40, min(max_results * pass_mult, 600))
                for attempt in range(search_retries):
                    try:
                        with DDGS() as ddgs:
                            raw_results = list(ddgs.text(site_query, max_results=fetch_limit))
                        break
                    except Exception as e:
                        stats["query_errors"] += 1
                        print(f"[YouTube Trends] РћС€РёР±РєР° РїРѕРёСЃРєР° ({attempt + 1}/{search_retries}): {e}")
                        if attempt < search_retries - 1:
                            time.sleep(0.4)

                if not raw_results:
                    print(f"[YouTube Trends] РџСѓСЃС‚РѕР№ РѕС‚РІРµС‚ РїРѕ Р·Р°РїСЂРѕСЃСѓ: {site_query}")
                    continue

                print(f"[YouTube Trends] РЎС‹СЂС‹С… СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ: {len(raw_results)}")

                candidate_inputs = []
                for r in raw_results:
                    raw_url = r.get("href", "")
                    title = r.get("title", "")
                    description = r.get("body", "")

                    if not raw_url.startswith("http") or "youtube.com/watch" not in raw_url:
                        continue
                    video_id = extract_youtube_video_id(raw_url)
                    if not video_id:
                        continue
                    if video_id in existing_video_ids:
                        stats["skipped_existing_db"] += 1
                        continue
                    if video_id in seen_video_ids:
                        stats["skipped_duplicate_url"] += 1
                        continue
                    seen_video_ids.add(video_id)

                    url = f"https://www.youtube.com/watch?v={video_id}"
                    if url in seen:
                        stats["skipped_duplicate_url"] += 1
                        continue
                    seen.add(url)

                    if is_irrelevant_youtube_trend_result(title, description, query):
                        stats["skipped_irrelevant"] += 1
                        print(f"[YouTube Trends] РџСЂРѕРїСѓС‰РµРЅРѕ (РЅРµСЂРµР»РµРІР°РЅС‚РЅРѕ): {title[:50]}")
                        continue

                    candidate_inputs.append({
                        "url": url,
                        "title": title,
                        "description": description,
                        "video_id": video_id,
                    })

                if not candidate_inputs:
                    continue

                # Ограничиваем очередь кандидатов, но даём больше в поздних проходах.
                candidate_inputs = candidate_inputs[:max_results * pass_mult * 2]

                future_to_candidate = {
                    metadata_pool.submit(
                        _prepare_youtube_trend_candidate,
                        candidate,
                        search_query,
                        duration_min,
                        duration_max,
                        subs_filter_active,
                        subs_min,
                        subs_max,
                        channel_subs_cache,
                        channel_subs_cache_lock,
                    ): candidate
                    for candidate in candidate_inputs
                }

                for future in as_completed(future_to_candidate):
                    prepared = future.result()
                    status = prepared.get("status")

                    if status == "skip_duration":
                        stats["skipped_duration"] += 1
                        print(f"[YouTube Trends] РџСЂРѕРїСѓС‰РµРЅРѕ (РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ): {prepared.get('title', '')[:50]}")
                        continue
                    if status == "skip_subscribers":
                        stats["skipped_subscribers"] += 1
                        subs_value = prepared.get("subscriber_count")
                        print(
                            f"[YouTube Trends] РџСЂРѕРїСѓС‰РµРЅРѕ (РїРѕРґРїРёСЃС‡РёРєРё {subs_value} РІРЅРµ РґРёР°РїР°Р·РѕРЅР°): "
                            f"{prepared.get('title', '')[:50]}"
                        )
                        continue
                    if status == "error":
                        stats["metadata_errors"] += 1
                        print(
                            f"[YouTube Trends] РћС€РёР±РєР° РєР°РЅРґРёРґР°С‚Р°: {prepared.get('title', '')[:50]} | "
                            f"{prepared.get('error', 'unknown')}"
                        )
                        continue
                    if status != "ok":
                        continue

                    video_data = prepared["video"]
                    channel_key = video_data.get("channel_id") or video_data.get("channel_url")
                    if channel_key:
                        if channel_key in seen_channels:
                            stats["skipped_duplicate_channel"] += 1
                            print(f"[YouTube Trends] РџСЂРѕРїСѓС‰РµРЅРѕ (РєР°РЅР°Р» СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅ): {video_data.get('title', '')[:50]}")
                            continue
                        seen_channels.add(channel_key)

                    subscriber_count = video_data.get("subscriber_count")
                    if subscriber_count is None and subs_filter_active:
                        video_data["subs_unverified"] = True
                        unknown_subs_candidates.append(video_data)
                        print(f"[YouTube Trends] РљР°РЅРґРёРґР°С‚ Р±РµР· РґР°РЅРЅС‹С… РїРѕ РїРѕРґРїРёСЃС‡РёРєР°Рј: {video_data.get('title', '')[:50]}")
                    else:
                        results.append(video_data)
                        pass_added += 1
                        print(
                            f"[YouTube Trends] Р’РёРґРµРѕ: {video_data.get('title', '')[:50]}... "
                            f"(Views: {video_data.get('views', 0)}, Score: {video_data.get('score', 0)})"
                        )

                    if len(results) >= max_results:
                        break

            if pass_added == 0:
                zero_passes += 1
                if zero_passes >= 2:
                    print("[YouTube Trends] Два прохода подряд без новых видео, завершаю добор.")
                    break
            else:
                zero_passes = 0

    if stats["query_errors"]:
        print(f"[YouTube Trends] РћС€РёР±РѕРє РїРѕРёСЃРєР°: {stats['query_errors']}")

    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Если строгие фильтры не дали добрать цель, добавляем кандидатов с неизвестными подписчиками.
    if len(results) < max_results and unknown_subs_candidates:
        unknown_subs_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        existing_urls = {r.get("url") for r in results}
        need = max_results - len(results)
        fallback_items = [v for v in unknown_subs_candidates if v.get("url") not in existing_urls]
        to_add = fallback_items[:need]
        if to_add:
            results.extend(to_add)
            stats["fallback_unknown_subs_added"] = len(to_add)
            print(f"[YouTube Trends] Добор из unknown-subs: +{len(to_add)} (нужно было {need})")

    if len(results) > max_results:
        results = results[:max_results]

    stats["found"] = len(results)
    print(f"[YouTube Trends] РС‚РѕРіРѕ: {len(results)} РІРёРґРµРѕ")
    if return_stats:
        return results, stats
    return results


def get_youtube_video_metadata(video_id, description=None):
    """
    РџРѕР»СѓС‡РёС‚СЊ РјРµС‚Р°РґР°РЅРЅС‹Рµ РІРёРґРµРѕ YouTube (РїСЂРѕСЃРјРѕС‚СЂС‹, РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ, РЅР°Р·РІР°РЅРёРµ)
    РСЃРїРѕР»СЊР·СѓРµС‚ noembed.com (Р±РµСЃРїР»Р°С‚РЅС‹Р№ YouTube oEmbed) + РїР°СЂСЃРёРЅРі СЃС‚СЂР°РЅРёС†С‹
    
    Returns:
        dict СЃ views, duration (РІ РјРёРЅСѓС‚Р°С…), title
    """
    metadata = {
        'views': 0,
        'duration': None,
        'title': '',
        'channel_title': '',
        'channel_url': '',
        'channel_id': '',
        'subscriber_count': None,
    }
    
    try:
        import requests as req

        # 1) РЎРЅР°С‡Р°Р»Р° РїР°СЂСЃРёРј СЃС‚СЂР°РЅРёС†Сѓ РІРёРґРµРѕ (СЃР°РјС‹Р№ РёРЅС„РѕСЂРјР°С‚РёРІРЅС‹Р№ Рё РѕР±С‹С‡РЅРѕ РґРѕСЃС‚Р°С‚РѕС‡РЅС‹Р№ РёСЃС‚РѕС‡РЅРёРє).
        yt_url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = req.get(yt_url, headers=headers, timeout=12)

        if resp.status_code == 200:
            html = resp.text

            duration_match = re.search(r'"lengthSeconds":"(\d+)"', html)
            if duration_match:
                seconds = int(duration_match.group(1))
                metadata["duration"] = seconds / 60

            views_match = re.search(r'"viewCount":"(\d+)"', html)
            if views_match:
                metadata["views"] = int(views_match.group(1))

            if not metadata["views"]:
                views_match = re.search(r'"videoViewCountRenderer".*?"text".*?":\s*"([\d,.]+)"', html)
                if views_match:
                    views_str = views_match.group(1).replace(",", "").replace(".", "")
                    metadata["views"] = int(views_str) if views_str.isdigit() else 0

            if not metadata["views"]:
                views_match = re.search(r'([\d,.]+[KkMmBb]?)\s*(?:РїСЂРѕСЃРј|views)', html, re.IGNORECASE)
                if views_match:
                    views_str = views_match.group(1)
                    suffix_map = {"K": 1000, "k": 1000, "M": 1000000, "m": 1000000, "B": 1000000000, "b": 1000000000}
                    for suffix, multiplier in suffix_map.items():
                        if views_str.endswith(suffix):
                            num = float(views_str[:-1].replace(",", ""))
                            metadata["views"] = int(num * multiplier)
                            break
                    else:
                        plain = views_str.replace(",", "")
                        metadata["views"] = int(plain) if plain.isdigit() else 0

            if not metadata["title"]:
                title_match = re.search(r'"videoDetails":\{"videoId":"[^"]+","title":"([^"]+)"', html)
                if title_match:
                    metadata["title"] = html_lib.unescape(title_match.group(1).replace("\\u0026", "&"))
            if not metadata["title"]:
                og_title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html, re.IGNORECASE)
                if og_title_match:
                    metadata["title"] = html_lib.unescape(og_title_match.group(1))

            if not metadata["channel_id"]:
                channel_match = re.search(r'"channelId":"([^"]+)"', html)
                if channel_match:
                    metadata["channel_id"] = channel_match.group(1)

            if not metadata["channel_title"]:
                channel_title_match = re.search(r'"ownerChannelName":"([^"]+)"', html)
                if channel_title_match:
                    metadata["channel_title"] = html_lib.unescape(channel_title_match.group(1).replace("\\u0026", "&"))

            if not metadata["channel_url"]:
                canonical_match = re.search(r'"canonicalBaseUrl":"([^"]+)"', html)
                if canonical_match:
                    base_path = canonical_match.group(1).replace("\\u0026", "&")
                    metadata["channel_url"] = f"https://www.youtube.com{base_path}"

            if not metadata["channel_id"] and metadata["channel_url"]:
                metadata["channel_id"] = extract_youtube_channel_id(metadata["channel_url"]) or metadata["channel_id"]

            subscriber_count = extract_subscriber_count_from_html(html)
            if subscriber_count is not None:
                metadata["subscriber_count"] = subscriber_count

        # 2) Р›С‘РіРєРёР№ fallback: oEmbed, С‚РѕР»СЊРєРѕ РµСЃР»Рё РїРѕСЃР»Рµ HTML РЅРµ С…РІР°С‚Р°РµС‚ РєР»СЋС‡РµРІС‹С… РїРѕР»РµР№.
        need_oembed = not metadata["title"] or not metadata["channel_title"] or not metadata["channel_url"]
        if need_oembed:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            resp = req.get(oembed_url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if not metadata["title"]:
                    metadata["title"] = data.get("title", "") or metadata["title"]
                metadata["channel_title"] = data.get("author_name", "") or metadata["channel_title"]
                metadata["channel_url"] = data.get("author_url", "") or metadata["channel_url"]
                metadata["channel_id"] = extract_youtube_channel_id(metadata["channel_url"]) or metadata["channel_id"]

    except Exception as e:
        print(f"[YouTube Metadata Error] {e}")
    
    return metadata


def extract_youtube_video_id(url):
    """РР·РІР»РµС‡СЊ ID РІРёРґРµРѕ РёР· YouTube URL"""
    match = re.search(r'v=([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    return None


def extract_subscriber_count_from_html(html):
    """РР·РІР»РµРєР°РµС‚ РєРѕР»РёС‡РµСЃС‚РІРѕ РїРѕРґРїРёСЃС‡РёРєРѕРІ РёР· HTML YouTube-СЃС‚СЂР°РЅРёС†С‹."""
    if not html:
        return None

    # 1) РџСЂРѕСЃС‚РѕР№ С„РѕСЂРјР°С‚: {"simpleText":"67 С‚С‹СЃ. РїРѕРґРїРёСЃС‡РёРєРѕРІ"}
    simple_text_match = re.search(
        r'"subscriberCountText"\s*:\s*\{"simpleText":"([^"]+)"',
        html,
        re.IGNORECASE
    )
    if simple_text_match:
        parsed = parse_subscriber_count(simple_text_match.group(1))
        if parsed is not None:
            return parsed

    # 2) Р¤РѕСЂРјР°С‚ runs: {"runs":[{"text":"67"},{"text":" С‚С‹СЃ."},{"text":" РїРѕРґРїРёСЃС‡РёРєРѕРІ"}]}
    # Р Р°РЅСЊС€Рµ Р±СЂР°Р»Рё С‚РѕР»СЊРєРѕ РїРµСЂРІС‹Р№ "text", РёР·-Р·Р° СЌС‚РѕРіРѕ "67 С‚С‹СЃ." РїСЂРµРІСЂР°С‰Р°Р»РѕСЃСЊ РІ 67.
    runs_iter = re.finditer(
        r'"subscriberCountText"\s*:\s*\{"runs":\[(.*?)\]\}',
        html,
        re.IGNORECASE | re.DOTALL
    )
    for runs_match in runs_iter:
        runs_block = runs_match.group(1)
        run_texts = re.findall(r'"text":"([^"]+)"', runs_block, re.IGNORECASE)
        if not run_texts:
            continue
        parsed = parse_subscriber_count("".join(run_texts))
        if parsed is not None:
            return parsed

    # 3) Fallback: label СЃ РїРѕР»РЅС‹Рј С‚РµРєСЃС‚РѕРј РґР»СЏ accessibility.
    subs_patterns = [
        r'"subscriberCountText".*?"label":"([^"]*subscribers[^"]*)"',
        r'"subscriberCountText".*?"label":"([^"]*РїРѕРґРїРёСЃС‡РёРє[^"]*)"',
        r'"subscriberCountText".*?"label":"([^"]*РїРѕРґРїРёСЃС‡[^"]*)"',
    ]
    for pattern in subs_patterns:
        subs_match = re.search(pattern, html, re.IGNORECASE)
        if not subs_match:
            continue
        parsed = parse_subscriber_count(subs_match.group(1))
        if parsed is not None:
            return parsed

    return None


def get_cached_channel_subscriber_count(channel_id=None, channel_url=None, cache=None, cache_lock=None):
    """РџРѕР»СѓС‡Р°РµС‚ РїРѕРґРїРёСЃС‡РёРєРѕРІ РєР°РЅР°Р»Р° СЃ РєСЌС€РµРј, С‡С‚РѕР±С‹ РЅРµ С…РѕРґРёС‚СЊ РІ СЃРµС‚СЊ РїРѕРІС‚РѕСЂРЅРѕ."""
    if cache is None:
        cache = {}

    cache_key = channel_id or channel_url
    if cache_key:
        if cache_lock:
            with cache_lock:
                if cache_key in cache:
                    return cache[cache_key]
        elif cache_key in cache:
            return cache[cache_key]

    value = fetch_channel_subscriber_count(channel_id=channel_id, channel_url=channel_url)

    if cache_lock:
        with cache_lock:
            if channel_id:
                cache[channel_id] = value
            if channel_url:
                cache[channel_url] = value
    else:
        if channel_id:
            cache[channel_id] = value
        if channel_url:
            cache[channel_url] = value

    return value


def fetch_channel_subscriber_count(channel_id=None, channel_url=None):
    """РџСЂРѕР±СѓРµС‚ РёР·РІР»РµС‡СЊ РїРѕРґРїРёСЃС‡РёРєРѕРІ СЃРѕ СЃС‚СЂР°РЅРёС†С‹ РєР°РЅР°Р»Р° YouTube."""
    candidate_urls = []

    def _add_candidate(url):
        url = (url or "").strip()
        if not url:
            return
        if url.startswith("/"):
            url = f"https://www.youtube.com{url}"
        if not url.startswith("http"):
            return
        url = url.split("?")[0].split("#")[0].rstrip("/")
        if url and url not in candidate_urls:
            candidate_urls.append(url)

    _add_candidate(channel_url)

    channel_id = (channel_id or "").strip()
    if channel_id:
        if channel_id.startswith("@"):
            _add_candidate(f"https://www.youtube.com/{channel_id}")
        elif channel_id.startswith("UC"):
            _add_candidate(f"https://www.youtube.com/channel/{channel_id}")
        else:
            _add_candidate(f"https://www.youtube.com/user/{channel_id}")
            _add_candidate(f"https://www.youtube.com/@{channel_id}")

    # РЎС‚СЂР°РЅРёС†Р° about С‡Р°СЃС‚Рѕ СЃРѕРґРµСЂР¶РёС‚ Р±РѕР»РµРµ СЃС‚Р°Р±РёР»СЊРЅС‹Р№ subscriberCountText.
    with_about = []
    for base in candidate_urls:
        with_about.append(base)
        with_about.append(f"{base}/about")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    for url in with_about:
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
            parsed = extract_subscriber_count_from_html(resp.text)
            if parsed is not None:
                return parsed
        except Exception:
            continue

    return None


def is_irrelevant_youtube_trend_result(title="", description="", query=""):
    """Р‘С‹СЃС‚СЂС‹Р№ РѕС‚СЃРµРІ С€СѓРјРЅС‹С… СЂРѕР»РёРєРѕРІ РґР»СЏ РЅРµРѕРґРЅРѕР·РЅР°С‡РЅС‹С… Р·Р°РїСЂРѕСЃРѕРІ (РЅР°РїСЂРёРјРµСЂ, 'РєСЂРёРїС‚Р°')."""
    query_text = (query or "").lower()
    haystack = f"{title} {description}".lower()

    crypto_query = any(token in query_text for token in ("РєСЂРёРїС‚", "crypto", "bitcoin", "Р±РёС‚РєРѕ"))
    if not crypto_query:
        return False

    allow_markers = [
        "РєСЂРёРїС‚РѕРІР°Р»СЋС‚", "Р±РёС‚РєРѕРёРЅ", "bitcoin", "Р°Р»СЊС‚РєРѕ", "Р±Р»РѕРєС‡РµР№РЅ",
        "СЂС‹РЅРѕРє", "С‚СЂРµР№РґРёРЅРі", "РёРЅРІРµСЃС‚", "СЌРєРѕРЅРѕРј", "С„РёРЅР°РЅСЃ", "РѕР±Р·РѕСЂ",
    ]
    if any(marker in haystack for marker in allow_markers):
        return False

    blocked_markers = [
        "crypttv", "mortal kombat", "С‚СЂРµР№Р»РµСЂ", "СЂСѓСЃСЃРєРёР№ С‚СЂРµР№Р»РµСЂ", "СѓР¶Р°СЃС‹",
        "РєСЂРёРјРёРЅР°Р»СЊРЅР°СЏ РґСЂР°РјР°", "С„РёР»СЊРј", "РєРёРЅРѕ", "official video", "music video",
        "soundtrack", "s1e", "season", "РјРѕРЅСЃС‚СЂ", "horror",
    ]
    return any(marker in haystack for marker in blocked_markers)


def parse_subscriber_count(raw_text):
    """РџСЂРµРѕР±СЂР°Р·СѓРµС‚ СЃС‚СЂРѕРєСѓ РІРёРґР° '1.2M subscribers' РёР»Рё '12 С‚С‹СЃ. РїРѕРґРїРёСЃС‡РёРєРѕРІ' РІ С‡РёСЃР»Рѕ."""
    if not raw_text:
        return None

    text = str(raw_text).strip()

    def _try_fix_mojibake(s):
        # Р§Р°СЃС‚С‹Р№ СЃР»СѓС‡Р°Р№: UTF-8 СЃС‚СЂРѕРєР° РѕС€РёР±РѕС‡РЅРѕ РґРµРєРѕРґРёСЂРѕРІР°РЅР° РєР°Рє latin1/cp1252.
        # РџСЂРёРјРµСЂ: "Г‘вЂљГ‘вЂ№Г‘ВЃ." РІРјРµСЃС‚Рѕ "С‚С‹СЃ."
        if not s:
            return s
        suspicious = any(ch in s for ch in ("Гђ", "Г‘", "Гѓ", "Р "))
        if not suspicious:
            return s
        for src_enc in ("latin1", "cp1252"):
            try:
                fixed = s.encode(src_enc).decode("utf-8")
                if fixed:
                    return fixed
            except Exception:
                continue
        return s

    # 1) Р”РµРєРѕРґРёСЂСѓРµРј \uXXXX РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅРѕСЃС‚Рё (РёРЅРѕРіРґР° РёРґСѓС‚ РґРІРѕР№РЅС‹Рј СЃР»РѕРµРј)
    for _ in range(2):
        if re.search(r'\\u[0-9a-fA-F]{4}', text):
            try:
                text = text.encode('utf-8').decode('unicode_escape')
            except Exception:
                break
        else:
            break

    # 2) HTML entities Рё РІРѕР·РјРѕР¶РЅР°СЏ РїСЂР°РІРєР° "РєСЂР°РєРѕР·СЏР±СЂ"
    text = html_lib.unescape(text)
    text = _try_fix_mojibake(text)

    text = (
        text
        .lower()
        .replace("\xa0", " ")
        .replace("\u202f", " ")
        .replace("&nbsp;", " ")
        .replace(",", ".")
    )
    text = re.sub(r'(?<=\d)\s+(?=\d)', '', text)

    multipliers = {
        "": 1,
        "k": 1_000,
        "Рє": 1_000,
        "С‚С‹СЃ": 1_000,
        "С‚РёСЃ": 1_000,
        "С‚С‹СЃСЏС‡": 1_000,
        "thousand": 1_000,
        "m": 1_000_000,
        "Рј": 1_000_000,
        "РјР»РЅ": 1_000_000,
        "million": 1_000_000,
        "b": 1_000_000_000,
        "Р±": 1_000_000_000,
        "РјР»СЂРґ": 1_000_000_000,
        "billion": 1_000_000_000,
    }

    suffix_pattern = (
        r'(k|Рє|m|Рј|b|Р±|С‚С‹СЃ\.?|С‚РёСЃ\.?|С‚С‹СЃСЏС‡(?:Р°|Рё)?|РјР»РЅ|РјР»СЂРґ|'
        r'thousand|million|billion)?'
    )

    def _normalize_suffix(suffix_text):
        suffix = (suffix_text or "").strip().lower().rstrip(".")
        if suffix.startswith("С‚С‹СЃСЏС‡"):
            return "С‚С‹СЃСЏС‡"
        return suffix

    def _to_number(num_text, suffix_text=None):
        try:
            n = str(num_text).strip()
            # Р•СЃР»Рё С‚РѕС‡РµРє РЅРµСЃРєРѕР»СЊРєРѕ Рё РЅРµС‚ СЃСѓС„С„РёРєСЃР°, СЌС‚Рѕ С‡Р°С‰Рµ СЂР°Р·РґРµР»РёС‚РµР»Рё С‚С‹СЃСЏС‡.
            if n.count(".") > 1 and not suffix_text:
                n = n.replace(".", "")
            value = float(n)
        except (TypeError, ValueError):
            return None
        suffix = _normalize_suffix(suffix_text)
        multiplier = multipliers.get(suffix, 1)
        return int(value * multiplier)

    # РЎРѕР±РёСЂР°РµРј РІСЃРµ С‡РёСЃР»РѕРІС‹Рµ С‚РѕРєРµРЅС‹.
    token_matches = []
    for m in re.finditer(rf'(\d+(?:\.\d+)?)\s*{suffix_pattern}\+?', text, re.IGNORECASE):
        parsed = _to_number(m.group(1), m.group(2))
        if parsed is None:
            continue
        token_matches.append({
            "value": parsed,
            "start": m.start(),
            "end": m.end(),
            "suffix": _normalize_suffix(m.group(2)),
        })

    if not token_matches:
        return None

    # РџСЂРёРѕСЂРёС‚РµС‚: С‡РёСЃР»Рѕ СЂСЏРґРѕРј СЃРѕ СЃР»РѕРІРѕРј "subscribers/РїРѕРґРїРёСЃС‡РёРєРё/РїС–РґРїРёСЃРЅРёРєРё".
    keyword_positions = [
        km.start()
        for km in re.finditer(r'(subscribers?|РїРѕРґРїРёСЃ\w*|РїС–РґРїРёСЃ\w*)', text, re.IGNORECASE)
    ]
    if keyword_positions:
        best = min(
            token_matches,
            key=lambda t: min(abs(t["start"] - p) for p in keyword_positions)
        )
        return best["value"]

    # Р•СЃР»Рё РµСЃС‚СЊ С‚РѕРєРµРЅС‹ СЃ СЃСѓС„С„РёРєСЃР°РјРё (k/С‚С‹СЃ/РјР»РЅ), РІС‹Р±РёСЂР°РµРј РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№ РёР· РЅРёС….
    with_suffix = [t for t in token_matches if t["suffix"]]
    if with_suffix:
        return max(t["value"] for t in with_suffix)

    # РРЅР°С‡Рµ вЂ” РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№ С‚РѕРєРµРЅ (Р»СѓС‡С€Рµ, С‡РµРј "РїРµСЂРІРѕРµ С‡РёСЃР»Рѕ", РєРѕС‚РѕСЂРѕРµ С‡Р°СЃС‚Рѕ = РєРѕР»-РІРѕ РІРёРґРµРѕ).
    return max(t["value"] for t in token_matches)


def extract_duration_from_description(description):
    """РР·РІР»РµС‡СЊ РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ РІРёРґРµРѕ РёР· РѕРїРёСЃР°РЅРёСЏ (РЅР°РїСЂРёРјРµСЂ '5:32' -> 5.53 РјРёРЅСѓС‚С‹)"""
    if not description:
        return None
    
    # РС‰РµРј РїР°С‚С‚РµСЂРЅ РІСЂРµРјРµРЅРё (X:YY РёР»Рё XX:YY РёР»Рё X:YY:ZZ)
    match = re.search(r'(\d+):(\d{2}):(\d{2})', description)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return hours * 60 + minutes + seconds / 60
    
    match = re.search(r'(\d+):(\d{2})', description)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes + seconds / 60
    
    return None


def extract_views_from_description(description):
    """РР·РІР»РµС‡СЊ РєРѕР»РёС‡РµСЃС‚РІРѕ РїСЂРѕСЃРјРѕС‚СЂРѕРІ РёР· РѕРїРёСЃР°РЅРёСЏ"""
    if not description:
        return 0
    
    # РС‰РµРј С‡РёСЃР»Рѕ РїСЂРѕСЃРјРѕС‚СЂРѕРІ (РЅР°РїСЂРёРјРµСЂ "100K views" РёР»Рё "1.2M РїСЂРѕСЃРјРѕС‚СЂРѕРІ")
    match = re.search(r'([\d,.]+)\s*[KkMmBb]?\s*(?:views|РїСЂРѕСЃРјРѕС‚СЂРѕРІ|views|РїСЂРѕСЃРј)', description, re.IGNORECASE)
    if match:
        views_str = match.group(1).replace(',', '')
        try:
            views = float(views_str)
            # РџСЂРѕРІРµСЂСЏРµРј СЃСѓС„С„РёРєСЃ
            suffix_match = re.search(r'([KkMmBb])', match.group(0))
            if suffix_match:
                suffix = suffix_match.group(1).upper()
                if suffix == 'K':
                    views *= 1000
                elif suffix == 'M':
                    views *= 1000000
                elif suffix == 'B':
                    views *= 1000000000
            return int(views)
        except:
            pass
    
    return 0


def calculate_viral_score(views, duration):
    """
    Р Р°СЃСЃС‡РёС‚Р°С‚СЊ viral score (РІРёСЂСѓСЃРЅРѕСЃС‚СЊ)
    Р§РµРј Р±РѕР»СЊС€Рµ РїСЂРѕСЃРјРѕС‚СЂРѕРІ Р·Р° РєРѕСЂРѕС‚РєРѕРµ РІСЂРµРјСЏ - С‚РµРј РІС‹С€Рµ score
    """
    if not duration or duration == 0:
        return 0
    
    # РџСЂРѕСЃРјРѕС‚СЂРѕРІ РІ РјРёРЅСѓС‚Сѓ
    views_per_minute = views / duration
    
    # РќРѕСЂРјР°Р»РёР·СѓРµРј (Р»РѕРіР°СЂРёС„РјРёС‡РµСЃРєР°СЏ С€РєР°Р»Р°)
    import math
    viral = math.log10(views_per_minute + 1) * 10
    
    return round(viral, 2)


def calculate_total_score(views, viral_score, title):
    """
    Р Р°СЃСЃС‡РёС‚Р°С‚СЊ РѕР±С‰РёР№ score РІРёРґРµРѕ
    РЈС‡РёС‚С‹РІР°РµС‚: РїСЂРѕСЃРјРѕС‚СЂС‹, РІРёСЂСѓСЃРЅРѕСЃС‚СЊ, РєР°С‡РµСЃС‚РІРѕ Р·Р°РіРѕР»РѕРІРєР°
    """
    # Score РЅР° РѕСЃРЅРѕРІРµ РїСЂРѕСЃРјРѕС‚СЂРѕРІ (Р»РѕРіР°СЂРёС„РјРёС‡РµСЃРєР°СЏ С€РєР°Р»Р°)
    import math
    views_score = math.log10(views + 1) * 5
    
    # Р‘РѕРЅСѓСЃ Р·Р° С…РѕСЂРѕС€РёР№ Р·Р°РіРѕР»РѕРІРѕРє (РЅР°Р»РёС‡РёРµ РєР»СЋС‡РµРІС‹С… СЃР»РѕРІ)
    title_lower = title.lower()
    title_bonus = 0
    viral_keywords = ['viral', 'trend', 'challenge', 'first', 'ever', 'best', 'top']
    for keyword in viral_keywords:
        if keyword in title_lower:
            title_bonus += 2
    
    total = views_score + viral_score + title_bonus
    return round(total, 1)


def analyze_youtube_thumbnail(video_id, screenshot_b64=None):
    """
    РђРЅР°Р»РёР· РїСЂРµРІСЊСЋ YouTube РІРёРґРµРѕ С‡РµСЂРµР· AI (LLaVA)
    
    Args:
        video_id: ID YouTube РІРёРґРµРѕ
        screenshot_b64: base64 СЃРєСЂРёРЅС€РѕС‚Р° РїСЂРµРІСЊСЋ
    
    Returns:
        dict СЃ Р°РЅР°Р»РёР·РѕРј РїСЂРµРІСЊСЋ
    """
    if not screenshot_b64:
        return {
            'thumbnail_analysis': 'РџСЂРµРІСЊСЋ РЅРµ Р·Р°РіСЂСѓР¶РµРЅРѕ',
            'thumbnail_score': 5,
            'clickbait_probability': 'unknown',
            'quality': 'unknown'
        }
    
    prompt = (
        f"РўС‹ СЌРєСЃРїРµСЂС‚ РїРѕ Р°РЅР°Р»РёР·Сѓ YouTube РїСЂРµРІСЊСЋ. РџСЂРѕР°РЅР°Р»РёР·РёСЂСѓР№ СЃРєСЂРёРЅС€РѕС‚ РїСЂРµРІСЊСЋ РІРёРґРµРѕ.\n\n"
        "РћС†РµРЅРё:\n"
        "1. CLICKBAIT: РќР°СЃРєРѕР»СЊРєРѕ РїСЂРµРІСЊСЋ РєР»РёРєР±РµР№С‚РЅРѕРµ (0-10)\n"
        "2. QUALITY: РљР°С‡РµСЃС‚РІРѕ РѕС„РѕСЂРјР»РµРЅРёСЏ РїСЂРµРІСЊСЋ (0-10)\n"
        "3. EMOTION: Р­РјРѕС†РёРѕРЅР°Р»СЊРЅР°СЏ РїСЂРёРІР»РµРєР°С‚РµР»СЊРЅРѕСЃС‚СЊ (0-10)\n"
        "4. TEXT: РќР°Р»РёС‡РёРµ Рё С‡РёС‚Р°РµРјРѕСЃС‚СЊ С‚РµРєСЃС‚Р° РЅР° РїСЂРµРІСЊСЋ\n\n"
        "Р¤РћР РњРђРў РћРўР’Р•РўРђ:\n"
        "CLICKBAIT: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]\n"
        "QUALITY: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]\n"
        "EMOTION: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]\n"
        "TEXT: [РѕРїРёСЃР°РЅРёРµ]"
    )
    
    from modules.common.python.config import Config
    import requests as req
    
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
        
        # РџР°СЂСЃРёРј РѕС‚РІРµС‚
        analysis = parse_thumbnail_analysis(content)
        analysis['thumbnail_analysis'] = content[:500]
        return analysis
    
    except Exception as e:
        return {
            'thumbnail_analysis': f'РћС€РёР±РєР° Р°РЅР°Р»РёР·Р°: {str(e)[:100]}',
            'thumbnail_score': 5,
            'clickbait_probability': 'unknown',
            'quality': 'unknown'
        }


def parse_thumbnail_analysis(raw):
    """РџР°СЂСЃРёРЅРі Р°РЅР°Р»РёР·Р° РїСЂРµРІСЊСЋ"""
    raw = raw.strip()
    
    clickbait_score = 5
    quality_score = 5
    emotion_score = 5
    
    # РС‰РµРј РѕС†РµРЅРєРё
    clickbait_match = re.search(r'CLICKBAIT\s*[:\-]?\s*(\d+)', raw, re.IGNORECASE)
    quality_match = re.search(r'QUALITY\s*[:\-]?\s*(\d+)', raw, re.IGNORECASE)
    emotion_match = re.search(r'EMOTION\s*[:\-]?\s*(\d+)', raw, re.IGNORECASE)
    
    if clickbait_match:
        clickbait_score = min(10, max(0, int(clickbait_match.group(1))))
    if quality_match:
        quality_score = min(10, max(0, int(quality_match.group(1))))
    if emotion_match:
        emotion_score = min(10, max(0, int(emotion_match.group(1))))
    
    # РћР±С‰РёР№ score РїСЂРµРІСЊСЋ
    thumbnail_score = (quality_score + emotion_score) / 2
    
    # РћРїСЂРµРґРµР»СЏРµРј РєР»РёРєР±РµР№С‚РЅРѕСЃС‚СЊ
    if clickbait_score >= 7:
        clickbait = 'high'
    elif clickbait_score >= 4:
        clickbait = 'medium'
    else:
        clickbait = 'low'
    
    # РћРїСЂРµРґРµР»СЏРµРј РєР°С‡РµСЃС‚РІРѕ
    if quality_score >= 7:
        quality = 'high'
    elif quality_score >= 4:
        quality = 'medium'
    else:
        quality = 'low'
    
    return {
        'thumbnail_score': round(thumbnail_score, 1),
        'clickbait_score': clickbait_score,
        'clickbait_probability': clickbait,
        'quality_score': quality_score,
        'quality': quality,
        'emotion_score': emotion_score
    }


# в”Ђв”Ђв”Ђ YouTube Search в”Ђв”Ђв”Ђ

def search_youtube_channels(query, max_results=10, city=None, exclude_urls=None):
    """
    РџРѕРёСЃРє YouTube РєР°РЅР°Р»РѕРІ РїРѕ Р·Р°РїСЂРѕСЃСѓ.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє РєР°РЅР°Р»РѕРІ СЃ РјРµС‚Р°РґР°РЅРЅС‹РјРё.
    """
    results = []
    seen = set(exclude_urls or set())
    print(f"[YouTube] РќР°С‡РёРЅР°СЋ РїРѕРёСЃРє: query='{query}', city='{city}', max_results={max_results}")
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            search_queries = build_social_queries(query, "youtube", city)
            for pass_idx, mult in enumerate((3, 6, 9), 1):
                if len(results) >= max_results:
                    break
                pass_added = 0

                for search_query in search_queries:
                    if len(results) >= max_results:
                        break

                    print(f"[YouTube] Р—Р°РїСЂРѕСЃ (pass {pass_idx}): {search_query}")
                    raw_results = list(ddgs.text(search_query, max_results=max(30, max_results * mult)))
                    print(f"[YouTube] РќР°Р№РґРµРЅРѕ СЃС‹СЂС‹С… СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ: {len(raw_results)}")

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
                        pass_added += 1
                        print(f"[YouTube] Р”РѕР±Р°РІР»РµРЅ СЂРµР·СѓР»СЊС‚Р°С‚: {url}")

                        if len(results) >= max_results:
                            break

                if pass_added == 0:
                    break
    except Exception as e:
        print(f"[YouTube Search Error] {e}")
    
    print(f"[YouTube] РС‚РѕРіРѕ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ: {len(results)}")
    return results

def extract_youtube_channel_id(url):
    """РР·РІР»РµС‡СЊ ID РєР°РЅР°Р»Р° РёР· URL"""
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
    РђРЅР°Р»РёР· YouTube РєР°РЅР°Р»Р° (С‚СЂРµР±СѓРµС‚ YouTube Data API)
    Р”Р»СЏ Р±Р°Р·РѕРІРѕРіРѕ Р°РЅР°Р»РёР·Р° РёСЃРїРѕР»СЊР·СѓРµРј СЃРєСЂРёРЅС€РѕС‚ Рё AI
    """
    # Р’ РїРѕР»РЅРѕР№ РІРµСЂСЃРёРё Р·РґРµСЃСЊ Р±СѓРґРµС‚ РёРЅС‚РµРіСЂР°С†РёСЏ СЃ YouTube Data API
    # Р”Р»СЏ РґРµРјРѕРЅСЃС‚СЂР°С†РёРё РІРѕР·РІСЂР°С‰Р°РµРј СЃС‚СЂСѓРєС‚СѓСЂСѓ
    return {
        'channel_id': channel_id,
        'subscribers': None,  # РўСЂРµР±СѓРµС‚СЃСЏ API
        'total_views': None,
        'video_count': None,
        'description': None,
        'thumbnail': None,
    }

# в”Ђв”Ђв”Ђ Instagram Search в”Ђв”Ђв”Ђ

def search_instagram_profiles(query, max_results=10, city=None, exclude_urls=None):
    """
    РџРѕРёСЃРє Instagram РїСЂРѕС„РёР»РµР№ РїРѕ Р·Р°РїСЂРѕСЃСѓ.
    """
    results = []
    seen = set(exclude_urls or set())
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            search_queries = build_social_queries(query, "instagram", city)
            for pass_idx, mult in enumerate((3, 6, 9), 1):
                if len(results) >= max_results:
                    break
                pass_added = 0

                for search_query in search_queries:
                    if len(results) >= max_results:
                        break

                    raw_results = list(ddgs.text(search_query, max_results=max(30, max_results * mult)))
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
                        pass_added += 1

                        if len(results) >= max_results:
                            break

                if pass_added == 0:
                    break
    except Exception as e:
        print(f"[Instagram Search Error] {e}")
    
    return results

def extract_instagram_username(url):
    """РР·РІР»РµС‡СЊ username РёР· Instagram URL"""
    match = re.search(r'instagram\.com/([a-zA-Z0-9_.-]+)', url)
    if match:
        username = match.group(1)
        # РСЃРєР»СЋС‡Р°РµРј СЃР»СѓР¶РµР±РЅС‹Рµ РїСѓС‚Рё
        if username not in ['p', 'tv', 'reel', 'stories', 'explore', 'accounts']:
            return username
    return None

# в”Ђв”Ђв”Ђ Twitter/X Search в”Ђв”Ђв”Ђ

def search_twitter_accounts(query, max_results=10, city=None, exclude_urls=None):
    """
    РџРѕРёСЃРє Р°РєРєР°СѓРЅС‚РѕРІ X (Twitter) РїРѕ Р·Р°РїСЂРѕСЃСѓ.
    """
    results = []
    seen = set(exclude_urls or set())
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            search_queries = build_social_queries(query, "twitter", city)
            for pass_idx, mult in enumerate((3, 6, 9), 1):
                if len(results) >= max_results:
                    break
                pass_added = 0

                for search_query in search_queries:
                    if len(results) >= max_results:
                        break

                    raw_results = list(ddgs.text(search_query, max_results=max(30, max_results * mult)))
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
                        pass_added += 1

                        if len(results) >= max_results:
                            break

                if pass_added == 0:
                    break
    except Exception as e:
        print(f"[Twitter Search Error] {e}")
    
    return results

def extract_twitter_username(url):
    """РР·РІР»РµС‡СЊ username РёР· Twitter/X URL"""
    match = re.search(r'(?:twitter|x)\.com/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

# в”Ђв”Ђв”Ђ Social Media Analysis в”Ђв”Ђв”Ђ

def analyze_social_profile(platform, url, screenshot_b64=None):
    """
    РђРЅР°Р»РёР· РїСЂРѕС„РёР»СЏ СЃРѕС†РёР°Р»СЊРЅРѕР№ СЃРµС‚Рё С‡РµСЂРµР· AI
    """
    from modules.common.python.config import Config
    import base64
    import requests as req
    
    # Р¤РѕСЂРјРёСЂСѓРµРј РїСЂРѕРјРїС‚ РґР»СЏ Р°РЅР°Р»РёР·Р°
    if platform == 'youtube':
        prompt = (
            f"РўС‹ СЌРєСЃРїРµСЂС‚ РїРѕ Р°РЅР°Р»РёР·Сѓ YouTube РєР°РЅР°Р»РѕРІ. РџСЂРѕР°РЅР°Р»РёР·РёСЂСѓР№ СЃРєСЂРёРЅС€РѕС‚ РєР°РЅР°Р»Р°: {url}\n\n"
            "РћС†РµРЅРё:\n"
            "1. Р”РР—РђР™Рќ РєР°РЅР°Р»Р° (Р±Р°РЅРЅРµСЂ, Р°РІР°С‚Р°СЂ, РѕС„РѕСЂРјР»РµРЅРёРµ)\n"
            "2. UX (РЅР°РІРёРіР°С†РёСЏ, РѕРїРёСЃР°РЅРёРµ, РїР»РµР№Р»РёСЃС‚С‹)\n\n"
            "Р¤РћР РњРђРў РћРўР’Р•РўРђ:\n"
            "DESIGN: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]\n"
            "UX: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]"
        )
    elif platform == 'instagram':
        prompt = (
            f"РўС‹ СЌРєСЃРїРµСЂС‚ РїРѕ Р°РЅР°Р»РёР·Сѓ Instagram РїСЂРѕС„РёР»РµР№. РџСЂРѕР°РЅР°Р»РёР·РёСЂСѓР№ СЃРєСЂРёРЅС€РѕС‚: {url}\n\n"
            "РћС†РµРЅРё:\n"
            "1. Р”РР—РђР™Рќ (Р°РІР°С‚Р°СЂ, highlights, Р»РµРЅС‚Р°)\n"
            "2. UX (Р±РёРѕ, РЅР°РІРёРіР°С†РёСЏ, РІРѕРІР»РµС‡С‘РЅРЅРѕСЃС‚СЊ)\n\n"
            "Р¤РћР РњРђРў РћРўР’Р•РўРђ:\n"
            "DESIGN: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]\n"
            "UX: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]"
        )
    elif platform == 'twitter':
        prompt = (
            f"РўС‹ СЌРєСЃРїРµСЂС‚ РїРѕ Р°РЅР°Р»РёР·Сѓ X (Twitter) РїСЂРѕС„РёР»РµР№. РџСЂРѕР°РЅР°Р»РёР·РёСЂСѓР№ СЃРєСЂРёРЅС€РѕС‚: {url}\n\n"
            "РћС†РµРЅРё:\n"
            "1. Р”РР—РђР™Рќ (Р±Р°РЅРЅРµСЂ, Р°РІР°С‚Р°СЂ, РѕС„РѕСЂРјР»РµРЅРёРµ)\n"
            "2. UX (Р±РёРѕ, Р·Р°РєСЂРµРїР»С‘РЅРЅС‹Рµ С‚РІРёС‚С‹, РЅР°РІРёРіР°С†РёСЏ)\n\n"
            "Р¤РћР РњРђРў РћРўР’Р•РўРђ:\n"
            "DESIGN: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]\n"
            "UX: [РѕС†РµРЅРєР° 0-10] [РѕРїРёСЃР°РЅРёРµ]"
        )
    else:
        return {'error': 'Unknown platform'}
    
    # Р’С‹Р·С‹РІР°РµРј AI РґР»СЏ Р°РЅР°Р»РёР·Р°
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
            
            # РџР°СЂСЃРёРј РѕС‚РІРµС‚
            return parse_social_analysis_response(content)
        except Exception as e:
            return {'error': str(e)}
    
    return {'error': 'No screenshot provided'}

def parse_social_analysis_response(raw):
    """РџР°СЂСЃРёРЅРі РѕС‚РІРµС‚Р° AI Р°РЅР°Р»РёР·Р° СЃРѕС†СЃРµС‚РµР№"""
    raw = raw.strip()
    
    design_score = 5
    ux_score = 5
    design_text = ""
    ux_text = ""
    
    # РС‰РµРј DESIGN: ...
    design_match = re.search(r'DESIGN\s*[:\-]?\s*(.+?)(?=UX\s*[:\-]|$)', raw, re.DOTALL | re.IGNORECASE)
    ux_match = re.search(r'UX\s*[:\-]?\s*(.+?)$', raw, re.DOTALL | re.IGNORECASE)
    
    if design_match:
        design_text = design_match.group(1).strip()
    if ux_match:
        ux_text = ux_match.group(1).strip()
    
    # РР·РІР»РµРєР°РµРј РѕС†РµРЅРєРё
    def extract_score(text):
        match = re.search(r'(\d+)\s*(?:/|РёР·)\s*10', text)
        if match:
            return min(10, max(0, int(match.group(1))))
        return None
    
    design_score_parsed = extract_score(design_text)
    ux_score_parsed = extract_score(ux_text)
    
    if design_score_parsed is not None:
        design_score = design_score_parsed
    if ux_score_parsed is not None:
        ux_score = ux_score_parsed
    
    # РЈРґР°Р»СЏРµРј РѕС†РµРЅРєРё РёР· С‚РµРєСЃС‚Р°
    design_text = re.sub(r'^\d+\s*(?:/|РёР·)\s*10\s*', '', design_text).strip()
    ux_text = re.sub(r'^\d+\s*(?:/|РёР·)\s*10\s*', '', ux_text).strip()
    
    return {
        'design_score': design_score,
        'ux_score': ux_score,
        'design_text': design_text[:500],
        'ux_text': ux_text[:500],
        'raw_response': raw[:1000]
    }

# в”Ђв”Ђв”Ђ Main Search Function в”Ђв”Ђв”Ђ

def search_social_media(query, platform, city=None, max_results=10):
    """
    Р“Р»Р°РІРЅР°СЏ С„СѓРЅРєС†РёСЏ РїРѕРёСЃРєР° РїРѕ СЃРѕС†РёР°Р»СЊРЅС‹Рј СЃРµС‚СЏРј
    
    Args:
        query: РїРѕРёСЃРєРѕРІС‹Р№ Р·Р°РїСЂРѕСЃ
        platform: 'youtube', 'instagram', 'twitter'
        city: РіРѕСЂРѕРґ (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)
        max_results: РјР°РєСЃРёРјСѓРј СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ
    
    Returns:
        РЎРїРёСЃРѕРє РЅР°Р№РґРµРЅРЅС‹С… РїСЂРѕС„РёР»РµР№
    """
    print(f"[Social Search] РќР°С‡РёРЅР°СЋ РїРѕРёСЃРє: platform='{platform}', query='{query}', city='{city}'")
    
    existing_urls = get_existing_social_urls(platform)
    if existing_urls:
        print(f"[Social Search] {platform}: пропускаю {len(existing_urls)} URL, уже сохранённых в БД")

    if platform == 'youtube':
        results = search_youtube_channels(query, max_results, city, exclude_urls=existing_urls)
    elif platform == 'instagram':
        results = search_instagram_profiles(query, max_results, city, exclude_urls=existing_urls)
    elif platform == 'twitter':
        results = search_twitter_accounts(query, max_results, city, exclude_urls=existing_urls)
    else:
        print(f"[Social Search] РќРµРёР·РІРµСЃС‚РЅР°СЏ РїР»Р°С‚С„РѕСЂРјР°: {platform}")
        return []
    
    print(f"[Social Search] {platform}: РЅР°Р№РґРµРЅРѕ {len(results)} РїСЂРѕС„РёР»РµР№")
    return results

# в”Ђв”Ђв”Ђ Database Functions в”Ђв”Ђв”Ђ
# РџР РРњР•Р§РђРќРР•: Р¤СѓРЅРєС†РёРё save_social_result() Рё get_social_results() Р±С‹Р»Рё РёСЃРїРѕР»СЊР·РѕРІР°РЅС‹ СЂР°РЅРµРµ
# РЅРѕ С‚РµРїРµСЂСЊ СЂРµР·СѓР»СЊС‚Р°С‚С‹ СЃРѕС…СЂР°РЅСЏСЋС‚СЃСЏ РЅР°РїСЂСЏРјСѓСЋ РІ server.py С„СѓРЅРєС†РёРµР№ process_social_search()
# РґР»СЏ РѕР±РµСЃРїРµС‡РµРЅРёСЏ РєРѕРЅСЃРёСЃС‚РµРЅС‚РЅРѕСЃС‚Рё СЃ С‚Р°Р±Р»РёС†РµР№ social_results РІ Р‘Р”

# в”Ђв”Ђв”Ђ CLI Test в”Ђв”Ђв”Ђ

if __name__ == "__main__":
    print("Testing Social Media Search...")
    
    # РўРµСЃС‚ РїРѕРёСЃРєР° YouTube
    print("\n[YouTube] РџРѕРёСЃРє РєР°РЅР°Р»РѕРІ РїСЂРѕ РІРµР±-РґРёР·Р°Р№РЅ...")
    yt_results = search_youtube_channels("web design", max_results=5)
    for r in yt_results:
        print(f"  - {r.get('title', 'N/A')}: {r.get('url', 'N/A')}")
    
    # РўРµСЃС‚ РїРѕРёСЃРєР° Instagram
    print("\n[Instagram] РџРѕРёСЃРє РїСЂРѕС„РёР»РµР№ РїСЂРѕ РґРёР·Р°Р№РЅ...")
    ig_results = search_instagram_profiles("web design studio", max_results=5)
    for r in ig_results:
        print(f"  - {r.get('title', 'N/A')}: {r.get('url', 'N/A')}")
    
    # РўРµСЃС‚ РїРѕРёСЃРєР° Twitter
    print("\n[Twitter] РџРѕРёСЃРє Р°РєРєР°СѓРЅС‚РѕРІ РїСЂРѕ РґРёР·Р°Р№РЅ...")
    tw_results = search_twitter_accounts("web designer", max_results=5)
    for r in tw_results:
        print(f"  - {r.get('title', 'N/A')}: {r.get('url', 'N/A')}")
    
    print("\nвњ“ РўРµСЃС‚ Р·Р°РІРµСЂС€С‘РЅ!")



