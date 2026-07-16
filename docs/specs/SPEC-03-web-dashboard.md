# SPEC-03 — Web Dashboard

> **Live document.** Tick as you build. Layout decisions here were settled with Jeffry on
> 2026-07-16 and are recorded in
> [`docs/01-design/06`](../01-design/06-deployment-topology-edge-relay.md) § *Dashboard design*.

| | |
|---|---|
| **Status** | 🟡 Specified, not built |
| **Priority** | 🔴 **TOP** (with SPEC-02) |
| **Runs on** | The **student laptop**, served by `relay_server.py`. Never the Jetson. |
| **Depends on** | SPEC-02 (`/events`, `/latest.jpg`, `/reset`) |

**Build order matters.** Per `docs/01-design/06` § *Build & test sequence*: get the
terminal back-end solid first, dashboard second. Do not start here until SPEC-02 §9
passes on hardware.

---

## 1. Layout — split: status on top, the lesson below

```
┌─ STATUS ──────────────────────┐
│  ● person-active              │   flag: quiet / person-active / FALL?
│  motion ▓▓▓▓▓░░░░░  0.34      │
│  audio  ▓▓░░░░░░░░  0.08      │
│  blobs: 2      fall: —        │
├─ THE LESSON ──────────────────┤
│  MODE 1   1.42 MB/s           │
│  MODE 2   2.1  KB/s           │
│  ratio      676× ▲            │   ← the headline number, live
└───────────────────────────────┘
```

- [ ] Both panels visible without scrolling on a laptop screen. The ratio is the point
      of the morning; it must never be below the fold.
- [ ] Serve at `GET /`, assets from `src/web/`.

---

## 2. The video panel — this *is* the privacy lesson

Not decoration. **The panel's emptiness in Mode 2 is the deliverable.**

```
MODE 1                MODE 2
┌────────────┐        ┌────────────┐
│  [ face ]  │        │  ␀         │
│  visible   │        │  no image  │
│  on relay  │        │  ever sent │
└────────────┘        └────────────┘
  ↑ privacy exposed     ↑ private
```

In Mode 1 the relay *has* the JPEGs — it must decode them to run `features.py` — so it
can show faces. In Mode 2 it **physically cannot**: no image ever crossed the LAN. The
same panel going blank on a mode switch turns *"faces leave the room"* from a claim into
something a student watches happen.

- [ ] `<img src="/latest.jpg">` refreshed ~5/s with a cache-buster (`?t=<ms>`).
- [ ] **On 404, show the placeholder** — "no image ever sent" — not a broken-image icon.
      Handle `onerror`.
- [ ] Never inline frames into the SSE stream (SPEC-02 §5). Keeping the data channel tiny
      is both correct engineering *and* the honest version of the story.
- [ ] Label the panel with its provenance: *"this frame is on the laptop because Mode 1
      sent it"* vs *"Mode 2 sent no image"*. Say why it is blank; do not make them guess.

> **If you see a face in Mode 2, that is a bug, not a glitch** — the relay is serving a
> stale frame. SPEC-02 §7 requires clearing it on mode switch.

---

## 3. History — rolling 60 s chart + fall event log

```
motion ╱╲__╱╲╱╲_____╱╲__
audio  __╱╲______╱╲______
       └─ 60s ago    now ┘

EVENTS
14:02:11  FALL? suspected
13:58:40  person-active
```

- [ ] Two sparklines (motion, audio) over the last 60 s.
- [ ] **The time axis is what makes pull-the-network legible**: Mode 1's trace flatlines
      and the lost seconds never return; Mode 2 buffers and **backfills** on reconnect.
      Without it, a dropped second flickers past unnoticed.
- [ ] Plot against **event timestamp `t`**, not arrival order — otherwise Mode 2's
      backfill draws as a smooth line and the whole resilience lesson evaporates.
- [ ] Gaps render as **gaps**, not interpolated lines.
- [ ] Event log: timestamped flag transitions; keep the last ~20. Log on *change*, not
      every second.
- [ ] On connect, the server replays its ring buffer (SPEC-02 §6). Render replayed events
      without firing alarm animations (`"replay": true`).

---

## 4. Mode comparison — one live, both totals persist

Students have one Jetson and one camera, so no simultaneous side-by-side.

```
LIVE: ▶ MODE 2
           bytes sent   last seen
MODE 1     84.2 MB      13:58
MODE 2     126 KB       ▶ now
           ─────────────────────
           ratio 668×
```

- [ ] Show the live mode prominently; keep both cumulative totals on screen.
- [ ] **Retaining totals across the switch is what makes the ratio appear** without a
      second sender.
- [ ] Show `—` for the ratio until both totals are non-zero (SPEC-02 §3.2).
- [ ] A visible **reset** control → `POST /reset` for the next student pair.
- [ ] Format bytes human-readably (KB/MB/GB); a raw `88293104` teaches nothing.

---

## 5. Stack

- [ ] **Vanilla HTML/JS.** No build step, no framework, no npm. Students read this code;
      a bundler is a barrier and the LAN has no internet to fetch one.
- [ ] **NVIDIA Elements**, vendored offline at `src/web/vendor/elements/` (already in
      place: `core.js`, `styles.css`, `themes.css`, `fonts/inter.woff2`, `LICENSE`).
      Verified offline-safe in a real browser — see
      [`docs/03-tooling/11`](../03-tooling/11-nvidia-tooling-and-skills-findings.md).
- [ ] **Zero external requests.** No CDN, no Google Fonts. The workshop LAN is a cable
      between two machines with no internet; one `<link>` to a CDN and the page hangs.
- [ ] Charts: hand-rolled SVG or `<canvas>`. Two sparklines do not justify a charting
      library, and every library here is another offline liability.
- [ ] `src/web/vendor/elements/smoke-test.html` renders the dashboard-relevant components
      — crib from it rather than guessing at the API.

---

## 6. SSE client

- [ ] `new EventSource("/events")`.
- [ ] `EventSource` auto-reconnects; on reopen the server replays the ring buffer, so the
      chart heals itself. **Do not hand-roll reconnection** — you will fight the browser.
- [ ] Show a connection indicator. When the student pulls the cable, the dashboard should
      *say* it lost the relay rather than silently freezing — the freeze looks like a bug
      and steps on the lesson.
- [ ] Guard every optional field (`posture` is `null` until SPEC-04).

---

## 7. Validation

- [ ] Loopback with `SENSOR=synthetic` Mode 1: status updates each second, video panel
      shows the synthetic block, byte totals climb.
- [ ] Switch to Mode 2: **video panel blanks**, ratio appears, motion still tracks.
- [ ] Refresh mid-demo → chart repopulates from the ring buffer (not blank).
- [ ] Open a **second browser** → both update. (Catches the SSE fan-out bug, SPEC-02 §5.)
- [ ] Pull the cable in Mode 1 → gap in the chart, connection indicator reacts.
- [ ] Pull the cable in Mode 2 → gap, then **backfill** on reconnect.
- [ ] **Airplane mode / unplug the internet** → dashboard fully functional. Any external
      asset shows up here.
- [ ] Check both light and dark themes (Elements ships `themes.css`).

---

## 8. Open

- [ ] Ratio panel: per-device rows, or the active device only? (SPEC-02 §10)
- [ ] Show the caregiver `note` field? Currently always `null` — the LLM is deferred to
      last priority, so the field exists but nothing fills it. Render only when non-null.
- [ ] Posture panel layout — deferred to SPEC-04.
