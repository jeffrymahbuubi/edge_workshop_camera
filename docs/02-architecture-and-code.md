# 02 — Architecture & Code Reference

Source lives in `references/context/edge-workshop-camera-en/`. This file is a
conceptual map of how the pieces fit — enough to reason about a port without
re-reading every line.

## System architecture

```
                         Mode 1: raw A/V fully uploaded
 [webcam + mic] --> [device] --Wi-Fi--> [Relay] --> cloud decodes + computes ALL features
       |            (no processing)      holds the real API key
       |                                 + device-token check + rate limit
       |               Mode 2: upload features only (~hundreds× less data)
       +--------> [device] --Wi-Fi--> [Relay] --> interpret / enrich (optional LLM)
                  frame-diff motion      returns a flag: FALL? / person-active / quiet
                  + audio RMS + fusion
                  + local store-and-forward buffer
```

Both modes wake up **once per second** (`SECONDS_PER_TICK = 1.0`). Each tick
grabs one second of video + audio and either streams it raw (Mode 1) or reduces
it to a feature vector (Mode 2).

### Common confusions (read this — they recur)

1. **"Cloud" and "API" are the SAME single server — the relay.** There is not a
   separate cloud-that-processes and an API-that-answers. The relay
   (`relay_server.py`, one FastAPI app) receives, processes, and responds in one
   round trip. "Cloud" is just a *role* = whichever machine runs the relay. **In
   this project (see `06`) the relay runs on the student laptop** and the Jetson is
   the edge; other options are Cloud Run, or the Jetson itself (all-in-one fallback).

2. **`extract_features` runs on only ONE side per mode — same function, different
   location.** Mode 1: the **edge sends raw and does nothing**; the **relay** runs
   `features.py`. Mode 2: the **edge** runs `features.py`; the relay never touches
   it (it trusts the received features and maps them to a flag). For identical
   input the feature vector is **identical** either way — that's why the relay copy
   is the "golden reference."

3. **The modes are NOT distinguished by the LLM note.** The optional
   `_maybe_llm_note` enrichment happens to be wired only into Mode 2's
   `/ingest_features`, but its purpose is a caregiver note on a fall event — *not* a
   Mode 1↔Mode 2 comparison. The real difference between the modes is **where
   compute runs + what crosses the network** (bandwidth, privacy, drop-resilience).

4. **Why does the workshop include Mode 1 if the result is identical?** Precisely
   *because* it's identical. Mode 1 is the **naive baseline** ("dumb edge, smart
   cloud") used as a foil: it works, then you measure it (~7.3 GB/day, faces+voices
   leave, data lost on drop) and Mode 2 gives the **same** answer 689× cheaper,
   private, and resilient. That contrast is the argument for edge compute. In a real
   deployment you would **not** pick pure Mode 1 — sending raw only earns its keep
   when the cloud does something the edge *can't* (a VLM that sees the scene), which
   is the escalation path in `05`.

## File-by-file

| File | Role | Notes for a port |
|---|---|---|
| `common.py` | All shared config + env-var knobs | Single source of tunables. Read this first. |
| `sensor.py` | Sensor layer: `SyntheticScene` (default) + `WebcamMicSource` | The only file that touches camera/mic hardware. Port risk concentrates here. |
| `features.py` | **The core algorithm.** Model-free motion + audio + fusion | Pure OpenCV + NumPy. Shared by Mode 2 **and** the relay (golden reference). |
| `codec.py` | Base64 codec: JPEG frames + int16 audio | Used by Mode 1, relay, and `compare.py` so everyone measures/decodes identically. |
| `relay_server.py` | FastAPI cloud relay: auth, rate-limit, ingest, optional LLM | Holds the API key + device-token whitelist. |
| `mode1_streamer.py` | Mode 1 client: capture → encode → POST raw | No analysis on device. Loses data on network drop (by design). |
| `mode2_edge.py` | Mode 2 client: capture → extract features → POST | Has the store-and-forward `outbox` buffer. |
| `compare.py` | Offline bandwidth + detection validation | No network/camera needed. Produces the headline ~689× number. |
| `webcam_selftest.py` | Real camera/mic self-test (wave/clap) | For calibrating thresholds on real hardware. |
| `requirements.txt` | Deps: numpy, opencv-python, requests, fastapi, uvicorn[standard], pydantic, sounddevice*, anthropic* | `*` = optional (mic / LLM). |

## The core algorithm (`features.py`)

Per second, three steps:

1. **Video motion** (`video_motion_features`):
   - Convert frames to grayscale.
   - For each consecutive pair: `diff = cv2.absdiff(a, b)`, then
     `mask = diff > PIX_DIFF_THRESH`.
   - `motion_level` = mean fraction of changed pixels across the second.
   - `motion_flag = motion_level > MOTION_LEVEL_THRESH`.
   - `n_blobs` = count of connected motion regions ≥ `MIN_BLOB_AREA`
     (via `cv2.connectedComponentsWithStats`).
2. **Audio energy** (`audio_energy_features`):
   - `rms = sqrt(mean(x^2))`; `loud_flag = rms > LOUD_RMS_THRESH`.
3. **Fusion** (`extract_features`):
   - `fall_suspected = loud_flag AND prev_motion_flag AND (NOT motion_flag)`
   - i.e. **a loud sound this second, and motion was present last second but has
     now stopped.** `prev_motion_flag` is threaded in by the caller (the client
     for Mode 2; per-device state in the relay for Mode 1).

The output feature vector (what Mode 2 uploads):
`motion_level, n_blobs, motion_flag, audio_rms, loud_flag, fall_suspected`.

## The relay API (`relay_server.py`)

FastAPI app. Every ingest endpoint requires header `X-Device-Token`.

| Endpoint | Method | Used by | Behavior |
|---|---|---|---|
| `/health` | GET | everyone | Returns `{"ok": true}`. |
| `/ingest_raw` | POST | Mode 1 | Decodes frames+audio, runs the **same** `extract_features` the edge would have (golden reference), returns `cloud_features`. |
| `/ingest_features` | POST | Mode 2 | Trusts the device's features; maps to a flag `FALL? / person-active / quiet`; optional LLM note. |

Cross-cutting relay behavior:

- **Auth** (`auth`): token must exist in `DEVICE_TOKENS` and be `active`.
  Revoke by flipping `active=False` → that device gets `401`, others unaffected.
  Default demo tokens: `tok_demo_bench01`, `tok_demo_bench02`.
- **Rate limit** (`rate`): `RATE_LIMIT=300` calls per `WINDOW_S=60` per device →
  `429` if exceeded.
- **Fusion state**: `_last_motion[device]` remembers the previous second's motion
  so Mode 1's cloud-side fusion works per device.
- **Optional LLM** (`_maybe_llm_note`): only fires when `fall_suspected` **and**
  `ANTHROPIC_API_KEY` is set on the relay. Default model string `LLM_MODEL =
  "claude-sonnet-5"` (override via env). Never returns the key to clients.

## Data flow, mode by mode

**Mode 1** (`mode1_streamer.py`): each second →
`encode_frame` (JPEG+base64) all frames + `encode_audio` (int16+base64) →
`POST /ingest_raw` → relay decodes + runs `extract_features` → prints
`cloud: motion/loud/fall`. On network error: prints `raw data lost (no buffer!)`.

**Mode 2** (`mode2_edge.py`): each second →
`extract_features` locally → append to `outbox` deque → `_flush` tries to POST
each item to `/ingest_features`. On success pops it; on `RequestException`
prints `[network down] buffering N item(s)` and **stops flushing** (data stays in
the buffer, N grows). When the network returns, the backlog flushes in order.

## Configuration knobs (`common.py`)

| Constant | Default | Meaning |
|---|---|---|
| `RELAY_URL` | `http://localhost:8000` | Where clients POST (env `RELAY_URL`). |
| `DEVICE_TOKEN` | `tok_demo_bench01` | Device's token (env `DEVICE_TOKEN`). |
| `SENSOR_KIND` | `synthetic` | `synthetic` or `webcam` (env `SENSOR`). |
| `CAMERA_INDEX` | `0` | Webcam index; external cams often 1/2 (env `CAMERA_INDEX`). |
| `FRAME_W, FRAME_H` | `320, 240` | Frame size — kept small on purpose. |
| `FPS` | `15` | Frames captured per second. |
| `JPEG_QUALITY` | `60` | JPEG quality for Mode 1 raw frames. |
| `AUDIO_SR` | `16000` | Audio sample rate. |
| `LOUD_RMS_THRESH` | `0.05` | Audio RMS above this = "loud." |
| `PIX_DIFF_THRESH` | `25` | Per-pixel gray change counted as motion. |
| `MOTION_LEVEL_THRESH` | `0.006` | Fraction of changed pixels above which = moving. |
| `MIN_BLOB_AREA` | `60` | Ignore motion blobs smaller than this. |
| `SECONDS_PER_TICK` | `1.0` | Both modes tick once per second. |

> These are the thresholds students tune, and the ones a real camera/lighting
> change would force you to re-calibrate. On a Jetson with a real webcam, expect
> to re-tune `MOTION_LEVEL_THRESH` / `LOUD_RMS_THRESH` via `webcam_selftest.py`.

## The sensor layer (`sensor.py`) — where hardware lives

- **`SyntheticScene`** (default): pure NumPy, deterministic (`seed=0`), needs no
  hardware. Emits per-second ground truth `{gt_moving, gt_impact}`.
- **`WebcamMicSource`** (`SENSOR=webcam`): `cv2.VideoCapture(CAMERA_INDEX)` for
  video (each frame resized to `FRAME_W×FRAME_H`); a background `sounddevice`
  `InputStream` fills a ring buffer for audio, aligned per second. **Graceful
  degradation**: if no mic / `sounddevice` missing, it runs **video-only with
  silent audio** and warns. Fast cameras are subsampled to ~FPS. Real frames have
  no ground truth (`gt_moving/gt_impact = None`).

This file is the main place a hardware port (drivers, camera index, audio
device, OpenCV build) will bite. See `03-ultimate-goal-jetson.md`.

## The headline numbers (from `compare.py`, synthetic scene, 12 s)

```
Mode 1 (raw stream) :   ~991.7 KB /12s   ~   7312 MB/day
Mode 2 (edge feats) :     ~1.44 KB /12s   ~  10.613 MB/day
--> Mode 1 sends about 689x more data than Mode 2

motion_flag matched truth in 12/12 seconds
fall events: 2 detected vs 2 in scene
```

Orders of magnitude are the point, not exact digits. This is the workshop's
central "aha," and it's fully reproducible with **no camera and no network** —
which makes it the safest first thing to run on any new machine (including the
Jetson) to confirm the environment.
