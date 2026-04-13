"""Social and YouTube processing/export logic."""

from modules.main.python.core import *
from modules.main.python.analysis import analysis_lock, recover_stale_analysis_lock, take_screenshots


def take_screenshot(url: str):
    """Single-url screenshot adapter for social analysis flow."""
    shots = take_screenshots([url])
    b64, _status = shots.get(url, (None, "not_found"))
    return b64


def save_youtube_results_to_db(results: list, query: str):
    """Сохраняет результаты YouTube трендов для дедупликации между запусками."""
    if not results:
        return 0, 0

    now = datetime.now().isoformat()
    inserted = 0
    updated = 0

    with sqlite3.connect(DB_PATH) as con:
        for result in results:
            video_id = (result.get("video_id", "") or "").strip()
            url = (result.get("url", "") or "").strip()
            if not video_id or not url:
                continue

            existing = con.execute(
                "SELECT 1 FROM youtube_results WHERE video_id=?",
                (video_id,)
            ).fetchone()
            if existing:
                updated += 1
            else:
                inserted += 1

            thumb = result.get("thumbnail_analysis", {}) or {}
            con.execute(
                """
                INSERT INTO youtube_results (
                    video_id, url, title, channel_id, channel_title, channel_url,
                    subscriber_count, views, duration, viral_score, score,
                    query, found_at, analyzed_at,
                    thumbnail_score, thumbnail_quality, clickbait_probability, emotion_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    url=excluded.url,
                    title=excluded.title,
                    channel_id=excluded.channel_id,
                    channel_title=excluded.channel_title,
                    channel_url=excluded.channel_url,
                    subscriber_count=excluded.subscriber_count,
                    views=excluded.views,
                    duration=excluded.duration,
                    viral_score=excluded.viral_score,
                    score=excluded.score,
                    query=excluded.query,
                    found_at=excluded.found_at,
                    analyzed_at=excluded.analyzed_at,
                    thumbnail_score=excluded.thumbnail_score,
                    thumbnail_quality=excluded.thumbnail_quality,
                    clickbait_probability=excluded.clickbait_probability,
                    emotion_score=excluded.emotion_score
                """,
                (
                    video_id,
                    url,
                    result.get("title", ""),
                    result.get("channel_id", ""),
                    result.get("channel_title", ""),
                    result.get("channel_url", ""),
                    result.get("subscriber_count"),
                    result.get("views", 0),
                    result.get("duration"),
                    result.get("viral_score", 0),
                    result.get("score", 0),
                    result.get("query", query),
                    result.get("found_at", now),
                    now,
                    thumb.get("thumbnail_score"),
                    thumb.get("quality"),
                    thumb.get("clickbait_probability"),
                    thumb.get("emotion_score"),
                )
            )
        con.commit()

    return inserted, updated


def process_youtube_trends(query, max_results, filters, sid=None):
    """Обработка поиска трендовых YouTube видео (TubelQ-style)"""
    from modules.chat.python.social_search import search_youtube_trends, analyze_youtube_thumbnail

    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен!", "warn")
        state["running"] = False
        return

    try:
        if sid:
            state["active_sid"] = sid
        emit_status(f"🎬 Ищу трендовые видео по запросу: {query}...", "info")
        videos, yt_stats = search_youtube_trends(query, max_results, filters, return_stats=True)
        if yt_stats:
            emit_status(
                f"📌 YouTube: собрано {yt_stats.get('found', len(videos))}/{yt_stats.get('target', max_results)} | "
                f"из БД: {yt_stats.get('skipped_existing_db', 0)} | "
                f"дубли URL: {yt_stats.get('skipped_duplicate_url', 0)} | "
                f"дубли каналов: {yt_stats.get('skipped_duplicate_channel', 0)}",
                "info"
            )
            emit_status(
                f"📌 Фильтры: нерелевантно {yt_stats.get('skipped_irrelevant', 0)}, "
                f"длительность {yt_stats.get('skipped_duration', 0)}, "
                f"подписчики {yt_stats.get('skipped_subscribers', 0)}, "
                f"errors {yt_stats.get('metadata_errors', 0) + yt_stats.get('query_errors', 0)}",
                "info"
            )
            if yt_stats.get("fallback_unknown_subs_added", 0):
                emit_status(
                    f"ℹ️ Добрано {yt_stats['fallback_unknown_subs_added']} видео с неизвестными подписчиками",
                    "warn"
                )
        unverified_subs = sum(1 for v in videos if v.get("subs_unverified"))
        if unverified_subs:
            emit_status(f"ℹ️ У {unverified_subs} видео подписчики не определены.", "warn")

        if not videos:
            emit_status("⚠️ Видео не найдены", "warn")
            state["running"] = False
            state["phase"] = "done"
            emit_state()
            state["active_sid"] = None
            return

        if len(videos) < max_results:
            emit_status(
                f"⚠️ Собрано {len(videos)} из {max_results} уникальных видео. "
                f"Больше новых релевантных результатов не найдено.",
                "warn"
            )

        emit_status(f"✅ Найдено {len(videos)} видео. Начинаю AI анализ превью...", "info")

        # Отправляем результаты клиенту
        for idx, video in enumerate(videos, 1):
            if state["stop"]:
                break

            state["current_url"] = video["url"]
            emit_state()

            # AI анализ превью
            thumbnail_analysis = None
            thumbnail_data = None
            try:
                # Скачиваем превью
                import requests as req
                thumb_url = video.get("thumbnail", "")
                if thumb_url:
                    resp = req.get(thumb_url, timeout=10)
                    if resp.status_code == 200:
                        import base64
                        screenshot_b64 = base64.b64encode(resp.content).decode()
                        content_type = resp.headers.get("Content-Type", "image/jpeg")
                        thumbnail_data = f"data:{content_type};base64,{screenshot_b64}"
                        thumbnail_analysis = analyze_youtube_thumbnail(video["video_id"], screenshot_b64)
            except Exception as e:
                print(f"[Thumbnail Error] {e}")

            if thumbnail_analysis:
                video["thumbnail_analysis"] = thumbnail_analysis
            # Сохраняем data-uri превью для Excel, чтобы не перекачивать картинку повторно.
            video["thumbnail_data"] = thumbnail_data or ""

            # Эмитим результат
            socketio.emit("youtube_trend_result", {
                "index": idx,
                "total": len(videos),
                "url": video["url"],
                "video_id": video.get("video_id", ""),
                "title": video.get("title", ""),
                "thumbnail": thumbnail_data or "",
                "channel_id": video.get("channel_id", ""),
                "channel_title": video.get("channel_title", ""),
                "channel_url": video.get("channel_url", ""),
                "subscriber_count": video.get("subscriber_count"),
                "views": video.get("views", 0),
                "duration": video.get("duration"),
                "viral_score": video.get("viral_score", 0),
                "score": video.get("score", 0),
                "thumbnail_analysis": thumbnail_analysis
            }, room=state.get("active_sid"))

            state["results"].append(video)
            emit_state()

        inserted, updated = save_youtube_results_to_db(state["results"], query)
        emit_status(
            f"💾 YouTube DB sync: добавлено {inserted}, обновлено {updated}",
            "success"
        )

        emit_status(f"✅ Поиск завершён! Найдено {len(state['results'])} видео.", "success")

    except Exception as e:
        emit_status(f"❌ Ошибка: {e}", "error")
        print(f"[YouTube Trends Error] {e}")

    finally:
        state["running"] = False
        state["phase"] = "done"
        state["city"] = ""
        state["current_url"] = ""
        emit_state()
        state["active_sid"] = None
        if analysis_lock.locked():
            try:
                analysis_lock.release()
            except RuntimeError:
                pass


def process_social_search(query, city, platforms, max_results_per_platform=10):
    """Обработка поиска по соцсетям с AI анализом"""
    # Блокировка чтобы SQLite не блокировался
    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен!", "warn")
        state["running"] = False
        return
    
    from modules.chat.python.social_search import search_social_media, analyze_social_profile

    all_results = []
    expected_total = max_results_per_platform * max(0, len(platforms or []))

    # 1. ПОИСК профилей
    for platform in platforms:
        if state["stop"]:
            break

        emit_status(f"🔍 Ищу на {platform}... Цель: {max_results_per_platform} новых профилей", "info")
        results = search_social_media(query, platform, city, max_results=max_results_per_platform)

        if results:
            emit_status(f"✅ Найдено {len(results)} новых результатов на {platform}", "success")
            if len(results) < max_results_per_platform:
                emit_status(
                    f"⚠️ На {platform} собрано {len(results)} из {max_results_per_platform} новых профилей "
                    f"(остальное уже в БД или нерелевантно)",
                    "warn"
                )
            all_results.extend(results)
        else:
            emit_status(f"⚠️ На {platform} ничего не найдено", "warn")

    if all_results:
        if expected_total and len(all_results) < expected_total:
            emit_status(
                f"⚠️ Собрано {len(all_results)} из {expected_total} новых профилей. "
                f"Остальное уже было в БД или не прошло фильтры.",
                "warn"
            )
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
        try:
            save_social_to_excel(all_results)
        except Exception as e:
            print(f"[ERROR] Social Excel export failed: {e}")
            emit_status(f"Social Excel write error: {e}", "error")
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
            }, room=state.get("active_sid"))
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
    state["active_sid"] = None
    if analysis_lock.locked():
        try:
            analysis_lock.release()
        except RuntimeError:
            pass

SOCIAL_EXCEL_PATH = REPORTS_DIR / "social_results.xlsx"
YOUTUBE_EXCEL_PATH = REPORTS_DIR / "youtube_trends.xlsx"

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


def save_youtube_to_excel(results: list, thumbnail_quality_filter=None):
    """
    Сохраняет результаты YouTube трендов в Excel с изображениями превью
    
    Args:
        results: список видео
        thumbnail_quality_filter: 'good', 'bad', или None (все)
    """
    if not results:
        return {
            "ok": False,
            "error": "no_results",
            "message": "Нет результатов для сохранения",
            "saved_count": 0,
            "images_added": 0,
        }

    filepath = YOUTUBE_EXCEL_PATH

    try:
        import io
        import requests as req
        from openpyxl.drawing.image import Image as XLImage

        source_total = len(results)

        # Фильтруем по качеству превью если нужно
        if thumbnail_quality_filter:
            filtered = []
            for r in results:
                ta = r.get('thumbnail_analysis', {})
                quality = ta.get('quality', 'unknown').lower()
                clickbait = ta.get('clickbait_probability', 'unknown').lower()
                thumbnail_score = ta.get('thumbnail_score', 5)
                
                if thumbnail_quality_filter == 'good':
                    # Хорошие: качество >= 6 ИЛИ кликбейт низкий/средний
                    if quality == 'high' or (thumbnail_score >= 6 and clickbait != 'high'):
                        filtered.append(r)
                elif thumbnail_quality_filter == 'bad':
                    # Плохие: качество low ИЛИ кликбейт high ИЛИ score < 5
                    if quality == 'low' or clickbait == 'high' or thumbnail_score < 5:
                        filtered.append(r)
                else:
                    # Все без фильтра
                    filtered.append(r)
            
            results = filtered
            emit_status(f"🔍 Фильтр '{thumbnail_quality_filter}': осталось {len(results)} из {source_total} видео", "info")

        if not results:
            msg = "После фильтрации не осталось видео для сохранения"
            emit_status(f"⚠️ {msg}", "warn")
            return {
                "ok": False,
                "error": "no_results_after_filter",
                "message": msg,
                "saved_count": 0,
                "images_added": 0,
            }

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "YouTube Trends"

        # Заголовки
        hf = PatternFill("solid", fgColor="FF0000")
        hfont = Font(bold=True, color="FFFFFF", size=11)
        
        headers = [
            "#", "Превью", "Название", "URL", "Канал", "Channel ID", "Подписчики",
            "Просмотры", "Длительность", "Viral Score", "Score",
            "Оценка превью", "Качество", "Clickbait", "Эмоции",
            "Итог анализа превью", "Дата"
        ]
        widths = [5, 20, 42, 48, 24, 22, 14, 14, 12, 12, 10, 12, 12, 12, 10, 50, 12]

        ws.append([""] * len(headers))
        ws.merge_cells(f"A1:{chr(64+len(headers))}1")
        tc = ws.cell(row=1, column=1)
        tc.value = f"🎬 TISH SEARCH — YouTube Trends"
        tc.font = Font(bold=True, size=13, color="FFFFFF")
        tc.alignment = Alignment(horizontal="center", vertical="center")
        tc.fill = PatternFill("solid", fgColor="FF0000")
        ws.row_dimensions[1].height = 32

        for col, (h, w) in enumerate(zip(headers, widths), 1):
            c = ws.cell(row=2, column=col, value=h)
            c.font = hfont
            c.fill = hf
            c.border = Border(left=Side(style="thin", color="CCCCCC"), right=Side(style="thin", color="CCCCCC"), top=Side(style="thin", color="CCCCCC"), bottom=Side(style="thin", color="CCCCCC"))
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[c.column_letter].width = w
        ws.row_dimensions[2].height = 28

        thin = Side(style="thin", color="CCCCCC")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        wrap = Alignment(wrap_text=True, vertical="top")

        start_row = 3
        images_added = 0

        for i, result in enumerate(results, 1):
            row = start_row + i - 1
            
            # Подготавливаем превью: сначала используем уже сохранённый data-uri,
            # затем fallback на URL если data-uri отсутствует.
            thumbnail_img = None
            thumb_data = result.get("thumbnail_data", "")
            if isinstance(thumb_data, str) and thumb_data.startswith("data:image"):
                try:
                    _meta, b64_data = thumb_data.split(",", 1)
                    raw_bytes = base64.b64decode(b64_data)
                    if raw_bytes:
                        thumbnail_img = XLImage(io.BytesIO(raw_bytes))
                except Exception as e:
                    print(f"[Excel Thumb Decode Error] {e}")

            if thumbnail_img is None:
                thumb_url = result.get("thumbnail", "")
                try:
                    if thumb_url:
                        resp = req.get(thumb_url, timeout=10)
                        if resp.status_code == 200:
                            thumbnail_img = XLImage(io.BytesIO(resp.content))
                except Exception as e:
                    print(f"[Excel Thumb Error] {e}")

            if thumbnail_img:
                thumbnail_img.width = 120
                thumbnail_img.height = 68

            # Номер
            ws.cell(row=row, column=1, value=i).alignment = Alignment(horizontal="center")
            
            # Превью (вставляем изображение)
            if thumbnail_img:
                cell = ws.cell(row=row, column=2)
                ws.add_image(thumbnail_img, f'B{row}')
                images_added += 1
            
            # Название
            ws.cell(row=row, column=3, value=result.get("title", "")).alignment = wrap
            
            # URL
            url_cell = ws.cell(row=row, column=4, value=result.get("url", ""))
            url_cell.font = Font(color="0563C1", underline="single")
            url_cell.alignment = Alignment(vertical="top")
            
            # Канал
            ws.cell(row=row, column=5, value=result.get("channel_title", "")).alignment = wrap
            ws.cell(row=row, column=6, value=result.get("channel_id", "")).alignment = Alignment(horizontal="center")

            subscriber_count = result.get("subscriber_count")
            ws.cell(row=row, column=7, value=subscriber_count if subscriber_count is not None else "—").alignment = Alignment(horizontal="center")

            # Просмотры
            views = result.get("views", 0)
            ws.cell(row=row, column=8, value=views).alignment = Alignment(horizontal="center")
            
            # Длительность
            duration = result.get("duration")
            if duration:
                mins = int(duration)
                secs = int((duration - mins) * 60)
                ws.cell(row=row, column=9, value=f"{mins}:{secs:02d}").alignment = Alignment(horizontal="center")
            else:
                ws.cell(row=row, column=9, value="—").alignment = Alignment(horizontal="center")
            
            # Viral Score
            ws.cell(row=row, column=10, value=result.get("viral_score", 0)).alignment = Alignment(horizontal="center")
            
            # Score
            ws.cell(row=row, column=11, value=result.get("score", 0)).alignment = Alignment(horizontal="center")
            
            # AI Анализ превью
            ta = result.get("thumbnail_analysis", {})
            quality = ta.get("quality", "unknown")
            clickbait = ta.get("clickbait_probability", "unknown")
            emotion = ta.get("emotion_score", "—")
            
            # Качество с цветом
            ws.cell(row=row, column=12, value=ta.get("thumbnail_score", "—")).alignment = Alignment(horizontal="center")

            quality_cell = ws.cell(row=row, column=13, value=quality)
            quality_cell.alignment = Alignment(horizontal="center")
            if quality == "high":
                quality_cell.fill = PatternFill("solid", fgColor="D4EDDA")
            elif quality == "low":
                quality_cell.fill = PatternFill("solid", fgColor="F8D7DA")
            
            # Clickbait с цветом
            clickbait_cell = ws.cell(row=row, column=14, value=clickbait)
            clickbait_cell.alignment = Alignment(horizontal="center")
            if clickbait == "high":
                clickbait_cell.fill = PatternFill("solid", fgColor="F8D7DA")
            elif clickbait == "low":
                clickbait_cell.fill = PatternFill("solid", fgColor="D4EDDA")
            
            # Эмоции
            ws.cell(row=row, column=15, value=emotion).alignment = Alignment(horizontal="center")

            analysis_summary = ta.get("thumbnail_analysis", "")[:1000] if ta else ""
            ws.cell(row=row, column=16, value=analysis_summary).alignment = wrap
            
            # Дата
            ws.cell(row=row, column=17, value=result.get("found_at", "")[:10] if result.get("found_at") else datetime.now().strftime("%Y-%m-%d")).alignment = Alignment(horizontal="center")
            
            for col in range(1, 18):
                c = ws.cell(row=row, column=col)
                if col not in [2, 13, 14]:  # Пропускаем ячейки с картинками и раскрашенные
                    c.border = border
            
            ws.row_dimensions[row].height = 70

        try:
            wb.save(str(filepath))
            emit_status(f"📊 YouTube Excel сохранён: {filepath.name} ({len(results)} видео, превью: {images_added})", "success")
            return {
                "ok": True,
                "path": str(filepath),
                "saved_count": len(results),
                "images_added": images_added,
            }
        except PermissionError:
            msg = "Файл Excel открыт. Закройте и попробуйте снова."
            emit_status(f"⚠️ {msg}", "warn")
            return {
                "ok": False,
                "error": "permission_denied",
                "message": msg,
                "saved_count": len(results),
                "images_added": images_added,
            }
        except Exception as e:
            msg = f"Ошибка сохранения: {e}"
            emit_status(f"❌ {msg}", "error")
            return {
                "ok": False,
                "error": "save_failed",
                "message": msg,
                "saved_count": len(results),
                "images_added": images_added,
            }

    except Exception as e:
        msg = f"Ошибка создания YouTube Excel: {e}"
        emit_status(f"❌ {msg}", "error")
        return {
            "ok": False,
            "error": "excel_build_failed",
            "message": msg,
            "saved_count": 0,
            "images_added": 0,
        }
