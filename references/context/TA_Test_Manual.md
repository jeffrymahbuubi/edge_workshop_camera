# TA Test Manual — Edge Sensing Workshop (Camera + Audio)

This manual is for the **teaching assistant, before the workshop**: follow it to
confirm the environment and code work on your machine, and to prepare the
classroom deployment. The teaching content lives in a separate document,
`Handout_Edge_Sensing_Camera_Audio.md`; this manual is only about testing and
preparation.

**Estimated time**: ~20–30 min for the software-only tests; ~1 hour including
the real-camera test and a classroom-deployment dry run.

**What success looks like**: all six tests A–F pass (see the checklist below),
and you can run Mode 1 / Mode 2 between two machines (one as the relay, one as
the client).

---

## 1. What you need

- A computer with internet access (Windows / macOS / Linux), with **Python 3.8+**
  (validated on 3.12).
- The software-only tests need **no** camera or microphone (they use the synthetic scene).
- To test real hardware: a **USB webcam** (with microphone) and a physical laptop with a screen.
- On the workshop day: one machine acting as the relay, with all clients on the
  **same Wi-Fi / LAN**.

---

## 2. Install the environment

From inside the package folder:

```bash
python -m venv venv                 # virtual environment recommended (optional)
# Windows: venv\Scripts\activate    # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

> **Headless test server (no display)**: replace `opencv-python` with
> `opencv-python-headless` in `requirements.txt` before installing (use one, not
> both). `sounddevice` is only needed for a real microphone; if it won't install
> in your test environment, skip it.

Verify the core packages:

```bash
python -c "import numpy,cv2,requests,fastapi,uvicorn,pydantic; print('OK', cv2.__version__)"
```
Expected: `OK 4.x.x`

---

## 3. File inventory (should be 11)

| # | File | Purpose |
|---|---|---|
| 1 | `common.py` | Shared config |
| 2 | `codec.py` | Frame/audio base64 codec |
| 3 | `sensor.py` | Sensor (synthetic scene + real webcam + mic) |
| 4 | `features.py` | Model-free feature extraction (motion + audio + fusion) |
| 5 | `relay_server.py` | Cloud relay server |
| 6 | `mode1_streamer.py` | Mode 1 client (raw stream) |
| 7 | `mode2_edge.py` | Mode 2 client (edge feature extraction) |
| 8 | `compare.py` | Offline bandwidth comparison + detection validation |
| 9 | `webcam_selftest.py` | Real webcam/mic self-test |
| 10 | `requirements.txt` | Dependencies |
| 11 | `Handout_Edge_Sensing_Camera_Audio.md` | Teaching handout |

- [ ] All 11 files present

---

## 4. Test protocol (run in order, tick each off)

> Each test lists the command → expected output → pass criterion. Matching the
> order of magnitude is enough; exact numbers need not match.

### Test A | Offline bandwidth comparison + detection validation (no network, no camera)

```bash
python compare.py
```
Expected:
```
=== 12s of 320x240 @15fps video + 16kHz audio ===
Mode 1 (raw stream) :     991.7 KB /12s   ~     7312 MB/day
Mode 2 (edge feats) :       1.44 KB /12s   ~   10.613 MB/day
--> Mode 1 sends about 689x more data than Mode 2

Validation vs ground truth:
  motion_flag matched truth in 12/12 seconds
  fall events: 2 detected vs 2 in scene
```
**Pass criterion**: the ratio is in the hundreds (not single digits); `matched
truth` ≥ 10/12; `fall events` is `2 detected vs 2`.

- [ ] Test A passed

---

### Test B | Start the relay and confirm it is alive

Open one terminal and leave it **running**:
```bash
uvicorn relay_server:app --host 0.0.0.0 --port 8000
```
Open another terminal:
```bash
curl http://localhost:8000/health
```
Expected: `{"ok":true}`

**Pass criterion**: returns `{"ok":true}`.
> On Windows without `curl`, open `http://localhost:8000/health` in a browser.

- [ ] Test B passed (keep the relay running for C/D/E)

---

### Test C | Mode 1 (raw video+audio stream → cloud does everything)

(relay must be running)
```bash
python mode1_streamer.py            # watch for a few seconds, then press Ctrl-C
```
Expected (one line per second; `fall=True` appears the second the block stops):
```
  cloud: motion=True loud=False fall=False   (all compute in the cloud)
  cloud: motion=True loud=False fall=False   (all compute in the cloud)
  cloud: motion=False loud=True fall=True   (all compute in the cloud)
```
After Ctrl-C it prints a bandwidth summary (GB/day scale).

**Pass criterion**: you see `cloud: ...` each second; `fall=True` appears at least once.

- [ ] Test C passed

---

### Test D | Mode 2 (edge feature extraction)

(relay must be running)
```bash
python mode2_edge.py                # watch for a few seconds, then press Ctrl-C
```
Expected:
```
  motion=True loud=False fall=False  -> flag=person-active
  motion=False loud=True fall=True  -> flag=FALL?
  motion=False loud=False fall=False  -> flag=quiet
```
**Pass criterion**: you see `flag=person-active`, and `flag=FALL?` appears the
second the block stops.

- [ ] Test D passed

---

### Test D2 | Store-and-forward on a network drop

Deliberately point at a non-existent relay:
```bash
# macOS/Linux:
RELAY_URL="http://127.0.0.1:9999" python mode2_edge.py
# Windows PowerShell:
$env:RELAY_URL="http://127.0.0.1:9999"; python mode2_edge.py
```
Expected:
```
  [network down] buffering 4 item(s): ...
  [network down] buffering 5 item(s): ...
```
**Pass criterion**: you see `buffering N item(s)` and **N increases** (data is
buffered, not lost). Afterwards, set `RELAY_URL` back (or close that window).

- [ ] Test D2 passed

---

### Test E | Bad token is rejected (key security)

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST http://localhost:8000/ingest_features \
  -H "X-Device-Token: BAD" -H "Content-Type: application/json" -d '{"motion_flag":true}'
```
Expected: `HTTP 401`

**Pass criterion**: returns `401` (an unauthorized device is rejected).

- [ ] Test E passed

---

### Test F | (Optional) Real webcam + microphone

**Only if you have a physical laptop + USB webcam.** First install:
`pip install opencv-python sounddevice`.

```bash
python webcam_selftest.py           # external camera: CAMERA_INDEX=1 python webcam_selftest.py
```
Expected: for 6 seconds it prints, once per second, the frame count, size,
motion_level, and audio_rms. **Wave your hand** and `motion?` should turn
`True`; **clap** and `loud?` should turn `True`.

If there is no camera (e.g. run by mistake on the test server), it prints cleanly:
```
CAMERA ERROR: Could not open camera at index 0. Try another index ...
```
(No traceback; a few OpenCV `WARN` lines above it are normal device-probing messages.)

Once it works on real hardware, run Mode 1/2 once each with the real camera:
```bash
# macOS/Linux:
SENSOR=webcam python mode1_streamer.py
SENSOR=webcam python mode2_edge.py
# Windows PowerShell:
$env:SENSOR="webcam"; python mode1_streamer.py
```

**Pass criterion**: waving/clapping in the self-test triggers motion/loud;
`SENSOR=webcam` sends data to the relay in both modes.

- [ ] Test F passed (if not using a real camera, skip and note "synthetic scene for this session")

---

## 5. Classroom deployment preparation

### 5.1 Where the relay lives

**Simplest (recommended for the workshop)**: pick one machine as the relay and
run it on the LAN:
```bash
uvicorn relay_server:app --host 0.0.0.0 --port 8000
```
Find that machine's LAN IP and give it to students as `RELAY_URL`:
- macOS/Linux: `ip addr` or `ifconfig`, look for `192.168.x.x` / `10.x.x.x`
- Windows: `ipconfig`, look for the IPv4 address

Student-side setup (replace `<relay-ip>` with the IP above):
```bash
# macOS/Linux:
RELAY_URL="http://<relay-ip>:8000" python mode1_streamer.py
# Windows PowerShell:
$env:RELAY_URL="http://<relay-ip>:8000"; python mode1_streamer.py
```

> **Firewall**: the relay machine may need to allow inbound connections on port
> 8000. Do one cross-machine test first (Test B's health check from a student
> machine: `curl http://<relay-ip>:8000/health`). All machines must be on the
> **same Wi-Fi / subnet**.

**Advanced (optional)**: deploy `relay_server.py` to GCP Cloud Run, with
`ANTHROPIC_API_KEY` in Secret Manager. Not needed for the workshop; see handout
section 7 and the earlier discussion.

### 5.2 Each student workstation

- [ ] Has the whole folder and `requirements.txt` installed
- [ ] Can run `python compare.py` (Test A)
- [ ] Has the relay's `RELAY_URL` and `curl .../health` works
- [ ] Uses the default device tokens `tok_demo_bench01` / `tok_demo_bench02`
      (in `DEVICE_TOKENS` in `relay_server.py`; add more if needed)

### 5.3 (Optional) LLM enrichment demo

To show an LLM-generated caregiver note when a fall is detected, set the key
**only on the relay machine**, then start the relay:
```bash
# macOS/Linux:
export ANTHROPIC_API_KEY=sk-...        # set a valid model string: export LLM_MODEL=claude-sonnet-5
uvicorn relay_server:app --host 0.0.0.0 --port 8000
```
Mode 2 will then print an extra `note=...` line when it detects `FALL?`. The key
stays on the server; student clients never receive it. Without a key, everything
still works — there is just no note line.

- [ ] (If used) LLM enrichment verified on the relay machine

---

## 6. Troubleshooting (setup-focused)

| Symptom | Fix |
|---|---|
| `import cv2` fails | `pip install opencv-python`; on a headless server use `opencv-python-headless` (one or the other) |
| `import sounddevice` hangs or fails | Only needed for a real mic; skip it in the test environment. The code falls back to video-only without it |
| Student can't reach the relay | Relay must use `--host 0.0.0.0` (not 127.0.0.1); same subnet; allow port 8000; `RELAY_URL` must use the real IP |
| Returns 401 | `DEVICE_TOKEN` not in the `DEVICE_TOKENS` whitelist, or that token is `active=False` |
| Real camera won't open | Wrong index (try `CAMERA_INDEX=0/1/2`); in use by another app; camera permission not granted (macOS) |
| Real mic does nothing | Mic permission not granted; or no input device; the code falls back to video-only and prints a warning |
| Mode 1 is CPU-heavy/slow | Per-frame JPEG encoding is naturally CPU-heavy; lower `FRAME_W/H` or `FPS` in `common.py` |
| Setting env vars on Windows | Use `$env:NAME="value"; python ...` (PowerShell), not `NAME=value python ...` |
| `port already in use` | A previous relay is still running; use `--port 8001` or stop the old one |

---

## 7. Day-of quick reference

```
# relay machine (keep running)
uvicorn relay_server:app --host 0.0.0.0 --port 8000

# student machines (replace <relay-ip> with the relay's LAN IP)
RELAY_URL="http://<relay-ip>:8000" python mode1_streamer.py     # Morning Lab A
python compare.py                                               # Morning measurement
RELAY_URL="http://<relay-ip>:8000" python mode2_edge.py         # Afternoon Lab B
RELAY_URL="http://127.0.0.1:9999"  python mode2_edge.py         # Afternoon network drop

# real camera (prepend)
SENSOR=webcam CAMERA_INDEX=0 ...
```

Key morning numbers: Mode 1 **~7.3 GB/day** vs Mode 2 **~10 MB/day** (about
**689×**); motion detection **12/12**, falls **2/2**.
Morning hands-on exercise: change `MOTION_LEVEL_THRESH` in `common.py` from
`0.006` to `0.05` — `compare.py`'s hit rate drops from 12/12 to 4/12.

---

## 8. Test sign-off

| Item | Pass | Notes |
|---|---|---|
| Environment install (§2) | ☐ | |
| File inventory (§3) | ☐ | |
| Test A — compare | ☐ | |
| Test B — relay health | ☐ | |
| Test C — Mode 1 | ☐ | |
| Test D — Mode 2 | ☐ | |
| Test D2 — store-and-forward | ☐ | |
| Test E — 401 | ☐ | |
| Test F — real camera | ☐ | note if skipped |
| Classroom relay dry run (§5) | ☐ | |

TA signature: ____________  Date: ____________

If anything gets stuck, check §6 first; if still unresolved, record the exact
command run plus the full error message and report back — it is usually one of
three things: network, port, or permissions.
