# SPEC-01 — Code Layout & Contracts

> **Live document.** Update it as implementation lands. Tick the checkboxes; when a
> decision changes, change it *here* first — every other SPEC depends on this one.

| | |
|---|---|
| **Status** | 🟢 **Realized** for Modes 1+2 (2026-07-16) — `src/` layout built, Mode 1/2 contract live and hardware-validated. Mode 3 (§4.3) and the posture contract (§5) remain 🟡 specified-only. |
| **Depends on** | [`docs/01-design/06-deployment-topology-edge-relay.md`](../01-design/06-deployment-topology-edge-relay.md) (locked topology) |
| **Depended on by** | SPEC-02 (🟢 built), SPEC-03, SPEC-04 *(SPEC-05 deleted 2026-07-16 — its pre-clone checklist is now §6 here)* |

This file fixes two things everything else builds on: **where code lives**, and **what
the two machines promise each other over the wire**. It is the contract; if the Jetson
and the laptop ever disagree, they disagree here.

---

## 1. Verified platform facts

Probed live on the dev unit `jetson-2gNANO` on **2026-07-16**. These are measurements,
not assumptions — several overturned what the docs previously assumed.

| Fact | Value | Why it matters |
|---|---|---|
| L4T / JetPack | `R32.7.4`, `BOARD: t210ref` | Jetson Nano, JetPack 4.6.4 |
| **`python3`** | **3.8.0** (`/usr/bin/python3` → `python3.8`) | **Not 3.6.** See §2 — this reverses an earlier assumption |
| `python3.6` | present but *not* default | Do not target it |
| OpenCV | `cv2` 4.11.0 | `features.py` / `pose.py` run as-is |
| NumPy | 1.23.5 | ✅ |
| **TensorFlow** | ✅ **2.13.1**, `tf.lite.Interpreter` works | **Mode 3 runs on this.** Already installed — the whole SPEC-05 install plan turned out unnecessary |
| **`tflite_runtime`** | ❌ **absent, and will stay absent** | The Coral wheel needs **GLIBC 2.29**; Ubuntu 18.04 has less. `pose.py` catches it and falls back to `tf.lite` — that fallback is the **only** path on this board |
| **MoveNet model** | ✅ `~/EDGE-CAMERA/models/movenet_lightning.tflite`, 4.7 MB | Loads in **7.0 s**; inference **0.08 s/frame (12.6 fps)** vs 1 fps needed |
| PyTorch / torchvision / TensorRT | 1.11.0a0 (CUDA ✅) / 0.12.0a0 / 8.2.1.8 | Installed, but **Mode 3 does not use them** — MoveNet is TFLite on CPU |
| `requests` | 2.32.3 | Edge clients work |
| **`sounddevice`** | ✅ **0.5.5 installed** (+ `libportaudio2`) | Not sufficient alone — the mic must be *selected* |
| **Microphone** | ✅ **FIXED + PERSISTED 2026-07-16** | `~/.config/pulse/default.pa` pins the default source to the C270. Verified across a PulseAudio restart: `audio_rms` **0.012–0.026**, was **0.0**. See **§6 step 3** |
| `curl` | ❌ not installed | Use `python3 -c "import requests…"` to probe the relay |
| ~~`torch2trt` / `trt_pose`~~ | ❌ not installed, **and no longer wanted** | SPEC-05 superseded — MoveNet replaced that plan |
| RAM | **3.9 GB** total, **5.9 GB swap** | So this is a **4 GB Nano**, despite the `jetson-2gNANO` hostname |
| **Disk** | 44 GB, **5.2 GB free (88%)** | Was the binding constraint for SPEC-05's ~81 MB + engine build. **MoveNet cost 4.7 MB and moved it 0.0 GB** — no longer binding |
| Camera | `/dev/video0` present, C270 @ 12.9 fps confirmed | ✅ |
| Workshop code | `~/EDGE-CAMERA` **exists**, all edge/ + common/ deployed | ✅ Modes 1/2/3 + supervisor run on the board |

> **Ignore other `~/` directories on the board** (`ultralytics`, `yolov8_models`,
> `python_apriltag_yolo`, `CAVEDU_jetson_inference`, …). Confirmed by Jeffry as
> pre-existing third-party material, unrelated to this project. Do not build on them
> and do not assume they will exist on a student image.

---

## 2. Python target: 3.8 — a reversal, with a caveat

Earlier docs assumed **Python 3.6**, on the general truth that JetPack 4.6 ships 3.6.
**On this board that is false**: `python3` is 3.8.0, and `cv2`, `numpy`, `torch` and
`tensorrt` all import under it.

- [ ] **Target `python3` (= 3.8) on the Jetson.** No 3.6 back-compat contortions.
- [ ] Laptop-side relay may use any modern Python — FastAPI/Pydantic v2 are fine
      (the relay never runs on the Jetson under Role A anyway).

> **⚠️ Image-provenance risk.** The 3.8 symlink is dated **2025-03-04** — it was set up
> by hand on this dev unit, it is *not* what a fresh JetPack 4.6 flash gives you.
> Student images are cloned **from this board**, so they inherit 3.8 and this is safe.
> But **anyone who reflashes from scratch lands on 3.6** and this spec breaks. Record
> the 3.8 setup as part of the image definition, not as a property of JetPack.
>
> This also explains why `references/edge_voice_assistant` uses stdlib `HTTPServer`
> "不依賴 FastAPI" — its author targeted stock 3.6. That reasoning does **not** apply here.

---

## 3. Repository layout

Organised **by machine**, so the tree teaches the topology and the deploy boundary is
obvious: *copy `edge/` + `common/` + `models/` to the Jetson* is the entire instruction.
*(`models/` joined the list with MoveNet — miss it and Mode 3 dies with
`MoveNet model not found`.)*

```
nvidia-workshop/
├── src/
│   ├── edge/            → runs on the JETSON (python3.8)
│   │   ├── mode1_streamer.py     raw → relay
│   │   ├── mode2_edge.py         features → relay
│   │   ├── mode3_posture.py      pose + abnormal → relay       (SPEC-04, built)
│   │   ├── pose.py               MoveNet/TFLite keypoints      (SPEC-04, built)
│   │   ├── behaviour.py          the fall-rule state machine   (SPEC-04, built)
│   │   ├── supervisor.py         polls /mode, swaps clients    (SPEC-07, built)
│   │   ├── sensor.py             webcam/mic + synthetic scene
│   │   └── webcam_selftest.py
│   │   ⛔ posture.py / posture_selftest.py DELETED 2026-07-16 (bgsub; SPEC-04 §3.1)
│   ├── relay/           → runs on the LAPTOP (any python)
│   │   ├── relay_server.py       FastAPI + SSE + dashboard
│   │   ├── bandwidth.py          byte accounting               (SPEC-02, new)
│   │   └── compare.py            offline 689× smoke test
│   ├── common/          → runs on BOTH — keep import-light
│   │   ├── features.py           the model-free detector
│   │   ├── codec.py              base64/JPEG/audio helpers
│   │   └── config.py             thresholds + env config (was common.py)
│   ├── models/          → deployed to the JETSON alongside edge/ + common/
│   │   └── movenet_lightning.tflite   4.7 MB (SPEC-04). Path mirrors the board's
│   │                                  ~/EDGE-CAMERA/models/, so pose.py's relative
│   │                                  default resolves on BOTH machines unedited
│   └── web/             → served by the relay
│       ├── index.html
│       ├── app.js                the live instrument: chart, status, Mode 3 skeleton canvas
│       ├── content.js            ALL copy, both languages (SPEC-03 §9)
│       ├── compare.js            the three-mode teaching section (SPEC-03 §9.0)
│       ├── alarm.js              the audible fall alarm (SPEC-09)
│       └── vendor/elements/      vendored NVIDIA Elements UI (offline)
│                                  ⚠️ new .js modules must ALSO join relay_server's
│                                  _JS_MODULES whitelist or the dashboard loads blank
├── scripts/             → laptop provisioning (ICS setup) — NOT app code
└── docs/
```

- [x] `common/` must import **only** `cv2` + `numpy` + stdlib. No `requests`, no
      `fastapi` — it is the one thing both machines load. ✅ *Verified 2026-07-16: the
      complete import set across `common/` is `base64`, `os`, `cv2`, `numpy` and
      `common.config`.*
- [x] Imports are package-qualified: `from common.features import extract_features`. ✅
- [x] `src/web/vendor/elements/` in place (moved from `static/`); `index.html` + `app.js`
      built (SPEC-03). ✅
- [x] `edge/mode3_posture.py` — built (SPEC-04). Also added since: `edge/behaviour.py`
      (SPEC-04 fall rule) and `edge/supervisor.py` (SPEC-07 mode switch). **The entire
      `src/` tree now exists**; nothing in SPEC-01's layout is unbuilt.

---

## 4. The edge ↔ relay contract

Transport is **HTTP/JSON over the LAN cable**. Every ingest endpoint requires the
`X-Device-Token` header. This section is normative for both machines.

### 4.1 Auth & rate limiting (unchanged from the boss's design)

| | |
|---|---|
| Header | `X-Device-Token: tok_demo_bench01` |
| Known tokens | `tok_demo_bench01` → `bench01`, `tok_demo_bench02` → `bench02` |
| Failure | `401` invalid or revoked device token |
| Rate limit | 300 requests / 60 s per device → `429` |

The **API key never leaves the laptop.** Devices carry a revocable token only.

### 4.2 Endpoints

| Method | Path | Mode | Purpose |
|---|---|---|---|
| `POST` | `/ingest_raw` | 1 | raw frames + audio |
| `POST` | `/ingest_features` | 2 | the 6-field feature vector |
| `POST` | `/ingest_posture` | 3 | posture + abnormal flag — ✅ **built**, awaiting SPEC-04's client |
| `GET` | `/events` | — | SSE stream → browser — ✅ **built** |
| `GET` | `/latest.jpg` | 1 only | most recent frame — ✅ **built** (404 in Modes 2/3, by design) |
| `POST` | `/reset` | — | clear byte totals — ✅ **built** |
| `GET`/`POST` | `/config` | 1,2 | live fall thresholds `{loud_rms_thresh, motion_level_thresh}` — ✅ **built** *(SPEC-06)*. Mode 1 applies on the relay; Mode 2's edge pulls it from the `/ingest_features` response and applies next tick |
| `GET`/`POST` | `/mode` | — | selected mode `{mode: 1\|2\|3\|null}` — ✅ **built** *(SPEC-07)*. The Jetson supervisor polls `GET`; the dashboard buttons `POST`. `null` = all stopped |
| `GET` | `/health` | — | `{"ok": true}` |
| `GET` | `/` | — | the dashboard *(new, SPEC-03)* |

> **Two runtime-control endpoints added this session (SPEC-06/07).** Both follow the same
> pattern: the relay holds state, the Jetson polls it — no inbound connection to the board,
> so they cross the firewall/NAT exactly like the ingest path. Mode 1/2's fall thresholds
> are therefore no longer fixed constants; they are seeded from `config.py` and overridable
> live. Defaults unchanged, so the boss's reference behaviour is intact unless a slider moves.

### 4.3 Payloads

**Mode 1 → `/ingest_raw`** *(unchanged — boss reference)*
```jsonc
{ "frames": ["<b64 JPEG>", "…15 of them…"], "audio": "<b64 int16>", "t_start": 1721145600.0 }
```
→ `{"received_frames": 15, "cloud_features": {…6 fields…}, "flag": "person-active"}`

> `flag` is **added** by SPEC-02. The boss's `/ingest_raw` returns `cloud_features` only,
> so Mode 1 currently has no flag to display. Additive; nothing removed.

**Mode 2 → `/ingest_features`** *(unchanged — boss reference)*
```jsonc
{ "motion_level": 0.34, "n_blobs": 2, "motion_flag": true,
  "audio_rms": 0.08, "loud_flag": false, "fall_suspected": false, "context": "" }
```
→ `{"device": "bench01", "flag": "person-active", "note": null}`

**Mode 3 → `/ingest_posture`** *(SPEC-04 — MoveNet 2026-07-16; audio added by SPEC-08)*
```jsonc
{ "posture": "lying",           // standing | walking | sitting | lying | absent
  "abnormal": true,
  "reason": "thump + upright→lying held 1s",  // counts up ("lying 1/3s") while building;
                                              // "thump + " prefix = sound corroborated
  "keypoints": [[0.51, 0.42, 0.9], /* …17 total… */],  // [x,y,score] 0..1, COCO order
  "bbox": [0.14, 0.68, 0.82, 0.18],    // [x,y,w,h] normalised 0..1; null if no person
  "score": 0.88,                       // mean confidence of trusted joints; null if none
  "audio_rms": 0.174,                  // SPEC-08 §A5 — a SCALAR, never samples
  "loud_flag": true,                   // SPEC-08 §A5 — did a thump land this second?
  "backend": "movenet",
  "context": "" }
```
→ `{"device": "bench01", "flag": "FALL?", "note": null, "config": {…live thresholds…}}`

**Measured: 562 B on hardware before SPEC-08; 611 B with the audio scalars** (measured on
the laptop from the real `_payload`, 2026-07-16 — the two fields cost **49 B**). Mode 1 is
~583,000 B, so Mode 3 is **~955× smaller and carries a skeleton.** Keypoints are rounded to
3 dp on the wire (0.3 px on a 320 px frame, 2.2× smaller than full-precision floats —
SPEC-04 §4.1).

> ⚠️ **`config` now rides the Mode 3 response too** (SPEC-08 §A7). Mode 3 reads the mic as
> of SPEC-08, so the dashboard's `loud_rms_thresh` must reach it or SPEC-06's slider
> silently lies in one of the three modes. Same channel Mode 2 uses — no second poll. The
> **fusion stays on the Jetson**; the relay only supplies the number.

> ⚠️ **Keypoints DO travel — this reverses the original rule**, deliberately (Jeffry,
> 2026-07-16). The old contract said "only the verdict, never keypoints", reasoning that a
> skeleton would repeat Mode 1's mistake in a new costume. It does not: Mode 1 shipped
> ~583 KB of recognisable **faces**; this is 17 numbers that identify nobody, and it buys
> the live stick figure that proves the ML ran on the edge.
>
> **The line that still holds absolutely: RAW PIXELS NEVER TRAVEL.** No frames, no JPEG,
> no audio *buffer* — note the deliberate absence of an `image` field. Pinned by
> `tests/test_mode3_payload.py::test_raw_pixels_never_travel`.
>
> ⚠️ **SPEC-08 moved this line a second time — 2026-07-16. Read SPEC-08 before trusting
> any "Mode 3 is keypoints only" statement elsewhere in the specs.**
>
> 1. **Sound is fused in** (SPEC-08 Part A). `audio_rms` + `loud_flag` now travel — two
>    scalars, ~20 B, exactly Mode 2's long-standing argument that an RMS is not a
>    recording. The mic's **samples** still never leave. The workshop's theme is
>    *Multi-Modal* Posture Recognition and Mode 3 was the only uni-modal mode.
> 2. **Pixels may travel from Mode 3 — but ONLY via `/ingest_preview`** (SPEC-08 Part B):
>    a separate endpoint, a separate payload, a separate byte bucket, default OFF and
>    non-sticky. **`/ingest_posture`'s contract above stays absolute** — no pixel may ever
>    enter it. The separation is the design: the preview is deliberately a *different
>    thing*, not a field someone can quietly add here.
>
> **Mode 3 still carries no Mode 2 VIDEO fields** — no `motion_level`, no `n_blobs`, no
> `motion_flag`, no `fall_suspected`. That last one matters most: it is *Mode 2's verdict*,
> and two fall verdicts in one payload is ambiguity, not multi-modality — the relay would
> not know which one raises the alarm.

### 4.4 The six-field feature vector

Produced by `common/features.py`. **Both modes converge on these**; only provenance
differs (Jetson-computed in Mode 2, laptop-computed in Mode 1).

| Field | Type | Meaning |
|---|---|---|
| `motion_level` | float 0..1 | fraction of pixels changed |
| `n_blobs` | int | distinct motion regions ≥ `MIN_BLOB_AREA` |
| `motion_flag` | bool | `motion_level > MOTION_LEVEL_THRESH` |
| `audio_rms` | float | audio energy this second |
| `loud_flag` | bool | `audio_rms > LOUD_RMS_THRESH` |
| `fall_suspected` | bool | `loud_flag AND prev_motion_flag AND NOT motion_flag` |

### 4.5 The flag mapping — one helper, both modes

```python
def flag_for(feats) -> str:
    if feats["fall_suspected"]: return "FALL?"
    return "person-active" if feats["motion_flag"] else "quiet"
```

- [ ] Lift into `common/` (or `relay/`) and call from **both** `/ingest_raw` and
      `/ingest_features`. Today it is inlined in `/ingest_features` only.

---

## 5. The pose estimator contract *(rewritten for MoveNet — SPEC-04)*

**One backend. `edge/pose.py`'s `MoveNetPose.estimate(frames) -> dict`:**

```python
{
  "posture":   "standing" | "walking" | "sitting" | "lying" | "absent",
  "keypoints": [[x, y, score], ...17],  # COCO order, normalised 0..1
  "bbox":      [x, y, w, h] | None,     # normalised 0..1, from keypoint extents
  "score":     float,                   # mean confidence of trusted joints
}
```

- [x] **`sitting` is a real label** (new with MoveNet). Anything consuming postures must
      handle it: `behaviour.py` counts it as UPRIGHT, and the relay maps it to
      `person-active`. It fell through to `quiet` at first — the dashboard reported an
      empty room with someone sitting in it.
- [x] Downstream treats `keypoints`/`bbox`/`score` as **optional, never assumed** — an
      `absent` second carries no skeleton.
- [x] **`estimate()` takes a list of frames but infers only `frames[-1]`.** Its vestigial
      `motion_level` parameter is **never read** (SPEC-04 §3.1) — leave it defaulted.

> **What changed and why.** This used to be a *superset* contract — `bgsub`'s four fields
> (`bbox`/`aspect`/`fill` in pixels) plus optional `keypoints`/`torso_angle` for a future
> pose backend. Both halves are gone: **bgsub was deleted** (it could not work without
> Mode 2's motion detector, so it could not coexist with "Mode 3 = keypoints only"), and
> **`torso_angle` was never built** — it belonged to SPEC-05's `trt_pose` design, which
> MoveNet replaced. MoveNet reads posture from head-vs-hip geometry and centroid movement
> instead, and reports `score` where the old contract said `confidence`.
>
> `bbox` is now **normalised 0..1**, not pixels. bgsub reported pixels; if any old code
> passes a pixel bbox to the dashboard it will draw ~30× the frame.

---

## 6. ⚠️ SD image / pre-clone checklist

> **Moved here from SPEC-05 §6 when that spec was deleted (2026-07-16).** It was never
> really about TensorRT — it is the definition of the golden image every student board is
> cloned from, which is a SPEC-01 concern. **Do not skip it: each unticked box below ships
> broken to every student.**

| # | Step | Why | State |
|---|---|---|---|
| 1 | `sudo rm -f /var/lib/dhcp/dhclient*.leases` | doc 09 — stale macOS leases install a dead gateway | ⏳ **at clone time** |
| 2 | Remove the `eth0:1` stanza from `/etc/network/interfaces` | doc 09 — the dev lifeline, must not ship | ⏳ **at clone time** |
| 3 | **Persist PulseAudio's default source → the USB webcam mic** | without it every board boots with a SILENT mic | ✅ **DONE** |
| 4 | `sounddevice` + `libportaudio2` installed | Modes 1/2 need audio | ✅ done |
| 5 | `models/movenet_lightning.tflite` on the board (4.7 MB) | Mode 3 dies with `MoveNet model not found` | ✅ done |
| 6 | Deploy `src/edge/` + `src/common/` + `src/models/` | §3 | ✅ done |
| 7 | Verify `python3` → **3.8** survives the clone | §2 — the whole layout rests on it | ⏳ **at clone time** |
| 8 | `df -h /` after everything | §2 | ✅ 5.2 GB free, unmoved |

- [x] Steps 1–2 are **deliberately deferred**: `eth0:1` is the lifeline for reaching the
      Jetson when internet sharing is off. Do them **only** at clone time.
- [x] **Step 3 — done and verified 2026-07-16.** `pactl set-default-source` is
      runtime-only, so it was baked into config instead:

      ```bash
      # ~/.config/pulse/default.pa (on the Jetson)
      .include /etc/pulse/default.pa
      set-default-source alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono
      ```

      Verified by **restarting the PulseAudio daemon** (so config, not a command, set it)
      and then **asserting on real captured audio** — the whole history of this bug is that
      a dead mic *looks* healthy: `audio_rms` went **0.0 → 0.012–0.026**, and
      `LOUD_RMS_THRESH` (0.05) sits ~2× above that floor. Modes 1/2 can now fire
      `fall_suspected` at all; previously it was impossible, silently.
- [ ] ⚠️ **Untested: a full reboot.** The daemon restart proves the config is read at
      daemon start, and a boot starts the daemon the same way — but that is inference, and
      this bug's history is *exactly* that assumptions about it were wrong.
- [ ] ⚠️ **The source name embeds the webcam's serial** (`…200901010001…`). Logitech reuses
      that string across many C270s so it will *probably* match every board — but one that
      enumerates differently **boots deaf again with no error**, which is the exact failure
      being fixed. Verify per board, or replace the line with a login-time script that
      pattern-matches `usb.*C270`. *(One more data point, 2026-07-17: a second physical
      C270 on the voice-assistant class board enumerated with the **identical** string —
      the reuse theory holds so far.)*

### 6b. The second board type — the voice-assistant class image (2026-07-17)

The real workshop runs **after the voice-assistant class, on that class's boards** — which
are *not* clones of this golden image. An end-to-end rehearsal on one (same
`jetson-2gNANO` hostname, but a different physical board at `192.168.1.100`) measured the
gap against the checklist above:

| Checklist step | On the class image |
|---|---|
| 3 — mic default source | ❌ **shipped deaf** (onboard jack) — fixed by hand on the rehearsal board only |
| 4 — `sounddevice` + `libportaudio2` | ❌ **absent** (`audio` silently 0.0000) — installed by hand on the rehearsal board only |
| 5–6 — code + model | arrives via `git clone` (README Part 2) instead of being baked in |
| network | `192.168.1.x`; `<LAPTOP_IP>` is **`192.168.1.1`** (README Step 6 table) |

README Step 9 now checks both missing pieces in order, so a student on an unfixed board
can self-serve — but **pre-fixing the fleet before class remains the safer play**; steps 3
and 4 are done on exactly one class board today. Everything else held: Python 3.8,
TensorFlow's `tf.lite` runs MoveNet untouched, and all three modes + mic were verified
live on that board (`audio_rms` 0.010–0.012 quiet-room).

---

## 7. Constraints this spec imposes

- [x] ~~**Disk is the budget**~~ — it was, while SPEC-05 planned ~81 MB of weights plus a
      TensorRT engine build against 5.2 GB free. **MoveNet cost 4.7 MB and moved disk by
      0.0 GB**, so disk no longer binds. Still worth `df -h /` before any future install.
- [ ] **`common/` stays import-light** (§3).
- [ ] **No credentials in the repo.** The dev board uses a default password over a
      point-to-point ICS link; it must not appear in any tracked file.
- [ ] **The API key stays on the laptop.** Non-negotiable — it is the boss's design.

---

## 8. Open

- [x] ~~Does the USB webcam expose a mic?~~ **Yes** — Logitech C270. The system default
      recorded silence; **fixed and persisted 2026-07-16** (§6 step 3).
- [x] ~~Select the mic **by name** rather than index~~ — done: `AUDIO_DEVICE` is left unset
      and PulseAudio's default source is pinned by name in config (§6 step 3).
