# Mode 3 — Test Guide (Edge Pose & Activity Monitor)

Mode 3 runs **deep-learning pose estimation on the Jetson** (MoveNet), classifies the
person's **activity** (standing / walking / sitting / lying), raises an **abnormal-
behaviour alarm** when someone was upright and is now lying on the ground, and shows
it all on a **live web dashboard on the PC**.

Only a tiny keypoint vector leaves the Jetson (Mode A) — the raw video stays on the
device, same edge-computing lesson as Mode 2. Mode B optionally also sends the image.

---

## 0. Topology

```
   Jetson (edge)                                     PC (server)
   ------------                                      -----------
   camera -> MoveNet pose -> activity + alarm  ==>   mode3_dashboard.py
   uploads keypoints (+image in Mode B)  HTTP/JSON   draws skeleton + box + alarm
                                                     open http://localhost:8090
```
The Jetson connects TO the PC, so the address you configure is the **PC's IP**.

---

## 1. Files

**Jetson (edge client)** — 6 `.py` files + the model:
```
mode3_edge.py   pose.py   sensor.py   features.py   common.py   codec.py
models/movenet_lightning.tflite
```
**PC (dashboard)** — 1 self-contained file (Python stdlib only, no install):
```
mode3_dashboard.py
```

---

## 2. Prerequisites (Jetson)

`cv2` and `numpy` come with JetPack. On top you need:
- `requests` (pip)
- a TFLite runtime for MoveNet — **either** `tflite_runtime` **or** full TensorFlow's
  `tf.lite` (`pose.py` auto-falls back to whichever is present).

```bash
python3 -c "import cv2, numpy, requests; print('base OK')"
# pose runtime -- one of these must work:
python3 -c "from tflite_runtime.interpreter import Interpreter; print('tflite_runtime OK')"  \
  || python3 -c "import tensorflow as tf; print('TF', tf.__version__, tf.lite.Interpreter)"
```
The **PC** needs nothing but Python 3.

> **JetPack-4 note:** the Coral `tflite_runtime` wheel needs GLIBC 2.29 and will fail to
> import on Ubuntu 18.04 (`GLIBC_2.29 not found`). That's fine — `pose.py` catches it
> and uses TensorFlow's `tf.lite` instead. If you have TF installed, ignore tflite.

---

## 3. Transfer the code

From a machine that has the files (adjust IP):
```powershell
# to the Jetson
scp mode3_edge.py pose.py sensor.py features.py common.py codec.py jetson@192.168.1.100:~/EDGE-CAMERA/
scp models/movenet_lightning.tflite jetson@192.168.1.100:~/EDGE-CAMERA/models/
# the dashboard to the PC: just copy mode3_dashboard.py
```
Do NOT copy any `venv/` folder — rebuild it per machine.

---

## 4. Preview the dashboard first (no Jetson needed)

Confirms the UI works before wiring up the camera:
```bash
python mode3_dashboard.py --mock       # on the PC
```
Open **http://localhost:8090** → you should see a stick figure cycle
standing → walking → lying, the box turn **red**, and a **"⚠ ABNORMAL BEHAVIOUR"**
banner on `lying`. Ctrl-C when done.

---

## 5. Run the real thing

**PC** — start the dashboard and open the firewall once (admin PowerShell):
```powershell
New-NetFirewallRule -DisplayName "Mode3 Dashboard 8090" -Direction Inbound -Protocol TCP -LocalPort 8090 -Action Allow
python mode3_dashboard.py               # open http://localhost:8090
```

**Jetson** — point it at the PC's IP:
```bash
cd ~/EDGE-CAMERA
# Mode A: keypoints only (~1 KB/frame, raw video stays on device)
SENSOR=webcam DASHBOARD_URL=http://<PC-IP>:8090/pose python3 mode3_edge.py

# Mode B: also send the JPEG so the dashboard shows the real frame (~15 KB/frame)
SENSOR=webcam MODE3_SEND_IMAGE=1 DASHBOARD_URL=http://<PC-IP>:8090/pose python3 mode3_edge.py
```
First start takes ~10–30 s while the pose runtime loads.

---

## 6. Test protocol (in front of the camera)

Do each and watch **both** the Jetson console (`posture=…`) and the dashboard:

| # | Action | Expected `posture` |
|---|---|---|
| 1 | Stand still | `standing` |
| 2 | Walk / move across the view | `walking` |
| 3 | Sit (chair or floor) | `sitting` |
| 4 | Lie down across the view | `lying` |
| 5 | Leave the frame | `absent` |
| 6 | **Fall test:** stand, then lie down and stay | after ~3 s → **`ABNORMAL`** |
| 7 | Get back up | alarm clears (`normal`) |

The dashboard shows the skeleton + box, the posture, the **Reason** (e.g.
`lying 2/3s` counting up, then `upright then lying 3s`), the **Mode** (A/B) and the
**Upload/frame** size. In Mode B, tick "Show camera image" to overlay the skeleton on
the real frame.

### Pass criteria
- [ ] Dashboard shows a live skeleton that follows you
- [ ] Standing / walking / sitting / lying label correctly (see framing note §9)
- [ ] Sitting + shuffling does **not** flip to `walking`
- [ ] Fall test raises `ABNORMAL` after ~3 s and clears when you get up
- [ ] Mode A upload ≈ ~1 KB; Mode B ≈ ~15 KB (bandwidth lesson visible)

---

## 7. How the alarm works (so it's not a black box)

Every second the system has one posture label. The alarm looks for a fall =
**"was up → now down → stays down"**:
1. When a **lying** episode begins, it records the time and whether the person was
   **upright** (standing/walking/sitting) within the last `UPRIGHT_LOOKBACK` s (10).
2. Once lying has held for **≥ `LYING_HOLD_S` s (3)** *and* the episode began from
   upright → **ALARM** (latched).
3. The alarm clears the moment they stop lying (got back up).

The live `Reason` field shows the state: `lying 1/3s` (building) → `upright then lying
3s` (fired). Brief lying (bending, sitting on the floor for a second) never alarms.

## 8. Tuning (environment variables — no code edits)

| Knob | Default | Effect |
|---|---|---|
| `LYING_HOLD_S` | 3 | seconds of lying before the alarm |
| `UPRIGHT_LOOKBACK` | 10 | how far back "was upright" is remembered |
| `UPRIGHT_MARGIN` | 0.03 | raise if upright is mislabeled `lying`; lower if lying is missed |
| `SIT_DROP_RATIO` | 0.6 | raise if `sitting` is missed; lower if standing reads `sitting` |
| `WALK_MOVE_THRESH` | 0.03 | raise if standing reads `walking`; lower if walking never registers |
| `SMOOTH_N` | 3 | majority-vote window; raise to 5 for more stability (more lag) |
| `KP_CONF` | 0.3 | min keypoint confidence to trust |

Example: `SMOOTH_N=5 SIT_DROP_RATIO=0.8 SENSOR=webcam DASHBOARD_URL=... python3 mode3_edge.py`

## 9. Camera framing — the biggest accuracy factor

- **Place the camera a few metres back so the FULL body is visible** (head to feet).
  Sitting/standing need the knees in view; lying needs the whole body.
- **Put the camera SIDE-ON** to where a fall happens, so the person lands **across**
  the view (head beside hips). A fall **toward/away** from the camera is foreshortened
  and no 2D method can read it as lying.
- Static camera, decent lighting.

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `MoveNet model not found` | model missing | copy `models/movenet_lightning.tflite` to `~/EDGE-CAMERA/models/` |
| `GLIBC_2.29 not found` on tflite import | Coral wheel too new for JetPack 4 | ignore — `pose.py` falls back to TF `tf.lite`; ensure TensorFlow is installed |
| `[dashboard unreachable]` on Jetson | wrong IP / firewall / dashboard down | check `DASHBOARD_URL` = PC IP; open TCP 8090; is `mode3_dashboard.py` running? |
| dashboard blank / no skeleton | client not sending / low confidence | check Jetson console prints `posture=`; improve lighting/framing |
| everything reads `absent` | person too small / low confidence | move closer / lower `KP_CONF` |
| standing → `walking` | movement threshold too low | raise `WALK_MOVE_THRESH` |
| sitting facing camera → `standing` | knees not seen / threshold | ensure lower body in view; raise `SIT_DROP_RATIO` |
| lying → `standing` | fall was toward/away from camera | reposition camera **side-on** (§9) |
| first run hangs ~30 s | TensorFlow loading on the Nano | normal; wait |

## 11. Known limits (state these in the demo)
- 2D single camera: a person falling **straight at/away** from the camera, or curled in
  a **tight ball facing** it, is ambiguous — reposition side-on.
- Activity is **rule-based on DL keypoints** (not a trained action model), so odd
  angles can misfire; tuning + framing handle most cases.
