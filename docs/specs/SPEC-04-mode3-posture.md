# SPEC-04 — Mode 3: Posture & Fall Detection

> **Live document.** Tick as you build.

| | |
|---|---|
| **Status** | 🟢 **Code built + laptop-validated + RUNS ON THE JETSON (2026-07-16)** — deployed and executed on the board (3.8, real webcam → relay, wire payload correct). ⚠️ §6's *posture-threshold* protocol still outstanding: whether bgsub reports `lying` on a real person, the aspect/motion numbers, and the fade time are unmeasured (needs a body in frame). |
| **Priority** | 🟢 Groundwork — after Modes 1+2 are solid on hardware |
| **Runs on** | The **Jetson** (posture *and* the fall rule) |
| **Depends on** | SPEC-01 (contract), SPEC-02 (relay) |
| **Related** | SPEC-05 (the `trt_pose` backend) |

**Provenance.** `posture.py`, `posture_selftest.py` and `POSTURE_TEST_GUIDE.md` are your
colleague's work. They implement the model-free `bgsub`
backend and deliberately wire up a `trt` backend that raises `NotImplementedError`.
**Mode 3's ML half does not exist yet** — SPEC-05 designs it.

- [x] `posture.py` + `posture_selftest.py` — moved into `src/edge/` and tracked.
- [ ] `POSTURE_TEST_GUIDE.md` — **still untracked** in
      `references/context/edge-workshop-camera-en/`, still one `git clean` from gone.
      Note its §4–5 are **stale**: they say `python3 posture_selftest.py`, which now
      fails with `ModuleNotFoundError: common`. Run as a module from `src/`:
      `python3 -m edge.posture_selftest`.

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

- [x] Default **N = 3 s** with `bgsub` (fires before the ~8 s fade). → `config.FALL_HOLD_S`
- [ ] With `trt_pose`, N may be longer (5–10 s) and *more* reliable — no fade to race.
- [x] Make N configurable: `FALL_HOLD_S` (env, default 3).

> **The ~8 s fade is still a CALCULATION, not a measurement** (history=120 @ 15 fps).
> §6's fade test is what turns it into a number, and until then N=3 is a guess with
> arithmetic behind it. It is the one bench result that could invalidate this default.

---

## 2. The behaviour monitor (`edge/behaviour.py`, new)

> ✅ **Built.** `src/edge/behaviour.py`. Every rule below is pinned by
> `tests/test_behaviour.py` (21 tests). `update(posture, now=None)` takes an
> **injectable clock** — a real-clock suite would burn 3 s per case and would be
> measuring `time.sleep`, not the rule.

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

- [x] Require an **upright posture within the last `UPRIGHT_LOOKBACK_S`** (default 10 s)
      before a `lying` can count as a fall. A person already lying when the camera starts
      is **not** a fall — without this, every demo boots into a false alarm.
- [x] `absent` **cancels** the pending fall — do not treat it as continued lying. With
      `bgsub` that is the fade (§1.2), and inferring a fall from a fade is inferring it
      from a bug.
- [x] Latch `abnormal` until posture returns to upright, so the dashboard banner does not
      flicker. *(`absent` does **not** release the latch — a fallen person fading out must
      not clear the alarm the fade's own state confirmed.)*
- [x] Emit `reason` as human text — it goes straight to the caregiver panel.
      **Frozen at the moment it fires**, so the banner does not churn `3s, 4s, 5s…`.
- [x] Keep the state machine **backend-agnostic**: it consumes `posture` labels only. It
      must work identically under `bgsub` and `trt_pose`. This is what lets SPEC-05 swap
      in with zero rework. *(If `behaviour.py` ever imports `cv2`, that has been broken.)*
- [x] Unknown labels are **inert, not crashes** — a backend inventing a label should
      degrade, not take the Jetson down mid-demo.

---

## 3. Posture backends

Contract in **SPEC-01 §5** (a superset: `bgsub` keeps the original 4 fields; pose
backends add `keypoints` + `torso_angle`).

| Backend | Status | Role |
|---|---|---|
| `bgsub` | ✅ works | **Development + fallback.** Build the whole pipeline on it |
| `trt_pose` | ❌ SPEC-05 | The real thing |

- [x] Extend `posture.py`'s returns with `keypoints: None, torso_angle: None` for `bgsub`
      so the shape is uniform from day one. Downstream never branches on backend *name*.
      *(All **three** returns, including both early `absent` exits — the one that fires
      before any contour exists would otherwise `KeyError` only on an empty room.)*
- [x] Keep `get_posture_estimator()` and the `POSTURE_BACKEND` env switch exactly as your
      colleague built them. **That switch is the demo**: same client, same rule, same
      dashboard — swap one env var and watch the fade disappear.
      *(Untouched. `tests/test_posture_contract.py` pins that `trt` still raises
      `NotImplementedError` — a silent fallback to `bgsub` would make the workshop's
      central contrast a lie.)*

> **Why `bgsub` stays** even after `trt_pose` lands: it lets the client, rule, and
> dashboard be built and tested *before* any PyTorch exists on the Jetson, and it is the
> fallback if TensorRT misbehaves on the day. It is also a genuine teaching contrast.

---

## 4. `edge/mode3_posture.py` (new)

> ✅ **Built.** `src/edge/mode3_posture.py`. Wire format pinned by
> `tests/test_mode3_payload.py`.

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

- [x] POST to **`/ingest_posture`**, payload per SPEC-01 §4.3.
- [x] **Send only the verdict** — `{posture, abnormal, reason, torso_angle, confidence,
      backend}`. **Never keypoints, never frames.** Shipping skeletons to the laptop would
      repeat Mode 1's mistake in a new costume; Mode 3 must stay Mode 2's philosophy with
      a better brain.

      > `_payload()` lists the wire fields **by hand** rather than splatting the
      > estimator's dict. The splat is the obvious shortcut and it is a trap: the
      > estimator carries `bbox`/`fill` today and 18 **keypoints** once SPEC-05 lands, so
      > a splat would quietly put a skeleton of the person on the LAN. **That leak is
      > invisible at the bench** — the dashboard renders identically either way, and
      > nothing else in the system would notice. It is also invisible *today*, because
      > `bgsub` has no keypoints to leak; it would first go wrong the day trt_pose
      > arrives. `test_pose_backend_keypoints_never_travel` feeds a fake pose result
      > through and asserts the string `keypoints` never appears in the JSON.
- [x] Reuse `mode2_edge.py`'s `outbox` store-and-forward so Mode 3 survives a cable pull.
      *(Mode 3 is the mode a caregiver would rely on: a cable pull must **delay** the fall
      alarm, not delete it.)*
- [x] Print the same per-second terminal line as Mode 2 — terminal-first validation
      (`docs/01-design/06`) applies here too.
- [x] Feed **every frame** to `est.estimate()` (not just one/second) or MOG2 never learns
      the background. `posture_selftest.py:52` already does this — copy the pattern.

---

## 5. Relay & dashboard

> ✅ **This section was already built before SPEC-04's client existed** — SPEC-02 built the
> endpoint and SPEC-03 the panel, both ahead of the client that feeds them. Nothing here
> needed writing; it needed **verifying**, which is what the ticks below record.
> All confirmed in a real browser (playwright-cli) against a live Mode 3 client, 2026-07-16.

- [x] `POST /ingest_posture` — auth + rate-limit like the others (SPEC-01 §4.1).
      *(SPEC-02, `relay_server.py:229`.)*
- [x] Flag mapping: `abnormal → "FALL?"`, else map posture
      (`walking`/`standing` → `person-active`, `absent`/still → `quiet`).
      *(Observed live: `absent`→`quiet`, `standing`→`person-active`, injected fall→`FALL?`.)*
- [x] Fill the SSE event's `posture` field (SPEC-02 §5 reserved it as `null`).
- [x] Dashboard posture panel: current label, `torso_angle` when present, and an alarm
      banner on `abnormal` showing `reason`. *(`app.js:57,64`. Rendered live: banner read
      **"upright→lying held 3s"**, posture read **"lying (78°)"** — so the pose-backend
      `torso_angle` path already renders and SPEC-05 needs no dashboard work.)*
- [x] Video panel in Mode 3: **`/latest.jpg` → 404**, same as Mode 2. Mode 3 sends no
      frames, so the privacy lesson holds — and now with ML on the edge, which is the
      strongest version of the argument. *(Verified: 404, panel read "Mode 3 sent no
      image — only a posture verdict". Mode 3 row un-dimmed at **86 B/s** vs Mode 1's
      ~78 KB/s.)*

> **Mode 3's motion/audio bars read `—`.** Correct, not a bug: Mode 3 sends a posture
> verdict and no feature vector, so the status panel's motion/audio/blobs have nothing to
> show. Worth knowing before someone reports it at the bench.

---

## 6. Validation

Follow `POSTURE_TEST_GUIDE.md` §5 — your colleague already wrote the protocol.

### Done on the laptop — 2026-07-16 (TDD)

**39 tests, all passing.** From the repo root:

```bash
uv run --with pytest --with opencv-python-headless --with numpy --with requests \
  python -m pytest tests/ -q
```

`tests/` is the repo's first test directory; `tests/conftest.py` puts `src/` on the path
so tests import `edge`/`common` exactly the way the Jetson does (`python3 -m edge.x`).

- [x] `tests/test_behaviour.py` (21) — the fall rule: fires on walk→lying held; does
      **not** fire when already lying at startup; `absent` cancels a pending fall and
      restarts the hold; latch releases only on upright; `reason` frozen at fire.
- [x] `tests/test_posture_contract.py` (9) — SPEC-01 §5 shape on all three returns; pose
      fields `None` under `bgsub`; `trt` still raises; backend switch intact.
- [x] `tests/test_mode3_payload.py` (9) — SPEC-01 §4.3 wire format; **keypoints never
      travel**, even from a pose backend that has them.
- [x] **End-to-end, synthetic sensor → live relay:** client posts real verdicts, relay
      maps flags, `/latest.jpg` 404s, dashboard renders (see §5).

> **What the unit tests do NOT prove.** They pin the *rule*, never the *labels*. Whether
> `bgsub` actually reports `lying` when a person lies down in **your** room is a threshold
> question only the bench can answer. Green tests here + a wrong `LYING_ASPECT` = a rule
> that is perfectly correct about a posture it never detects.
>
> These two are worth the test file on their own: *"start already lying → must not fire"*
> and *"absent cancels"* are **absences of an event**. At the bench you watch nothing
> happen for a few seconds and call it a pass — which is also exactly what a broken rule
> looks like when the camera is pointed at a wall.

### Done on the Jetson — 2026-07-16 (import / runtime / wire path)

Deployed the four files to `~/EDGE-CAMERA/` and ran on the board (`plink`, Python **3.8.0**,
`L4T R32.7.4`). This closes the *"does it run on the target at all"* half of the gate; the
posture-threshold half below still needs a body in frame.

- [x] **Imports + rule execute on 3.8** — `behaviour.py` and `mode3_posture.py` (real
      `cv2` 4.11 / `sensor` / `posture`) import clean; a scripted walk→lying→held returned
      `{'abnormal': True, 'reason': 'upright→lying held 3s'}`.
- [x] **The `→` in `reason` prints safely** — Jetson locale is `zh_TW.UTF-8`,
      `sys.stdout.encoding` = `utf-8`, so no `UnicodeEncodeError`. (This was a real worry:
      the client `print()`s that string every second.)
- [x] **Live run, real C270 webcam → relay over the LAN** —
      `RELAY_URL=http://192.168.137.1:8000 SENSOR=webcam POSTURE_BACKEND=bgsub python3 -m
      edge.mode3_posture`. Client posted verdicts, store-and-forward summary clean (0
      buffered), relay received `mode 3` / posture payload / `mode3_total: 130 B`. The wire
      payload on real hardware was **exactly** SPEC-01 §4.3 — no keypoints, no frames.
- [x] **Confirms SPEC-04 §9's audio note** — the run fired the mic-silence warning
      (PulseAudio default source = empty onboard jack), and Mode 3 ran anyway. Mode 3 is
      the one mode that works with the mic unfixed.

> ⚠️ **All postures read `absent`** in that run — the scene was empty/static, so this is
> wiring evidence, **not** posture evidence. Whether bgsub reports `standing`/`walking`/
> `lying` on a real person is the untested half, immediately below.

### Outstanding — the bench (needs the Jetson + webcam + a person in frame)

- [x] **Smoke (no camera):** `SENSOR=synthetic python3 -m edge.posture_selftest` → table
      prints, no traceback. Proves imports only. *(Run: prints `absent`/`standing`; the
      synthetic scene is a moving square, so labels are wiring evidence, not posture
      evidence.)*
- [ ] **Real (Jetson + webcam):** `SENSOR=webcam python3 -m edge.posture_selftest`
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
      *(Logic already unit-tested; this proves the **labels** feeding it are real.)*
- [ ] **False-alarm test:** start already lying → must **not** fire (§2 lookback).
      *(Same — unit-tested; the bench proves `bgsub` calls it `lying` and not `absent`.)*
- [ ] **Run Mode 3 for real:** `RELAY_URL=http://192.168.137.1:8000 SENSOR=webcam
      python3 -m edge.mode3_posture` from `~/EDGE-CAMERA/`, and watch the dashboard.

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
