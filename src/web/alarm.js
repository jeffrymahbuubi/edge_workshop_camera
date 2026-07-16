// The fall alarm sound (SPEC-09). The dashboard is the only machine in the
// topology with a speaker -- the Jetson is headless -- so the alarm lives here,
// keyed on the SAME fall boolean that opens the banner. Each cycle: a two-tone
// siren (Web Audio, synthesized -- no file in the repo, works with the venue
// offline) followed by a spoken "Fall detected" (SpeechSynthesis).
//
// Three constraints shape this file:
//
//  * AUTOPLAY. Browsers refuse to start audio before the user has interacted
//    with the page. The AudioContext is created/resumed by the first
//    pointerdown/keydown -- in practice the student's first mode-button click
//    arms the alarm, so the normal flow needs zero extra steps. If a fall is
//    already showing when that first gesture lands, sounding starts then.
//
//  * THE FALL IS A PULSE, NOT A STATE. In Modes 1/2 `fall_suspected` is true
//    only for the one second where loud + was-moving + now-still coincide
//    (features.py) -- the next event clears it. Jeffry's first hardware test
//    proved it: the siren started and was cut mid-wail, and the words never
//    played. So once the alarm begins it is LATCHED for one full cycle
//    (MIN_SOUND_MS): a falling edge inside the latch schedules the stop for
//    the latch's end instead of executing it. Past the latch, a falling edge
//    stops everything immediately -- the person got up, the room goes quiet.
//
//  * REPLAY. On (re)connect the relay replays its 60 s ring buffer through the
//    same render path (SPEC-03), so a FALL? from a minute ago repaints the
//    banner history and must NOT sound the siren. Clocks cannot be compared --
//    an ngrok viewer (SPEC-08) does not share the relay's clock -- but the
//    replay has a tell that IS local: it arrives in the first moments of the
//    connection. app.js calls alarmHoldOff() on every EventSource open, and a
//    rising edge inside that window is deferred to the window's end -- where a
//    replayed clear will have cancelled it, while a genuinely-still-active
//    fall (the banner agrees) begins late but begins. A LIVE fall on an open
//    connection starts the siren with no delay at all.

const HOLDOFF_MS = 2000;    // the replay window after a connect -- see above
const CYCLE_MS = 4000;      // siren (1.6 s) + speech + a breath, then again
const MIN_SOUND_MS = 3800;  // the latch: one full cycle, deliberately < CYCLE_MS
                            // so a latched stop always lands before cycle two

let ctx = null;          // AudioContext -- created on first gesture, NEVER before
let fallActive = false;  // the banner's boolean, mirrored
let sounding = false;
let cycles = 0;          // total cycles ever played (verification reads this)
let beganAt = 0;         // when sounding started, for the latch arithmetic
let holdoffUntil = 0;    // rising edges before this instant are replay-suspect
let pendingBegin = null; // begin deferred to the holdoff's end
let pendingStop = null;  // stop deferred to the latch's end
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
  // `sounding`, not `fallActive`: inside the latch the fall may already have
  // cleared, and the whole point of the latch is that the words still play.
  setTimeout(() => { if (sounding) speak(); }, ms);
  cycles++;
}

function begin() {
  pendingBegin = null;
  sounding = true;
  beganAt = performance.now();
  console.log("fall-alarm: sounding");
  cycle();
  repeatTimer = setInterval(cycle, CYCLE_MS);
}

function stop() {
  pendingStop = null;
  if (!sounding) return;
  sounding = false;
  clearInterval(repeatTimer);
  repeatTimer = null;
  // Cut the playing siren's tail and any speech mid-word.
  if (curGain) {
    curGain.gain.cancelScheduledValues(ctx.currentTime);
    curGain.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.02);
    curGain = null;
  }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  console.log("fall-alarm: stopped");
}

// Called by app.js on EVERY EventSource open (first connect and reconnects) --
// the ring-buffer replay arrives in the moments right after this.
export function alarmHoldOff() {
  holdoffUntil = performance.now() + HOLDOFF_MS;
}

// Called from renderStatus() on EVERY event with the banner's own boolean --
// all edge detection happens here, so app.js stays one line.
export function setFallAlarm(on, text, lang) {
  spoken = { text, lang: lang === "zh" ? "zh-TW" : "en-US" };
  if (on === fallActive) return;
  fallActive = on;

  if (on) {
    // The fall came back while a latched stop was pending: keep sounding.
    if (pendingStop) { clearTimeout(pendingStop); pendingStop = null; }
    if (sounding || pendingBegin) return;
    const wait = holdoffUntil - performance.now();
    if (wait > 0) pendingBegin = setTimeout(begin, wait);   // replay-suspect
    else begin();                                           // live: no delay
  } else {
    // A clear during the holdoff window is the replay finishing its story --
    // exactly the case the deferred begin exists to cancel.
    if (pendingBegin) { clearTimeout(pendingBegin); pendingBegin = null; }
    if (!sounding) return;
    const played = performance.now() - beganAt;
    if (played >= MIN_SOUND_MS) stop();
    else pendingStop = setTimeout(stop, MIN_SOUND_MS - played);  // the latch
  }
}

// Read-only state for the browser-verification pass (SPEC-09 §3) -- playwright
// cannot hear, but it can read this.
window.__fallAlarm = {
  get armed() { return !!ctx && ctx.state === "running"; },
  get sounding() { return sounding; },
  get cycles() { return cycles; },
};
