"""Main analysis pipeline extracted from server.py."""

from modules.main.python.core import *
from modules.profile.python.activity import track_user_activity
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
        if analysis_lock.locked():
            try:
                analysis_lock.release()
            except RuntimeError:
                pass
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
        if analysis_lock.locked():
            try:
                analysis_lock.release()
            except RuntimeError:
                pass
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
            needs_redesign = design_score <= 5 or ux_score <= 5

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
    if analysis_lock.locked():
        try:
            if analysis_lock.locked():
                try:
                    analysis_lock.release()
                except RuntimeError:
                    pass
        except RuntimeError:
            pass


# ──────────────────────────────────────────────
# ПОИСК
# ──────────────────────────────────────────────
def search_urls(
    queries_with_categories: list,
    city: str,
    label: str,
    exclude_domains: set = None,
    skip_db_check: bool = False,
    force_mode: str = None,
    target_count: int = None,
) -> list:
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

    db_domains = set()
    if not skip_db_check:
        try:
            with sqlite3.connect(DB_PATH) as con:
                db_domains = {row[0] for row in con.execute("SELECT domain FROM sites").fetchall()}
            emit_status(f"[{label}] В БД уже {len(db_domains)} доменов — не будут засчитаны в найденные", "info")
        except Exception as e:
            emit_status(f"[{label}] ⚠ Не удалось загрузить домены БД: {str(e)[:80]}", "warn")
            db_domains = set()
    
    # Нормализуем входные данные
    normalized_queries = []
    for item in queries_with_categories:
        if isinstance(item, tuple):
            query, category = item
            normalized_queries.append((query, category))
        else:
            # Если просто строка запроса
            normalized_queries.append((item, "Другое"))
    
    max_passes = 10

    for pass_idx in range(max_passes):
        if state["stop"]:
            break
        if target_count and len(found) >= target_count:
            break

        pass_added = 0
        fetch_mult = search_mult * (pass_idx + 1)
        emit_status(f"[{label}] Проход {pass_idx + 1}/{max_passes}: углубляю поиск (x{fetch_mult})", "info")

        for q, category in normalized_queries:
            if state["stop"]:
                break
            if target_count and len(found) >= target_count:
                break

            local_added = 0
            max_local = mpq
            if target_count:
                max_local = max(0, min(mpq, target_count - len(found)))
            if max_local <= 0:
                break

            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(q, max_results=mpq * fetch_mult))
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

                        # Уже есть в БД — не считаем найденным и продолжаем искать дальше
                        if not skip_db_check and domain in db_domains:
                            continue

                        seen_urls.add(url)
                        seen_domains.add(domain)
                        found.append({"url": url, "category": category})
                        local_added += 1
                        pass_added += 1

                        if local_added >= max_local:
                            break
                        if target_count and len(found) >= target_count:
                            break

                if local_added > 0:
                    emit_status(f"[{label}] «{q}» → +{local_added} новых URL ({category}) | всего: {len(found)}", "success")
                elif pass_idx == max_passes - 1:
                    emit_status(f"[{label}] «{q}» → 0 новых URL", "warn")

            except Exception as e:
                err_str = str(e).lower()
                if "no results" in err_str or "request" in err_str:
                    pass
                else:
                    emit_status(f"[{label}] ⚠ Ошибка «{q}»: {str(e)[:50]}", "warn")

            emit_state()
            time.sleep(0.2)

        if pass_added == 0:
            emit_status(f"[{label}] Новых ссылок в этом проходе не найдено, прекращаю добор.", "warn")
            break

    if target_count and len(found) < target_count:
        emit_status(
            f"[{label}] Собрано {len(found)} из {target_count} уникальных новых сайтов. "
            f"Дальше релевантных новых ссылок не найдено.",
            "warn"
        )

    if target_count:
        return found[:target_count]
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

    if isinstance(raw, str) and raw.startswith("Timeout:"):
        log_event(
            "site_analysis_timeout",
            level="error",
            url=url,
            domain=get_domain(url),
            idx=idx,
            total=total,
            model=settings.get("vision_model"),
        )
    elif isinstance(raw, str) and raw.startswith("Нет соединения"):
        log_event(
            "site_analysis_connection_error",
            level="error",
            url=url,
            domain=get_domain(url),
            idx=idx,
            total=total,
            ollama_url=settings.get("ollama_url"),
        )

    # Fallback если ответ не парсится правильно
    if design.startswith("Нет ответа") or design.startswith("Ошибка"):
        design = raw[:300] if raw else "Не удалось проанализировать дизайн"
        design_score = 5  # дефолт
    if ux.startswith("Нет"):
        ux = raw[300:600] if len(raw) > 300 else "Не удалось проанализировать UX"
        ux_score = 5  # дефолт

    log_event(
        "site_analysis_result",
        url=url,
        domain=get_domain(url),
        idx=idx,
        total=total,
        category=category,
        site_type=site_type,
        design_score=design_score,
        ux_score=ux_score,
    )

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
    
    target_total = settings["max_large"] + settings["max_niche"]
    log_event(
        "city_process_start",
        city=city,
        is_recheck=is_recheck,
        target_total=target_total,
        max_large=settings.get("max_large"),
        max_niche=settings.get("max_niche"),
    )
    prefix = "🔄 " if is_recheck else "🏙 "
    goal_msg = (
        f"{prefix}Повторный анализ «{city}»"
        if is_recheck else
        f"{prefix}Начинаю «{city}» | Цель: {target_total} новых уникальных сайтов"
    )
    emit_status(goal_msg, "info")
    emit_state()

    # 1. Поиск крупных сайтов
    emit_status(f"📦 Агент 2: крупные сайты (цель: {settings['max_large']})...", "info")
    large = search_urls(
        get_large_queries(city),
        city,
        "А2",
        exclude_domains=set(),
        skip_db_check=is_recheck,
        target_count=settings["max_large"],
    )[:settings["max_large"]]
    state["found_urls"] += [s["url"] for s in large]
    emit_status(f"✅ Крупных новых: {len(large)}/{settings['max_large']}", "success")
    
    # АДАПТИВНАЯ ЛОГИКА: если крупных сайтов мало - переключаемся на более мягкий режим для нишевых
    adapt_mode = None
    if len(large) < settings["max_large"] // 2:  # Если нашли менее половины ожидаемого
        emit_status(f"📊 Недостаточно крупных сайтов ({len(large)}/{settings['max_large']//2}), переключаемся на LENIENT для нишевых", "warn")
        adapt_mode = "LENIENT"

    if not state["stop"]:
        niche_target = max(0, target_total - len(large))
        emit_status(f"🔬 Агент 3: нишевые сайты (цель добора: {niche_target})...", "info")
        ld = {get_domain(u["url"]) for u in large}
        niche = search_urls(
            get_niche_queries(city),
            city,
            "А3",
            exclude_domains=ld,
            skip_db_check=is_recheck,
            force_mode=adapt_mode,
            target_count=niche_target,
        )[:niche_target]
        state["found_urls"] += [s["url"] for s in niche]
        emit_status(f"✅ Нишевых новых: {len(niche)}/{niche_target}", "success")
    else:
        niche = []

    all_sites = (
        [{"url": s["url"], "type": "Крупный", "category": s["category"]} for s in large] +
        [{"url": s["url"], "type": "Нишевый", "category": s["category"]} for s in niche]
    )
    if len(all_sites) > target_total:
        all_sites = all_sites[:target_total]
    state["found_urls"] = [s["url"] for s in all_sites]
    if not is_recheck and len(all_sites) < target_total:
        emit_status(
            f"⚠️ Найдено {len(all_sites)} из {target_total} новых уникальных сайтов. "
            f"Доступных новых ссылок больше не найдено.",
            "warn"
        )
    emit_state()

    if not all_sites:
        emit_status(f"⚠ Новых сайтов для «{city}» не найдено (возможно все уже в БД)", "warn")
        log_event("city_process_no_sites", level="warn", city=city, is_recheck=is_recheck)
        return

    if state["stop"]:
        log_event("city_process_stopped_before_analysis", level="warn", city=city, is_recheck=is_recheck)
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
            log_event(
                "city_process_stop_break",
                level="warn",
                city=city,
                processed=len(state["results"]),
                total=total,
            )
            break
        url  = site["url"]
        state["current_url"] = url
        log_event(
            "city_process_site_start",
            city=city,
            idx=idx,
            total=total,
            url=url,
            category=site.get("category"),
            site_type=site.get("type"),
        )
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
        socketio.emit("result", result, room=state.get("active_sid"))
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
        socketio.emit("done", {"city": city, "count": len(valid)}, room=state.get("active_sid"))
    else:
        print(f"[DEBUG process_city] ВНИМАНИЕ: Нет валидных результатов для сохранения!")
        emit_status(f"⚠️ Нет валидных результатов для сохранения (может быть ошибка анализа)", "warn")

    s = state["elapsed_sec"]
    emit_status(
        f"✅ «{city}» завершён за {s//60}м {s%60:02d}с | "
        f"Проанализировано: {len(valid)} | Пропущено: {state['skipped']}",
        "success"
    )
    log_event(
        "city_process_done",
        city=city,
        elapsed_sec=s,
        analyzed_valid=len(valid),
        analyzed_total=len(state["results"]),
        skipped=state["skipped"],
    )


# ──────────────────────────────────────────────
# ГЛАВНЫЙ ПАЙПЛАЙН — обрабатывает очередь
# ──────────────────────────────────────────────
# Глобальная блокировка чтобы SQLite не блокировался
analysis_lock = threading.Lock()

def recover_stale_analysis_lock():
    """Release stuck analysis lock when state says nothing is running."""
    if state.get("running") and not analysis_lock.locked():
        state["running"] = False
        state["phase"] = "idle"
        state["current_url"] = ""
    if state.get("running"):
        return False
    if not analysis_lock.locked():
        return False
    try:
        if analysis_lock.locked():
            try:
                analysis_lock.release()
            except RuntimeError:
                pass
        print("[RECOVERY] Released stale analysis_lock")
        log_event("analysis_lock_recovered", level="warn")
        return True
    except RuntimeError:
        log_event("analysis_lock_recover_failed", level="error")
        return False

def run_queue(user_id=None, username="user"):
    # Проверяем что нет другого анализа
    if not analysis_lock.acquire(blocking=False):
        emit_status("⚠️ Анализ уже запущен! Дождитесь завершения.", "warn")
        log_event(
            "queue_start_blocked",
            level="warn",
            reason="analysis_lock_busy",
            user_id=user_id,
            username=username,
        )
        state["running"] = False
        return
    
    try:
        state["running"] = True
        state["stop"]    = False
        log_event(
            "queue_start",
            user_id=user_id,
            username=username,
            queue=list(state.get("queue", [])),
        )

        # Отслеживаем активность
        if user_id:
            track_user_activity(user_id, username, 'Running queue')

        emit_state()

        while state["queue"] and not state["stop"]:
            city = state["queue"].pop(0)
            state["queue_done"].append(city)
            log_event(
                "queue_city_dequeued",
                city=city,
                queue_left=list(state.get("queue", [])),
                queue_done=list(state.get("queue_done", [])),
            )
            emit_state()
            try:
                process_city(city, is_recheck=False)
            except Exception as e:
                emit_status(f"❌ Ошибка при обработке «{city}»: {e}", "error")
                log_event("queue_city_error", level="error", city=city, error=str(e))

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
            log_event(
                "queue_done",
                db_total=st.get("total"),
                db_cities=st.get("cities"),
                queue_done=list(state.get("queue_done", [])),
            )
        else:
            emit_status("⛔ Очередь остановлена.", "warn")
            log_event(
                "queue_stopped",
                level="warn",
                queue_left=list(state.get("queue", [])),
                queue_done=list(state.get("queue_done", [])),
                current_url=state.get("current_url"),
            )
        emit_state()
        state["active_sid"] = None
    finally:
        if analysis_lock.locked():
            try:
                analysis_lock.release()
            except RuntimeError:
                pass
        log_event("queue_finally_release_lock", running=state.get("running"), stop=state.get("stop"))


# ──────────────────────────────────────────────
# FLASK ROUTES
