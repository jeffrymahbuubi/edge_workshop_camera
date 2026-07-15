# Edge Sensing Workshop (Camera + Audio) — Package Overview

Use a laptop + USB webcam as a sensing node: do preliminary feature extraction,
then upload to a cloud API for processing. This package teaches students to
reason about *where to draw the compute-partitioning line*: Mode 1 streams raw
video+audio and the cloud does everything; Mode 2 extracts features at the edge
and uploads only the results.

**Everything runs by default on a synthetic scene, so the whole pipeline works
on a single laptop with no webcam.**

## Which document to read first

- **Teaching assistant** → read `TA_Test_Manual.md` first. Follow it to test the
  environment and code on your machine and to prepare the classroom deployment.
- **Instructor** → `Handout_Edge_Sensing_Camera_Audio.md`, with the full
  morning/afternoon (3h + 3h) schedule, per-segment guidance, assignment, and rubric.

## 30-second smoke test (no hardware)

```bash
pip install -r requirements.txt
python compare.py          # expect ~689x bandwidth gap, motion 12/12, falls 2/2
```

## Files

| File | Purpose |
|---|---|
| `TA_Test_Manual.md` | For the TA: test protocol, classroom deployment, sign-off sheet |
| `Handout_Edge_Sensing_Camera_Audio.md` | For teaching: full workshop handout |
| `common.py` | Shared config (relay URL, token, resolution, thresholds; `SENSOR`/`CAMERA_INDEX`) |
| `codec.py` | Base64 codec for JPEG frames / int16 audio |
| `sensor.py` | Sensor layer: synthetic scene (default) + real webcam + mic |
| `features.py` | Model-free feature extraction: motion + audio energy + fusion |
| `relay_server.py` | Cloud relay server (FastAPI): holds key, validates token, rate-limits |
| `mode1_streamer.py` | Mode 1: raw video+audio streamer |
| `mode2_edge.py` | Mode 2: edge feature extraction + store-and-forward |
| `compare.py` | Offline bandwidth comparison + detection validation |
| `webcam_selftest.py` | Real webcam/mic self-test (wave / clap) |
| `requirements.txt` | Dependencies |

## Real webcam (physical laptop)

```bash
pip install opencv-python sounddevice
python webcam_selftest.py                 # wave to see motion, clap to see loud
SENSOR=webcam python mode1_streamer.py     # use the real camera; nothing else changes
```

If no microphone is available, it falls back to video-only with silent audio, so
the workshop is never blocked. See the two documents for details.
