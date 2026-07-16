# Posture Detection — Test Guide (for TAs)

A short protocol to validate the new **posture signal** (standing / walking / lying /
absent) on a Jetson Nano with a USB webcam. This is groundwork for a future
**Mode 3** (abnormal-behaviour alarm); this guide only tests the posture *signal* in
isolation — no relay, no dashboard, no alarm yet.

**Time:** ~10 minutes with a Jetson + webcam. A no-camera smoke test takes 1 minute.

---

## 1. What this is

`posture.py` adds a posture estimate on top of the existing model-free motion
features. It is a **pluggable backend** (like the `SENSOR` switch):

- `POSTURE_BACKEND=bgsub` (default) — **model-free** OpenCV background subtraction
  (MOG2) + person bounding-box aspect ratio. **This is what we test here.**
- `POSTURE_BACKEND=trt` — TensorRT person detector (Jetson only) — **not built yet**
  (selecting it raises a clear "not implemented" error).

How posture is decided (bgsub):
| Bounding box | Motion | → Posture |
|---|---|---|
| wide / flat (aspect ≤ 0.8) | any | **lying** |
| tall-ish (aspect > 0.8) | high (≥ WALK_MOTION_THRESH) | **walking** |
| tall-ish | low | **standing** |
| no significant blob | — | **absent** |

`aspect = box height / box width`. It's model-free: no neural net, just OpenCV.

---

## 2. Files & prerequisites

Files needed (both live in the workshop package):
- `posture.py`
- `posture_selftest.py`
- (plus the existing `common.py`, `sensor.py`, `features.py`)

Dependencies: only what the workshop already needs — `cv2` and `numpy`
(both ship with JetPack). No extra install for posture.

---

## 3. Get the files onto the Jetson

From the **laptop** (adjust the IP/path to your setup):
```powershell
cd "path\to\edge-workshop-camera-en"
scp posture.py posture_selftest.py jetson@192.168.1.100:~/EDGE-CAMERA/
```
Verify on the Jetson:
```bash
ls ~/EDGE-CAMERA/posture*.py
```

---

## 4. Quick smoke test (no camera, optional)

Confirms the code imports and runs anywhere (uses the synthetic scene):
```bash
cd ~/EDGE-CAMERA
SENSOR=synthetic python3 posture_selftest.py
```
Expected: a table prints without errors. On the synthetic scene it tracks the moving
block as a small blob (usually labelled `standing`/`absent`) — this only proves the
code runs; **real posture testing needs the webcam (§5).**

---

## 5. Real test (Jetson + USB webcam)

```bash
cd ~/EDGE-CAMERA
SENSOR=webcam python3 posture_selftest.py
```
It prints one row per second for ~30 s. **Follow these steps in front of the camera:**

1. **Step OUT of frame for ~5 seconds.** Background subtraction must learn the empty
   scene first. During this warm-up you may see noisy `lying`/`absent` labels — ignore
   them.
2. **STAND still** in frame → expect **`standing`**.
3. **WALK / wave around** → expect **`walking`**.
4. **LIE DOWN** (or, if that's awkward, hold a wide object low in the frame, or crouch
   flat) → expect **`lying`**.
5. **Leave the frame** → expect **`absent`**.

Example of a good run:
```
sec   motion   fill   bbox(WxH)  aspect   posture
  0   0.0100  0.010          -     0.00    absent     (warm-up / empty)
  6   0.0500  0.180     70x150     2.14   standing
  7   0.1200  0.220     95x160     1.68   walking
  9   0.0400  0.160    180x60      0.33    lying
 12   0.0100  0.005          -     0.00    absent
```

---

## 6. Pass criteria

- [ ] Runs for ~30 s with **no errors / no traceback**.
- [ ] Standing still in frame reads **`standing`** (not `absent`).
- [ ] Walking / waving reads **`walking`**.
- [ ] Lying down (wide, low body) reads **`lying`**.
- [ ] Leaving the frame reads **`absent`**.

Getting `standing`/`walking`/`lying`/`absent` to switch correctly as you move is the
goal. Exact numbers don't matter; **the label transitions do.**

---

## 7. Tuning (only if labels are wrong)

All three knobs are constants at the top of `posture.py` — edit, re-`scp`, re-run:

| Symptom | Knob | Change |
|---|---|---|
| Lying down never reads `lying` | `LYING_ASPECT` (0.8) | raise toward `1.0` |
| Walking reads `standing` | `WALK_MOTION_THRESH` (0.02) | lower it |
| Standing reads `walking` (twitchy) | `WALK_MOTION_THRESH` | raise it |
| In-frame person reads `absent` | `MIN_FG_FRACTION` (0.02) | lower it |

Use the live `aspect` and `motion` columns to pick values: note the `aspect` while
lying vs standing, and set `LYING_ASPECT` between them.

---

## 8. Known limitations (expected, not bugs)

- **Static camera required.** Background subtraction assumes the camera doesn't move.
- **Warm-up needed.** The empty background must be learned first (step out ~5 s).
- **A person perfectly still for a long time fades into the background** and reads
  `absent`. This is inherent to background subtraction; a moving/breathing person is
  usually fine, and the future `trt` backend (person detector) will fix it.
- **Posture is inferred from box shape**, so extreme camera angles can fool it (a
  person far away or at a steep top-down angle). Aim the camera roughly at standing
  height, side-on.

---

## 9. What's NOT in this test yet

This validates only the posture *label*. Still to come once posture is reliable:
- **Behaviour monitor** — raise "abnormal behaviour" text when the sequence goes
  *upright → lying, held for N seconds*.
- **Mode 3 client** — upload `{posture, abnormal, reason}` to the relay.
- **Dashboard** — live posture + timeline + alarm banner on the PC.

Report back the `aspect`/`motion` values you see for standing vs walking vs lying —
those let us finalise the thresholds and the abnormal-behaviour rule.
