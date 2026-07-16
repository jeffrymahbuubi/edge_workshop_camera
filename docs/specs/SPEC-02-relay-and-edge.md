# SPEC-02 — Relay & Edge Clients (Modes 1 + 2)

> **Live document.** Tick as you build. The contract lives in SPEC-01 — if something
> here contradicts it, SPEC-01 wins and this file is the bug.

| | |
|---|---|
| **Status** | 🟢 **Built and hardware-validated** (2026-07-16) — only the cable-pull test outstanding |
| **Priority** | 🔴 **TOP** — Modes 1+2 on the dashboard is the critical path |
| **Depends on** | SPEC-01 |
| **Depended on by** | SPEC-03 (dashboard consumes what this emits) |

**Built:** `relay/bandwidth.py` (new) + `relay_server.py` gains byte accounting, the
shared `flag_for()` helper, `GET /events` (SSE), `GET /latest.jpg`, a 60 s ring buffer,
`POST /reset`, and `POST /ingest_posture` (reserved for SPEC-04). All verified end-to-end
against the Jetson's real webcam — see §9.

**Governing rule: additive changes only.** The boss's Mode 1/Mode 2 semantics, endpoint
names, payload shapes, `features.py`, and the ~689× lesson stay **exactly as designed**.
Everything below *adds* to his package without changing what either mode does or sends.

---

## 1. Why this work exists

Reading `references/context/edge-workshop-camera-en/relay_server.py` against the agreed
dashboard design surfaced two gaps that **block the dashboard as specified**:

1. **No payload accounting exists anywhere.** Neither `/ingest_raw` nor
   `/ingest_features` records how many bytes arrived. **The ~689× counter — the
   workshop's headline number — has nothing feeding it.**
2. **`/ingest_raw` never computes the `flag` string.** The `"FALL?"/"person-active"/
   "quiet"` mapping lives only in `/ingest_features` (`relay_server.py:94`).
   `/ingest_raw` returns `cloud_features` and stops — so **Mode 1 has no flag to show**.

Neither is hard. Both would surface as confusing blanks mid-build if discovered late.

---

## 2. Task 1 — restructure into `src/` and rewire imports

The boss's package is flat; SPEC-01 splits it by machine. That breaks his imports.

- [x] Copy files to their SPEC-01 §3 homes (`edge/`, `relay/`, `common/`). ✅ 2026-07-16
- [x] Rewire every import: ✅

| Was | Becomes |
|---|---|
| `from features import extract_features` | `from common.features import extract_features` |
| `from codec import decode_frame, decode_audio` | `from common.codec import decode_frame, decode_audio` |
| `from common import RELAY_URL, …` | `from common.config import RELAY_URL, …` |
| `from sensor import get_sensor` | `from edge.sensor import get_sensor` |
| `from posture import …` | `from edge.posture import …` |

- [x] `__init__.py` in `common/`, `edge/`, `relay/`. ✅
- [x] `common/common.py` → **`common/config.py`**. `common.common` was ugly; it is a
      config module, and `from common.config import …` reads correctly. Behaviour
      unchanged. ✅

### 2.1 Run as modules — this is now mandatory

Package-qualified imports mean **scripts can no longer be run directly**. `python3
posture_selftest.py` puts `edge/` on `sys.path` and `common` becomes invisible.

| Machine | From | Command |
|---|---|---|
| Laptop | `src/` | `uv run python -m relay.compare` |
| Jetson | `~/EDGE-CAMERA/` | `python3 -m edge.mode2_edge` |

- [ ] **`POSTURE_TEST_GUIDE.md` §4–5 is now stale** — it says `python3
      posture_selftest.py`. Either update the guide or add a thin launcher shim.
      A TA following it verbatim gets `ModuleNotFoundError: common`.
- [x] Verified with the offline smoke test (no hardware, no network):
      `cd src && uv run python -m relay.compare` → **689×, motion 12/12, falls 2/2** ✅

> `compare.py` lives in `relay/` and imports `edge.sensor` for the synthetic scene — it
> is a dev/teaching tool that runs on the laptop, which has the whole repo. Only the
> Jetson gets a subset (`edge/` + `common/`), so the split holds. It is the fastest
> regression check in the repo — run it after every change in this spec.

---

## 3. Task 2 — byte accounting (`relay/bandwidth.py`, new)

Feeds the dashboard's lesson panel. **Per-device, per-mode, with reset.**

### 3.1 Where the bytes come from

Pydantic parses the body before handler code sees it, so raw size is already gone.
**Do not** re-serialise the model to measure it — that measures *your* encoder, not what
crossed the wire, and Mode 1's number would be wrong by the JSON whitespace.

- [x] Read **`Content-Length` from the request headers** — the byte count the LAN
      actually carried. ✅

> **Built differently from the original plan.** This spec first called for Starlette
> **middleware**. The implementation reads the header **in each handler** via a
> `Request` param (`_content_length(request)`), because middleware runs before routing
> and therefore does not yet know the device or the mode — it would have had to stash
> the value on `request.state` for the handler to pick up anyway. Same byte source, one
> less indirection.

### 3.2 State

```python
# per device, per mode
{"bench01": {
    "mode1": {"total_bytes": 88_293_104, "last_seen": 1721145600.0, "ewma_bps": 1_490_000},
    "mode2": {"total_bytes": 129_024,    "last_seen": 1721145900.0, "ewma_bps": 2_150},
}}
```

- [ ] `total_bytes` — cumulative, survives a mode switch. **This is what makes the ratio
      appear when a student switches Mode 1 → Mode 2.**
- [ ] `ewma_bps` — smoothed bytes/sec for the live readout. A raw per-second delta is
      too jumpy to read on screen.
- [ ] `ratio = mode1.total_bytes / max(mode2.total_bytes, 1)` — computed, never stored.
- [ ] Guard the ratio: show `—` until **both** modes have non-zero totals, or the panel
      shows a meaningless `84 MB / 0`.

### 3.3 Reset

- [ ] `POST /reset` → `{"device": "bench01"}` clears that device; no body clears all.
- [ ] The next student pair needs a clean 689× demo, not the previous group's totals.

---

## 4. Task 3 — the shared flag helper

- [ ] Lift the mapping (SPEC-01 §4.5) out of `/ingest_features` into one helper.
- [ ] Call it from `/ingest_raw` **and** `/ingest_features`.
- [ ] `/ingest_raw` response gains `"flag"` alongside `cloud_features`. Additive — the
      existing `received_frames` and `cloud_features` keys stay.

---

## 5. Task 4 — SSE (`GET /events`)

One-way relay → browser. FastAPI `StreamingResponse`; browser `EventSource`.

- [ ] `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
      `X-Accel-Buffering: no`.
- [ ] **Data only** — no frames. Target ~200 bytes/event (SPEC-03 pulls video separately).
- [ ] Fan out to *all* connected browsers; keep a `set` of per-client `asyncio.Queue`s
      and drop the queue on disconnect. A single shared generator will deadlock the
      second browser.
- [ ] Event shape:

```jsonc
{ "t": 1721145600.0, "device": "bench01", "mode": 2,
  "flag": "person-active",
  "feats": { "motion_level": 0.34, "n_blobs": 2, "motion_flag": true,
             "audio_rms": 0.08, "loud_flag": false, "fall_suspected": false },
  "posture": null,                      // SPEC-04 fills this
  "bandwidth": { "mode1_total": 88293104, "mode2_total": 129024,
                 "mode1_bps": 1490000, "mode2_bps": 2150,
                 "ratio": 684.3, "live_mode": 2 } }
```

- [ ] Send a heartbeat comment (`: ping\n\n`) every ~15 s or idle proxies will hang up.

---

## 6. Task 5 — the 60-second ring buffer (server-side)

- [ ] `collections.deque(maxlen=60)` **per device** of the event shape above.
- [ ] On a new SSE connection, **replay the buffer first**, then stream live.
- [ ] Rationale: students open the dashboard mid-demo and refresh constantly. Client-only
      history means every one of them starts at an empty chart and **misses the fall that
      just happened**.
- [ ] Mark replayed events (`"replay": true`) so the client can render them without
      re-firing alarm animations.

---

## 7. Task 6 — `GET /latest.jpg` (Mode 1 only)

- [ ] Keep the **most recent decoded frame** per device, in memory, as JPEG bytes.
- [ ] `/ingest_raw` already decodes frames — reuse the last one; do **not** re-encode
      every frame in the batch.
- [ ] **Return `404` when there is no frame.** In Mode 2 the relay never receives one, so
      404 is the correct, honest answer — and the dashboard's video panel blanks by
      itself. *The privacy lesson needs no special-casing; it falls out of the design.*
- [ ] Clear the stored frame when a device switches to Mode 2, so a stale Mode 1 face
      cannot linger on screen during the privacy demo. **This would wreck the lesson.**
- [ ] `Cache-Control: no-store`.

---

## 8. Edge clients — what changes

**Almost nothing.** Per the additive rule:

| File | Change |
|---|---|
| `edge/mode1_streamer.py` | imports only (SPEC-01 §3) |
| `edge/mode2_edge.py` | imports only |
| `edge/sensor.py` | none |
| `common/features.py` | none |
| `common/codec.py` | none |

- [ ] Their existing `total_bytes` Ctrl-C summaries **stay**. They are the boss's teaching
      device and they now cross-check the relay's independent count — if the two disagree,
      the byte accounting is wrong. Free validation.
- [ ] `RELAY_URL=http://<laptop-ip>:8000` — the Jetson points at the laptop. Never localhost.
- [ ] Relay binds `0.0.0.0:8000`, not `127.0.0.1`, or the Jetson cannot reach it.

---

## 9. Validation

Run in order. Each step is cheap and isolates the next failure.

- [x] **Offline** — `cd src && uv run python -m relay.compare` → **689×, motion 12/12,
      falls 2/2** ✅ *(2026-07-16 — exactly the README's expected values, so the §2
      import rewiring preserved the boss's behaviour precisely)*
- [x] **Imports on the Jetson** under python3.8 — `common.config`, `common.features`,
      `common.codec`, `edge.sensor`, `edge.posture` all import ✅
- [x] **`trt` backend raises cleanly** — `NotImplementedError`, as SPEC-05 assumes ✅
- [x] **Posture selftest (synthetic)** — runs, no traceback ✅
- [x] **Webcam selftest on the Jetson** — 15 frames/s at 320×240 from `/dev/video0` ✅
- [x] **Jetson → laptop relay reachable** — `GET /health` → `200 {"ok":true}` across the
      ICS link. **Windows firewall does not block it** ✅
- [x] **Mode 2 on hardware** — Jetson webcam → edge features → relay →
      `flag=person-active` ✅
- [x] **Mode 1 on hardware** — Jetson webcam → raw → relay → `cloud_features` ✅
- [x] **Byte accounting live** — SSE `bandwidth` block after a Mode 1 → Mode 2 switch:
      `mode1_total: 583,063 B`, `mode2_total: 246 B`, **`ratio: 2370.2`**, `live_mode: 2`.
      **Totals survive the switch, so the ratio appears with only one Jetson** ✅
- [x] **Cross-check** — client reported 569 KB, relay counted 583,063 B. The ~2.5% delta
      is HTTP/JSON framing the client doesn't count. **Independent agreement** ✅
- [x] **`/latest.jpg` → 200 `image/jpeg`** in Mode 1 — a valid **320×240 JPEG, 12,607 B** ✅
- [x] **`/latest.jpg` → 404 after switching to Mode 2** — the stale frame is cleared, so
      **no face survives into the privacy demo** ✅
- [x] **SSE ring-buffer replay** — a late-joining client received 4 buffered events
      tagged `replay: true` ✅
- [x] **`POST /reset`** clears totals + history ✅
- [x] **No errors or tracebacks** in the relay log across all endpoints ✅
- [ ] **Pull the cable** — Mode 1 loses seconds; Mode 2 buffers and backfills.
      *(Not yet run — needs someone at the bench.)*
- [ ] **Two browsers at once** — catches SSE fan-out bugs. *(Needs the dashboard.)*

### 9.1 Measured on hardware — 2026-07-16

Jetson `jetson-2gNANO` → laptop relay at `192.168.137.1:8000`, real USB webcam, ~6 s each:

| | Sent | Projected |
|---|---|---|
| **Mode 1** (raw) | **856 KB / 6 s** | ~12,568 MB/day |
| **Mode 2** (features) | **366 B / 6 s** | ~5.2 MB/day |
| **Ratio** | **≈ 2,395×** | |

### 9.2 ⚠️ Finding — the real ratio is ~2,395×, not 689×

**The dashboard's live counter will not show 689×.** The synthetic scene compresses well
(a flat grey background with a clean block); a real camera's sensor noise defeats JPEG, so
Mode 1's payload roughly doubles while Mode 2's stays fixed. The gap gets **~3.5× wider**
on real hardware.

This is *good news for the lesson* but it **contradicts the handout's headline number**.
Decide before the workshop:

- [ ] Reconcile: does the handout say ~689× (synthetic, reproducible via `compare.py`)
      while the dashboard shows the live figure? Two different numbers on screen and on
      paper **will** get asked about.
- [ ] Suggested framing: 689× is the *reproducible baseline* anyone can rerun offline;
      the live number is *your room, your camera* — and it is **even worse than the
      handout promised.** That is a stronger story than hiding the discrepancy.

### 9.3 ✅ RESOLVED — PulseAudio's default source was the empty onboard jack

**The root cause was neither the library nor the code. It was a one-line system setting.**
This took three wrong diagnoses to reach; the trail is recorded because the failure mode
is nasty and will recur on every student board.

**Layer 1 — `sounddevice` was missing.** `microphone unavailable (No module named
'sounddevice'); running VIDEO-ONLY with silent audio` → `audio_rms` pinned at 0.0000 →
`loud_flag` never fires → `fall_suspected = loud_flag AND prev_motion AND NOT motion`
**can never be True**.

- [x] Installed `libportaudio2` + **sounddevice 0.5.5** ✅ — the warning vanished, the
      stream opened cleanly… and `audio_rms` **stayed 0.0000**.

**Layer 2 — the default input recorded silence.** Measured directly:

```
default(18)    rms=0.000000  peak=0.0000  SILENT
C270 hw:2,0    rms=0.045126  peak=1.0000  LIVE AUDIO
```

**Layer 3 — the C270 then vanished from PortAudio entirely.** Selecting index 11 worked
once, then printed `microphone: pulse`, then `no input device matching 'C270'` — while
`lsusb`, `/proc/asound/cards` and `arecord -l` all still showed the webcam, and
`arecord -D hw:2,0` recorded 64 KB happily. **ALSA was fine the whole time.**

**The actual cause:**

```
$ pactl info | grep 'Default Source'
Default Source: alsa_input.platform-sound.analog-stereo     ← the ONBOARD JACK. Nothing plugged in.

$ pactl list short sources
0  alsa_input.usb-046d_C270_HD_WEBCAM_...-02.analog-mono     ← the real mic, unused
```

**PulseAudio owned the C270's card**, so PortAudio could not open `hw:2,0` exclusively
and **dropped it from its device list**; a hard-coded index then silently slid onto
`pulse`, which routes to Pulse's default source — the **empty onboard jack**.

**The fix — one command, no code:**

```bash
pactl set-default-source alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono
```

- [x] **Verified:** with the default source fixed, `device=None` (plain system default)
      → `rms=0.017456` **LIVE AUDIO**; `webcam_selftest` → `audio_rms` 0.021–0.030 ✅
- [x] **`AUDIO_DEVICE` is now unnecessary** — leave it unset. It remains supported (name
      or index) as an escape hatch, and a **name miss now falls back to the system
      default instead of raising**, because no match is a reason to use Pulse's routing,
      not a reason to run deaf.
- [x] `sensor.py` prints the chosen mic and **warns only when audio is genuinely silent**
      — measured, not guessed — naming `pactl` as the fix. ✅

> **⚠️ Three lessons worth keeping.**
> 1. **It fails silently and looks healthy** — no error, both modes running, falls quietly
>    impossible. A dead mic is invisible unless you assert on it.
> 2. **PortAudio indices are not stable identifiers.** They are valid only for the
>    enumeration that produced them, and PulseAudio can remove a card mid-session.
> 3. **`lsusb`/`arecord` proving the hardware works does not mean your library sees it.**
>    Four layers disagreed; only `pactl info` told the truth.

- [ ] ⚠️ **`pactl set-default-source` is runtime-only — it will NOT survive a reboot.**
      Make it persistent before cloning (a `~/.config/pulse/default.pa` line or a
      systemd user unit) and add it to the pre-clone checklist in SPEC-05 §6. **Every
      student board will otherwise boot deaf.**
- [ ] Retune `LOUD_RMS_THRESH` (0.05). Measured ambient ≈ **0.017–0.045** — the C270's
      gain is high. Speech reads ~0.098, so 0.05 does separate them, but the margin is
      thin and the room will be noisy on the day.

### 9.4 ✅ RESOLVED — `MOTION_LEVEL_THRESH` is fine; the earlier reading was real motion

An earlier run showed `motion_level` **0.057–0.115** continuously against a 0.006
threshold, which looked like sensor noise swamping the detector.

**It wasn't.** A later run on a genuinely still scene read **0.0003–0.005** with
`motion_flag=False`. The high readings were **real movement in frame**.

`MOTION_LEVEL_THRESH = 0.006` discriminates correctly on this camera — a static room
sits ~10× below it, and movement sits ~10–70× above. **No retune needed.**

---

## 10. Open

- [x] ~~Install `sounddevice`?~~ Done — but see §9.3 layer 2: the **device must be
      selected**, or it silently records nothing.
- [x] ~~Retune `MOTION_LEVEL_THRESH`?~~ Not needed (§9.4).
- [ ] Select the mic **by name** rather than index `11` before cloning. (§9.3)
- [ ] Retune `LOUD_RMS_THRESH` — ambient 0.045 vs threshold 0.05 is a thin margin. (§9.3)
- [ ] Reconcile 689× vs the live ~2,395×. (§9.2)
- [ ] Does the ratio panel show per-device or the active device only? SPEC-03 decides.
