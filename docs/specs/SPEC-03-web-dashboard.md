# SPEC-03 — Web Dashboard

> **Live document.** Tick as you build. Layout decisions here were settled with Jeffry on
> 2026-07-16 and are recorded in
> [`docs/01-design/06`](../01-design/06-deployment-topology-edge-relay.md) § *Dashboard design*.

| | |
|---|---|
| **Status** | 🟢 **Built + verified in a real browser** (2026-07-16, playwright-cli — §7, 8/10 checks; the 2 open are cable-pull, bench-only). **Since extended** with the SPEC-06 fall-sensitivity sliders and the SPEC-07 Mode 1/2/3 buttons — both browser-verified live against the Jetson. |
| **Priority** | 🔴 **TOP** (with SPEC-02) |
| **Runs on** | The **student laptop**, served by `relay_server.py`. Never the Jetson. |
| **Depends on** | SPEC-02 (`/events`, `/latest.jpg`, `/reset`) — ✅ all built |

> **The dashboard now carries three control clusters, not just readouts:** the header
> **Mode 1/2/3 buttons** (SPEC-07, drive `/mode`), the **Fall sensitivity** panel with two
> sliders (SPEC-06, drive `/config`), and the original reset/theme controls. New element ids
> since the §7 audit: `mode1-btn`/`mode2-btn`/`mode3-btn`, `loud-slider`/`loud-val`,
> `motion-slider`/`motion-slider-val`. Two open rendering bugs from the first browser load
> (fall banner on load; theme loads light) are **still Jeffry's to fix** — see §7 for the
> root causes.

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

Not decoration. **The panel's emptiness in Mode 2 is the deliverable** — and with Mode 3
it became a three-way progression instead of a two-way one:

```
MODE 1                MODE 2                MODE 3
┌────────────┐        ┌────────────┐        ┌────────────┐
│  [ face ]  │        │  ␀         │        │    ᛭       │
│  visible   │        │  no image  │        │  skeleton  │
│  on relay  │        │  ever sent │        │  no pixels │
└────────────┘        └────────────┘        └────────────┘
  ↑ privacy exposed     ↑ private             ↑ private AND understood
  ~583 KB of pixels     ~200 B vector         562 B of coordinates
```

In Mode 1 the relay *has* the JPEGs — it must decode them to run `features.py` — so it
can show faces. In Mode 2 it **physically cannot**: no image ever crossed the LAN. The
same panel going blank on a mode switch turns *"faces leave the room"* from a claim into
something a student watches happen.

**Mode 3 (2026-07-16) is the strongest panel of the three**: a moving stick figure over an
empty background. It is not empty because nothing happened — it is **empty of pixels**
while still proving the Jetson understood the person completely. The browser draws it from
17 coordinates; `/latest.jpg` still 404s the whole time.

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
- [x] Guard every optional field (`posture` is `null` outside Mode 3).
- [x] ✅ **The two open rendering bugs are FIXED 2026-07-16** — both were invisible in
      source and only a real browser showed them:
      - **The alarm banner cried wolf on load and then never closed.** Root cause: the
        vendored `nve-alert` **does not observe an `open` attribute**, so
        `removeAttribute("open")` was silently a no-op — the banner was stuck up forever,
        which made a *real* `FALL?` indistinguishable from the stuck one. Now driven by our
        own `data-open` + `#fall-alert { display: none }`, independent of the component's
        API. Verified: clean load → fires on a fall → **clears**.
      - **Dark theme rendered dark-on-dark.** `nve-theme` was on `<body>`, but themes.css
        declares `--nve-sys-layer-canvas-color: var(--nve-sys-text-color)` at `:root`/`html`
        where the attribute was absent — and custom properties resolve **at the element
        that declares them**, so it locked in light's 20% text while `background` flipped
        correctly. Moved to `<html>` (themes.css's own selector list allows it). Verified
        legible.

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

### The browser pass — RUN 2026-07-16 (playwright-cli, synthetic sensor): **8/10 pass**

The two cable-pull checks need someone at the bench with the Jetson and are **not run**.
Everything else below is verified in a real browser. Two rendering bugs found on the
*first* load (2026-07-16, earlier session) are **still open** and are Jeffry's to fix:
the `#fall-alert` banner shows on page load with no data (`index.html:111` has no initial
hidden state), and the page loads light despite `nve-theme="dark inter"` — see the note
under *Both light and dark themes* for the root cause of the second.

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

- [x] **Does it render at all** — layout, Elements components upgrading (`nve-badge`,
      `nve-dot`, `nve-alert`, `nve-button`), Inter font loading.
      *(All 4 `customElements.get()` → defined, each with a `shadowRoot`;
      `document.fonts.check('12px Inter')` → true.)*
- [x] **Zero network requests leave the machine.** Assert this in Playwright by failing
      on any request whose URL is not same-origin — the strongest version of the offline
      guarantee, and the one static analysis can't give. `vendor/elements/smoke-test.html`
      already demonstrates the `window.fetch` interception trick.
      *(**5,537 requests across two browsers, every one `127.0.0.1:8000`.** `playwright-cli
      requests` lists them all — no interception trick needed.)*
- [x] Video panel shows the frame in Mode 1 and **blanks** on the switch to Mode 2.
      **If a face survives into Mode 2 that is a bug, not a glitch** — see SPEC-02 §7.
      *(Frame shown in Mode 1 → on switch, `/latest.jpg` 404s and the panel reads "Mode 2
      sent no image — only a feature vector". No face survived.)*
- [x] Ratio reads `—` with only one mode seen, then a number once both have sent.
      *(Held `—` through a Mode-1-only run, then read `996×`.)*
- [x] Refresh mid-demo → chart repopulates from the ring buffer (not blank).
      *(Chart path 627 chars + 20 log rows after reload; totals retained.)*
- [x] **Two browsers at once** → both update. Catches the SSE fan-out bug (SPEC-02 §5) —
      a single shared generator would deadlock the second client.
      *(Both advanced together: 12.1→14.1 KB and 12.5→14.4 KB. No deadlock.)*
- [ ] Pull the cable in Mode 1 → gap in the chart. **Needs the bench.**

      > ⚠️ **This check used to say "connection badge turns red" — that was wrong.**
      > `#conn` tracks the **browser→relay** `EventSource` (`app.js:215 es.onerror`), not
      > the Jetson→relay link. The relay and the dashboard both run on the laptop, so
      > pulling the Jetson's cable gaps the chart and leaves the badge **green**. Do not
      > report that as a failure. The badge only goes red if the **relay** dies — verified
      > separately by routing `/events`→500: it reads "relay unreachable — retrying".
      > *(Auto-recovery is still unverified: per WHATWG, `EventSource` fails **permanently**
      > on an HTTP error status and only auto-retries on a true connection error, so a
      > routed 500 cannot test it.)*
- [ ] Pull the cable in Mode 2 → gap, then **backfill** on reconnect, drawn at the
      correct *timestamps* rather than bunched at "now". **Needs the bench.**
- [x] Both **light and dark** themes — toggle in the header, persisted to `localStorage`.
      *(Toggle works and persists. **Both open theme bugs root-caused:** the page loads
      light because `app.js:240` calls `applyTheme(localStorage ?? prefers-color-scheme)`,
      overwriting the `dark inter` in `index.html:101` — that attribute is dead. And dark
      renders **dark-on-dark** because `nve-theme` sits on `<body>`, one level too low:
      themes.css declares `--nve-sys-layer-canvas-color: var(--nve-sys-text-color)` at
      `:root`, where the attribute is absent, so it resolves against light's 20% text and
      `body` inherits that already-resolved value — while `background` flips correctly
      because it is declared inside the theme blocks, which do match `body`.
      **Fix: move `nve-theme` to `<html>`** (`index.html:101` + `app.js:233` →
      `document.documentElement`); tested live, renders perfectly.)*
- [x] Reset button clears totals, chart and log.
      *(`m1`/`ratio` → `—`, log 20→4, chart cleared.)*

> **Console noise.** The only console errors are the by-design `/latest.jpg` 404s — 187 in
> one run, ~5/sec while no frame exists. No JS errors at all. The 404 *is* the privacy
> lesson (SPEC-02 §7), but the volume will bury a real error during the workshop.

> ⚠️ **Environment trap that will waste your afternoon.** A relay left running from an
> earlier session can hold `0.0.0.0:8000` while a new one binds `127.0.0.1:8000`.
> Localhost prefers the **specific** bind, so stray clients from other sessions land on
> *your* relay — this produced a phantom Mode 2 total and a bogus `858×` ratio that looked
> exactly like a relay bug — and killing your relay silently hands the port to the stale
> one, so the badge never goes red. **`POST /reset` before trusting any number**, and
> check `netstat -ano | grep :8000` for more than one listener.

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
- [x] Posture is a single line (`posture` + `score`) plus the alarm banner carrying the
      rule's `reason`. *(`torso_angle` is gone — it belonged to SPEC-05's abandoned
      `trt_pose` design and was never produced. MoveNet reports `score` instead.)*
- [x] **The skeleton canvas (SPEC-04 §5.1)** — hand-rolled `<canvas>`, for the same reason
      the chart is hand-rolled SVG (§8): no Elements component draws a skeleton, and this
      one is load-bearing. Joints below `KP_DRAW_CONF` (0.2) are not drawn — an
      unconfident joint invents a limb. Red on `abnormal`, NVIDIA green otherwise.
      ⚠️ `.has-skeleton img { display: none }` — a skeleton must never render over a
      leftover Mode 1 frame, which `/latest.jpg`'s 404 only clears on the *next* poll.
- [ ] A posture **timeline** is still open.
