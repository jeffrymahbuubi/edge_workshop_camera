// Dashboard for the edge-sensing workshop. Vanilla ES modules on purpose:
// students read this code, and the workshop LAN has no internet to fetch a
// bundler or a CDN from.
//
// Two things here are the lesson, not decoration:
//   * the video panel going BLANK in Modes 2/3 -- the relay physically has no
//     image, because none crossed the LAN.
//   * the chart's TIME axis -- it is what makes pull-the-network legible:
//     Mode 1 flatlines and loses those seconds forever, Mode 2 backfills.

import { UI, FLAGS, PROVENANCE, WHY_BLANK, MODE_INFO, MODE_IDS } from "/content.js";
// The comparison section lives in its own module: it is static teaching content
// with no live data, and app.js had reached CLAUDE.md's 500-line limit.
import { renderCompare, wireCompare } from "/compare.js";

const DEVICE = new URLSearchParams(location.search).get("device") || "bench01";
const WINDOW_S = 60;          // chart window, matches the relay's ring buffer
const GAP_S = 2.5;            // a longer silence than this breaks the line
const FRAME_MS = 200;         // video refresh (~5/s)
const LOG_MAX = 20;

const $ = (id) => document.getElementById(id);
const history = [];           // [{t, motion, audio}]
let lastFlag = null;
let latestMode = null;
let selectedMode = null;      // what the BUTTONS say -- drives the how-to card
let previewOn = false;

// ⚠️ Language can be switched at ANY time, including before a single event has
// arrived. Anything painted only by a data path (the flag, the ratio caption,
// the connection badge) would be stranded in the old language until the next
// event -- and on an idle dashboard that is forever. So the last value of each
// is remembered here and repainted by applyLang().
// This was NOT theoretical: switching to 中文 on a fresh page left "waiting…",
// "connected" and "run both modes to see the ratio" sitting in English. Found by
// looking at the rendered page, not by reading the code.
let lastEvent = null;
let lastBandwidth = null;
let connState = "connecting";   // connecting | connected | unreachable

// ---------------------------------------------------------------------- i18n
// Default English (Jeffry's call). Remembered like the theme.
const LANG_KEY = "nv-workshop-lang";
let lang = localStorage.getItem(LANG_KEY) === "zh" ? "zh" : "en";
const t = (key) => UI[lang][key];

// ---------------------------------------------------------------- formatting

function bytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  const v = n / Math.pow(1024, i);
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${u[i]}`;
}

const rate = (bps) => (bps ? `${bytes(bps)}/s` : "—");
const clock = (t) => new Date(t * 1000).toLocaleTimeString();

// --------------------------------------------------------- teaching content
// Both blocks below render from the SAME content.js entry. That is the point of
// the data module: the card a student reads mid-experiment and the column an
// instructor reads cannot drift apart, because there is only one copy.

function renderHowTo() {
  // Follows the SELECTED mode, not the live one: a student presses Mode 3 and
  // needs the instructions immediately -- not in two seconds when the supervisor
  // has swapped clients and data starts flowing.
  const info = selectedMode ? MODE_INFO[selectedMode][lang] : null;
  const ol = $("howto-steps"), empty = $("howto-empty");
  $("howto-mode").textContent = selectedMode ? t("inThisMode")(selectedMode) : "";
  if (!info) {
    ol.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  ol.innerHTML = info.how.map((s) => `<li>${s}</li>`).join("");
}

function renderTeaching() {
  $("compare-title").textContent = t("compareTitle");
  $("compare-lead").textContent = t("compareLead");
  $("mm-title").textContent = t("multimodalTitle");
  $("mm-text").innerHTML = t("multimodal");
  renderCompare(lang);        // the rows themselves -- compare.js
}

function applyLang(next) {
  lang = next;
  localStorage.setItem(LANG_KEY, lang);
  document.documentElement.lang = lang === "zh" ? "zh-TW" : "en";

  // Static labels declare their own key; nothing here needs to know what they say.
  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.dataset.i18n);
  }
  // A few strings carry <b> for emphasis. Separate attribute so the plain path
  // above stays textContent -- innerHTML everywhere would be an XSS habit, even
  // though this copy is ours.
  for (const el of document.querySelectorAll("[data-i18n-html]")) {
    el.innerHTML = t(el.dataset.i18nHtml);
  }

  const modeWord = lang === "zh" ? "模式" : "Mode";
  $("lang-btn").textContent = t("langBtn");
  $("reset-btn").textContent = t("reset");
  for (const m of MODE_IDS) {
    $(`m${m}-name`).textContent = `${modeWord} ${m}`;
    $(MODE_BTNS[m]).textContent = `${modeWord} ${m}`;
  }
  $("prev-name").textContent = t("previewRow");

  // The data-driven strings. Repaint from remembered state, or the page keeps
  // the old language until the next event -- which never comes when idle.
  $("conn").textContent = t(connState);
  if (lastEvent) renderStatus(lastEvent);
  else $("flag-text").textContent = t("waiting");
  if (lastBandwidth) {
    renderBandwidth(lastBandwidth);
  } else {
    $("ratio-cap").textContent = t("ratioNone");
    $("live-mode").textContent = t("noData");
  }
  $("preview-banner-text").textContent = t("previewBanner");
  $("preview-btn").textContent = previewOn ? t("hideCamera") : t("showCamera");
  $("theme-btn").textContent =
    document.documentElement.getAttribute("nve-theme").startsWith("dark")
      ? t("themeLight") : t("themeDark");
  document.title = `${t("appTitle")} — ${DEVICE}`;
  $("app-title").textContent = t("appTitle");

  renderHowTo();
  renderTeaching();
  renderProvenance();
}

// ------------------------------------------------------------------- status

const FLAG_STATUS = { "FALL?": "danger", "person-active": "success", "quiet": "neutral" };

function renderStatus(ev) {
  const f = ev.feats;
  // The flag arrives as DATA (`person-active`), English on the wire by design --
  // translating it there would make the relay and the dashboard disagree about
  // what a flag means. Translate for display only.
  $("flag-text").textContent = ev.flag ? (FLAGS[lang][ev.flag] ?? ev.flag) : "—";
  $("flag-dot").setAttribute("status", FLAG_STATUS[ev.flag] ?? "neutral");

  // Bars are scaled to a readable range, not to 1.0: motion_level lives around
  // 0.0-0.3 in practice, so a 0..1 bar would never visibly move.
  const motion = f?.motion_level ?? 0;
  const audio = f?.audio_rms ?? 0;
  $("motion-bar").style.width = `${Math.min(motion / 0.3, 1) * 100}%`;
  $("audio-bar").style.width = `${Math.min(audio / 0.15, 1) * 100}%`;
  $("motion-val").textContent = f ? motion.toFixed(4) : "—";
  $("audio-val").textContent = f ? audio.toFixed(4) : "—";
  $("blobs").textContent = f?.n_blobs ?? "—";
  $("fall").textContent = f ? (f.fall_suspected ? "YES" : "—") : "—";

  // posture is null outside Mode 3 (SPEC-04); never assume it is there
  const p = ev.posture;
  $("posture").textContent = p
    ? p.posture + (p.score != null ? ` (${p.score.toFixed(2)})` : "")
    : "—";
  drawSkeleton(p);

  // Modes 1/2 raise `fall_suspected` (loud sound + motion stopped); Mode 3 raises
  // `abnormal` (upright → lying held). Different questions, same banner.
  const fall = f?.fall_suspected || p?.abnormal;
  const alert = $("fall-alert");
  if (fall) {
    $("fall-text").textContent = p?.reason || "Fall suspected — loud sound, then motion stopped";
    alert.setAttribute("data-open", "");
  } else {
    // `data-open`, not `open`: nve-alert does not observe `open`, so this branch
    // used to be a no-op and the banner stayed up forever. See index.html.
    alert.removeAttribute("data-open");
  }
}

// ------------------------------------------------------------- the lesson

function renderBandwidth(b) {
  if (!b) return;
  for (const m of [1, 2, 3]) {
    $(`m${m}-rate`).textContent = rate(b[`mode${m}_bps`]);
    $(`m${m}-total`).textContent = b[`mode${m}_total`] ? bytes(b[`mode${m}_total`]) : "—";
  }
  // Mode 3 is dim until it has ever sent, so it does not imply a mode that is
  // not built yet.
  const m3seen = b.mode3_total > 0;
  for (const el of ["m3-name", "m3-rate", "m3-total"]) {
    $(el).classList.toggle("muted", !m3seen);
  }

  // The ratio only means something once BOTH modes have sent -- "84 MB / 0" is
  // not a teaching moment. This is why totals persist across a mode switch:
  // one Jetson, run Mode 1 then Mode 2, and the number appears.
  if (b.ratio) {
    $("ratio").textContent = `${Math.round(b.ratio).toLocaleString()}×`;
    $("ratio-cap").textContent = t("ratioBoth");
  } else {
    $("ratio").textContent = "—";
    $("ratio-cap").textContent = b.mode1_total ? t("ratioSwitch") : t("ratioNone");
  }

  // The setup camera's own row (SPEC-08 §B3). Dim until it has ever sent, so it
  // does not imply pixels are flowing when they are not -- and NOT folded into
  // Mode 3's numbers above, which is what keeps Mode 3's figure quotable.
  $("prev-rate").textContent = rate(b.preview_bps);
  $("prev-total").textContent = b.preview_total ? bytes(b.preview_total) : "—";
  for (const el of ["prev-name", "prev-rate", "prev-total"]) {
    $(el).classList.toggle("muted", !b.preview_total);
  }

  latestMode = b.live_mode;
  const badge = $("live-mode");
  badge.textContent = b.live_mode ? t("modeLive")(b.live_mode) : t("noData");
  badge.setAttribute("status", b.live_mode ? "success" : "neutral");
}

// --------------------------------------------------------- the skeleton (Mode 3)

// COCO/MoveNet 17-point topology, as pairs of keypoint indices to join.
const EDGES = [[0,1],[0,2],[1,3],[2,4],[0,5],[0,6],[5,7],[7,9],[6,8],[8,10],
               [5,6],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
const KP_DRAW_CONF = 0.2;   // below this a joint is a guess; drawing it invents a limb

// Hand-rolled canvas, for the same reason the chart is hand-rolled SVG (SPEC-03
// §8): no Elements component draws a skeleton, and this one is load-bearing.
// It renders ONLY coordinates — there is deliberately no image beneath it. The
// panel showing a moving stick figure over an empty background IS the lesson:
// the Jetson understood the person without the laptop ever seeing them.
function drawSkeleton(p) {
  const wrap = $("video-wrap");
  const kp = p?.keypoints;
  if (!kp || !kp.length) {
    wrap.classList.remove("has-skeleton");
    return;
  }
  const cv = $("skeleton"), ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);

  const abn = !!p.abnormal;
  const stroke = abn ? "#ff6b6b" : "#76b900";     // NVIDIA green, or alarm red

  if (p.bbox) {
    const [bx, by, bw, bh] = p.bbox;
    ctx.strokeStyle = abn ? "#ff6b6b" : "rgba(128,128,128,.55)";
    ctx.lineWidth = 1;
    ctx.strokeRect(bx * W, by * H, bw * W, bh * H);
  }

  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  for (const [a, b] of EDGES) {
    const q = kp[a], r = kp[b];
    if (q && r && q[2] > KP_DRAW_CONF && r[2] > KP_DRAW_CONF) {
      ctx.beginPath();
      ctx.moveTo(q[0] * W, q[1] * H);
      ctx.lineTo(r[0] * W, r[1] * H);
      ctx.stroke();
    }
  }
  ctx.fillStyle = stroke;
  for (const q of kp) {
    if (q && q[2] > KP_DRAW_CONF) {
      ctx.beginPath();
      ctx.arc(q[0] * W, q[1] * H, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  wrap.classList.add("has-skeleton");
}

// --------------------------------------------------------- video / privacy

function renderProvenance() {
  // ⚠️ Mode 3's line claims no pixel crossed the LAN. While the setup preview is
  // ON that is FALSE, and leaving it up would make the dashboard lie at exactly
  // the moment a student is watching pixels arrive. The banner takes over.
  const p = $("provenance");
  p.textContent = previewOn && latestMode === 3
    ? "" : (PROVENANCE[lang][latestMode] ?? "");

  $("why-blank").textContent = WHY_BLANK[lang][latestMode] ?? t("waitingData");
}

function pollFrame() {
  const img = $("frame");
  const probe = new Image();
  probe.onload = () => {
    img.src = probe.src;
    $("video-wrap").classList.add("has-frame");
  };
  // A 404 is the CORRECT answer in Modes 2/3, not a failure: no image was ever
  // sent. Blank the panel rather than showing a broken-image icon.
  probe.onerror = () => $("video-wrap").classList.remove("has-frame");
  probe.src = `/latest.jpg?device=${encodeURIComponent(DEVICE)}&t=${Date.now()}`;
}

// -------------------------------------------------------------- the chart

function renderChart() {
  const svg = $("chart");
  const w = svg.clientWidth || 600;
  const h = svg.clientHeight || 78;
  const now = Date.now() / 1000;
  const from = now - WINDOW_S;

  while (history.length && history[0].t < from) history.shift();

  const x = (t) => ((t - from) / WINDOW_S) * w;
  const y = (v, max) => h - 3 - (Math.min(v / max, 1) * (h - 6));

  // A dropped second must render as a GAP, never as a line interpolated across
  // it -- the gap IS the resilience lesson.
  const path = (key, max) => {
    let d = "", prev = null;
    for (const p of history) {
      const cmd = prev === null || p.t - prev > GAP_S ? "M" : "L";
      d += `${cmd}${x(p.t).toFixed(1)},${y(p[key], max).toFixed(1)}`;
      prev = p.t;
    }
    return d;
  };

  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML =
    `<path d="${path("audio", 0.15)}" fill="none" stroke="var(--audio)" stroke-width="1.5"
       stroke-linejoin="round" opacity=".85"/>` +
    `<path d="${path("motion", 0.3)}" fill="none" stroke="var(--motion)" stroke-width="1.75"
       stroke-linejoin="round"/>`;
}

// -------------------------------------------------------------- event log

function logEvent(ev) {
  if (ev.flag === lastFlag) return;      // log transitions, not every second
  lastFlag = ev.flag;

  const ul = $("log");
  ul.querySelector(".empty")?.remove();
  const li = document.createElement("li");
  li.innerHTML = `<time>${clock(ev.t)}</time>` +
    `<span class="${ev.flag === "FALL?" ? "fall" : ""}">` +
    `${FLAGS[lang][ev.flag] ?? ev.flag}</span>`;
  ul.prepend(li);
  while (ul.children.length > LOG_MAX) ul.lastElementChild.remove();
}

// ------------------------------------------------------------------- feed

function onEvent(ev) {
  const f = ev.feats;
  if (f) history.push({ t: ev.t, motion: f.motion_level ?? 0, audio: f.audio_rms ?? 0 });

  lastEvent = ev;
  if (ev.bandwidth) lastBandwidth = ev.bandwidth;
  renderStatus(ev);
  renderBandwidth(ev.bandwidth);
  renderProvenance();
  logEvent(ev);
  renderChart();
}

function connect() {
  const es = new EventSource(`/events?device=${encodeURIComponent(DEVICE)}`);

  es.onopen = () => {
    connState = "connected";
    $("conn").textContent = t(connState);
    $("conn").setAttribute("status", "success");
  };
  es.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); } catch (e) { console.error("bad event", e); }
  };
  // Say so out loud when the relay is gone. A silently frozen dashboard looks
  // like a bug and steps on the pull-the-network lesson. EventSource reconnects
  // by itself and the relay replays its ring buffer, so the chart heals.
  es.onerror = () => {
    connState = "unreachable";
    $("conn").textContent = t(connState);
    $("conn").setAttribute("status", "danger");
  };
}

// ------------------------------------------ the setup preview (SPEC-08 Part B)
// The ONE way camera pixels may leave the Jetson in Mode 3. The relay holds the
// state and the Jetson polls it, exactly like /mode and /config -- so this
// button never talks to the board directly.
//
// Mode 3 ONLY. Mode 1 already streams pixels, and Mode 2's blank panel IS its
// lesson: offering "show camera" there would be offering to break the point.

function renderPreview() {
  const btn = $("preview-btn");
  btn.hidden = selectedMode !== 3;
  btn.textContent = previewOn ? t("hideCamera") : t("showCamera");
  btn.classList.toggle("on", previewOn);
  $("preview-banner").toggleAttribute("data-open", previewOn);
  renderProvenance();
}

async function syncPreview() {
  try {
    const { camera } = await (await fetch("/preview")).json();
    previewOn = !!camera;
  } catch { previewOn = false; }   // relay gone -> assume no pixels, the safe way
  renderPreview();
}

$("preview-btn").addEventListener("click", async () => {
  const next = !previewOn;
  previewOn = next;
  renderPreview();                 // optimistic; syncPreview corrects on failure
  try {
    await fetch("/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera: next }),
    });
  } catch { syncPreview(); }
});

// ------------------------------------------------------------------ chrome

$("reset-btn").addEventListener("click", async () => {
  await fetch(`/reset?device=${encodeURIComponent(DEVICE)}`, { method: "POST" });
  history.length = 0;
  lastFlag = null;
  lastBandwidth = null;      // or the ratio caption keeps describing cleared totals
  $("log").innerHTML = `<li class="empty">${t("noEvents")}</li>`;
  $("ratio-cap").textContent = t("ratioNone");
  renderChart();
});

// ------------------------------------------------ live fall tuning (SPEC-06)
// Two sliders POST the fall thresholds to the relay. Mode 1 applies them on the
// next frame; Mode 2's edge on its next tick. The relay is the single source of
// truth, so a fresh browser seeds its sliders from GET /config.
const TUNERS = [
  { slider: "loud-slider",   out: "loud-val",         key: "loud_rms_thresh",     digits: 3 },
  { slider: "motion-slider", out: "motion-slider-val", key: "motion_level_thresh", digits: 3 },
];

async function loadTuning() {
  try {
    const cfg = await (await fetch("/config")).json();
    for (const t of TUNERS) {
      if (cfg[t.key] == null) continue;
      $(t.slider).value = cfg[t.key];
      $(t.out).textContent = Number(cfg[t.key]).toFixed(t.digits);
    }
  } catch { /* offline / not up yet -- sliders stay at their dashes */ }
}

for (const t of TUNERS) {
  const s = $(t.slider);
  // Label tracks the drag; POST only on release, so we don't flood the relay.
  s.addEventListener("input", () => {
    $(t.out).textContent = Number(s.value).toFixed(t.digits);
  });
  s.addEventListener("change", () => {
    fetch("/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [t.key]: Number(s.value) }),
    }).catch(() => {});
  });
}

// ------------------------------------------------ mode switch (SPEC-07)
// Buttons POST the chosen mode to the relay; a supervisor on the Jetson swaps
// clients to match. These buttons show the SELECTED mode; the live-mode badge
// (driven by real data) shows what is actually running once it starts flowing.
const MODE_BTNS = { 1: "mode1-btn", 2: "mode2-btn", 3: "mode3-btn" };

function markMode(mode) {
  selectedMode = mode;
  for (const [m, id] of Object.entries(MODE_BTNS)) {
    $(id).classList.toggle("active", Number(m) === mode);
  }
  // The how-to card follows the SELECTED mode, not the live one: a student
  // presses Mode 3 and needs the instructions now, not in two seconds when the
  // supervisor has finished swapping clients.
  renderHowTo();
  renderPreview();
}

async function syncMode() {
  try {
    const { mode } = await (await fetch("/mode")).json();
    markMode(mode);
  } catch { /* relay not up -- leave buttons unhighlighted */ }
}

for (const [m, id] of Object.entries(MODE_BTNS)) {
  $(id).addEventListener("click", async () => {
    const mode = Number(m);
    markMode(mode);                       // optimistic; syncMode corrects if it fails
    try {
      await fetch("/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      // The relay clears the preview on every mode change (SPEC-08 §B4 -- the
      // toggle is not sticky). Mirror that here rather than waiting for the next
      // poll, or the button would claim pixels are flowing when they stopped.
      previewOn = false;
      renderPreview();
    } catch { syncMode(); }
  });
}

const THEME_KEY = "nv-workshop-theme";
// <html>, not <body> — see the comment on the <html> tag in index.html. Setting it
// on body left text dark-on-dark because the canvas colour token resolves at :root.
const THEME_HOST = document.documentElement;
function applyTheme(mode) {
  THEME_HOST.setAttribute("nve-theme", `${mode} inter`);
  $("theme-btn").textContent = mode === "dark" ? t("themeLight") : t("themeDark");
  localStorage.setItem(THEME_KEY, mode);
}
$("theme-btn").addEventListener("click", () => {
  applyTheme(THEME_HOST.getAttribute("nve-theme").startsWith("dark") ? "light" : "dark");
});
applyTheme(
  localStorage.getItem(THEME_KEY) ||
  (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
);

$("lang-btn").addEventListener("click", () => applyLang(lang === "zh" ? "en" : "zh"));

// Delegated once, before the first render: renderCompare() replaces that subtree
// on every language switch, so per-button listeners would leak or be lost.
wireCompare();

// applyLang paints every label, so it must run AFTER applyTheme (whose button
// text it sets) and BEFORE anything renders.
applyLang(lang);

loadTuning();
syncMode();
syncPreview();
setInterval(syncMode, 3000);   // reflect switches made from another browser
setInterval(syncPreview, 3000);
connect();
setInterval(pollFrame, FRAME_MS);
setInterval(renderChart, 1000);   // keep the window scrolling even when idle
addEventListener("resize", renderChart);
