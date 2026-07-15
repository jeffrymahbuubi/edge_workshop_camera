# 01 — Project Overview

## What this is (and is not)

- **It is**: a **6-hour instructional workshop** — a curriculum plus a small,
  runnable reference codebase. The deliverable is *teaching*, not a product.
- **It is not**: a production monitoring system, and not (today) a machine-learning
  project. The detection is deliberately model-free.

The package is titled **"Edge Sensing & Cloud Processing (Camera + Audio
Edition)."** Original source: `references/context/edge-workshop-camera-en/`
(11 files: 9 Python + `requirements.txt` + the handout). Two companion docs ship
with it: `Handout_Edge_Sensing_Camera_Audio.md` (for the instructor) and
`TA_Test_Manual.md` (for the teaching assistant).

## The one core idea

> **Between the sensor and the cloud, where should you draw the
> compute-partitioning line?**

Everything in the workshop serves this single question. The teaching method is:
take the *same* audio/video, process it two different ways, **measure** the
difference, and make students *argue* for a partitioning decision.

## The two modes (the two ends of the axis)

| | **Mode 1 — dumb streamer** | **Mode 2 — edge processing** |
|---|---|---|
| File | `mode1_streamer.py` | `mode2_edge.py` |
| Edge (device) does | Nothing but capture + forward | Motion + audio feature extraction |
| What leaves the device | **Raw** JPEG frames + audio (faces, voices) | Only a tiny **feature vector** (labels/numbers) |
| Cloud (relay) does | **Everything** — decode + detect | Just interprets/enriches the labels |
| Bandwidth (measured) | **~7.3 GB/day** | **~10 MB/day** |
| Ratio | — | **~689× less data** in Mode 2 |
| Privacy | Identifiable data leaves the room | De-identified at the edge; faces/voices stay local |
| Network drop | Data is **lost** (no buffer) | **Store-and-forward** buffer; data preserved |

Mode 1 draws the line closest to the sensor (pure forwarding). Mode 2 pushes it
toward the cloud (compute first at the edge). The whole course is about deciding
where that line belongs — and the honest answer in the handout is often a
**hybrid**: normally send features only, upload raw *only* for anomalous segments
(e.g. a suspected fall).

## The application domain

The running example is **home / elderly fall detection** — e.g. *"an elderly
person living alone, unstable home Wi-Fi, privacy-conscious family."* This is why
bandwidth and privacy are dramatized so heavily: streaming a camera+mic from
someone's home is exactly where cost, Wi-Fi limits, and privacy/IRB concerns
collide.

## What "detection" means here (deliberately model-free)

No neural networks, no TensorRT, no model downloads. Just:

- **Motion** — OpenCV frame differencing: how large a fraction of pixels changed
  between consecutive frames.
- **Audio** — RMS energy: is this second "loud" (a possible impact/speech)?
- **Fusion** — a crude fall signature: **a loud sound *and* motion that was
  happening but just stopped.** Neither signal alone is enough (sitting down is
  motion stopping without a bang; a slammed door is a bang without motion
  stopping) — it takes both together.

This is intentional. A key teaching point is the **fragility of model-free
detection**: the whole thing rides on hand-tuned thresholds, and a change of
lighting or camera can throw it off. (Demo: raising `MOTION_LEVEL_THRESH` from
`0.006` to `0.05` drops detection accuracy from 12/12 to 4/12.)

## Runs with no hardware (important design choice)

By default the pipeline runs on a **synthetic scene** — a colored block that
moves for 4 s, stops for 2 s, and emits a short loud burst each time it stops.
That known pattern is the **ground truth**: motion should fire while it moves and
go quiet when it stops; stop + burst = a checkable "fall." This means:

- The whole workshop works on **any laptop with no webcam and no microphone**.
- A real USB webcam + mic is a **one-env-var swap** (`SENSOR=webcam`), fully
  implemented and ready — no code changes.
- If the camera or mic fails on the day, the class is **never blocked**.

## Key non-detection concepts the workshop also teaches

- **Key security**: the real cloud API key lives **only on the relay**; each
  device carries a **revocable device token**. A stolen device can be cut off
  (set its token `active=False`) without touching the account. Live "revocation"
  demo included.
- **Network resilience**: Mode 2's store-and-forward buffer vs Mode 1's data
  loss when the network drops — a required lesson in *failure modes*.
- **Irreversibility**: Mode 2 fixes the feature set at collection time; if you
  later want a new feature (gait, expression) the raw is gone — motivating the
  hybrid design.
- **Optional LLM enrichment**: on a real fall event *only*, the relay can call an
  LLM (if `ANTHROPIC_API_KEY` is set **on the relay**) to write a one-sentence
  caregiver note. Purely optional; everything works without it.

## Honest gaps the workshop names but does NOT solve

The handout is explicit that these are out of today's scope (listed here so the
Jetson-side reader knows the boundary of the current code):

- Real person / object / pose detection (would need YOLO / MediaPipe + TensorRT).
- Audio *classification* (speech vs cough vs door vs impact) — today it's energy only.
- Environmental robustness of thresholds (the fragility is shown, not fixed).
- Audio-video time synchronization.
- Cost/power quantification, full protocol choice (RTSP/WebRTC/MQTT),
  containerization/reproducibility.

> These gaps matter for the Jetson goal because several of them (H.264 hardware
> encode, real detection models) are exactly what Jetson hardware is good at — but
> per the project's chosen scope they remain **future direction, not current
> work.** See `03-ultimate-goal-jetson.md`.
