// The fall alarm sound (SPEC-09). The dashboard is the only machine in the
// topology with a speaker -- the Jetson is headless -- so the alarm lives here,
// keyed on the SAME fall boolean that opens the banner. Each cycle: a two-tone
// siren (Web Audio, synthesized -- no file in the repo, works with the venue
// offline) followed by a spoken "Fall detected" (SpeechSynthesis).
//
// Two constraints shape this file:
//
//  * AUTOPLAY. Browsers refuse to start audio before the user has interacted
//    with the page. The AudioContext is created/resumed by the first
//    pointerdown/keydown -- in practice the student's first mode-button click
//    arms the alarm, so the normal flow needs zero extra steps. If a fall is
//    already showing when that first gesture lands, sounding starts then.
//
//  * REPLAY. On (re)connect the relay replays its 60 s ring buffer through the
//    same render path (SPEC-03), so a FALL? from a minute ago repaints the
//    banner history and must NOT sound the siren. Clocks cannot be compared --
//    an ngrok viewer (SPEC-08) does not share the relay's clock -- so the gate
//    is wall time HERE: the fall must hold for HOLD_MS before the first sound.
//    The replay burst flashes past in milliseconds and can never hold that
//    long; a real fall is held >= 3 s by the edge rule, so it always qualifies.
//    Costs 1.5 s of alarm latency; the banner stays instant.

const HOLD_MS = 1500;    // the replay gate -- see above before changing
const CYCLE_MS = 4000;   // siren (1.6 s) + speech + a breath, then again

let ctx = null;          // AudioContext -- created on first gesture, NEVER before
let sounding = false;
let cycles = 0;          // total cycles ever played (verification reads this)
let holdTimer = null;    // pending rising edge, cancelled if the fall clears
let repeatTimer = null;
let curGain = null;      // the playing siren's gain, so stop() can cut its tail
let spoken = { text: "Fall detected", lang: "en-US" };

function unlock() {
  const first = !ctx;
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") ctx.resume();
  // A fall was already sounding "silently" (state on, nothing audible yet)
  // when the first gesture landed: make noise now, not at the next interval.
  if (first && sounding) cycle();
}
addEventListener("pointerdown", unlock);
addEventListener("keydown", unlock);

// 880/660 Hz alternating square wave -- the classic two-tone alarm. The gain
// envelope ramps in/out because starting a square wave at full volume clicks.
function siren() {
  const t0 = ctx.currentTime;
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = "square";
  for (let i = 0; i < 4; i++) o.frequency.setValueAtTime(i % 2 ? 660 : 880, t0 + i * 0.4);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.25, t0 + 0.03);
  g.gain.setValueAtTime(0.25, t0 + 1.55);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.6);
  o.connect(g).connect(ctx.destination);
  o.start(t0);
  o.stop(t0 + 1.6);
  curGain = g;
  return 1600;
}

function speak() {
  if (!("speechSynthesis" in window)) return;
  // If the OS has no voice for the language (zh-TW on a bare venue machine),
  // this is silently skipped by the browser -- the siren still sounded.
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(spoken.text);
  u.lang = spoken.lang;
  speechSynthesis.speak(u);
}

function cycle() {
  if (!sounding || !ctx || ctx.state !== "running") return;  // not unlocked yet
  const ms = siren();
  setTimeout(() => { if (sounding) speak(); }, ms);
  cycles++;
}

function begin() {
  holdTimer = null;
  sounding = true;
  console.log("fall-alarm: sounding");
  cycle();
  repeatTimer = setInterval(cycle, CYCLE_MS);
}

function stop() {
  if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; }
  if (!sounding) return;
  sounding = false;
  clearInterval(repeatTimer);
  repeatTimer = null;
  // Cut the playing siren's tail and any speech mid-word: the person got up,
  // the room should go quiet NOW, not 1.6 s from now.
  if (curGain) {
    curGain.gain.cancelScheduledValues(ctx.currentTime);
    curGain.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.02);
    curGain = null;
  }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  console.log("fall-alarm: stopped");
}

// Called from renderStatus() on EVERY event with the banner's own boolean --
// edge detection happens here, so app.js stays one line.
export function setFallAlarm(on, text, lang) {
  spoken = { text, lang: lang === "zh" ? "zh-TW" : "en-US" };
  if (on) {
    if (!sounding && !holdTimer) holdTimer = setTimeout(begin, HOLD_MS);
  } else {
    stop();
  }
}

// Read-only state for the browser-verification pass (SPEC-09 §3) -- playwright
// cannot hear, but it can read this.
window.__fallAlarm = {
  get armed() { return !!ctx && ctx.state === "running"; },
  get sounding() { return sounding; },
  get cycles() { return cycles; },
};
