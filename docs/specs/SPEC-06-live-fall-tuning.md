# SPEC-06 — Live fall-threshold tuning (Modes 1 & 2)

> **Live document.** Built 2026-07-16 at Jeffry's request during a bench session.

| | |
|---|---|
| **Status** | 🟢 **Built + laptop-verified**; live Mode 2 edge-pull path pending a Jetson run |
| **Depends on** | SPEC-01 (contract), SPEC-02 (relay), SPEC-03 (dashboard) |
| **Touches** | `common/features.py`, `relay/relay_server.py`, `edge/mode2_edge.py`, `web/` — the boss's reference path, so **additive only** |

## 1. Why

The Mode 1/2 fall rule is `loud AND was-moving AND motion-stopped`. On real hardware
it is **hard to trigger solo**: making the loud sound (clap/shout) is itself motion, so
`motion` never reads "stopped" in the loud second. Measured live 2026-07-16: `loud=True`
fired twice, both times with `motion=True`, so `fall` never fired. Tuning the two
thresholds live — from the dashboard, without restarting the Jetson — makes the demo
workable and is itself a teaching moment (watch sensitivity change the detector in real
time).

The two knobs (both in `config.py`, the fall determinants):

- `LOUD_RMS_THRESH = 0.05` → `loud_flag = audio_rms > thresh`
- `MOTION_LEVEL_THRESH = 0.006` → `motion_flag = motion_level > thresh`

## 2. The design — relay holds the numbers, the edge keeps deciding

The key fact that makes this clean: **the relay already has the raw `motion_level` and
`audio_rms` for both modes** — Mode 1 computes them there, Mode 2 sends them in its
payload. So a single live config on the relay drives both, and **no fusion logic moves
off the Jetson** (the boss's "edge decides" design is preserved for Mode 2):

```
dashboard slider ──POST /config──▶ relay._live_cfg
                                     │
   Mode 1 (relay computes features) ─┘ applies immediately, next frame
   Mode 2 (edge computes features) ──▶ relay returns _live_cfg in the
                                        /ingest_features response; the EDGE
                                        applies it on its next tick
```

- [x] `common/features.py` — `video_motion_features`, `audio_energy_features` and
      `extract_features` take **optional** `motion_level_thresh` / `loud_rms_thresh`.
      `None` ⇒ the module constants, so **every existing caller is byte-for-byte
      unchanged**. Pinned by `tests/test_features_tuning.py` (`test_defaults_match_the_module_constants`).
- [x] `relay` — `_live_cfg` seeded from the constants; `GET /config` (seed the sliders),
      `POST /config` (update; **clamped** to `[0,1]` so a bad slider can't wedge the demo).
      Mode 1's `ingest_raw` passes `_live_cfg` into `extract_features`; Mode 2's
      `ingest_features` returns `config` in its response.
- [x] `edge/mode2_edge.py` — reads `resp["config"]` and applies it to `extract_features`
      **next tick**. The fusion still runs on the Jetson.
- [x] `web/` — a "Fall sensitivity / LIVE" panel with two sliders. Seeds from
      `GET /config` on load; POSTs on release (not during drag, to spare the relay).

## 3. Behaviour

- **Mode 1** picks up a change on the **next frame** (~instant — the relay computes).
- **Mode 2** picks it up on the **next tick** (~1 s — the edge pulls it back and applies).
- A fresh browser seeds its sliders from the relay, so two dashboards agree.
- Defaults unchanged: with no slider ever touched, the demo behaves exactly as before.

## 4. Validation

### Done — 2026-07-16 (laptop)

- [x] **9 unit tests** (`tests/test_features_tuning.py`): overrides flip the flags; the
      measured values (`audio_rms`, `motion_level`) are unaffected; overrides flow through
      `extract_features` into the fall rule; **defaults identical to the reference**.
      Full suite 48 passing.
- [x] **Relay endpoints**: `GET /config` returns defaults; `POST` updates; out-of-range
      values clamp (`5.0 → 1.0`).
- [x] **Dashboard (real browser, playwright-cli)**: sliders seed from `/config`; moving a
      slider POSTs and the relay reflects it; **zero external requests** (457, all
      same-origin); no JS errors. Panel renders with the LIVE badge.

### Outstanding — the bench (needs the Jetson)

- [ ] **Mode 2 edge-pull, live**: run `mode2_edge` on the Jetson, drag the loud slider
      down mid-run, confirm `loud`/`fall` start firing within ~1 s — i.e. the edge really
      applied the dashboard's number.
- [ ] **Trigger a real fall** in Mode 2 with a lowered `loud` threshold + raised `motion`
      threshold, and see the FALL? banner. (Blocked earlier only by the coupling problem
      this spec solves; also needs the C270 mic — `AUDIO_DEVICE=C270`, see the mic note in
      SPEC-02 / the pre-clone steps.)

## 5. Open

- [ ] Persisting a tuned value across a relay restart (currently resets to the reference
      defaults on boot — arguably correct for a clean demo each time).
- [ ] Exposing `PIX_DIFF_THRESH` / `MIN_BLOB_AREA` too — deferred; the two fall
      determinants are what the demo needs.
