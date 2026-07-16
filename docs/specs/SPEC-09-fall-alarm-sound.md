# SPEC-09 — Fall alarm sound (the dashboard speaks up)

> **Live document.** Written 2026-07-17 at Jeffry's request, before the code.

| | |
|---|---|
| **Status** | 🟢 **Built + browser-verified** (2026-07-17). Reworked same day after Jeffry's live test caught the pulse-cut bug (§2 Constraint 2); re-verified in full. By-ear check on real hardware still owed — §3. |
| **Depends on** | SPEC-03 (the fall banner + render path), SPEC-07 (mode buttons — they double as the audio unlock gesture) |
| **Runs on** | the **browser only** — new `web/alarm.js`; nothing on the relay, nothing on the Jetson |

## 1. Why

Every mode already *shows* a fall (the FALL? banner, SPEC-03 §6), but a demo room is
not a monitoring station: nobody stares at the dashboard while a colleague performs a
fall. The alarm must reach ears, not eyes. The dashboard is the **only machine in the
topology with a speaker** — the Jetson is headless — so the sound lives in `web/`,
keyed on the **same fall boolean that opens the banner** (`feats.fall_suspected ||
posture.abnormal`). That one expression is what makes this automatically cover Modes
1, 2 **and** 3, plus every ngrok viewer (SPEC-08 Part C): anywhere the banner opens,
the alarm sounds.

Decisions (Jeffry's, 2026-07-17 — do not re-litigate):

- **Synthesized, not a shipped file.** A Web Audio siren + a SpeechSynthesis
  "Fall detected". No binary in the repo, no licensing, works with the venue offline —
  the same self-contained ethos as the hand-rolled SVG chart (SPEC-03 §8). A pre-made
  WAV was considered and dropped.
- **Alarm + voice**, in that order per cycle: the siren turns heads, the words say why.
- **Repeats while FALL? is active** — real alarm semantics. The existing banner-clear
  logic is what stops it.
- **No mute toggle.** Any first interaction with the page unlocks audio; the browser
  tab's own mute is the only off switch.

## 2. Design — three constraints shape everything

```
renderStatus() ── fall boolean (same as banner) ──▶ setFallAlarm(on, text, lang)
                                                        │ alarm.js
    rising edge  (live)      ──▶ siren NOW, then every 4 s: siren (1.6 s) + speech
    rising edge  (≤2 s after ──▶ deferred to the window's end; a replayed clear
                  a connect)     cancels it
    falling edge (<1 cycle)  ──▶ finish the cycle — the words must play (latch)
    falling edge (after)     ──▶ cut the siren, cancel the speech, NOW
```

**Constraint 1 — autoplay.** Browsers refuse to start audio before the user has
interacted with the page. The `AudioContext` is created/resumed by the first
`pointerdown`/`keydown` — in practice the student's *first mode-button click* arms the
alarm, so the normal workshop flow needs zero extra steps. If a fall is already showing
when that first gesture lands, the alarm starts immediately.

**Constraint 2 — the fall is a PULSE, not a state.** In Modes 1/2 `fall_suspected` is
true only for the one second where loud + was-moving + now-still coincide
(`features.py`) — the next event clears it. ⚠️ **Found on hardware by Jeffry
(2026-07-17), not at a desk**: the first build stopped on the falling edge
unconditionally, so the siren was cut mid-wail and the words never played. So the alarm
**latches for one full cycle** (3.8 s — siren + speech): a falling edge inside the
latch schedules the stop for the latch's end; a falling edge after it stops everything
immediately (the person got up, the room goes quiet *now*).

**Constraint 3 — the ring-buffer replay.** On (re)connect the relay replays 60 s of
history through the same render path (SPEC-03). A FALL? from a minute ago must repaint
the log but **not** sound the siren. Clocks cannot be compared — an ngrok viewer's
machine does not share the relay's clock — but the replay has a tell that *is* local:
it arrives in the first moments of the connection. `app.js` calls `alarmHoldOff()` on
every `EventSource` open; a rising edge in the next **2 s** is deferred to the window's
end, where a replayed clear will have cancelled it — while a fall that is *genuinely
still active* (the banner agrees) begins late but begins. A live fall on an open
connection sounds with **no delay at all**. (The first build gated on "state held
1.5 s" instead — that swallowed exactly the 1-second pulses of Constraint 2, and cost
every real fall 1.5 s of latency besides.)

Checklist:

- [x] **`web/alarm.js`** (new module — `app.js` is past CLAUDE.md's 500-line limit,
      same reason `compare.js` exists): siren = square-wave oscillator alternating
      880/660 Hz for 1.6 s under a click-free gain envelope; voice = SpeechSynthesis
      utterance in the dashboard's current language (`en-US` / `zh-TW`); one cycle
      every 4 s while active.
- [x] **`app.js`** — one call in `renderStatus()`, right after the banner branch, passing
      the same boolean. No second fall computation anywhere.
- [x] **`content.js`** — `fallSpoken` in both languages. The spoken words follow the
      language toggle like everything else.
- [x] **Stop is immediate — after the first full cycle**: past the latch, a falling
      edge cuts the current siren's gain, clears the repeat timer, and
      `speechSynthesis.cancel()`s any speech mid-word. Inside the latch it waits
      for the cycle to finish (Constraint 2).
- [x] **Observable for verification**: `window.__fallAlarm` exposes `{armed, sounding,
      cycles}` read-only, and start/stop log one console line each — playwright cannot
      hear, but it can read.
- [x] **The relay's JS whitelist** (`_JS_MODULES`) gained `alarm` — found while wiring,
      not in the original design: an ES-module import that 404s kills the WHOLE module
      graph, so the dashboard would have loaded blank. The existing served-modules test
      now covers all four.

Non-goals: no sound on the Jetson (no speaker), no relay involvement (the relay already
publishes the fall; adding an audio flag would be a second copy of the same fact), no
volume slider (the OS has one).

## 3. Validation

### Browser (laptop, relay + synthetic events, playwright-cli)

Verified 2026-07-17 (headless Chromium, local relay, falls injected via
`POST /ingest_features`, `speechSynthesis.speak` instrumented to record
utterances — playwright cannot hear, so the evidence is state + records).
Re-run in full after the pulse-latch rework; the boxes below are the rework's
results:

- [x] Fresh page, no gesture: fall injected → banner opens (screenshot read), `armed:
      false`, `cycles: 0` — nothing can sound before a gesture.
- [x] **The hardware bug**: after a click, a single 1-second fall pulse → `sounding`
      still true right after the clearing event (the latch holding where the first
      build had already cut it), spoken `["Fall detected", "en-US"]` recorded, then
      self-stopped — exactly 1 cycle, console shows `sounding` then `stopped`.
- [x] A held fall (~9 s) → 5 more cycles; the clear stops it immediately,
      `speechSynthesis` queue empty.
- [x] Reload with FALL? events in the ring buffer (ending cleared) → the event log
      repaints them, banner stays closed, `cycles: 0` at +4 s — past the 2 s hold-off,
      so a deferred begin would already have fired if the gate leaked.
- [x] Switched to 中文, pulse → spoken `["偵測到跌倒", "zh-TW"]`, one cycle,
      self-stopped.

### By ear (real hardware — Jeffry)

- [ ] Mode 3 live fall → siren audible across the room, then "Fall detected"; repeats
      until the person gets up; stops by itself.
- [ ] Mode 1/2 fall (SPEC-06 slider workaround or the real mic) → same sound, no
      per-mode difference.
- [ ] 中文 dashboard speaks Chinese. (SpeechSynthesis voices are OS-local on Windows;
      if the venue laptop lacks a zh-TW voice the utterance is silent — the siren still
      sounds. Check once on the venue machine.)

## 4. Open

- [ ] The banner's fallback text (`app.js`: "Fall suspected — loud sound, then motion
      stopped") is hardcoded English — predates this spec, noticed while wiring the
      alarm. Belongs in `content.js` with the rest of the copy.
- [ ] If the venue machine has no zh-TW voice installed, spoken Chinese is silently
      skipped (siren unaffected). Acceptable; note for the venue checklist.
