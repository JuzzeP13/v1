function _legacyStartYoutubeTrendsDoNotUse() {
  const query = document.getElementById("yt-query").value.trim();
  const maxResults = parseInt(document.getElementById("yt-max").value) || 50;
  const parallelRequests = parseInt(document.getElementById("yt-parallel").value) || 12;
  const durationMin = parseInt(document.getElementById("yt-duration-min").value) || 0;
  const durationMax = parseInt(document.getElementById("yt-duration-max").value) || 25;
  const subsMin = parseInt(document.getElementById("yt-subs-min").value) || 0;
  const subsMax = parseInt(document.getElementById("yt-subs-max").value) || 10000000;
  const tag = document.getElementById("yt-tag").value.trim();

  if (!query) {
    alert("Введи поисковый запрос!");
    return;
  }

  firstResult = true;
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">Жду результаты YouTube трендов...</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML   = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);

  socket.emit("start_youtube_trends", {
    query: query,
    max_results: maxResults,
    filters: {
      parallel_requests: parallelRequests,
      duration_min: durationMin,
      duration_max: durationMax,
      subs_min: subsMin,
      subs_max: subsMax,
      tag: tag,
      language: ytLang
    }
  });
}

function stopYoutubeTrends() {
  socket.emit("stop_youtube_trends");
}

function startQueue() {
  firstResult = true;
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">${uiText("waitingResults")}</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);
  setOperationControls(true);
  socket.emit("start_queue");
}

function startYoutubeTrends() {
  const query = document.getElementById("yt-query").value.trim();
  const maxResults = parseInt(document.getElementById("yt-max").value) || 50;
  const parallelRequests = parseInt(document.getElementById("yt-parallel").value) || 12;
  const durationMin = parseInt(document.getElementById("yt-duration-min").value) || 0;
  const durationMax = parseInt(document.getElementById("yt-duration-max").value) || 25;
  const subsMin = parseInt(document.getElementById("yt-subs-min").value) || 0;
  const subsMax = parseInt(document.getElementById("yt-subs-max").value) || 10000000;
  const tag = document.getElementById("yt-tag").value.trim();

  if (!query) {
    alert("Введите поисковый запрос!");
    return;
  }

  if (subsMax < subsMin) {
    alert("Максимум подписчиков не может быть меньше минимума.");
    return;
  }

  firstResult = true;
  window.stateResults = [];
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">Жду результаты YouTube трендов...</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);
  setOperationControls(true);

  socket.emit("start_youtube_trends", {
    query: query,
    max_results: maxResults,
    filters: {
      parallel_requests: parallelRequests,
      duration_min: durationMin,
      duration_max: durationMax,
      subs_min: subsMin,
      subs_max: subsMax,
      tag: tag,
      language: ytLang
    }
  });
}

// Сохранить YouTube в Excel с фильтром качества
let ytQualityFilter = null; // null = все, 'good' = хорошие, 'bad' = плохие
let ytExcelSaveInProgress = false;

function setYtExcelFilter(filter) {
  ytQualityFilter = filter;
  
  // Обновляем стиль кнопок
  document.getElementById("yt-filter-all").style.background = !filter ? "rgba(0,212,255,.14)" : "transparent";
  document.getElementById("yt-filter-all").style.color = !filter ? "var(--cyan)" : "var(--text2)";
  
  document.getElementById("yt-filter-good").style.background = filter === "good" ? "rgba(0,255,136,.14)" : "transparent";
  document.getElementById("yt-filter-good").style.color = filter === "good" ? "var(--green)" : "var(--text2)";
  
  document.getElementById("yt-filter-bad").style.background = filter === "bad" ? "rgba(255,68,85,.14)" : "transparent";
  document.getElementById("yt-filter-bad").style.color = filter === "bad" ? "var(--red)" : "var(--text2)";
}

function saveYoutubeToExcel() {
  if (!window.stateResults || window.stateResults.length === 0) {
    alert("Сначала выполните поиск YouTube трендов!");
    return;
  }
  if (ytExcelSaveInProgress) {
    emitStatus("⏳ Сохранение уже выполняется, подождите...", "warn");
    return;
  }

  const filterText = ytQualityFilter === 'good' ? 'ХОРОШИЕ' : ytQualityFilter === 'bad' ? 'ПЛОХИЕ' : 'ВСЕ';
  emitStatus(`💾 Сохраняю ${filterText} превью в Excel...`, 'info');
  ytExcelSaveInProgress = true;
  
  socket.emit("save_youtube_to_excel", {
    quality_filter: ytQualityFilter
  });
}

function emitStatus(msg, level) {
  const log = document.getElementById("log");
  if (log) {
    const e = document.createElement("div");
    e.className = "le " + (level || "info");
    e.textContent = msg;
    log.appendChild(e);
    log.scrollTop = log.scrollHeight;
  }
}

// Обработка результатов YouTube трендов
socket.on("youtube_trend_result", d => {
  const list = document.getElementById("rlist");
  if (firstResult) { list.innerHTML = ""; firstResult = false; }

  // Сохраняем результаты для Excel
  if (!window.stateResults) window.stateResults = [];
  window.stateResults.push(d);

  const card = document.createElement("div");
  card.className = "rcard";

  // Форматируем длительность
  let durationText = "—";
  if (d.duration) {
    const mins = Math.floor(d.duration);
    const secs = Math.floor((d.duration - mins) * 60);
    durationText = `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  // Форматируем просмотры
  let viewsText = d.views ? d.views.toLocaleString() : "—";
  let subscribersText = d.subscriber_count ? d.subscriber_count.toLocaleString() : "—";

  // AI анализ превью
  let analysisHtml = "";
  if (d.thumbnail_analysis) {
    const ta = d.thumbnail_analysis;
    analysisHtml = `
      <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--bdr);font-size:9px;color:var(--text3)">
        <div>🎨 Превью: ${ta.thumbnail_score || '?'}/10 | Clickbait: ${ta.clickbait_probability || '?'}</div>
        <div>✨ Качество: ${ta.quality || '?'} | Эмоции: ${ta.emotion_score || '?'}/10</div>
      </div>
    `;
  }

  card.innerHTML = `
    <div style="display:flex;gap:10px;align-items:start">
      <img src="${d.thumbnail}" style="width:120px;height:68px;object-fit:cover;border-radius:6px;border:1px solid var(--bdr)" onerror="this.style.display='none'">
      <div style="flex:1;min-width:0">
        <div class="rc-url" title="${d.url}" style="font-size:11px;color:var(--cyan);margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${d.title || 'Без названия'}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;font-size:10px;color:var(--text2)">
          <span>👥 ${subscribersText}</span>
          <span>👁️ ${viewsText}</span>
          <span>⏱️ ${durationText}</span>
          <span>🔥 Viral: ${d.viral_score || '0'}</span>
          <span>⭐ Score: ${d.score || '0'}</span>
        </div>
        ${analysisHtml}
      </div>
      <a href="${d.url}" target="_blank" style="display:flex;align-items:center;justify-content:center;width:32px;height:32px;background:var(--red);color:#fff;border-radius:6px;text-decoration:none;font-size:14px;flex-shrink:0">▶</a>
    </div>
  `;
  list.insertBefore(card, list.firstChild);
});

socket.on("youtube_excel_saved", d => {
  ytExcelSaveInProgress = false;
  const savedCount = d?.saved_count || 0;
  const imagesAdded = d?.images_added || 0;
  emitStatus(`✅ Excel сохранён: ${savedCount} видео, превью: ${imagesAdded}. Начинаю скачивание...`, "success");

  const downloadUrl = d?.download_url || `/download/youtube?ts=${Date.now()}`;
  window.location.href = downloadUrl;
});

socket.on("youtube_excel_error", d => {
  ytExcelSaveInProgress = false;
  const message = d?.message || "Не удалось сохранить Excel файл";
  emitStatus(`❌ ${message}`, "error");
});

// ── HYPERSPACE WEBGL BACKGROUND ──
const bgCanvas = document.getElementById("starfield");
const LIGHT_THEME_CLASS = "light-theme";
const RUNTIME_BG_ANIMATION_STORAGE_KEY = "tish-bg-animation-enabled";

function isRuntimeBackgroundAnimationEnabled() {
  return localStorage.getItem(RUNTIME_BG_ANIMATION_STORAGE_KEY) !== "0";
}

function getBgTheme() {
  return document.body.classList.contains(LIGHT_THEME_CLASS) ? "light" : "dark";
}

function watchBgTheme(onChange) {
  if (!document.body) return;
  let lastTheme = getBgTheme();
  const observer = new MutationObserver(() => {
    const nextTheme = getBgTheme();
    if (nextTheme === lastTheme) return;
    lastTheme = nextTheme;
    onChange(nextTheme);
  });
  observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
}

function hexToRgb(hex) {
  const normalized = hex.replace("#", "");
  const full = normalized.length === 3
    ? normalized.split("").map(ch => ch + ch).join("")
    : normalized;
  const int = parseInt(full, 16);
  return {
    r: (int >> 16) & 255,
    g: (int >> 8) & 255,
    b: int & 255,
  };
}

function initCanvasWarpFallback(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const lowEndDevice = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4;
  const baseCount = isMobile ? 520 : 760;
  const STAR_COUNT = Math.max(isMobile ? 420 : 500, Math.floor(baseCount * (lowEndDevice ? 0.8 : 1)));
  const stars = new Array(STAR_COUNT);
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  let w = 0;
  let h = 0;
  let dpr = 1;
  let prev = performance.now();
  let warp = 0.2;
  let targetWarp = 0.2;
  let themeMode = getBgTheme();
  const darkPalette = ["#ffffff", "#00e5ff", "#f050ff", "#22f6d1", "#8f6bff", "#00b8ff"];
  const lightPalette = ["#000000", "#141414", "#222222", "#2d2d2d", "#3a3a3a"];
  const lightAccent = ["#6f87a4", "#9a6363"];

  function pickColor() {
    if (themeMode !== "light") {
      return darkPalette[(Math.random() * darkPalette.length) | 0];
    }
    if (Math.random() < 0.1) {
      return lightAccent[(Math.random() * lightAccent.length) | 0];
    }
    return lightPalette[(Math.random() * lightPalette.length) | 0];
  }

  function setStarColor(star, hex) {
    const rgb = hexToRgb(hex);
    star.color = hex;
    star.r = rgb.r;
    star.g = rgb.g;
    star.b = rgb.b;
  }

  function resetStar(i, randomDepth = false) {
    const s = stars[i] || {};
    const a = Math.random() * Math.PI * 2;
    const r = Math.pow(Math.random(), 0.58) * 0.92;
    s.x = Math.cos(a) * r;
    s.y = Math.sin(a) * r;
    s.z = randomDepth ? (0.1 + Math.random() * 0.9) : (0.9 + Math.random() * 0.25);
    s.speed = (0.16 + Math.random() * 0.42) * (1 + r * 0.4);
    s.tail = themeMode === "light" ? (0.04 + Math.random() * 0.13) : (0.035 + Math.random() * 0.11);
    s.width = themeMode === "light" ? (0.45 + Math.random() * 1.1) : (0.5 + Math.random() * 1.5);
    setStarColor(s, pickColor());
    stars[i] = s;
  }

  function applyTheme(nextTheme) {
    themeMode = nextTheme === "light" ? "light" : "dark";
    for (let i = 0; i < STAR_COUNT; i++) {
      if (!stars[i]) continue;
      setStarColor(stars[i], pickColor());
    }
  }

  function resize() {
    w = window.innerWidth;
    h = window.innerHeight;
    dpr = Math.min(2.5, window.devicePixelRatio || 1);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.imageSmoothingEnabled = true;
  }
  resize();
  window.addEventListener("resize", resize);

  for (let i = 0; i < STAR_COUNT; i++) resetStar(i, true);

  window.addEventListener("pointermove", (e) => {
    pointer.tx = (e.clientX / w) * 2 - 1;
    pointer.ty = (e.clientY / h) * 2 - 1;
  }, { passive: true });

  watchBgTheme(theme => {
    applyTheme(theme);
  });

  socket.on("state", data => {
    const phase = data?.phase || "idle";
    const active = (
      phase === "searching" ||
      phase === "analyzing" ||
      phase === "rechecking" ||
      phase === "rechecking_screenshots" ||
      phase === "rechecking_analysis"
    );
    targetWarp = active ? 1.0 : 0.2;
  });

  function frame(ts) {
    const dt = Math.min(0.05, Math.max(0.001, (ts - prev) / 1000));
    prev = ts;
    warp += (targetWarp - warp) * 0.06;
    pointer.x += (pointer.tx - pointer.x) * 0.08;
    pointer.y += (pointer.ty - pointer.y) * 0.08;

    const cx = w * 0.5 + (-pointer.x * w * 0.045);
    const cy = h * 0.5 + (pointer.y * h * 0.03);
    const isLight = themeMode === "light";
    if (isLight) {
      const bg = ctx.createLinearGradient(0, 0, 0, h);
      bg.addColorStop(0, "#ffffff");
      bg.addColorStop(1, "#f5f5f5");
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
    } else {
      const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.85);
      bg.addColorStop(0, "rgba(24,5,58,0.75)");
      bg.addColorStop(0.55, "rgba(10,3,34,0.78)");
      bg.addColorStop(1, "rgba(5,1,18,0.9)");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
    }

    for (let i = 0; i < STAR_COUNT; i++) {
      const s = stars[i];
      const speedFactor = isLight ? (0.34 + warp * 1.6) : (0.45 + warp * 2.1);
      s.z -= s.speed * dt * speedFactor;
      if (s.z <= 0.018) {
        resetStar(i, false);
        continue;
      }

      const invZ = 1 / s.z;
      const f = Math.min(w, h) * 0.54;

      const hx = cx + s.x * invZ * f;
      const hy = cy + s.y * invZ * f;

      const zN = 1 - Math.min(1, s.z);
      const alphaHead = isLight ? (0.45 + zN * 0.5) : (0.28 + zN * 0.65);
      const pointRadius = s.width * (isLight ? (0.5 + zN * 1.15) : (0.55 + zN * 1.75));

      const pointAlpha = isLight ? Math.min(1, alphaHead + 0.05) : Math.min(1, alphaHead);
      ctx.fillStyle = `rgba(${s.r},${s.g},${s.b},${pointAlpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(hx, hy, Math.max(isLight ? 0.45 : 0.8, pointRadius * (isLight ? 0.34 : 0.52)), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
}

if (!bgCanvas || !isRuntimeBackgroundAnimationEnabled()) {
  if (bgCanvas) {
    bgCanvas.style.display = "none";
  }
} else if (!window.THREE) {
  console.warn("[HYPERSPACE] Three.js недоступен, запускаю Canvas fallback.");
  initCanvasWarpFallback(bgCanvas);
} else {
  const isMobileDevice = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const cpuCores = navigator.hardwareConcurrency || 4;
  const deviceMem = navigator.deviceMemory || 8;
  const lowEndDevice = cpuCores <= 4 || deviceMem <= 4;
  let baseParticles = isMobileDevice ? 540 : 760;
  if (lowEndDevice) baseParticles = Math.floor(baseParticles * 0.78);
  const PARTICLE_COUNT = Math.max(isMobileDevice ? 420 : 500, Math.min(800, baseParticles));
  const LAYER_COUNT = 4;
  const DEPTH_START = -1800;
  const DEPTH_END = 24;
  const TUNNEL_RADIUS = 240;
  const TAU = Math.PI * 2;

  let themeMode = getBgTheme();
  const darkPalette = [
    new THREE.Color("#ffffff"),
    new THREE.Color("#00e5ff"),
    new THREE.Color("#00b8ff"),
    new THREE.Color("#22f6d1"),
    new THREE.Color("#f050ff"),
    new THREE.Color("#8f6bff"),
  ];
  const lightPalette = [
    new THREE.Color("#000000"),
    new THREE.Color("#141414"),
    new THREE.Color("#202020"),
    new THREE.Color("#2a2a2a"),
    new THREE.Color("#363636"),
  ];
  const lightAccent = [
    new THREE.Color("#6f87a4"),
    new THREE.Color("#9a6363"),
  ];

  function pickThreeColor() {
    if (themeMode !== "light") {
      return darkPalette[(Math.random() * darkPalette.length) | 0];
    }
    if (Math.random() < 0.08) {
      return lightAccent[(Math.random() * lightAccent.length) | 0];
    }
    return lightPalette[(Math.random() * lightPalette.length) | 0];
  }

  const renderer = new THREE.WebGLRenderer({
    canvas: bgCanvas,
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(isMobileDevice ? 1.5 : 2.2, window.devicePixelRatio || 1));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(66, window.innerWidth / window.innerHeight, 0.1, 2800);
  camera.position.z = 16;

  const starRoot = new THREE.Group();
  scene.add(starRoot);

  const particles = new Array(PARTICLE_COUNT);
  const headPositions = new Float32Array(PARTICLE_COUNT * 3);
  const headColors = new Float32Array(PARTICLE_COUNT * 3);

  const headGeometry = new THREE.BufferGeometry();
  headGeometry.setAttribute("position", new THREE.BufferAttribute(headPositions, 3));
  headGeometry.setAttribute("color", new THREE.BufferAttribute(headColors, 3));

  function makePointTexture(size, softGlow) {
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const gx = c.getContext("2d");
    const g = gx.createRadialGradient(size * 0.5, size * 0.5, 0, size * 0.5, size * 0.5, size * 0.5);
    if (softGlow) {
      g.addColorStop(0, "rgba(255,255,255,1)");
      g.addColorStop(0.35, "rgba(255,255,255,0.92)");
      g.addColorStop(1, "rgba(255,255,255,0)");
    } else {
      g.addColorStop(0, "rgba(255,255,255,1)");
      g.addColorStop(0.68, "rgba(255,255,255,1)");
      g.addColorStop(0.88, "rgba(255,255,255,0.24)");
      g.addColorStop(1, "rgba(255,255,255,0)");
    }
    gx.fillStyle = g;
    gx.fillRect(0, 0, size, size);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  const glowHeadTexture = makePointTexture(96, true);
  const crispHeadTexture = makePointTexture(72, false);

  const haloMaterial = new THREE.PointsMaterial({
    size: isMobileDevice ? 9 : 12,
    map: glowHeadTexture,
    transparent: true,
    opacity: 0.24,
    vertexColors: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  });
  const halos = new THREE.Points(headGeometry, haloMaterial);
  starRoot.add(halos);

  const headMaterial = new THREE.PointsMaterial({
    size: isMobileDevice ? 3.8 : 4.8,
    map: glowHeadTexture,
    transparent: true,
    opacity: 0.95,
    vertexColors: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  });
  const heads = new THREE.Points(headGeometry, headMaterial);
  starRoot.add(heads);

  const dustCount = isMobileDevice ? 260 : 420;
  const dustGeo = new THREE.BufferGeometry();
  const dustPos = new Float32Array(dustCount * 3);
  const dustCol = new Float32Array(dustCount * 3);
  for (let i = 0; i < dustCount; i++) {
    const r = TUNNEL_RADIUS * (1.1 + Math.random() * 0.9);
    const a = Math.random() * TAU;
    const d = DEPTH_START + Math.random() * (DEPTH_END - DEPTH_START);
    dustPos[i * 3] = Math.cos(a) * r;
    dustPos[i * 3 + 1] = Math.sin(a) * r;
    dustPos[i * 3 + 2] = d;
    const v = 0.1 + Math.random() * 0.14;
    dustCol[i * 3] = v;
    dustCol[i * 3 + 1] = v;
    dustCol[i * 3 + 2] = v;
  }
  dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
  dustGeo.setAttribute("color", new THREE.BufferAttribute(dustCol, 3));
  const dustMaterial = new THREE.PointsMaterial({
    size: 1.4,
    transparent: true,
    opacity: 0.14,
    vertexColors: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  });
  const dust = new THREE.Points(dustGeo, dustMaterial);
  starRoot.add(dust);

  function applyThemeToThree(nextTheme) {
    themeMode = nextTheme === "light" ? "light" : "dark";
    const isLight = themeMode === "light";

    renderer.setClearColor(isLight ? 0xffffff : 0x050012, 1);
    bgCanvas.style.backgroundColor = isLight ? "#ffffff" : "transparent";

    haloMaterial.visible = !isLight;
    haloMaterial.opacity = isLight ? 0 : 0.24;
    haloMaterial.blending = isLight ? THREE.NormalBlending : THREE.AdditiveBlending;

    headMaterial.blending = isLight ? THREE.NormalBlending : THREE.AdditiveBlending;
    headMaterial.opacity = isLight ? 0.96 : 0.95;
    headMaterial.size = isLight ? (isMobileDevice ? 2.8 : 3.4) : (isMobileDevice ? 3.8 : 4.8);
    headMaterial.map = isLight ? crispHeadTexture : glowHeadTexture;

    dustMaterial.blending = isLight ? THREE.NormalBlending : THREE.AdditiveBlending;
    dustMaterial.opacity = isLight ? 0.04 : 0.14;

    haloMaterial.needsUpdate = true;
    headMaterial.needsUpdate = true;
    dustMaterial.needsUpdate = true;
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function resetParticle(i, randomDepth = false) {
    const layer = i % LAYER_COUNT;
    const isLight = themeMode === "light";
    const radius = Math.pow(Math.random(), 0.58) * TUNNEL_RADIUS * (0.72 + layer * 0.16);
    const angle = Math.random() * TAU;
    const color = pickThreeColor();

    const p = particles[i] || {};
    p.layer = layer;
    p.x = Math.cos(angle) * radius;
    p.y = Math.sin(angle) * radius;
    p.z = randomDepth ? rand(DEPTH_START, DEPTH_END - 40) : DEPTH_START - Math.random() * 420;
    p.speed = isLight
      ? rand(110, 420) * (0.7 + layer * 0.38)
      : rand(170, 620) * (0.72 + layer * 0.23);
    p.tail = isLight
      ? rand(110, 300) * (0.72 + layer * 0.18)
      : rand(70, 260) * (0.78 + layer * 0.22);
    p.width = isLight
      ? rand(0.45, 1.1) * (0.72 + layer * 0.2)
      : rand(0.6, 1.4) * (0.8 + layer * 0.18);
    p.phase = Math.random() * TAU;
    p.r = color.r;
    p.g = color.g;
    p.b = color.b;
    particles[i] = p;
  }

  applyThemeToThree(themeMode);
  for (let i = 0; i < PARTICLE_COUNT; i++) resetParticle(i, true);

  function resizeHyper() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(isMobileDevice ? 1.5 : 2.2, window.devicePixelRatio || 1));
  }
  resizeHyper();
  window.addEventListener("resize", resizeHyper);

  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  window.addEventListener("pointermove", (e) => {
    pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
    pointer.ty = (e.clientY / window.innerHeight) * 2 - 1;
  }, { passive: true });

  watchBgTheme(theme => {
    applyThemeToThree(theme);
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      resetParticle(i, true);
    }
  });

  let targetWarp = 0.2;
  let warp = 0.2;
  let prevTime = performance.now();

  function updateParticles(dt, t) {
    const isLight = themeMode === "light";
    const speedBoost = isLight ? (0.42 + warp * 1.6) : (0.35 + warp * 1.85);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const p = particles[i];
      p.z += p.speed * speedBoost * dt;
      if (p.z > DEPTH_END) resetParticle(i, false);

      const zNorm = (p.z - DEPTH_START) / (DEPTH_END - DEPTH_START);
      const pulse = isLight
        ? (0.98 + Math.sin(t * 0.9 + p.phase) * 0.02)
        : (0.86 + Math.sin(t * 1.45 + p.phase) * 0.14);
      const headI = isLight
        ? (0.62 + zNorm * 0.34) * pulse
        : (0.35 + zNorm * 1.08) * pulse;

      const headZ = p.z;

      const hb = i * 3;
      headPositions[hb] = p.x;
      headPositions[hb + 1] = p.y;
      headPositions[hb + 2] = headZ;
      const headScale = isLight ? (0.82 + zNorm * 0.2) : (0.68 + zNorm * 0.7);
      headColors[hb] = Math.min(1, p.r * headScale);
      headColors[hb + 1] = Math.min(1, p.g * headScale);
      headColors[hb + 2] = Math.min(1, p.b * headScale);
    }

    headGeometry.attributes.position.needsUpdate = true;
    headGeometry.attributes.color.needsUpdate = true;
  }

  function renderHyper(now) {
    const dt = Math.min(0.05, Math.max(0.001, (now - prevTime) / 1000));
    prevTime = now;
    const t = now * 0.001;

    pointer.x += (pointer.tx - pointer.x) * 0.06;
    pointer.y += (pointer.ty - pointer.y) * 0.06;

    warp += (targetWarp - warp) * 0.045;
    dust.rotation.z += dt * 0.03 * (0.5 + warp);

    const xTarget = -pointer.x * (themeMode === "light" ? 8.6 : 7.5);
    const yTarget = -pointer.y * (themeMode === "light" ? 5.2 : 4.5);
    camera.position.x += (xTarget - camera.position.x) * 0.055;
    camera.position.y += (yTarget - camera.position.y) * 0.055;
    camera.lookAt(camera.position.x * 0.08, camera.position.y * 0.06, -220);

    starRoot.rotation.y += ((pointer.x * 0.12) - starRoot.rotation.y) * 0.035;
    starRoot.rotation.x += ((-pointer.y * 0.09) - starRoot.rotation.x) * 0.035;

    updateParticles(dt, t);
    renderer.render(scene, camera);
    requestAnimationFrame(renderHyper);
  }

  requestAnimationFrame(renderHyper);

  // Реакция на текущую фазу процесса: ускоряем "прыжок" во время поиска/анализа.
  socket.on("state", data => {
    const phase = data?.phase || "idle";
    const active = (
      phase === "searching" ||
      phase === "analyzing" ||
      phase === "rechecking" ||
      phase === "rechecking_screenshots" ||
      phase === "rechecking_analysis"
    );
    targetWarp = active ? 1.0 : 0.2;
  });
}

setLanguage(currentLang);
setOperationControls(false);

// ── ПЕРЕПРОВЕРКА БД ──
function openRecheckDialog() {
  const dbCount = parseInt(document.getElementById("db-total").textContent) || 0;
  
  if (dbCount === 0) {
    alert(uiText("noSitesForRecheck"));
    return;
  }
  
  const maxLimit = Math.min(100, dbCount);
  const defaultLimit = Math.min(10, dbCount);
  
  const limit = prompt(uiText("recheckPrompt", "") || UI_TEXT[currentLang].recheckPrompt(dbCount), defaultLimit);
  
  if (limit === null) return; // Отмена
  
  const num = parseInt(limit);
  if (isNaN(num) || num < 1 || num > maxLimit) {
    alert((uiText("invalidRange", "") || "").replace("${max}", maxLimit) || UI_TEXT[currentLang].invalidRange(maxLimit));
    return;
  }
  
  startRecheck(num);
}

function startRecheck(limit) {
  firstResult = true;
  document.getElementById("rlist").innerHTML =
    `<div style="padding:20px;text-align:center;color:var(--text3);font-size:11px">${uiText("waitingRecheck")}</div>`;
  document.getElementById("chips").innerHTML = "";
  document.getElementById("log").innerHTML   = "";
  document.getElementById("sv-elapsed").textContent = "0м 00с";
  Object.keys(chips).forEach(k => delete chips[k]);
  
  socket.emit("recheck_db", { limit: limit });
}
