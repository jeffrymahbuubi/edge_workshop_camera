# Edge Sensing & Cloud Processing | 6-Hour Workshop Handout (Camera + Audio Edition)

**Topic**: Use a laptop + USB webcam (with microphone) as a sensing node, do
preliminary feature extraction, then upload to a cloud API for processing.
**Core question**: Between the sensor and the cloud, where should the
compute-partitioning line be drawn?
**Running thread**: Take the same audio/video, do it both ways, measure the
difference, and argue for your partitioning decision.

- **Mode 1**: pure streamer — send raw video + audio over the network; the cloud does everything.
- **Mode 2**: do part of it at the edge (motion detection + audio energy) — upload only a feature vector.

> The two modes are two ends of one axis. The course is about *deciding where to
> draw that line*; camera + audio makes the "bandwidth" and "privacy" issues
> especially dramatic, and opens a multimodal (audio-video fusion) thread.

---

## 0. Note to the TA (read this first, and complete the prep tests)

A deliberate design choice: **the whole pipeline runs by default on a "synthetic
scene," so it works on an ordinary laptop with no camera and no microphone.** The
synthetic scene is a colored block moving along a known path that "stops" every
few seconds while a short impact sound is injected — this gives a checkable
ground truth (motion should be detected while the block moves and go quiet when
it stops; a stop + impact = suspected fall). If the camera fails on the day, the
workshop still runs.

**Environment assumptions**: split into **morning 3 h + afternoon 3 h**, with a
lunch break in between; graduate students or undergraduates with some
programming background; **laptop + USB webcam ready on the day**. The split is
intentional: the morning is its own arc (build the pipeline, see the numbers,
understand detection), the afternoon its own arc (edge compute, key security,
break it). **The afternoon opens with a "restart check," because cameras/network
often drop over the lunch break.**

### TA prep checklist

- [ ] Each machine can run Python 3.8+, `pip install -r requirements.txt`
- [ ] **If the test server is headless**: swap `opencv-python` for `opencv-python-headless` (noted in `requirements.txt`)
- [ ] One machine runs the relay; another (or the same) can reach it
- [ ] Run the four smoke tests below; outputs match "Expected"
- [ ] (Optional) LLM enrichment: set `ANTHROPIC_API_KEY` **on the relay machine**, confirm a `note=...` line appears when a fall is detected
- [ ] For a real camera: `pip install opencv-python sounddevice`, run `python webcam_selftest.py` first (wave/clap to confirm and calibrate thresholds), then verify once with `SENSOR=webcam python mode1_streamer.py` (see §6)

### Four smoke tests

**Test A | Offline bandwidth comparison + detection validation (no network, no camera)**
```bash
python compare.py
```
Expected (orders of magnitude are what matter):
```
=== 12s of 320x240 @15fps video + 16kHz audio ===
Mode 1 (raw stream) :     991.7 KB /12s   ~     7312 MB/day
Mode 2 (edge feats) :       1.44 KB /12s   ~   10.613 MB/day
--> Mode 1 sends about 689x more data than Mode 2

Validation vs ground truth:
  motion_flag matched truth in 12/12 seconds
  fall events: 2 detected vs 2 in scene
```
> Key point: Mode 1 is **~7.3 GB/day**, Mode 2 **~10 MB/day** — about **689×**;
> motion detection matches ground truth 12/12, and both falls are caught. These
> two results are the most important teaching moment of the morning; confirm your
> machine produces them.

**Test B | Start the relay** (leave one terminal running)
```bash
uvicorn relay_server:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health          # expect {"ok":true}
```

**Test C | Mode 1 (raw A/V stream → cloud does everything)** (relay running)
```bash
python mode1_streamer.py                    # Ctrl-C to stop
```
Expect `cloud: motion=... loud=... fall=...` each second, with `fall=True` the
second the block stops. On exit it prints a bandwidth summary (GB/day scale).

**Test D | Mode 2 (edge feature extraction) + store-and-forward** (relay running)
```bash
python mode2_edge.py                        # expect flag=person-active / FALL? / quiet
```
Test the network drop:
```bash
RELAY_URL="http://127.0.0.1:9999" python mode2_edge.py
```
Expect `[network down] buffering N item(s)` with **N increasing** (data buffered, not lost).

---

## 1. Learning objectives

1. Build a complete end-to-end A/V pipeline: sense → upload → cloud processing → return.
2. Implement Mode 1 and Mode 2, and **quantify** the differences in bandwidth,
   privacy, and network resilience.
3. Explain why uploading raw A/V (faces, voices) has privacy and regulatory costs,
   and how edge de-identification mitigates them.
4. Do motion detection and audio-event detection at the edge using a **model-free**
   method (OpenCV frame differencing + audio energy), and understand its
   **threshold sensitivity and fragility**.
5. Experience **multimodal fusion**: neither video nor audio alone is enough;
   "impact sound + motion suddenly ending" is what constitutes a suspected fall.
6. Explain why an API key must not live on the device, and how the relay solves
   this with a revocable token.
7. For a given scenario, **argue** where you would draw the partitioning line and why.

---

## 2. System architecture

```
                                Mode 1: raw A/V fully uploaded
 [USB webcam+mic] --> [laptop] --Wi-Fi--> [Relay (cloud)] --> cloud decodes + computes all features
        |             (no processing)       holds the real API key
        |                                   + device-token check
        |                         Mode 2: upload features only
        +----------> [laptop] --Wi-Fi--> [Relay (cloud)] --> interpret/enrich (optional LLM)
                     frame-diff motion       (hundreds of times less data)
                     + audio RMS + fusion
                     + local buffer (no data loss on drop)
```

**Key security design**: the real API key lives only on the relay; the device
carries only a revocable `device token`, so a stolen device does not compromise
the account.
**Key privacy design**: in Mode 2 the edge compresses A/V into labels like
"motion / sound / suspected fall" — **faces and voices never leave the room**.

---

## 3. File inventory

| File | Role |
|---|---|
| `common.py` | Shared config (relay URL, token, resolution, FPS, thresholds) |
| `sensor.py` | Sensor layer. Default "synthetic scene," plus a real USB webcam+mic implementation |
| `codec.py` | Base64 codec for JPEG frames / int16 audio (shared by clients, relay, compare) |
| `features.py` | **Model-free** feature extraction: motion + audio energy + fusion. **Shared by Mode 2 and the relay** |
| `relay_server.py` | Cloud relay server (FastAPI). Holds the API key, validates tokens, rate-limits |
| `mode1_streamer.py` | Mode 1: raw A/V streamer |
| `mode2_edge.py` | Mode 2: edge feature extraction + store-and-forward |
| `compare.py` | Offline bandwidth comparison + detection validation (the "aha" moment) |
| `webcam_selftest.py` | On-site self-test for a real camera/mic (wave/clap to calibrate thresholds) |
| `requirements.txt` | Dependencies |

---

## 4. Course flow: morning 3 h + afternoon 3 h

Times are relative within each half (morning and afternoon each start at 0:00).
Each half has one 10-minute break in the middle.

### Morning (3 h) | Understand the line: build the pipeline, see the numbers, understand detection

| Time | Content | Files |
|---|---|---|
| 0:00–0:20 | **Opening**: pose the "partitioning line" core question; frame the two modes as the two ends | — |
| 0:20–1:20 | **Lab A | Mode 1**: get the raw A/V streaming pipeline working end to end (an early success) | `mode1_streamer.py`, `relay_server.py` |
| 1:20–1:30 | Break | — |
| 1:30–2:10 | **Measure Mode 1**: the striking `compare.py` numbers (~7.3 GB/day vs ~10 MB/day) + discussion | `compare.py` |
| 2:10–2:55 | **Motion detection intro + hands-on threshold tuning**: walk through `features.py`; change `MOTION_LEVEL_THRESH` and watch the hit rate change | `features.py`, `common.py`, `compare.py` |
| 2:55–3:00 | **Morning wrap**: pose the cliffhanger — raw works but is 7 GB/day and sends faces+voices out; the afternoon pushes the line to the edge | — |

### [Lunch]

### Afternoon (3 h) | Push the line to the edge: edge compute, key security, break it

| Time | Content | Files |
|---|---|---|
| 0:00–0:15 | **Restart check**: recap the morning; reconnect the relay, run Mode 1 once to confirm the environment still works | `mode1_streamer.py` |
| 0:15–1:15 | **Lab B | Mode 2** (afternoon focus): extract features at the edge, send features only, re-measure bandwidth; weave in privacy + irreversibility + fusion | `mode2_edge.py`, `features.py` |
| 1:15–1:25 | Break | — |
| 1:25–2:05 | **Cloud processing + key security**: interpret/enrich fall events; relay and device token; revocation demo | `relay_server.py` |
| 2:05–2:45 | **"Pull the network" stress test**: how each mode fails; Mode 2's store-and-forward | `mode2_edge.py` |
| 2:45–3:00 | **Design argument + closing**: state in one sentence where the line goes; show the full issue map and today's gaps | design assignment |

---

## 5. Per-segment guidance (for the instructor)

> Every heading's time is "relative within the half." Morning and afternoon each start at 0:00.

### [Morning]

### Opening (M 0:00–0:20) | Pose the core question

Use a few slides to build the mental model: between sensor and cloud there is a
"compute-partitioning line." Mode 1 draws it closest to the sensor (pure
forwarding); Mode 2 pushes it a bit toward the cloud (compute first at the edge).
**All day is about answering: where should this line go?**

### Lab A (M 0:20–1:20) | Mode 1: pure streaming

**Goal**: get a working end-to-end A/V pipeline first, for an early success. No
optimization here; just make it work.

1. One group designates a machine as the relay: `uvicorn relay_server:app --host 0.0.0.0 --port 8000`.
2. Everyone else points `RELAY_URL` at the relay's IP (env var `RELAY_URL=http://<relay-ip>:8000`).
3. Run `python mode1_streamer.py`, watch the returned `motion / loud / fall`; note `fall=True` the second the block stops.
4. **Guiding question**: who is doing the detection now? (Answer: the cloud. The laptop is just a pipe — and it sent all the raw A/V out.)

### Measure Mode 1 (M 1:30–2:10) | See the numbers

Run `python compare.py`, focus on:
```
Mode 1 (raw stream) :  ~7312 MB/day
Mode 2 (edge feats) :  ~10.6 MB/day   --> about 689x
```
**Guiding question**: with several devices streaming 1080p at once, can home
Wi-Fi cope? What does a month of cloud ingest/storage cost? Translate "saving
bandwidth" into "saving money."
> Honest caveat 1: Mode 1's raw would be much smaller with H.264 hardware
> encoding (a Jetson strength) than per-frame JPEG, but the "orders of magnitude
> larger than features" conclusion holds.
> Honest caveat 2: here Mode 2 sends once per second (~10 MB/day); sending "only
> on events" would cut another order of magnitude — the hybrid design mentioned
> in the afternoon.

### Motion detection intro + hands-on threshold tuning (M 2:10–2:55)

First walk through the model-free core of `features.py`:

```python
# features.py (excerpt): pure OpenCV, no model
diff = cv2.absdiff(gray_a, gray_b)               # difference consecutive frames
mask = (diff > PIX_DIFF_THRESH).astype(np.uint8) # pixels that changed enough
motion_level = mask.mean()                       # fraction of the frame in motion
motion_flag = motion_level > MOTION_LEVEL_THRESH # above threshold = someone moving
# audio: rms = sqrt(mean(x^2)); rms > LOUD_RMS_THRESH = sound/impact
# fusion: loud AND "was moving last second, stopped this second" = suspected fall
```

**Hands-on threshold tuning (the first lesson in model-free methods)**: have
students open `common.py`, raise `MOTION_LEVEL_THRESH` from `0.006` to `0.05`,
rerun `python compare.py`, and watch `matched truth` drop **from 12/12 to 4/12**.
> Teaching point: in the synthetic scene the block's `motion_level ≈ 0.008` while
> moving — very close to the default threshold `0.006`. This exposes the
> **fragility of model-free detection: it all rides on a hand-tuned threshold, and
> a different light or camera can throw it off**. This is the first lesson in "what
> you compute at the edge must be verifiable," and it comes back in the afternoon.

### Morning wrap (M 2:55–3:00) | Leave a cliffhanger

One sentence to close: "Uploading everything raw works, but it's 7 GB/day and
sends the patient's face and voice out of the room. This afternoon we push the
line to the edge — see how much we save, and what new responsibilities appear."

### [Afternoon]

### Restart check (A 0:00–0:15) | Reconnect the environment after lunch

Cameras and Wi-Fi often drop over lunch; spend 15 minutes on it:

1. Restart the relay, `curl .../health` returns `{"ok":true}`.
2. Everyone reruns `python mode1_streamer.py` to confirm connectivity and see `cloud: ...`.
3. One-sentence recap of the morning result (7.3 GB vs 10 MB) to bring everyone back.

### Lab B (A 0:15–1:15) | Mode 2: edge feature extraction (afternoon focus)

**Goal**: move detection onto the device, upload only features, then re-measure bandwidth.

1. Run `python mode2_edge.py`, watch it print `motion / loud / fall -> flag=person-active / FALL? / quiet`, with upload volume dropping to the KB scale.
2. Weave in three key issues while working:

- **Privacy (the star of this edition)**: Mode 1 sends **faces and voices**
  (identifiable data) — IRB / privacy law light up immediately; Mode 2 sends only
  labels like "motion, sound, suspected fall," so **faces and voices never leave
  the device**. This is the most convincing live demo of the "edge
  de-identification" principle for home monitoring. Principle: **which raw data
  should simply never leave the device?**
- **Irreversibility**: Mode 2 fixes the feature set at collection time. If you
  later want new features (e.g. gait, or facial expression) for a new research
  question, the raw A/V is gone. The mature compromise is a **hybrid design**:
  normally send features only, and upload raw only for segments flagged as
  anomalous (e.g. `fall_suspected`).
- **Multimodal fusion**: point out that "motion stopped" alone might just be
  sitting down; "a loud bang" alone might be a door. It takes **both together** to
  suggest a fall. That is the value of fusion, and it maps to fall detection and
  rehab assessment.

3. **Tie back to the morning's validation**: once Mode 2 "computes something," ask
   "is it correct?" This echoes the threshold exercise — in a real deployment a
   change of lighting/camera means retuning thresholds, so **any detection moved to
   the edge needs regression tests**.

### Cloud processing + key security (A 1:25–2:05)

1. Open `relay_server.py`, explain how `/ingest_features` turns features into `FALL? / person-active / quiet`.
2. (Optional) If the relay machine has `ANTHROPIC_API_KEY`, `_maybe_llm_note`
   generates a caregiver note when a fall is detected (**only on real events, to
   save tokens**). Emphasize the key stays on the server.
3. Explain token validation:

```python
# relay_server.py (excerpt): the device carries only a token; the real key is a server env var
def auth(token):
    info = DEVICE_TOKENS.get(token)
    if not info or not info["active"]:       # revoke a stolen device by setting active=False
        raise HTTPException(401, "invalid or revoked device token")
    return info
```

**Live revocation demo**: set a token's `active` to `False`, restart the relay,
that device immediately gets 401, others keep working.

### "Pull the network" stress test (A 2:05–2:45)

1. Let `mode2_edge.py` run normally, then **kill the relay** (or drop Wi-Fi).
2. Watch `[network down] buffering N item(s)`, N increasing — data goes to a local buffer, not lost.
3. Restart the relay, watch the buffered data get flushed (store-and-forward).
4. **Contrast with Mode 1**: on a drop `mode1_streamer.py` just prints `raw data lost (no buffer!)` — data vanishes.
> This is a required lesson in **failure modes**. Many students have only ever
> demoed with good networking; these 40 minutes will change that.

### Design argument + closing (A 2:45–3:00)

No code. See §8 for the assignment and rubric. Close by showing the §9 "gap map,"
so students see they only touched a small part of the whole picture today.

---

## 6. Swapping in a real webcam + mic (for the TA / advanced)

**`WebcamMicSource` is already implemented and ready to use** — no code changes
needed. The synthetic scene is still the default; to use a real camera you only
change one environment variable.

**Steps (on a physical laptop):**

1. Install the real-hardware packages: `pip install opencv-python sounddevice`
   (`opencv-python` is the windowed build, not headless).
2. **Run the self-test first to confirm hardware and calibrate thresholds**:
   ```bash
   python webcam_selftest.py          # external camera: CAMERA_INDEX=1 python webcam_selftest.py
   ```
   It prints, for 6 seconds, each second's frame count, size, motion_level, and
   audio_rms. **Wave** to make `motion?` go `True`; **clap** to make `loud?` go
   `True`. If waving never lights motion, lower `MOTION_LEVEL_THRESH` in
   `common.py`; if clapping never lights loud, lower `LOUD_RMS_THRESH`.
3. Switch the sensor source with an environment variable; nothing else changes:
   ```bash
   SENSOR=webcam python mode1_streamer.py     # Mode 1: raw A/V stream
   SENSOR=webcam python mode2_edge.py         # Mode 2: edge feature extraction
   ```
   (Without `SENSOR` it defaults to `synthetic`; for an external camera add `CAMERA_INDEX=1`.)

**What the implementation already handles for you**: frames are auto-resized to
`FRAME_W×FRAME_H` (regardless of the camera's native resolution); audio is
recorded via a continuous background stream and aligned per second; a fast
camera's excess frames are subsampled to ~FPS; the camera is released on exit.
**Graceful degradation**: if the laptop has no usable microphone (or `sounddevice`
is not installed), it prints a warning and continues with **video only + silent
audio** — the workshop is never blocked by a mic problem.

**Real-hardware notes**: the camera index is not always 0 (external cameras are
often 1 — set `CAMERA_INDEX`); macOS prompts for camera/mic permission on first
use — allow it; a headless/remote server has no camera or audio device, so **test
real hardware only on a physical laptop** (`compare.py`'s validation still uses the
synthetic scene and is unaffected); real footage has no ground truth, so
`webcam_selftest.py` uses "wave/clap" so you **verify with your eyes**, replacing
the synthetic scene's automatic comparison.

---

## 7. Protocols and API contract (extension material, if time permits)

For simplicity the workshop uses HTTP POST + JSON throughout. Real A/V systems
would use **RTSP/WebRTC** for continuous video (not per-frame POST); HTTPS POST or
**MQTT** for events and features; and to teach interface contracts, students can
write an **OpenAPI/Swagger** spec formalizing "what the device sends and the cloud
returns."

---

## 8. Design-argument assignment and rubric

**Assignment**: given a scenario (e.g. "home fall detection for an elderly person
living alone, with unstable home Wi-Fi and privacy-conscious family"), each group
answers in one page:

1. Where do you draw the compute-partitioning line? (Pure Mode 1, pure Mode 2, or hybrid?)
2. Three supporting reasons, each tied to an issue measured or discussed today
   (bandwidth / privacy / network drop / irreversibility / fusion / threshold fragility).
3. At least three issues you **did not do today but a real deployment must handle**.

**Scoring (0–4 each, 20 total)**

| Dimension | 4 | 2 | 0 |
|---|---|---|---|
| Partitioning decision | Clear and fits the scenario | A decision but weak reasoning | Undefined |
| Quantitative evidence | Cites measured numbers | Only qualitative | None |
| Trade-off awareness | Names the opposing side and chooses | Only one-sided benefits | No trade-off |
| Privacy/regulation | Specific about where de-identification happens | Vague mention of privacy | Not mentioned |
| Awareness of gaps | Honestly lists unhandled issues | Lists but incomplete | Claims everything is done |

> The last row echoes the course's epistemic standard: **say what you did not
> handle** — worth more than pretending to have covered it.

---

## 9. Issues deliberately not covered today, only named (an honest gap map)

- **Real person/object/pose detection**: today uses frame differencing, which only
  knows "is something moving," not "is it a person, doing what." Real systems need
  YOLO/MediaPipe (models + TensorRT) — an advanced upgrade path.
- **Audio classification**: today only energy thresholds (is there sound); it can't
  distinguish speech, coughing, a door, or a fall impact. Real systems need an
  audio-event classification model.
- **Environmental robustness of thresholds**: different light, camera, or
  background throws hand-tuned thresholds off — today shows the fragility but does not solve it.
- **Audio-video time synchronization**: the lifeblood of multimodal fusion; the single-sensor version doesn't touch it.
- **Cost and power quantification**, **full protocol selection (RTSP/WebRTC/MQTT)**,
  **containerization and reproducible environments**: today uses a preinstalled environment and doesn't go deep.

---

## 10. Troubleshooting

| Symptom | Possible cause / fix |
|---|---|
| `import cv2` fails | `pip install opencv-python`; on a **headless server** use `opencv-python-headless` |
| Client can't reach the relay | Relay needs `--host 0.0.0.0`; same subnet and firewall; `RELAY_URL` must use the real IP |
| Returns 401 | `DEVICE_TOKEN` not in the whitelist, or that token is `active=False` |
| Real camera won't open | Wrong `VideoCapture` index (try 0 or 1); in use by another app; permission not granted |
| Real mic silent | Headless/remote has no audio device; `sounddevice` needs OS audio permission; test on a physical laptop first |
| Mode 1 slow/laggy | Per-frame JPEG encoding is CPU-heavy — normal; lower `FRAME_W/H` or `FPS`, or shorten the test |
| No `note` line | Normal — no `ANTHROPIC_API_KEY`, or no fall detected that second, so the LLM isn't called |

---

*All code in this material runs by default on a laptop without a camera; please
have the TA complete the four smoke tests in §0 before class.*
