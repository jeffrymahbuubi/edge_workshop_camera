# SPEC-04 — Mode 3: Posture & Fall Detection

> **Live document.** Tick as you build.

| | |
|---|---|
| **Status** | 🟡 Specified, not built |
| **Priority** | 🟢 Groundwork — after Modes 1+2 are solid on hardware |
| **Runs on** | The **Jetson** (posture *and* the fall rule) |
| **Depends on** | SPEC-01 (contract), SPEC-02 (relay) |
| **Related** | SPEC-05 (the `trt_pose` backend) |

**Provenance.** `posture.py`, `posture_selftest.py` and `POSTURE_TEST_GUIDE.md` are your
colleague's work, currently **untracked** in
`references/context/edge-workshop-camera-en/`. They implement the model-free `bgsub`
backend and deliberately wire up a `trt` backend that raises `NotImplementedError`
(`posture.py:95`). **Mode 3's ML half does not exist yet** — SPEC-05 designs it.

- [ ] Commit those three files (or move them into `src/edge/`) — untracked work is one
      `git clean` from gone.

---

## 1. The fall rule

Jeffry's definition:

> *walking, walking, walking → suddenly lying on the ground → lying* = **fall**

Formally: **an upright posture, followed by a transition to `lying`, held for N seconds.**

```
t-4  t-3  t-2  t-1   t    t+1  t+2  t+3
walk walk walk walk  LYING lying lying lying
                     └─ transition      └─ held N s → ABNORMAL: fall
```

### 1.1 What the rule needs

| # | Requirement | Difficulty |
|---|---|---|
| 1 | Reliable **upright** labels before | easy — motion is everywhere |
| 2 | Catch the **transition** | easy — a fall is full of motion |
| 3 | **`lying` persists** for N s | ⚠️ **this is the hard one** |

### 1.2 ⚠️ Why `bgsub` fails requirement 3

`POSTURE_TEST_GUIDE.md` §8 admits it: *"A person perfectly still for a long time fades
into the background and reads `absent`… the future `trt` backend will fix it."*

Now apply that to this rule. **A person who has fallen lies still.** `posture.py:52` sets
MOG2 `history=120`, and every frame is fed at 15 fps — so after roughly **8 seconds of
stillness the fallen person is learned into the background and reads `absent`, not
`lying`.**

**The confirmation step of the rule is exactly the state background subtraction erases.**
The person falls, then vanishes.

Not hopeless — with a short hold (N ≈ 2–3 s) it usually fires before the fade, and
breathing keeps some foreground alive. But you are **racing the background model**, and
tuning that race per room is precisely the fragility you do not want in front of
students. Hence SPEC-05.

- [ ] Default **N = 3 s** with `bgsub` (fires before the ~8 s fade).
- [ ] With `trt_pose`, N may be longer (5–10 s) and *more* reliable — no fade to race.
- [ ] Make N configurable: `FALL_HOLD_S` (env, default 3).

---

## 2. The behaviour monitor (`edge/behaviour.py`, new)

A small state machine. **Runs on the Jetson.**

```python
UPRIGHT = {"standing", "walking"}

# state: deque of recent postures + a lying-since timestamp
# every second:
#   if posture == "lying" and previous was UPRIGHT:  lying_since = now
#   if posture == "lying" and lying_since and now - lying_since >= FALL_HOLD_S:
#        → abnormal = True, reason = "upright→lying held {n}s"
#   if posture in UPRIGHT or posture == "absent":    lying_since = None
```

- [ ] Require an **upright posture within the last `UPRIGHT_LOOKBACK_S`** (default 10 s)
      before a `lying` can count as a fall. A person already lying when the camera starts
      is **not** a fall — without this, every demo boots into a false alarm.
- [ ] `absent` **cancels** the pending fall — do not treat it as continued lying. With
      `bgsub` that is the fade (§1.2), and inferring a fall from a fade is inferring it
      from a bug.
- [ ] Latch `abnormal` until posture returns to upright, so the dashboard banner does not
      flicker.
- [ ] Emit `reason` as human text — it goes straight to the caregiver panel.
- [ ] Keep the state machine **backend-agnostic**: it consumes `posture` labels only. It
      must work identically under `bgsub` and `trt_pose`. This is what lets SPEC-05 swap
      in with zero rework.

---

## 3. Posture backends

Contract in **SPEC-01 §5** (a superset: `bgsub` keeps the original 4 fields; pose
backends add `keypoints` + `torso_angle`).

| Backend | Status | Role |
|---|---|---|
| `bgsub` | ✅ works | **Development + fallback.** Build the whole pipeline on it |
| `trt_pose` | ❌ SPEC-05 | The real thing |

- [ ] Extend `posture.py`'s returns with `keypoints: None, torso_angle: None` for `bgsub`
      so the shape is uniform from day one. Downstream never branches on backend *name*.
- [ ] Keep `get_posture_estimator()` and the `POSTURE_BACKEND` env switch exactly as your
      colleague built them. **That switch is the demo**: same client, same rule, same
      dashboard — swap one env var and watch the fade disappear.

> **Why `bgsub` stays** even after `trt_pose` lands: it lets the client, rule, and
> dashboard be built and tested *before* any PyTorch exists on the Jetson, and it is the
> fallback if TensorRT misbehaves on the day. It is also a genuine teaching contrast.

---

## 4. `edge/mode3_posture.py` (new)

Mirrors `mode2_edge.py` — same shape, same store-and-forward discipline.

```python
sensor = get_sensor(SENSOR_KIND)
est    = get_posture_estimator()          # POSTURE_BACKEND
monitor = BehaviourMonitor()

while True:
    frames, audio, _ = sensor.read_second()
    motion = video_motion_features(frames)["motion_level"]
    for f in frames:                       # feed all frames: bgsub must learn
        result = est.estimate(f, motion)   # keep the last
    verdict = monitor.update(result["posture"])
    outbox.append({...})                   # SPEC-01 §4.3 payload
    flush(outbox)                          # buffer on network failure
```

- [ ] POST to **`/ingest_posture`**, payload per SPEC-01 §4.3.
- [ ] **Send only the verdict** — `{posture, abnormal, reason, torso_angle, confidence,
      backend}`. **Never keypoints, never frames.** Shipping skeletons to the laptop would
      repeat Mode 1's mistake in a new costume; Mode 3 must stay Mode 2's philosophy with
      a better brain.
- [ ] Reuse `mode2_edge.py`'s `outbox` store-and-forward so Mode 3 survives a cable pull.
- [ ] Print the same per-second terminal line as Mode 2 — terminal-first validation
      (`docs/01-design/06`) applies here too.
- [ ] Feed **every frame** to `est.estimate()` (not just one/second) or MOG2 never learns
      the background. `posture_selftest.py:52` already does this — copy the pattern.

---

## 5. Relay & dashboard

- [ ] `POST /ingest_posture` — auth + rate-limit like the others (SPEC-01 §4.1).
- [ ] Flag mapping: `abnormal → "FALL?"`, else map posture
      (`walking`/`standing` → `person-active`, `absent`/still → `quiet`).
- [ ] Fill the SSE event's `posture` field (SPEC-02 §5 reserved it as `null`).
- [ ] Dashboard posture panel: current label, `torso_angle` when present, and an alarm
      banner on `abnormal` showing `reason`.
- [ ] Video panel in Mode 3: **`/latest.jpg` → 404**, same as Mode 2. Mode 3 sends no
      frames, so the privacy lesson holds — and now with ML on the edge, which is the
      strongest version of the argument.

---

## 6. Validation

Follow `POSTURE_TEST_GUIDE.md` §5 — your colleague already wrote the protocol.

- [ ] **Smoke (no camera):** `SENSOR=synthetic python3 posture_selftest.py` → table
      prints, no traceback. Proves imports only.
- [ ] **Real (Jetson + webcam):** `SENSOR=webcam python3 posture_selftest.py`
      - [ ] Step out ~5 s (background warm-up; ignore noisy labels)
      - [ ] Stand → `standing`
      - [ ] Walk/wave → `walking`
      - [ ] Lie down → `lying`
      - [ ] Leave → `absent`
- [ ] **Record `aspect` and `motion` for standing vs walking vs lying** — your colleague
      explicitly asked for these numbers to finalise thresholds. Report them back.
- [ ] **The fade test (new, and the important one):** lie down and **stay still for 15 s**.
      Watch for `lying → absent`. Time it. **This measures §1.2 on real hardware and sets
      the ceiling on `FALL_HOLD_S`.**
- [ ] **Rule test:** walk, then lie down → `abnormal` within `FALL_HOLD_S`.
- [ ] **False-alarm test:** start already lying → must **not** fire (§2 lookback).

---

## 7. Tuning knobs

From `POSTURE_TEST_GUIDE.md` §7, all constants at the top of `posture.py`:

| Symptom | Knob | Change |
|---|---|---|
| Lying never reads `lying` | `LYING_ASPECT` (0.8) | raise toward 1.0 |
| Walking reads `standing` | `WALK_MOTION_THRESH` (0.02) | lower |
| Standing reads `walking` | `WALK_MOTION_THRESH` | raise |
| In-frame person reads `absent` | `MIN_FG_FRACTION` (0.02) | lower |
| Fall fires late / never | `FALL_HOLD_S` (3) | lower — but see §1.2 |

---

## 8. Known limitations (inherited, expected)

From `POSTURE_TEST_GUIDE.md` §8 — **all four are `bgsub` limitations that SPEC-05 fixes**:

- **Static camera required.**
- **Warm-up needed** — the empty background must be learned first.
- **A still person fades to `absent`** — §1.2, the one that matters for the fall rule.
- **Posture inferred from box shape** — steep or head-on camera angles fool it.

---

## 9. Open

- [ ] Measure the real fade time (§6) before fixing `FALL_HOLD_S`.
- [ ] Does Mode 3 replace Mode 2 in the demo flow, or run as a fourth position after it?
- [ ] Mode 3 has no audio dependency — worth noting it works even though `sounddevice` is
      absent (SPEC-02 §9), which may make it the *only* mode that can fire a fall until
      that is resolved.
