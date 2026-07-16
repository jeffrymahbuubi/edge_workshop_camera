// Dashboard for the edge-sensing workshop. Vanilla ES modules on purpose:
// students read this code, and the workshop LAN has no internet to fetch a
// bundler or a CDN from.
//
// Two things here are the lesson, not decoration:
//   * the video panel going BLANK in Modes 2/3 -- the relay physically has no
//     image, because none crossed the LAN.
//   * the chart's TIME axis -- it is what makes pull-the-network legible:
//     Mode 1 flatlines and loses those seconds forever, Mode 2 backfills.

const DEVICE = new URLSearchParams(location.search).get("device") || "bench01";
const WINDOW_S = 60;          // chart window, matches the relay's ring buffer
const GAP_S = 2.5;            // a longer silence than this breaks the line
const FRAME_MS = 200;         // video refresh (~5/s)
const LOG_MAX = 20;

const $ = (id) => document.getElementById(id);
const history = [];           // [{t, motion, audio}]
let lastFlag = null;
let latestMode = null;

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

// ------------------------------------------------------------------- status

const FLAG_STATUS = { "FALL?": "danger", "person-active": "success", "quiet": "neutral" };

function renderStatus(ev) {
  const f = ev.feats;
  $("flag-text").textContent = ev.flag ?? "—";
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

  // posture stays null until Mode 3 exists (SPEC-04); never assume it is there
  const p = ev.posture;
  $("posture").textContent = p
    ? p.posture + (p.torso_angle != null ? ` (${Math.round(p.torso_angle)}°)` : "")
    : "—";

  const fall = f?.fall_suspected || p?.abnormal;
  const alert = $("fall-alert");
  if (fall) {
    $("fall-text").textContent = p?.reason || "Fall suspected — loud sound, then motion stopped";
    alert.setAttribute("open", "");
  } else {
    alert.removeAttribute("open");
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
    $("ratio-cap").textContent = "more data sent by Mode 1 than Mode 2";
  } else {
    $("ratio").textContent = "—";
    $("ratio-cap").textContent = b.mode1_total
      ? "now switch to Mode 2 to see the ratio"
      : "run both modes to see the ratio";
  }

  latestMode = b.live_mode;
  const badge = $("live-mode");
  badge.textContent = b.live_mode ? `▶ Mode ${b.live_mode} live` : "no data";
  badge.setAttribute("status", b.live_mode ? "success" : "neutral");
}

// --------------------------------------------------------- video / privacy

const PRIVACY = {
  1: ["raw frames crossed the LAN, so the relay can show your face",
      "Mode 1 sends every pixel — the relay decodes them to find motion."],
  2: ["Mode 2 sent no image — only a feature vector",
      "Mode 3 sends only a posture label — still no image."],
};

function renderProvenance() {
  const p = $("provenance");
  if (latestMode === 1) p.textContent = PRIVACY[1][1];
  else if (latestMode === 2) p.textContent = "Mode 2 computed the features on the Jetson and sent ~200 bytes. Raw pixels never left the device.";
  else if (latestMode === 3) p.textContent = "Mode 3 ran posture estimation on the Jetson and sent only its verdict.";
  else p.textContent = "";

  $("why-blank").textContent =
    latestMode === 2 ? "Mode 2 sent no image — only a feature vector"
    : latestMode === 3 ? "Mode 3 sent no image — only a posture verdict"
    : "waiting for data…";
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
    `<span class="${ev.flag === "FALL?" ? "fall" : ""}">${ev.flag}</span>`;
  ul.prepend(li);
  while (ul.children.length > LOG_MAX) ul.lastElementChild.remove();
}

// ------------------------------------------------------------------- feed

function onEvent(ev) {
  const f = ev.feats;
  if (f) history.push({ t: ev.t, motion: f.motion_level ?? 0, audio: f.audio_rms ?? 0 });

  renderStatus(ev);
  renderBandwidth(ev.bandwidth);
  renderProvenance();
  logEvent(ev);
  renderChart();
}

function connect() {
  const es = new EventSource(`/events?device=${encodeURIComponent(DEVICE)}`);

  es.onopen = () => {
    $("conn").textContent = "connected";
    $("conn").setAttribute("status", "success");
  };
  es.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); } catch (e) { console.error("bad event", e); }
  };
  // Say so out loud when the relay is gone. A silently frozen dashboard looks
  // like a bug and steps on the pull-the-network lesson. EventSource reconnects
  // by itself and the relay replays its ring buffer, so the chart heals.
  es.onerror = () => {
    $("conn").textContent = "relay unreachable — retrying";
    $("conn").setAttribute("status", "danger");
  };
}

// ------------------------------------------------------------------ chrome

$("reset-btn").addEventListener("click", async () => {
  await fetch(`/reset?device=${encodeURIComponent(DEVICE)}`, { method: "POST" });
  history.length = 0;
  lastFlag = null;
  $("log").innerHTML = '<li class="empty">no events yet</li>';
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
  for (const [m, id] of Object.entries(MODE_BTNS)) {
    $(id).classList.toggle("active", Number(m) === mode);
  }
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
    } catch { syncMode(); }
  });
}

const THEME_KEY = "nv-workshop-theme";
function applyTheme(mode) {
  document.body.setAttribute("nve-theme", `${mode} inter`);
  $("theme-btn").textContent = mode === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, mode);
}
$("theme-btn").addEventListener("click", () => {
  applyTheme(document.body.getAttribute("nve-theme").startsWith("dark") ? "light" : "dark");
});
applyTheme(
  localStorage.getItem(THEME_KEY) ||
  (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
);

document.title = `Edge Sensing — ${DEVICE}`;
loadTuning();
syncMode();
setInterval(syncMode, 3000);   // reflect switches made from another browser
connect();
setInterval(pollFrame, FRAME_MS);
setInterval(renderChart, 1000);   // keep the window scrolling even when idle
addEventListener("resize", renderChart);
