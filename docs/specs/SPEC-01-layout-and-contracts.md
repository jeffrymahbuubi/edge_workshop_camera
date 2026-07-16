# SPEC-01 — Code Layout & Contracts

> **Live document.** Update it as implementation lands. Tick the checkboxes; when a
> decision changes, change it *here* first — every other SPEC depends on this one.

| | |
|---|---|
| **Status** | 🟢 **Realized** for Modes 1+2 (2026-07-16) — `src/` layout built, Mode 1/2 contract live and hardware-validated. Mode 3 (§4.3) and the posture contract (§5) remain 🟡 specified-only. |
| **Depends on** | [`docs/01-design/06-deployment-topology-edge-relay.md`](../01-design/06-deployment-topology-edge-relay.md) (locked topology) |
| **Depended on by** | SPEC-02 (🟢 built), SPEC-03, SPEC-04, SPEC-05 |

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
| OpenCV | `cv2` 4.11.0 | `features.py` / `posture.py` run as-is |
| NumPy | 1.23.5 | ✅ |
| **PyTorch** | **1.11.0a0**, `torch.cuda.is_available() == True`, `NVIDIA Tegra X1` | **Already installed** — SPEC-05's main cost is already paid |
| torchvision | 0.12.0a0 | ✅ |
| TensorRT | 8.2.1.8 | ✅ |
| `requests` | 2.32.3 | Edge clients work |
| **`sounddevice`** | ✅ **0.5.5 installed** 2026-07-16 (+ `libportaudio2`) | ⚠️ Not sufficient alone — the mic must be *selected*, see SPEC-02 §9.3 |
| Microphone | ✅ Logitech **C270 webcam mic**, `hw:2,0`, **index 11** | The system default (18) is the onboard codec and records **silence** |
| `curl` | ❌ not installed | Use `python3 -c "import requests…"` to probe the relay |
| `torch2trt` | ❌ not installed | Needed by SPEC-05 |
| `trt_pose` | ❌ not installed | Needed by SPEC-05 |
| RAM | 3.9 GB total, ~3.5 GB available, **5.9 GB swap** | Not the binding constraint |
| **Disk** | 44 GB, **37 GB used, 5.2 GB free (88%)** | ⚠️ **The binding constraint.** See §6 |
| Camera | `/dev/video0` present, C270 @ 12.9 fps confirmed | ✅ |
| Audio capture | C270 USB mic **confirmed present** (`alsa_input.usb-046d_C270...`) | ⚠️ works only when it is PulseAudio's default source, which **keeps reverting** — see SPEC-02 §9.3 |
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
obvious: *copy `edge/` + `common/` to the Jetson* is the entire instruction.

```
nvidia-workshop/
├── src/
│   ├── edge/            → runs on the JETSON (python3.8)
│   │   ├── mode1_streamer.py     raw → relay
│   │   ├── mode2_edge.py         features → relay
│   │   ├── mode3_posture.py      posture + abnormal → relay   (SPEC-04, built)
│   │   ├── behaviour.py          the fall-rule state machine   (SPEC-04, built)
│   │   ├── supervisor.py         polls /mode, swaps clients    (SPEC-07, built)
│   │   ├── sensor.py             webcam/mic + synthetic scene
│   │   ├── posture.py            posture backends              (SPEC-04/05)
│   │   ├── webcam_selftest.py
│   │   └── posture_selftest.py
│   ├── relay/           → runs on the LAPTOP (any python)
│   │   ├── relay_server.py       FastAPI + SSE + dashboard
│   │   ├── bandwidth.py          byte accounting               (SPEC-02, new)
│   │   └── compare.py            offline 689× smoke test
│   ├── common/          → runs on BOTH — keep import-light
│   │   ├── features.py           the model-free detector
│   │   ├── codec.py              base64/JPEG/audio helpers
│   │   └── config.py             thresholds + env config (was common.py)
│   └── web/             → served by the relay
│       ├── index.html
│       ├── app.js
│       └── vendor/elements/      vendored NVIDIA Elements UI (offline)
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

**Mode 3 → `/ingest_posture`** *(new — SPEC-04)*
```jsonc
{ "posture": "lying",           // standing | walking | lying | absent
  "abnormal": true,
  "reason": "upright→lying held 3s",
  "torso_angle": 78.4,          // pose backends only; null for bgsub
  "confidence": 0.91,           // pose backends only; null for bgsub
  "backend": "trt_pose",        // bgsub | trt_pose
  "context": "" }
```
→ `{"device": "bench01", "flag": "FALL?", "note": null}`

> Mode 3 sends **only the verdict**, never keypoints or frames. The abnormal-behaviour
> rule runs **on the Jetson** — same philosophy as Mode 2. Shipping skeletons to the
> laptop would repeat Mode 1's mistake in a new costume.

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

## 5. The posture backend contract *(extended — SPEC-04/05)*

A **superset**: `bgsub` keeps satisfying the original four fields; pose backends add
two more. The `POSTURE_BACKEND` switch your colleague built stays intact, and the
dashboard branches on presence rather than on backend name.

```python
{
  "posture": "standing" | "walking" | "lying" | "absent",
  "bbox":    (x, y, w, h) | None,
  "aspect":  float,            # h/w, 0.0 if no box
  "fill":    float,            # foreground fraction 0..1
  # --- pose backends only; None for bgsub ---
  "keypoints":   {...} | None, # 18 COCO keypoints
  "torso_angle": float | None, # neck→hip vector vs vertical, degrees
}
```

| Backend | `bbox` | `aspect` | `fill` | `keypoints` | `torso_angle` |
|---|---|---|---|---|---|
| `bgsub` | ✅ | ✅ | ✅ | `None` | `None` |
| `trt_pose` | ✅ *(from keypoint extents)* | ✅ | ✅ | ✅ | ✅ |

- [ ] Downstream code must treat `keypoints`/`torso_angle` as **optional**, never assume.

---

## 6. Constraints this spec imposes

- [ ] **Disk is the budget.** 5.2 GB free at 88%. Every addition (torch2trt, trt_pose,
      81 MB weights, pre-built `.engine`) comes out of it. Check `df -h /` before and
      after each install; if it drops below ~2 GB, stop and reclaim first.
- [ ] **`common/` stays import-light** (§3).
- [ ] **No credentials in the repo.** The dev board uses a default password over a
      point-to-point ICS link; it must not appear in any tracked file.
- [ ] **The API key stays on the laptop.** Non-negotiable — it is the boss's design.

---

## 7. Open

- [x] ~~Does the USB webcam expose a mic?~~ **Yes** — Logitech C270, index 11. But the
      system default records silence; `AUDIO_DEVICE` must be set. See SPEC-02 §9.3.
- [ ] Select the mic **by name** (`"C270"`) rather than index `11` — the index depends on
      enumeration order and may differ on a student board. Do this before cloning.
- [ ] Confirm 5.2 GB is enough for SPEC-05's full install (measure, don't guess).
