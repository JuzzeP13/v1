const socket = io();
let firstResult = true;
const chips = {};
let currentLang = localStorage.getItem("tish-lang") || "ru";
let translations = {};

const UI_TEXT = {
  ru: {
    appTitle: "TISH SEARCH v4",
    appSubtitle: "Multi-Agent Site Analyzer v4",
    connected: "Подключено",
    disconnected: "Откл",
    connecting: "Подкл...",
    waiting: "Ожидание",
    idle: "Ожидание",
    searching: "Поиск",
    analyzing: "Анализ",
    rechecking: "Перепроверка",
    done: "Готово",
    stopped: "Остановлено",
    searchTypeSites: "🌐 Сайты",
    searchTypeSocial: "📱 Соцсети",
    searchTypeProducts: "🛍️ Товары/Услуги",
    progWaiting: "ожидание",
    curWaiting: "Ожидание...",
    curStopped: "⛔ Остановлено",
    curDone: "✅ Завершено",
    currentScan: "Сканирую:",
    waitingResults: "Жду результаты...",
    waitingSocial: "Жду результаты поиска по соцсетям...",
    waitingProducts: "Жду результаты поиска товаров/услуг...",
    waitingRecheck: "Жду результаты перепроверки...",
    noExamples: "Нет примеров",
    noModels: "НЕТ ДОСТУПНЫХ МОДЕЛЕЙ",
    modelsLoading: "Загрузка моделей...",
    modelLoadError: "Ошибка загрузки",
    fillAllFields: "Заполни все поля!",
    fillScores: "Введи оценки для дизайна и UX!",
    enterSearchQuery: "Введи поисковый запрос!",
    choosePlatform: "Выбери хотя бы одну платформу!",
    noSitesForRecheck: "В БД нет сайтов для перепроверки!",
    recheckPrompt: count => `В БД ${count} сайтов.\n\nСколько сайтов перепроверить? (1-${Math.min(100, count)})`,
    invalidRange: max => `Введи число от 1 до ${max}`,
    cityHistory: "История городов",
    queueEmpty: "Добавьте города для анализа",
    now: "сейчас",
    saveScores: "💾 Сохранить оценки",
    goodBtn: "👍 Хороший",
    badBtn: "👎 Плохой",
    designLabel: "🎨 Дизайн (0-10)",
    uxLabel: "👤 UX (0-10)",
    noDescription: "Описание отсутствует",
    noTitle: "Заголовок отсутствует",
    domainTypeLarge: "Крупный",
    domainTypeNiche: "Нишевый"
  },
  en: {
    appTitle: "TISH SEARCH v4",
    appSubtitle: "Multi-Agent Site Analyzer v4",
    connected: "Connected",
    disconnected: "Off",
    connecting: "Conn...",
    waiting: "Waiting",
    idle: "Waiting",
    searching: "Search",
    analyzing: "Analysis",
    rechecking: "Recheck",
    done: "Done",
    stopped: "Stopped",
    searchTypeSites: "🌐 Websites",
    searchTypeSocial: "📱 Social Media",
    searchTypeProducts: "🛍️ Products/Services",
    progWaiting: "waiting",
    curWaiting: "Waiting...",
    curStopped: "⛔ Stopped",
    curDone: "✅ Done",
    currentScan: "Scanning:",
    waitingResults: "Waiting for results...",
    waitingSocial: "Waiting for social search results...",
    waitingProducts: "Waiting for product/service results...",
    waitingRecheck: "Waiting for recheck results...",
    noExamples: "No examples",
    noModels: "NO MODELS AVAILABLE",
    modelsLoading: "Loading models...",
    modelLoadError: "Loading error",
    fillAllFields: "Fill in all fields!",
    fillScores: "Enter design and UX scores!",
    enterSearchQuery: "Enter search query!",
    choosePlatform: "Choose at least one platform!",
    noSitesForRecheck: "There are no sites in DB for recheck!",
    recheckPrompt: count => `There are ${count} sites in DB.\n\nHow many sites should be rechecked? (1-${Math.min(100, count)})`,
    invalidRange: max => `Enter a number from 1 to ${max}`,
    cityHistory: "City history",
    queueEmpty: "Add cities for analysis",
    now: "now",
    saveScores: "💾 Save scores",
    goodBtn: "👍 Good",
    badBtn: "👎 Bad",
    designLabel: "🎨 Design (0-10)",
    uxLabel: "👤 UX (0-10)",
    noDescription: "Description is missing",
    noTitle: "Title is missing",
    domainTypeLarge: "Large",
    domainTypeNiche: "Niche"
  }
};

function uiText(key, fallback = "") {
  return UI_TEXT[currentLang]?.[key] ?? fallback;
}

function deepGet(obj, path) {
  return path.split(".").reduce((acc, part) => acc && acc[part], obj);
}

function t(path, fallback = "") {
  return deepGet(translations, path) ?? fallback;
}

async function loadTranslations(lang) {
  try {
    const response = await fetch(`/api/translations/${lang}`);
    if (!response.ok) throw new Error("translation fetch failed");
    translations = await response.json();
  } catch (e) {
    translations = {};
    console.error("[i18n] translation load failed:", e);
  }
}

function applyTranslations() {
  document.documentElement.lang = currentLang;
  document.title = t("index.page_title", "TISH SEARCH v4");

  // Update all elements with data-i18n attribute
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const translated = t(key, el.textContent);
    if (translated && translated !== key) {
      el.textContent = translated;
    }
  });

  // Update all elements with data-i18n-placeholder attribute
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    const translated = t(key, el.getAttribute("placeholder"));
    if (translated && translated !== key) {
      el.setAttribute("placeholder", translated);
    }
  });

  // Update lang buttons
  document.getElementById("lang-ru").style.background = currentLang === "ru" ? "rgba(0,212,255,.14)" : "transparent";
  document.getElementById("lang-en").style.background = currentLang === "en" ? "rgba(0,212,255,.14)" : "transparent";
  document.getElementById("lang-ru").style.color = currentLang === "ru" ? "var(--cyan)" : "var(--text2)";
  document.getElementById("lang-en").style.color = currentLang === "en" ? "var(--cyan)" : "var(--text2)";

  // Update phase badge
  const pbadge = document.getElementById("pbadge");
  renderPhaseBadge(pbadge.dataset.phase || "idle", pbadge.dataset.stopped === "true");

  // Re-render queue
  renderQueue(window.__lastQueue || [], window.__lastQueueDone || [], window.__lastCurrentCity || "");
}

async function setLanguage(lang) {
  currentLang = lang === "en" ? "en" : "ru";
  localStorage.setItem("tish-lang", currentLang);
  await loadTranslations(currentLang);
  applyTranslations();
}

// ── connect ──
socket.on("connect", () => {
  document.getElementById("cdot").className = "dot on";
  document.getElementById("clabel").textContent = uiText("connected");
  loadAvailableModels();
  loadExamples();
  loadSubscriptionInfo();
});

// Автоматический вход через токен главного сайта (если есть в URL)
function tryLoginFromMainSite() {
  // Проверяем токен в URL (?token=xxx или ?api_token=xxx)
  const urlParams = new URLSearchParams(window.location.search);
  const apiToken = urlParams.get('token') || urlParams.get('api_token');
  
  if (apiToken) {
    fetch('/auth/login-from-main-site', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_token: apiToken })
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        console.log('[AUTH] Успешный вход через главный сайт:', data.user.username);
        // Убираем токен из URL
        window.history.replaceState({}, document.title, window.location.pathname);
        // Перезагружаем страницу
        window.location.reload();
      } else {
        console.error('[AUTH] Ошибка входа:', data.error);
      }
    })
    .catch(e => console.error('[AUTH] Ошибка:', e));
  }
}

// Проверяем токен при загрузке страницы
tryLoginFromMainSite();

// Проверяем cookie с главного сайта
function checkMainSiteCookie() {
  const mainSiteToken = document.cookie
    .split('; ')
    .find(row => row.startsWith('main_site_token='));
  
  if (mainSiteToken) {
    const token = mainSiteToken.split('=')[1];
    fetch('/auth/login-from-main-site', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_token: token })
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        console.log('[AUTH] Успешный вход через cookie:', data.user.username);
        window.location.reload();
      }
    })
    .catch(e => console.error('[AUTH] Ошибка:', e));
  }
}

checkMainSiteCookie();

// ── ПОДПИСКА ──
function loadSubscriptionInfo() {
  fetch("/auth/api/me/subscription")
    .then(r => {
      if (r.status === 401) {
        // Не авторизован - показываем вход/регистрацию
        document.getElementById("login-link").style.display = "inline-block";
        document.getElementById("register-link").style.display = "inline-block";
        document.getElementById("subscription-link").style.display = "none";
        document.getElementById("logout-btn").style.display = "none";
        document.getElementById("subscription-badge").style.display = "none";
        document.getElementById("subscription-panel").style.display = "none";
        return null;
      }
      return r.json();
    })
    .then(data => {
      if (!data) return;

      // Авторизован - показываем подписку
      document.getElementById("login-link").style.display = "none";
      document.getElementById("register-link").style.display = "none";
      document.getElementById("subscription-link").style.display = "inline-block";
      document.getElementById("logout-btn").style.display = "inline-block";
      document.getElementById("subscription-badge").style.display = "block";
      document.getElementById("subscription-panel").style.display = "block";

      // Обновляем бейдж в шапке
      const badge = document.getElementById("subscription-badge");
      const planColors = {
        'Basic': { bg: 'rgba(0,255,136,.12)', color: 'var(--green)', border: 'rgba(0,255,136,.3)' },
        'Pro': { bg: 'rgba(0,212,255,.12)', color: 'var(--cyan)', border: 'rgba(0,212,255,.3)' },
        'Enterprise': { bg: 'rgba(217,70,239,.12)', color: 'var(--purple)', border: 'rgba(217,70,239,.3)' },
      };
      const colors = planColors[data.plan] || planColors['Basic'];
      badge.style.background = colors.bg;
      badge.style.color = colors.color;
      badge.style.borderColor = colors.border;
      badge.textContent = data.plan.toUpperCase();

      // Обновляем панель подписки
      document.getElementById("sub-plan-name").textContent = data.plan_ru || data.plan;
      document.getElementById("sub-status").textContent = data.is_active ? "✓ Активна" : "❌ Истекла";
      document.getElementById("sub-status").style.color = data.is_active ? "var(--green)" : "var(--red)";

      // Лимиты
      const citiesText = data.limits.max_cities_per_day > 0
        ? `${data.usage.cities_today}/${data.limits.max_cities_per_day}`
        : "∞ Без ограничений";
      document.getElementById("sub-cities-today").textContent = citiesText;

      const sitesText = data.limits.max_sites_per_city > 0
        ? data.limits.max_sites_per_city
        : "∞";
      document.getElementById("sub-sites-limit").textContent = sitesText;

      document.getElementById("sub-parallel-limit").textContent = data.limits.max_parallel;
      document.getElementById("sub-export").textContent = data.limits.can_export ? "✅ Да" : "❌ Нет";

      // Обновляем лимиты в настройках
      updateParallelLimits(data.limits.max_parallel);
    })
    .catch(e => console.error("[ERROR] Failed to load subscription info:", e));
}

function logoutUser() {
  fetch("/auth/logout")
    .then(() => {
      window.location.reload();
    });
}

// Обновить настройки параллелизма на основе подписки
function updateParallelLimits(maxParallel) {
  const input = document.getElementById("s-parallel");
  if (input) {
    input.max = maxParallel;
    if (parseInt(input.value) > maxParallel) {
      input.value = maxParallel;
    }
  }
}

socket.on("disconnect", () => {
  document.getElementById("cdot").className = "dot";
  document.getElementById("clabel").textContent = uiText("disconnected");
});

// ── МОДЕЛИ ──
socket.on("models_available", d => {
  const select = document.getElementById("s-model");
  const models = d.models || [];
  select.innerHTML = "";
  
  if (models.length === 0) {
    select.innerHTML = `<option value="" disabled selected>${uiText("noModels")}</option>`;
    return;
  }
  
  models.forEach(model => {
    const opt = document.createElement("option");
    opt.value = model;
    opt.textContent = model;
    // По умолчанию выбираем LLaVA (быстрее для скриншотов)
    if (model.includes("llava") || model.includes("qwen") || model.includes("vision")) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });
  
  console.log(currentLang === "ru" ? "[OK] Модели загружены:" : "[OK] Models loaded:", models);
});

function loadAvailableModels() {
  fetch("/api/models")
    .then(r => r.json())
    .then(d => {
      const select = document.getElementById("s-model");
      const models = d.models || [];
      select.innerHTML = "";
      
      if (models.length === 0) {
        select.innerHTML = `<option value="" disabled selected>${uiText("noModels")}</option>`;
        select.innerHTML = `<option value="" disabled selected>${uiText("noModels")}</option>`;
        return;
      }
      
      models.forEach(model => {
        const opt = document.createElement("option");
        opt.value = model;
        opt.textContent = model;
        // По умолчанию выбираем LLaVA (быстрее для скриншотов)
        if (model.includes("llava") || model.includes("qwen") || model.includes("vision")) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
    })
    .catch(e => {
      console.error(`[ERROR] ${currentLang === "ru" ? "Не удалось загрузить модели" : "Failed to load models"}:`, e);
      document.getElementById("s-model").innerHTML = `<option value="" disabled selected>${uiText("modelLoadError")}</option>`;
    });
}

function loadExamples() {
  const goodDiv = document.getElementById("examples-good");
  const badDiv = document.getElementById("examples-bad");
  if (!goodDiv || !badDiv) {
    return;
  }

  fetch("/api/examples")
    .then(r => r.json())
    .then(d => {
      if (d.good && d.good.length > 0) {
        goodDiv.innerHTML = d.good.map(e => `<div style="margin-bottom:4px">• ${new URL(e.url).hostname}</div>`).join("");
      } else {
        goodDiv.innerHTML = `<div style="color:var(--text3)">${uiText("noExamples")}</div>`;
      }

      if (d.bad && d.bad.length > 0) {
        badDiv.innerHTML = d.bad.map(e => `<div style="margin-bottom:4px">• ${new URL(e.url).hostname}</div>`).join("");
      } else {
        badDiv.innerHTML = `<div style="color:var(--text3)">${uiText("noExamples")}</div>`;
      }
    })
    .catch(e => console.error(`[ERROR] ${currentLang === "ru" ? "Не удалось загрузить примеры" : "Failed to load examples"}:`, e));
}

// ── TICK — таймер каждую секунду ──
socket.on("tick", d => {
  document.getElementById("sv-elapsed").textContent = d.elapsed;
});

function setOperationControls(running) {
  const isRunning = !!running;
  const startIds = ["btn-start", "btn-social-search", "btn-product-search", "btn-yt-search"];
  const stopIds = ["btn-stop", "btn-social-stop", "btn-product-stop", "btn-yt-stop"];

  startIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = isRunning;
  });

  stopIds.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !isRunning;
    el.classList.toggle("on", isRunning);
  });

  document.body.classList.toggle("is-busy", isRunning);
}

// ── STATE ──
socket.on("state", d => {
  // счётчики
  document.getElementById("sv-found").textContent    = d.found;
  document.getElementById("sv-analyzed").textContent = d.analyzed;
  document.getElementById("sv-left").textContent     = Math.max(0, d.total - d.analyzed);
  document.getElementById("sv-skipped").textContent  = d.skipped || 0;
  if (d.db_stats) {
    document.getElementById("sv-db").textContent    = d.db_stats.total;
    document.getElementById("db-total").textContent = d.db_stats.total;
    document.getElementById("db-cities").textContent= d.db_stats.cities;
  }
  if (!d.running || d.phase === "idle") {
    document.getElementById("sv-elapsed").textContent = d.elapsed || "0м 00с";
  }

  // прогресс
  const pct = d.total > 0 ? Math.round(d.analyzed / d.total * 100) : 0;
  document.getElementById("pfill").style.width = pct + "%";
  document.getElementById("pct").textContent   = pct + "%";
  document.getElementById("prog-city").textContent = d.city || uiText("progWaiting");

  if (d.current_url) {
    document.getElementById("cur-url").innerHTML = `${uiText("scanning")} <span>${d.current_url}</span>`;
    Object.values(chips).forEach(c => c.classList.remove("scanning"));
    if (chips[d.current_url]) chips[d.current_url].classList.add("scanning");
  } else if (d.phase === "done" || d.phase === "idle") {
    const txt = d.stopped ? uiText("stopped_text") : (d.phase === "done" ? uiText("completed_text") : uiText("curWaiting"));
    const col = d.stopped ? "var(--red)" : (d.phase === "done" ? "var(--green)" : "var(--text3)");
    document.getElementById("cur-url").innerHTML = `<span style="color:${col}">${txt}</span>`;
    Object.values(chips).forEach(c => { c.classList.remove("scanning"); if(d.phase==="done") c.classList.add("done-chip"); });
  }

  // phase badge
  renderPhaseBadge(d.phase, d.stopped);

  // cards
  document.getElementById("sc-found").classList.toggle("lit", d.found > 0);
  document.getElementById("sc-analyzed").classList.toggle("lit", d.analyzed > 0);

  // buttons
  const running = !!d.running;
  setOperationControls(running);

  // blinking
  const active = d.phase === "searching" || d.phase === "analyzing";
  ["lb","ub","qblink"].forEach(id => document.getElementById(id).style.display = active ? "block" : "none");

  // queue
  window.__lastQueue = d.queue || [];
  window.__lastQueueDone = d.queue_done || [];
  window.__lastCurrentCity = d.city || "";
  renderQueue(window.__lastQueue, window.__lastQueueDone, window.__lastCurrentCity);
});

// ── LOG ──
socket.on("status", d => {
  const log = document.getElementById("log");
  const e = document.createElement("div");
  e.className = "le " + (d.level || "info");
  e.textContent = d.msg;
  log.appendChild(e);
  log.scrollTop = log.scrollHeight;

  // Перезагружаем примеры если один сохранился
  if (d.msg && (d.msg.includes("Пример сохранён") || d.msg.includes("добавлен") || d.msg.includes("Example saved") || d.msg.includes("added"))) {
    setTimeout(() => loadExamples(), 500);
  }
});

socket.on("reload_examples", d => {
  loadExamples();
});

// ── RESULT ──
socket.on("result", d => {
  const list = document.getElementById("rlist");
  if (firstResult) { list.innerHTML = ""; firstResult = false; }

  const skipped = d.design && (d.design.startsWith("Пропущено") || d.design.startsWith("Skipped"));
  addChip(d.url, (d.type === "Крупный" || d.type === "Large") ? "l" : "n", skipped);

  if (!skipped) {
    const card = document.createElement("div");
    card.className = "rcard";
    let host = d.url; try { host = new URL(d.url).hostname; } catch {}
    const bc = (d.type === "Крупный" || d.type === "Large") ? "l" : "n";
    
    const domain = host;
    const goodBtn = `<button class="rc-action-btn rc-good" onclick="saveExample('${d.url}', '${d.design.replace(/'/g, "\\'")}', '${d.ux.replace(/'/g, "\\'")}', true)">${uiText("goodBtn")}</button>`;
    const badBtn = `<button class="rc-action-btn rc-bad" onclick="saveExample('${d.url}', '${d.design.replace(/'/g, "\\'")}', '${d.ux.replace(/'/g, "\\'")}', false)">${uiText("badBtn")}</button>`;

    // Получаем домен для сохранения оценок
    let saveDomain = domain.replace(/www\./, "").split('/')[0];

    // Быстрые кнопки оценок (1-10)
    let quickDesignBtns = '';
    let quickUxBtns = '';
    for (let i = 1; i <= 10; i++) {
      quickDesignBtns += `<button class="rc-quick-score" onclick="quickRate('design-${d.index}', ${i})">${i}</button>`;
      quickUxBtns += `<button class="rc-quick-score" onclick="quickRate('ux-${d.index}', ${i})">${i}</button>`;
    }

    const domainTypeText = (d.type === "Крупный" || d.type === "Large") ? uiText("domainTypeLarge") : uiText("domainTypeNiche");

    card.innerHTML = `
      <div class="rc-url" title="${d.url}">${host}</div>
      <div class="rc-badge ${bc}">${domainTypeText}</div>
      <div class="rc-text">🎨 ${d.design || "—"}<br><br>👤 ${d.ux || "—"}</div>
      <div class="rc-actions">${goodBtn}${badBtn}</div>
      <div class="rc-scores">
        <div class="rc-score-item">
          <label class="rc-score-label">${uiText("designLabel")}</label>
          <input type="number" class="rc-score-input" id="design-${d.index}" min="0" max="10" placeholder="0">
          <div class="rc-quick-scores">${quickDesignBtns}</div>
        </div>
        <div class="rc-score-item">
          <label class="rc-score-label">${uiText("uxLabel")}</label>
          <input type="number" class="rc-score-input" id="ux-${d.index}" min="0" max="10" placeholder="0">
          <div class="rc-quick-scores">${quickUxBtns}</div>
        </div>
        <div class="rc-score-item" style="display:flex;align-items:flex-end">
          <button class="rc-score-btn" onclick="saveScores('${saveDomain}', ${d.index})">${uiText("saveScores")}</button>
        </div>
      </div>`;
    list.insertBefore(card, list.firstChild);
  }
});

socket.on("done", d => {
  if (d.city) {
    const cityLabel = currentLang === "ru" ? `«${d.city}»` : `"${d.city}"`;
    const sitesText = currentLang === "ru" ? `сайтов сохранено в БД` : `sites saved to DB`;
    addLog(`✅ ${cityLabel} ${d.count} ${sitesText}`, "success");
  }
});

// ── QUEUE RENDER ──
function renderPhaseBadge(phase, stopped) {
  const pm = {
    idle:[uiText("idle"),"idle"],
    searching:[uiText("searching"),"searching"],
    analyzing:[uiText("analyzing"),"analyzing"],
    rechecking:[uiText("rechecking"),"analyzing"],
    done:[uiText("done"),"done"]
  };
  let [lbl, cls] = pm[phase] || ["—","idle"];
  if (stopped && phase !== "idle") { lbl = uiText("stopped"); cls = "stopped"; }
  const pb = document.getElementById("pbadge");
  pb.dataset.phase = phase || "idle";
  pb.dataset.stopped = stopped ? "true" : "false";
  pb.textContent = lbl;
  pb.className = "phase " + cls;
}

function renderQueue(queue, done, currentCity) {
  const el = document.getElementById("queue-list");
  if (!queue.length && !done.length) {
    el.innerHTML = `<div class="queue-empty">${uiText("queueEmpty")}</div>`;
    return;
  }
  el.innerHTML = "";
  // текущий город
  if (currentCity && (queue.length || done.length)) {
    const item = document.createElement("div");
    item.className = "queue-item active";
    item.innerHTML = `<span>▶ ${currentCity}</span><span style="font-size:10px;color:var(--cyan)">${uiText("now")}</span>`;
    el.appendChild(item);
  }
  // ожидающие
  queue.forEach(city => {
    const item = document.createElement("div");
    item.className = "queue-item";
    item.innerHTML = `<span>${city}</span><button class="btn-sm" onclick="removeCity('${city}')">✕</button>`;
    el.appendChild(item);
  });
  // завершённые с кнопкой переанализа
  if (done.length > 0) {
    const historyTitle = document.createElement("div");
    historyTitle.style.cssText = "font-size:9px;color:var(--text3);padding:8px 6px 4px 6px;text-transform:uppercase;letter-spacing:1px;margin-top:6px;border-top:1px solid var(--bdr)";
    historyTitle.textContent = uiText("cityHistory");
    el.appendChild(historyTitle);
  }
  done.forEach(city => {
    const item = document.createElement("div");
    item.className = "queue-item done-q";
    item.style.display = "flex";
    item.style.justifyContent = "space-between";
    item.style.alignItems = "center";
    item.style.paddingRight = "6px";
    item.innerHTML = `<span>✓ ${city}</span><button class="btn-sm" style="font-size:9px;padding:3px 6px;flex-shrink:0" onclick="reanalyzeCity('${city}')">🔄</button>`;
    el.appendChild(item);
  });
}

function reanalyzeCity(city) {
  const largeVal = document.getElementById("s-max-large").value;
  const nicheVal = document.getElementById("s-max-niche").value;
  const prompt_msg = currentLang === "ru"
    ? `Переанализ города: ${city}\n\nТекущие настройки:\n- Крупных: ${largeVal}\n- Нишевых: ${nicheVal}\n\nДля увеличения количества,\nотредактируй настройки выше\nи запусти переанализ.\n\nПродолжить с текущими настройками?`
    : `Re-analyze city: ${city}\n\nCurrent settings:\n- Large sites: ${largeVal}\n- Niche sites: ${nicheVal}\n\nTo increase the amount,\nedit the settings above\nand start re-analysis.\n\nContinue with current settings?`;

  if (confirm(prompt_msg)) {
    socket.emit("reanalyze_city", { city });
  }
}

// ── HELPERS ──
function addLog(msg, level="info") {
  const log = document.getElementById("log");
  const e = document.createElement("div");
  e.className = "le " + level;
  e.textContent = msg;
  log.appendChild(e);
  log.scrollTop = log.scrollHeight;
}

function addChip(url, type, skipped) {
  if (chips[url]) return;
  let host = url; try { host = new URL(url).hostname; } catch {}
  const chip = document.createElement("div");
  chip.className = "chip " + type + (skipped ? " skipped" : "");
  chip.textContent = host; chip.title = url;
  document.getElementById("chips").appendChild(chip);
  chips[url] = chip;
}

function updateTotalHint() {
  const l = parseInt(document.getElementById("s-max-large").value) || 0;
  const n = parseInt(document.getElementById("s-max-niche").value) || 0;
  document.getElementById("s-total-hint").textContent = l + n;
}
["s-max-large","s-max-niche"].forEach(id =>
  document.getElementById(id).addEventListener("input", updateTotalHint)
);

// ── ACTIONS ──
function addCity() {
  const input = document.getElementById("city-input");
  const city  = input.value.trim();
  if (!city) { input.focus(); return; }
  socket.emit("add_city", { city });
  input.value = "";
  input.focus();
}

function removeCity(city) {
  socket.emit("remove_city", { city });
}

function _legacyStartQueueDoNotUse() {
  if (subsMax < subsMin) {
    alert("Верхняя граница подписчиков должна быть больше или равна нижней.");
    return;
  }

  firstResult = true;
  window.stateResults = [];
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">${uiText("waitingResults")}</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML   = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);
  socket.emit("start_queue");
}

function stopScan() {
  socket.emit("stop_scan");
}

function saveSettings() {
  socket.emit("update_settings", {
    max_large:    document.getElementById("s-max-large").value,
    max_niche:    document.getElementById("s-max-niche").value,
    max_per_query:document.getElementById("s-per-query").value,
    parallel:     document.getElementById("s-parallel").value,
    page_timeout: document.getElementById("s-timeout").value,
    vision_model: document.getElementById("s-model").value,
  });
}

function saveExample(url, design, ux, isGood) {
  const reason = isGood ? (currentLang === "ru" ? "Хороший дизайн и UX" : "Good design and UX") : (currentLang === "ru" ? "Плохой дизайн или UX" : "Poor design or UX");
  socket.emit("save_example", {
    url: url,
    design: design,
    ux: ux,
    is_good: isGood,
    reason: reason
  });
}

function addManualExample(isGood) {
  const urlInput = document.getElementById("ex-url");
  const designInput = document.getElementById("ex-design");
  const uxInput = document.getElementById("ex-ux");
  if (!urlInput || !designInput || !uxInput) {
    return;
  }

  const url = urlInput.value;
  const design = designInput.value;
  const ux = uxInput.value;
  
  if (!url || !design || !ux) {
    alert(uiText("fillAllFields"));
    return;
  }
  
  socket.emit("add_manual_example", {
    url: url,
    design: design,
    ux: ux,
    is_good: isGood
  });
  
  // Очищаем форму
  urlInput.value = "";
  designInput.value = "";
  uxInput.value = "";
}

function saveScores(domain, index) {
  const designScore = document.getElementById(`design-${index}`).value;
  const uxScore = document.getElementById(`ux-${index}`).value;
  
  if (!designScore || !uxScore) {
    alert(uiText("fillScores"));
    return;
  }
  
  socket.emit("save_scores", {
    domain: domain,
    design_score: parseInt(designScore),
    ux_score: parseInt(uxScore)
  });
}

function quickRate(inputId, rating) {
  const input = document.getElementById(inputId);
  input.value = rating;
  
  // Обновляем стиль кнопок
  const container = input.parentElement.querySelector('.rc-quick-scores');
  if (container) {
    container.querySelectorAll('.rc-quick-score').forEach(btn => {
      if (parseInt(btn.textContent) === rating) {
        btn.style.backgroundColor = 'var(--magenta)';
        btn.style.color = '#000';
        btn.style.fontWeight = 'bold';
      } else {
        btn.style.backgroundColor = '';
        btn.style.color = '';
        btn.style.fontWeight = '';
      }
    });
  }
}

document.getElementById("city-input").addEventListener("keydown", e => {
  if (e.key === "Enter") addCity();
});

// ── ПЕРЕКЛЮЧЕНИЕ ТИПА ПОИСКА ──
function toggleSearchType() {
  const searchType = document.querySelector('input[name="search-type"]:checked').value;
  const cityPanel = document.getElementById("city-queue-panel");
  const socialPanel = document.getElementById("social-search-panel");
  const productsPanel = document.getElementById("products-search-panel");
  const ytPanel = document.getElementById("youtube-trends-panel");

  // Скрываем все панели
  cityPanel.style.display = "none";
  socialPanel.style.display = "none";
  productsPanel.style.display = "none";
  ytPanel.style.display = "none";

  // Показываем нужную
  if (searchType === "sites") {
    cityPanel.style.display = "block";
  } else if (searchType === "social") {
    socialPanel.style.display = "block";
  } else if (searchType === "products") {
    productsPanel.style.display = "block";
  } else if (searchType === "youtube-trends") {
    ytPanel.style.display = "block";
  }
}

// ── ПОИСК ПО СОЦСЕТЯМ ──
function startSocialSearch() {
  const query = document.getElementById("social-query").value.trim();
  const city = document.getElementById("social-city").value.trim();
  const maxResults = parseInt(document.getElementById("social-max")?.value, 10) || 10;
  
  if (!query) {
    alert(uiText("enterSearchQuery"));
    return;
  }
  
  const platforms = [];
  document.querySelectorAll('input[name="platform"]:checked').forEach(cb => {
    platforms.push(cb.value);
  });
  
  if (platforms.length === 0) {
    alert(uiText("choosePlatform"));
    return;
  }
  
  firstResult = true;
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">${uiText("waitingSocial")}</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML   = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);
  setOperationControls(true);
  
  socket.emit("start_social_search", {
    query: query,
    city: city || "",
    platforms: platforms,
    max_results: maxResults
  });
}

function stopSocialSearch() {
  socket.emit("stop_social_search");
}

// ── ПОИСК ТОВАРОВ/УСЛУГ ──
function startProductSearch() {
  const query = document.getElementById("product-query").value.trim();
  const city = document.getElementById("product-city").value.trim();
  const maxResults = parseInt(document.getElementById("product-max").value) || 20;
  
  if (!query) {
    alert(uiText("enterSearchQuery"));
    return;
  }
  
  firstResult = true;
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">${uiText("waitingProducts")}</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML   = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);
  setOperationControls(true);
  
  socket.emit("start_product_search", {
    query: query,
    city: city || "",
    max_results: maxResults
  });
}

function stopProductSearch() {
  socket.emit("stop_product_search");
}

// ── YOUTUBE ТРЕНДЫ ──
let ytLang = 'RU';

function setYtLang(lang) {
  ytLang = lang;
  document.getElementById("yt-lang-ru").style.background = lang === "RU" ? "rgba(0,212,255,.14)" : "transparent";
  document.getElementById("yt-lang-ru").style.color = lang === "RU" ? "var(--cyan)" : "var(--text2)";
  document.getElementById("yt-lang-en").style.background = lang === "EN" ? "rgba(0,212,255,.14)" : "transparent";
  document.getElementById("yt-lang-en").style.color = lang === "EN" ? "var(--cyan)" : "var(--text2)";
}

