# SPEC-07 — Dashboard mode switch (student-driven)

> **Live document.** Built 2026-07-16 at Jeffry's request during a bench session.

| | |
|---|---|
| **Status** | 🟢 **Built + validated end-to-end on the Jetson** |
| **Depends on** | SPEC-01, SPEC-02 (relay), SPEC-03 (dashboard), SPEC-06 (the poll-from-relay pattern) |
| **Runs on** | new `edge/supervisor.py` on the **Jetson**; `/mode` on the relay; buttons in `web/` |

## 1. Why

Mode is set by *which client runs on the Jetson* — three separate programs. Switching
therefore needed a terminal on the board, which a **student in their seat cannot do**.
Jeffry's format is **hands-on: each student switches modes themselves**, so the dashboard
needs a switch. Chosen approach (of the three offered): **dashboard buttons + a Jetson
supervisor** — keep the three programs separate (the boss's structure), add a small
control channel so a button picks which one runs.

## 2. Design — the relay holds the choice, the Jetson obeys

```
[Mode 1|2|3] button ──POST /mode──▶ relay._desired_mode
                                       │
  edge/supervisor.py on the Jetson ────┘ polls GET /mode every 2 s,
      starts/stops the matching client (one at a time)
                                       │
  mode1_streamer / mode2_edge / mode3_posture  ── unchanged, still separate
```

The same poll-from-relay shape as SPEC-06's config, kept deliberately dumb: the relay is
the single source of truth, the Jetson polls and reconciles. No inbound connection to the
Jetson, so it survives the firewall / NAT exactly like the ingest path.

- [x] **relay** — `_desired_mode`; `GET /mode` (supervisor polls), `POST /mode`
      (`1|2|3|null`, validated → 422 on anything else). Default **null** = nothing running,
      camera free, until a student clicks.
- [x] **`edge/supervisor.py`** (new) — polls `GET /mode`; on a change, `SIGINT`s the
      current client (its own Ctrl-C handler closes the camera), waits, then starts the new
      one. **One child at a time**, so no camera contention. A 2 s settle after stop lets
      the USB camera fully release (a rapid re-open hands back empty frames — learned the
      hard way this session). Restarts a child that crashed. Children inherit the
      supervisor's env (`RELAY_URL`, `SENSOR`, …).
- [x] **`web/`** — three header buttons. Click → `POST /mode`; the clicked one highlights
      optimistically. A 3 s `GET /mode` poll keeps every open dashboard in sync, so two
      students' browsers agree on the selected mode. The **live-mode badge** (real data)
      still shows what is *actually* running, so "selected" vs "running" are both visible
      during the ~2–4 s swap.

## 3. Validation — 2026-07-16

### Unit (laptop)

- [x] `tests/test_relay_control.py` — `/mode` accepts `1/2/3/null`, **rejects `0/4/99/-1`
      with 422**, defaults to `null`. (Plus the `/config` endpoints.) Full suite green.

### End-to-end (real Jetson, dashboard in a browser)

- [x] Supervisor starts idle on `null` (camera free).
- [x] `POST /mode 2` → supervisor **starts** `mode2_edge`; Mode 2 data reaches the relay.
- [x] `POST /mode 3` → supervisor **stops** Mode 2 (SIGINT) and **starts** `mode3_posture`;
      posture payload flows.
- [x] **Clicking the Mode 1 button in a real browser** → `/mode` = 1, button highlights,
      supervisor swaps to `mode1_streamer`, `/latest.jpg` → 200 (live frames).
- [x] After cycling all three, the bandwidth panel holds all three totals and shows the
      ratio (**1,959×** on the day). Zero external requests.

## 4. Open

- [ ] **Mode 3 warm-up on switch-in**: `bgsub` starts cold each time Mode 3 begins, so the
      first ~5 s of posture is noisy until the background is learned. Expected; worth a
      one-line "learning the room…" hint on the dashboard when Mode 3 is freshly selected.
- [ ] **Run the supervisor on boot** (systemd unit) so a student board comes up ready to
      switch without anyone starting the supervisor by hand. Pre-clone step.
- [ ] A visible "switching…" state on the button for the ~2 s swap (currently the
      live-mode badge is the only cue).
