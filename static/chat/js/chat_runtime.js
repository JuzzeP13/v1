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
function initCanvasWarpFallback(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const STAR_COUNT = isMobile ? 360 : 540;
  const stars = new Array(STAR_COUNT);
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  let w = 0;
  let h = 0;
  let dpr = 1;
  let prev = performance.now();
  let warp = 0.2;
  let targetWarp = 0.2;

  const palette = ["#ffffff", "#00e5ff", "#f050ff", "#22f6d1", "#8f6bff", "#00b8ff"];

  function resetStar(i, randomDepth = false) {
    const s = stars[i] || {};
    const a = Math.random() * Math.PI * 2;
    const r = Math.pow(Math.random(), 0.58) * 0.92;
    s.x = Math.cos(a) * r;
    s.y = Math.sin(a) * r;
    s.z = randomDepth ? (0.1 + Math.random() * 0.9) : (0.9 + Math.random() * 0.25);
    s.speed = (0.16 + Math.random() * 0.42) * (1 + r * 0.4);
    s.tail = 0.035 + Math.random() * 0.11;
    s.width = 0.5 + Math.random() * 1.5;
    s.color = palette[(Math.random() * palette.length) | 0];
    stars[i] = s;
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

    // Глубокий космос + пыль
    const cx = w * 0.5 + (-pointer.x * w * 0.045);
    const cy = h * 0.5 + (pointer.y * h * 0.03);
    const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.85);
    bg.addColorStop(0, "rgba(24,5,58,0.75)");
    bg.addColorStop(0.55, "rgba(10,3,34,0.78)");
    bg.addColorStop(1, "rgba(5,1,18,0.9)");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    ctx.globalCompositeOperation = "lighter";
    for (let i = 0; i < STAR_COUNT; i++) {
      const s = stars[i];
      s.z -= s.speed * dt * (0.45 + warp * 2.1);
      if (s.z <= 0.018) {
        resetStar(i, false);
        continue;
      }

      const invZ = 1 / s.z;
      const invZT = 1 / (s.z + s.tail);
      const f = Math.min(w, h) * 0.54;

      const hx = cx + s.x * invZ * f;
      const hy = cy + s.y * invZ * f;
      const tx = cx + s.x * invZT * f;
      const ty = cy + s.y * invZT * f;

      const zN = 1 - Math.min(1, s.z);
      const alphaTail = 0.03 + zN * 0.2;
      const alphaHead = 0.28 + zN * 0.65;
      const lw = s.width * (0.55 + zN * 1.75);

      const g = ctx.createLinearGradient(tx, ty, hx, hy);
      g.addColorStop(0, "rgba(255,255,255,0)");
      g.addColorStop(0.45, s.color + "22");
      g.addColorStop(1, s.color + "ff");

      ctx.strokeStyle = g;
      ctx.lineWidth = lw;
      ctx.globalAlpha = alphaTail;
      ctx.beginPath();
      ctx.moveTo(tx, ty);
      ctx.lineTo(hx, hy);
      ctx.stroke();

      ctx.globalAlpha = alphaHead;
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(hx, hy, Math.max(0.8, lw * 0.52), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
}

if (!window.THREE || !bgCanvas) {
  console.warn("[HYPERSPACE] Three.js недоступен, запускаю Canvas fallback.");
  initCanvasWarpFallback(bgCanvas);
} else {
const isMobileDevice = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
const cpuCores = navigator.hardwareConcurrency || 4;
const deviceMem = navigator.deviceMemory || 8;

let baseParticles = isMobileDevice ? 560 : 920;
if (cpuCores <= 4 || deviceMem <= 4) baseParticles = Math.floor(baseParticles * 0.72);
const PARTICLE_COUNT = Math.max(420, Math.min(1100, baseParticles));
const LAYER_COUNT = 4;
const DEPTH_START = -1800;
const DEPTH_END = 24;
const TUNNEL_RADIUS = 240;
const TAU = Math.PI * 2;

const renderer = new THREE.WebGLRenderer({
  canvas: bgCanvas,
  antialias: true,
  alpha: true,
  powerPreference: "high-performance",
});
renderer.setClearColor(0x050012, 1);
renderer.setPixelRatio(Math.min(isMobileDevice ? 1.5 : 2.2, window.devicePixelRatio || 1));
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(66, window.innerWidth / window.innerHeight, 0.1, 2800);
camera.position.z = 16;

const starRoot = new THREE.Group();
scene.add(starRoot);

const palette = [
  new THREE.Color("#ffffff"),
  new THREE.Color("#00e5ff"),
  new THREE.Color("#00b8ff"),
  new THREE.Color("#22f6d1"),
  new THREE.Color("#f050ff"),
  new THREE.Color("#8f6bff"),
];

const particles = new Array(PARTICLE_COUNT);
const streakPositions = new Float32Array(PARTICLE_COUNT * 2 * 3);
const streakColors = new Float32Array(PARTICLE_COUNT * 2 * 3);
const headPositions = new Float32Array(PARTICLE_COUNT * 3);
const headColors = new Float32Array(PARTICLE_COUNT * 3);

const streakGeometry = new THREE.BufferGeometry();
streakGeometry.setAttribute("position", new THREE.BufferAttribute(streakPositions, 3));
streakGeometry.setAttribute("color", new THREE.BufferAttribute(streakColors, 3));

const headGeometry = new THREE.BufferGeometry();
headGeometry.setAttribute("position", new THREE.BufferAttribute(headPositions, 3));
headGeometry.setAttribute("color", new THREE.BufferAttribute(headColors, 3));

const streakMaterial = new THREE.LineBasicMaterial({
  vertexColors: true,
  transparent: true,
  opacity: 0.98,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});
const streaks = new THREE.LineSegments(streakGeometry, streakMaterial);
starRoot.add(streaks);

function makeGlowTexture(size, inner = "rgba(255,255,255,1)", outer = "rgba(255,255,255,0)") {
  const c = document.createElement("canvas");
  c.width = size;
  c.height = size;
  const gx = c.getContext("2d");
  const g = gx.createRadialGradient(size * 0.5, size * 0.5, 0, size * 0.5, size * 0.5, size * 0.5);
  g.addColorStop(0, inner);
  g.addColorStop(0.35, "rgba(255,255,255,.92)");
  g.addColorStop(1, outer);
  gx.fillStyle = g;
  gx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

const headTexture = makeGlowTexture(96);

const haloMaterial = new THREE.PointsMaterial({
  size: isMobileDevice ? 9 : 12,
  map: headTexture,
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
  map: headTexture,
  transparent: true,
  opacity: 0.95,
  vertexColors: true,
  depthWrite: false,
  blending: THREE.AdditiveBlending,
  sizeAttenuation: true,
});
const heads = new THREE.Points(headGeometry, headMaterial);
starRoot.add(heads);

const dustCount = isMobileDevice ? 320 : 560;
const dustGeo = new THREE.BufferGeometry();
const dustPos = new Float32Array(dustCount * 3);
const dustCol = new Float32Array(dustCount * 3);
for (let i = 0; i < dustCount; i++) {
  const r = TUNNEL_RADIUS * (1.15 + Math.random() * 0.9);
  const a = Math.random() * TAU;
  const d = DEPTH_START + Math.random() * (DEPTH_END - DEPTH_START);
  dustPos[i * 3] = Math.cos(a) * r;
  dustPos[i * 3 + 1] = Math.sin(a) * r;
  dustPos[i * 3 + 2] = d;
  const v = 0.16 + Math.random() * 0.18;
  dustCol[i * 3] = v * 0.7;
  dustCol[i * 3 + 1] = v * 0.8;
  dustCol[i * 3 + 2] = v;
}
dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
dustGeo.setAttribute("color", new THREE.BufferAttribute(dustCol, 3));
const dust = new THREE.Points(
  dustGeo,
  new THREE.PointsMaterial({
    size: 1.6,
    transparent: true,
    opacity: 0.18,
    vertexColors: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  })
);
starRoot.add(dust);

function rand(min, max) {
  return min + Math.random() * (max - min);
}

function resetParticle(i, randomDepth = false) {
  const layer = i % LAYER_COUNT;
  const radius = Math.pow(Math.random(), 0.58) * TUNNEL_RADIUS * (0.72 + layer * 0.16);
  const angle = Math.random() * TAU;
  const color = palette[(Math.random() * palette.length) | 0];

  const p = particles[i] || {};
  p.layer = layer;
  p.x = Math.cos(angle) * radius;
  p.y = Math.sin(angle) * radius;
  p.z = randomDepth ? rand(DEPTH_START, DEPTH_END - 40) : DEPTH_START - Math.random() * 420;
  p.speed = rand(170, 620) * (0.72 + layer * 0.23);
  p.tail = rand(70, 260) * (0.78 + layer * 0.22);
  p.width = rand(0.6, 1.4) * (0.8 + layer * 0.18);
  p.phase = Math.random() * TAU;
  p.r = color.r;
  p.g = color.g;
  p.b = color.b;
  particles[i] = p;
}

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

let targetWarp = 0.2;
let warp = 0.2;
let prevTime = performance.now();

function updateParticles(dt, t) {
  const speedBoost = 0.35 + warp * 1.85;

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const p = particles[i];
    p.z += p.speed * speedBoost * dt;
    if (p.z > DEPTH_END) resetParticle(i, false);

    const zNorm = (p.z - DEPTH_START) / (DEPTH_END - DEPTH_START);
    const pulse = 0.86 + Math.sin(t * 1.45 + p.phase) * 0.14;
    const headI = (0.35 + zNorm * 1.08) * pulse;
    const tailI = 0.03 + zNorm * 0.26;

    const headZ = p.z;
    const tailZ = p.z - p.tail * (0.75 + zNorm * 1.25);

    const base = i * 6;
    streakPositions[base] = p.x;
    streakPositions[base + 1] = p.y;
    streakPositions[base + 2] = tailZ;
    streakPositions[base + 3] = p.x;
    streakPositions[base + 4] = p.y;
    streakPositions[base + 5] = headZ;

    streakColors[base] = p.r * tailI;
    streakColors[base + 1] = p.g * tailI;
    streakColors[base + 2] = p.b * tailI;
    streakColors[base + 3] = p.r * headI;
    streakColors[base + 4] = p.g * headI;
    streakColors[base + 5] = p.b * headI;

    const hb = i * 3;
    headPositions[hb] = p.x;
    headPositions[hb + 1] = p.y;
    headPositions[hb + 2] = headZ;
    headColors[hb] = Math.min(1, p.r * (0.68 + zNorm * 0.7));
    headColors[hb + 1] = Math.min(1, p.g * (0.68 + zNorm * 0.7));
    headColors[hb + 2] = Math.min(1, p.b * (0.68 + zNorm * 0.7));
  }

  streakGeometry.attributes.position.needsUpdate = true;
  streakGeometry.attributes.color.needsUpdate = true;
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

  camera.position.x += ((-pointer.x * 7.5) - camera.position.x) * 0.055;
  camera.position.y += ((pointer.y * 4.5) - camera.position.y) * 0.055;
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
