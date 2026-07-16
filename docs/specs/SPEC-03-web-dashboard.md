# SPEC-03 — Web Dashboard

> **Live document.** Tick as you build. Layout decisions here were settled with Jeffry on
> 2026-07-16 and are recorded in
> [`docs/01-design/06`](../01-design/06-deployment-topology-edge-relay.md) § *Dashboard design*.

| | |
|---|---|
| **Status** | 🟢 **Built** (2026-07-16) — data path validated against the real Jetson. ⚠️ **Visual rendering not yet verified in a browser** (§7). |
| **Priority** | 🔴 **TOP** (with SPEC-02) |
| **Runs on** | The **student laptop**, served by `relay_server.py`. Never the Jetson. |
| **Depends on** | SPEC-02 (`/events`, `/latest.jpg`, `/reset`) — ✅ all built |

**Built:** `src/web/index.html` + `src/web/app.js`, served by the relay at `GET /`
(`/app.js`, and `/vendor/*` mounted via `StaticFiles`). Open
**`http://<laptop-ip>:8000/`** — add `?device=bench02` to watch the other bench.

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

### Done — 2026-07-16

- [x] **All 7 assets serve 200** with correct content types: `/`, `/app.js`, `core.js`,
      `styles.css`, `themes.css`, `fonts/inter.css`, `inter.woff2` ✅
- [x] **Zero external references** in `index.html` / `app.js`, and no `fetch(http…)` or
      `import(http…)` inside the vendored Elements bundle ✅
- [x] **`app.js` parses** (`node --check`); all relay Python parses ✅
- [x] **All 30 element IDs cross-check** — every `$("…")` in `app.js` exists in
      `index.html`, none missing, none orphaned. *(This is the failure that would
      otherwise be silent: a typo'd id returns `null` and that panel just never updates.)* ✅
- [x] **All 4 Elements components** used (`nve-alert`, `nve-badge`, `nve-button`,
      `nve-dot`) are registered in `core.js` ✅
- [x] **Driven with real Jetson data** — Mode 1 → Mode 2, real C270 webcam, over the LAN.
      The exact feed the browser receives: `flag: person-active`, `live_mode: 2`,
      `mode1_total: 879,984 B`, `mode2_total: 374 B`,
      **`ratio: 2352.9` → renders as `2,353×`**, `posture: null` (guarded) ✅
- [x] **`/latest.jpg` → 404 after switching to Mode 2** — the privacy panel blanks ✅

### ⚠️ Outstanding — the browser pass (next phase: playwright-cli)

**None of this is verified.** The data path is proven; the **rendering has never been
loaded in a browser**. No screenshot tooling was available in the build session, so these
are honest unknowns, not assumed passes.

#### How to bring it up

```bash
# 1. Relay + dashboard on the laptop (from src/)
cd src && uv run --with fastapi --with "uvicorn[standard]" --with opencv-python \
  --with numpy --with pydantic uvicorn relay.relay_server:app --host 0.0.0.0 --port 8000
# 2. Open http://localhost:8000/          (?device=bench02 for the other bench)

# 3. Feed it real data from the Jetson (PuTTY, not ssh -- no key installed):
#    "/c/Program Files/PuTTY/plink" -batch -pw <pw> jetson@192.168.137.100 \
#      "cd ~/EDGE-CAMERA && RELAY_URL=http://192.168.137.1:8000 SENSOR=webcam \
#       timeout -s INT 8 python3 -m edge.mode1_streamer"
#    ...then the same with edge.mode2_edge to make the ratio appear.

# No hardware? Run a client on the laptop with SENSOR=synthetic and
# RELAY_URL=http://localhost:8000 -- enough to exercise every panel.
```

#### The checks

- [ ] **Does it render at all** — layout, Elements components upgrading (`nve-badge`,
      `nve-dot`, `nve-alert`, `nve-button`), Inter font loading.
- [ ] **Zero network requests leave the machine.** Assert this in Playwright by failing
      on any request whose URL is not same-origin — the strongest version of the offline
      guarantee, and the one static analysis can't give. `vendor/elements/smoke-test.html`
      already demonstrates the `window.fetch` interception trick.
- [ ] Video panel shows the frame in Mode 1 and **blanks** on the switch to Mode 2.
      **If a face survives into Mode 2 that is a bug, not a glitch** — see SPEC-02 §7.
- [ ] Ratio reads `—` with only one mode seen, then a number once both have sent.
- [ ] Refresh mid-demo → chart repopulates from the ring buffer (not blank).
- [ ] **Two browsers at once** → both update. Catches the SSE fan-out bug (SPEC-02 §5) —
      a single shared generator would deadlock the second client.
- [ ] Pull the cable in Mode 1 → gap in the chart, connection badge turns red/"relay
      unreachable".
- [ ] Pull the cable in Mode 2 → gap, then **backfill** on reconnect, drawn at the
      correct *timestamps* rather than bunched at "now".
- [ ] Both **light and dark** themes — toggle in the header, persisted to `localStorage`.
- [ ] Reset button clears totals, chart and log.

> **Playwright note.** The page is entirely SSE- and timer-driven; there is no
> "load complete" moment to await. Wait on **content** (e.g. `#ratio` not being `—`)
> rather than on network idle, which will never arrive while `/events` is open.

---

## 8. Implementation notes

Decisions taken while building, worth knowing before you change something:

- **The chart is hand-rolled SVG, not `nve-sparkline`.** Elements ships a sparkline and
  it was tempting, but it takes a plain `data` array — it cannot express a **time axis**
  or a **gap**, and both are load-bearing. Points plot against the event's own `t`, and a
  silence longer than `GAP_S` (2.5 s) **breaks the path** rather than interpolating over
  it. Without that, Mode 2's backfill draws as a smooth line and the resilience lesson
  evaporates. Elements still does all the chrome.
- **Bars scale to a readable range, not to 1.0.** Measured on hardware, `motion_level`
  lives around 0.0–0.3 and `audio_rms` around 0.0–0.15 (SPEC-02 §9), so a 0..1 bar would
  sit visibly dead. Scaled to 0.3 / 0.15.
- **Video uses a detached probe `Image()`.** Swapping `src` on the live element flickers
  it to broken on every 404; loading into a probe and committing only on success keeps
  the blank state clean and deliberate.
- **Mode 3's row is dimmed until it ever sends**, so the panel doesn't imply a mode that
  isn't built.
- **The event log records transitions, not seconds** — logging every second buries the fall.

---

## 9. Open

- [ ] Ratio panel shows the **active device only**; `?device=bench02` selects the other.
      Per-device rows deferred until a second bench exists. (SPEC-02 §10)
- [ ] The caregiver `note` field is **not rendered** — always `null` while the LLM is
      deferred to last priority. Add when the interpreter lands.
- [ ] Posture is a single line (`posture` + `torso_angle`). SPEC-04 may want the
      timeline + alarm-banner treatment.
