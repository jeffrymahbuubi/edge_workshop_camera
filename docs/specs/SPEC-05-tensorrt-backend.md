# SPEC-05 — TensorRT Posture Backend (`trt_pose`)

> **Live document.** This spec **designs code that does not exist yet.** `posture.py`'s
> `TrtPosture` is a placeholder that raises `NotImplementedError` (`posture.py:95`).

| | |
|---|---|
| **Status** | 🟡 Specified, not built. **Nothing installed yet.** |
| **Priority** | 🟢 After SPEC-04's pipeline works on `bgsub` — **now backed by measured evidence (below), not just theory** |
| **Runs on** | The **Jetson** |
| **Depends on** | SPEC-01 (§5 contract), SPEC-04 (the rule this feeds) |

> **Measured on hardware 2026-07-16 — the case for this spec is no longer hypothetical.**
> A first bench pass of `bgsub` Mode 3 (SPEC-04 §6) showed **`lying` never held more than
> ~2 seconds** before MOG2 faded the still person to `absent`, while the fall rule needs it
> held 3 s and treats `absent` as a cancel. In other words **the `bgsub` fall barely fires
> on a real person**, and `standing` was almost never produced at all (a still upright
> person fades before it can be labelled). The fade §1.2 predicted was not only real, it was
> *faster* than estimated. This is the concrete failure `trt_pose` exists to fix: pose /
> torso-angle does not fade, because it does not depend on a moving-foreground model. Get a
> clean controlled fade number when possible, but the direction already justifies building
> this. **Blocker for starting: the ~81 MB stack is deliberately not installed (disk 88%).**

---

## 1. Why `trt_pose` and not `ssd-mobilenet-v2`

They are **different kinds of model**, and the difference decides how good the fall rule
can be.

| | `ssd-mobilenet-v2` | **`trt_pose`** |
|---|---|---|
| Type | object **detection** | **pose estimation** |
| Returns | a person bounding box | **18 keypoints** + skeleton |
| Posture from | box **aspect ratio** | **torso angle** (neck→hip) |
| vs `bgsub` | same crude rule, better person-finding | **genuinely different algorithm** |
| Fixes the fade (SPEC-04 §1.2) | ✅ | ✅ |
| Fixes camera-angle fragility | ❌ | ✅ |

`ssd` would fix *finding* the person but keep `bgsub`'s aspect-ratio posture rule — so
students would see the same labels computed the same way. **The teaching story collapses.**
`trt_pose` earns the mode: *the GPU buys you a skeleton, and a skeleton knows lying from
standing.*

Both need a pre-baked model on the offline LAN, so `ssd` is not meaningfully cheaper to
deploy. **The real extra cost of `trt_pose` is disk, not complexity** — and per §2, its
biggest dependency is already paid for.

Source: `references/nvidia-jetson/trt_pose` (NVIDIA-AI-IOT, official).

---

## 2. Environment — verified, not assumed

Probed live on `jetson-2gNANO`, **2026-07-16**. **This is much better than expected.**

| Dependency | State |
|---|---|
| **PyTorch** | ✅ **1.11.0a0 installed**, `torch.cuda.is_available() == True`, `NVIDIA Tegra X1` |
| **torchvision** | ✅ 0.12.0a0 |
| **TensorRT** | ✅ 8.2.1.8 |
| `python3` | ✅ 3.8.0 |
| `cv2` / `numpy` | ✅ 4.11.0 / 1.23.5 |
| **`torch2trt`** | ❌ **missing** — must install |
| **`trt_pose`** | ❌ **missing** — must install |
| **weights** | ❌ **missing** — 81 MB, see §4 |
| **Disk** | ⚠️ **5.2 GB free of 44 GB (88% used)** |

> **The heavy lift is already done.** PyTorch on a Nano is normally the painful part
> (~2–3 GB, NVIDIA-specific wheels) and it is **already installed and CUDA-enabled**.
> What remains is small: `torch2trt` and `trt_pose` are thin Python packages, plus 81 MB
> of weights.

- [ ] **Measure disk before and after.** 5.2 GB should be ample, but 88% is not a number
      to be casual about. `df -h /` at each step; if free drops below ~2 GB, stop.

---

## 3. Model choice

| Model | Nano FPS | Weights | Verdict |
|---|---|---|---|
| **`resnet18_baseline_att_224x224_A`** | **22** | 81 MB | ✅ **use this** |
| `densenet121_baseline_att_256x256_B` | 12 | 84 MB | ❌ too slow, no benefit here |

FPS figures are NVIDIA's own, from `references/nvidia-jetson/trt_pose/README.md:52`.

- [ ] Pin **`resnet18_baseline_att_224x224_A`**.
- [ ] 22 FPS is **far more headroom than needed** — the pipeline's cadence is **one
      second per tick** (`SECONDS_PER_TICK = 1.0`). Even a few frames per second suffices.
- [ ] Therefore: **do not run inference on all 15 frames/s.** Sample ~2–3 frames per
      second for posture. Unlike `bgsub`, `trt_pose` has no background model to feed, so
      there is no reason to burn GPU on every frame. *(This is a real divergence from
      SPEC-04 §4's "feed every frame" loop — that requirement is `bgsub`-specific.)*

---

## 4. ⚠️ The offline problem — both halves

The workshop LAN is **a cable between two machines with no internet**. Two separate
things try to reach the network and will fail on the day:

### 4.1 The weights (81 MB, Google Drive)

`trt_pose`'s README links weights on **Google Drive** — unreachable on the workshop LAN,
and awkward to script even *with* internet (Drive's confirm-token dance).

- [ ] Download **once, on the laptop**, while online.
- [ ] Commit? **No** — 81 MB of binary. Instead: bake into the SD image (§6) and record
      the URL + SHA256 in this spec.
- [ ] Record the checksum here once known: `SHA256: ______`

### 4.2 The TensorRT engine (the subtle one)

`torch2trt` **builds the `.engine` at first run** — minutes of optimisation on a Nano.
This is not a download, so it is easy to miss when planning for "offline".

- [ ] **Pre-build the engine and save it** (`torch2trt`'s `state_dict` → `.pth`), so
      first run on a student board *loads* rather than *builds*.
- [ ] An engine is **specific to the TensorRT version and the GPU**. Built on this Nano
      with TRT 8.2.1.8, it is valid for cloned student Nanos — and **worthless anywhere
      else**. Build it on the golden image, not on your laptop.
- [ ] If the engine is missing at runtime, **fall back to `bgsub` with a loud warning**
      rather than blocking a student for 5 minutes of engine build.

---

## 5. Implementation — `TrtPosture`

Replaces the stub at `posture.py:86`. Must satisfy **SPEC-01 §5**.

```python
class TrtPosture:
    def __init__(self):
        # 1. load topology from human_pose.json (18 keypoints, 21 skeleton links)
        # 2. build/load the trt model (prefer the pre-built engine, §4.2)
        # 3. ParseObjects(topology)

    def estimate(self, frame, motion_level=0.0):
        # 1. resize to 224x224, normalise, → CUDA tensor
        # 2. infer → cmap, paf
        # 3. ParseObjects → counts, objects, peaks
        # 4. no person → {"posture": "absent", ...all None}
        # 5. take the highest-confidence person
        # 6. torso_angle = angle(neck → hip_midpoint, vertical)
        # 7. posture from torso_angle + motion_level  (§5.1)
        # 8. bbox = extents(visible keypoints); aspect = h/w; fill = bbox area / frame
```

### 5.1 Posture from torso angle

```
torso_angle = angle between (neck → hip midpoint) and vertical, degrees

  < 30°            → upright  → walking if motion_level >= WALK_MOTION_THRESH
                              → else standing
  > 60°            → lying
  30°..60°         → ambiguous: hold the previous label (hysteresis)
  no person        → absent
```

- [ ] **Hysteresis in the 30–60° band is required.** Without it the label flaps mid-fall
      and the state machine (SPEC-04 §2) sees garbage exactly when it matters most.
- [ ] Keypoint indices from `tasks/human_pose/human_pose.json`: `neck` (18),
      `left_hip` (12), `right_hip` (13). **1-indexed in the JSON** — off-by-one here is
      silent and produces plausible-but-wrong angles.
- [ ] Use the **hip midpoint**, not one hip — a single hip is often occluded.
- [ ] If `neck` or both hips are missing/low-confidence, **fall back to bbox aspect**
      rather than returning garbage, and lower `confidence`.
- [ ] Still populate `bbox`/`aspect`/`fill` (SPEC-01 §5) so the dashboard and any
      bbox-based logic keep working across a backend switch.

### 5.2 Thresholds

New constants at the top of `posture.py`, alongside your colleague's existing three:

```python
TORSO_UPRIGHT_DEG = 30    # below this = upright
TORSO_LYING_DEG   = 60    # above this = lying
MIN_KEYPOINT_CONF = 0.3   # ignore keypoints below this
```

---

## 6. SD image / pre-clone steps

⚠️ **Two pre-clone steps are already outstanding** on this board (see
[`docs/02-hardware/09`](../02-hardware/09-internet-sharing-setup.md) and the project
memory). **This spec adds more.** Consolidate before cloning:

| # | Step | Source |
|---|---|---|
| 1 | `sudo rm -f /var/lib/dhcp/dhclient*.leases` | doc 09 — stale macOS leases install a dead gateway |
| 2 | Remove the `eth0:1` stanza from `/etc/network/interfaces` | doc 09 — dev lifeline, must not ship |
| 3 | ⚠️ **Persist the PulseAudio default source → the USB webcam mic** | **SPEC-02 §9.3 — `pactl set-default-source` is runtime-only. Without this every student board boots with a SILENT mic and falls can never fire in Modes 1/2 — silently.** |
| 4 | `sounddevice` + `libportaudio2` installed | SPEC-02 §9.3 *(done on the dev unit)* |
| 5 | Install `torch2trt` + `trt_pose` | this spec §2 |
| 6 | Place weights at `~/EDGE-CAMERA/` | §4.1 |
| 7 | **Pre-build + save the TRT engine** | §4.2 |
| 8 | Deploy `src/edge/` + `src/common/` | SPEC-01 §3 |
| 9 | Verify `python3` → 3.8 survives the clone | SPEC-01 §2 |
| 10 | Check free disk after all of it | §2 |

- [ ] Steps 1 and 2 are **deliberately kept on the dev unit** — `eth0:1` is the lifeline
      for reaching the Jetson when sharing is off. Do them **only** at clone time.

---

## 7. Validation

- [ ] `python3 -c "import torch2trt; print('ok')"`
- [ ] `python3 -c "import trt_pose; print('ok')"`
- [ ] Engine builds (time it) and **saves**; second run **loads** in < 5 s.
- [ ] `POSTURE_BACKEND=trt SENSOR=webcam python3 posture_selftest.py` — the full
      `POSTURE_TEST_GUIDE.md` §5 protocol: stand → walk → lie → leave.
- [ ] **The fade test — the one that justifies this whole spec.** Lie still for 30 s.
      `bgsub` reads `absent` after ~8 s; **`trt_pose` must still read `lying`.** Run both
      backends back-to-back and record the difference. *This is the before/after that
      proves Mode 3 earns its cost.*
- [ ] **Camera-angle test:** lie with feet toward the camera. `bgsub`/`ssd` read
      `standing` (tall box); `trt_pose` should read `lying`.
- [ ] Measure real FPS and RAM. Compare against NVIDIA's claimed 22 FPS.
- [ ] `df -h /` after install — record the cost.
- [ ] Backend switch works with **zero other changes**: `POSTURE_BACKEND=bgsub` vs `trt`.

---

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Disk at 88%** | ⚠️ high | Measure at each step; reclaim before installing |
| Engine build blocks a student | medium | Pre-build (§4.2); fall back to `bgsub` |
| Weights unreachable on the day | medium | Bake into the image (§6); never fetch live |
| torch2trt build fails on py3.8 | medium | `bgsub` fallback keeps Mode 3 demoable |
| Nano thermal throttle under load | low | 22 FPS claimed vs ~2–3 needed — huge margin |
| Engine invalid after a JetPack change | low | Rebuild on the golden image; never ship a laptop-built engine |

---

## 9. Open

- [ ] Record the weights SHA256 (§4.1).
- [ ] Measure engine build time on this Nano.
- [ ] Confirm `torch2trt` installs cleanly against torch 1.11.0a0 / py3.8 — it is the one
      untested link in an otherwise verified chain.
- [ ] Decide whether `trt_pose` is installed system-wide or into a venv. A venv is
      cleaner but must see the **system** torch/cv2 (`--system-site-packages`), which are
      NVIDIA builds and **cannot be pip-installed**.
