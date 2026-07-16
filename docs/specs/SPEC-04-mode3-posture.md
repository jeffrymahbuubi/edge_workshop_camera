# SPEC-04 — Mode 3: Posture & Fall Detection

> # ⚠️ TWO OF THIS SPEC'S RULES WERE REVERSED — SEE [SPEC-08](SPEC-08-mode3-multimodal-and-preview.md)
>
> Jeffry's call, 2026-07-16, **after** this spec was written and after he tried to run
> the live test himself. **Do not act on §3.1's "no sound" or §4.1's "no pixels, ever"
> without reading SPEC-08 first** — both moved, for reasons recorded there.
>
> | Where | This spec says | Now |
> |---|---|---|
> | §3.1, §4 | Mode 3 is **keypoints only — no sound**; imports nothing from `common.features` | **Sound is fused in** as *corroboration* — a thump fires a fall in ~1 s instead of 3 s, but **never gates** it. `loud=False` ⇒ byte-identical to this spec. SPEC-08 §A |
> | §4.1 | **Mode B rejected.** Pixels never travel from Mode 3 | **Pixels may travel** behind an explicit, **default-OFF, non-sticky** toggle on a **separate endpoint**. `/ingest_posture`'s contract here is **unchanged and still absolute**. SPEC-08 §B |
>
> What did **not** change: `behaviour.py` is still backend-agnostic (it takes a `bool`,
> never a keypoint), Mode 2's **video** detector still may not ride along, and no pixel
> may ever enter `_payload()`.

> # ✅ REBUILT ON MoveNet — 2026-07-16
>
> **Mode 3 is deep-learning keypoints, and nothing else.** The colleague built and
> hardware-validated a MoveNet implementation
> (`references/context/edge-workshop-camera-en/mode3/`, with `MODE3_TEST_GUIDE.md`);
> it is now **integrated** — folded onto the existing relay, not run as a second
> dashboard. Background subtraction is **deleted** (§3.1), and with it SPEC-05's
> `trt_pose` design, which MoveNet/TFLite replaced with a different stack entirely.
>
> **What survived, and why it matters:** the fall rule (§1, §2) was built
> backend-agnostic on purpose — labels only, never a frame or a keypoint. Swapping the
> entire brain from MOG2 to a neural net cost it **one line** (`sitting` joining
> `UPRIGHT`). That was the bet §2 made, and it paid.

> **Live document.** Tick as you build.

| | |
|---|---|
| **Status** | 🟢 **BUILT + HARDWARE-VALIDATED 2026-07-16** — MoveNet on the Jetson → keypoints → relay → live skeleton, and **the fall alarm fires on a real person** (§6). 66 tests pass. On the board: model loads **7.0 s**, inference **0.08 s/frame (12.6 fps)** against a 1 fps need, wire payload **562 B** (~1,037× under Mode 1), **no fade**. |
| **Priority** | 🟢 Built |
| **Runs on** | The **Jetson** (pose *and* the fall rule) |
| **Depends on** | SPEC-01 (contract), SPEC-02 (relay) |
| **Related** | *(SPEC-05 designed a `trt_pose` backend that was never built; MoveNet replaced it and that spec was **deleted** 2026-07-16)* |

### The integration decisions (Jeffry, 2026-07-16)

Four forks, all his call, recorded because the code alone will not explain them:

1. **Mode 3 is keypoints only.** No sound, no Mode 2 feature vector, no bgsub — see §3.1.
   *"Mode 3 in my goal was to use the keypoint-based method only."*
2. **One dashboard, not two.** The colleague's Mode 3 shipped its own stdlib dashboard on
   **:8090**. Discarded; Mode 3 folded onto the relay (`:8000`, `/ingest_posture`), because
   a second dashboard would put Mode 3 outside the byte accounting and the bandwidth ratio,
   break SPEC-07's Mode 1/2/3 buttons, and make SPEC-01's single-relay contract false. The
   skeleton canvas was ported into `src/web/app.js` instead.
3. **⚠️ Keypoints may now travel — this REVERSES §4's old rule.** See §4.1.
4. **Mode B was NOT adopted.** The colleague's `MODE3_SEND_IMAGE=1` also uploads a JPEG
   (~15 KB) so the dashboard can show the real frame. It would put camera pixels back on
   the LAN and undo Mode 3's entire argument. Mode A only.

**Provenance.** Mode 3's brain is the colleague's work:
`references/context/edge-workshop-camera-en/mode3/` — `pose.py`, `mode3_edge.py`,
`mode3_dashboard.py`, `MODE3_TEST_GUIDE.md`, `movenet_lightning.tflite`. Built and
hardware-validated by him on a Jetson Nano 4 GB, then integrated here.

- [x] `pose.py` copied **byte-identical** into `src/edge/` — it has zero project imports,
      so it dropped straight in and his validation carries over untouched. Do not
      refactor it casually; a zero diff against his copy is worth keeping.
- [x] `movenet_lightning.tflite` → `src/models/` (4.7 MB). Path mirrors the Jetson's
      `~/EDGE-CAMERA/models/`, so `pose.py`'s default relative path resolves on **both**
      machines with no edit.
- [x] `mode3_edge.py` → became `src/edge/mode3_posture.py` (imports rewritten to the
      package layout; his flat `sensor/features/common/codec` are already here as
      `edge.sensor` / `common.*`, and `common.py` is `config.py`).
- [x] `mode3_dashboard.py` → **discarded**, folded onto the relay instead (see above).
- [ ] `MODE3_TEST_GUIDE.md` — **untracked**, one `git clean` from gone, along with the
      model binary. Same trap the old `POSTURE_TEST_GUIDE.md` had. Its §9 (camera framing)
      and §11 (2D limits) are the best writing on Mode 3's real constraints — §8 is
      reproduced in §7 below so the knobs survive even if that file does not.

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

Requirements 1 (upright labels before) and 2 (catch the transition) are easy — a fall is
full of motion. **Requirement 3, `lying` persisting for N seconds, is the hard one, and it
decided the entire mode.**

### 1.2 ⚠️ Why background subtraction could never do this — the reason Mode 3 is ML

Requirement 3 is the one that decided the whole mode. **A person who has fallen lies
still** — and a still person is exactly what a background model erases. MOG2 learns them
into the background and reports `absent`: *the confirmation step of the rule is precisely
the state the algorithm deletes.* The person falls, then vanishes.

The arithmetic predicted ~8 s of grace (`history=120` @ 15 fps). **The hardware was
harsher: `lying` never held past ~2 s, and `standing` appeared once in 90 rows.** So N=3
was not merely tight, it was **unreachable** — bgsub could not hold `lying` for 3 s, and
`absent` cancels the pending fall (§2), so **a bgsub fall essentially never fired.**

**MoveNet has no background model, so there is nothing to fade into.** On the same board a
still upright person read `standing` for **20+ consecutive seconds**, and the fall alarm
fires (§6). This is the entire justification for putting a neural net on the edge — not
that it is fancier, but that the cheap method was *structurally incapable* of the one
thing the rule needs.

- [x] Default **N = 3 s** → `config.FALL_HOLD_S`, env-configurable.
- [x] The fade ceiling is gone, so N could now go 5–10 s. It **stays at 3**: that is what
      was validated on hardware, and a caregiver alarm that waits 10 s is a worse product.
      **The number is now a choice rather than a compromise** — that is the real change.

---

## 2. The behaviour monitor (`edge/behaviour.py`, new)

> ✅ **Built, and it SURVIVED the backend swap** (see the banner). `src/edge/behaviour.py`,
> pinned by `tests/test_behaviour.py` (27 tests). `update(posture, now=None)` takes an
> **injectable clock** — a real-clock suite would burn 3 s per case and would be measuring
> `time.sleep`, not the rule.

A small state machine. **Runs on the Jetson.**

```python
UPRIGHT = {"standing", "walking", "sitting"}

# state: deque of recent postures + a lying-since timestamp
# every second:
#   if posture == "lying" and previous was UPRIGHT:  lying_since = now
#   if posture == "lying" and lying_since and now - lying_since >= FALL_HOLD_S:
#        → abnormal = True, reason = "upright→lying held {n}s"
#   if posture in UPRIGHT or posture == "absent":    lying_since = None
```

- [x] Require an **upright posture within the last `UPRIGHT_LOOKBACK_S`** (default 10 s)
      before a `lying` counts as a fall. Someone already lying when the camera starts is
      **not** falling — without this, every demo boots into a false alarm.
- [x] **`sitting` is UPRIGHT** (new with MoveNet; bgsub never produced the label). Falling
      out of a chair is the archetypal elderly fall — if `sitting` were inert, the single
      most likely real fall would never fire. Matches the colleague's validated rule.
- [x] `absent` **cancels** the pending fall — never treat it as continued lying. Under
      bgsub that was the fade (§1.2); under MoveNet the keypoints genuinely went away.
      Either way, inventing a fall out of missing data is inventing it out of a bug.
- [x] Latch `abnormal` until posture returns to upright, so the banner does not flicker.
      *(`absent` must **not** release it — that would let a fallen person's own
      disappearance clear the alarm it confirmed.)*
- [x] Emit `reason` as human text — it goes straight to the caregiver panel. **Frozen at
      the moment it fires**, so the banner does not churn `3s, 4s, 5s…` for one event.
- [x] **While still building, `reason` counts up** — `lying 1/3s`. Not the churn the freeze
      guards against (that is text moving *after* firing); before it fires the count is the
      only visible evidence the rule is armed, and the colleague's guide §7 makes it a pass
      criterion. It must never read like a fired alarm (no `upright→lying` until `abnormal`
      is true), and a half-built count must be **cleared** if they go absent — else the
      panel keeps counting someone who left. *(Both pinned by tests.)*
- [x] Keep the state machine **backend-agnostic**: it consumes `posture` labels only.
      ✅ **Proven, not asserted** — the MoveNet swap cost this file one line.
      *(If `behaviour.py` ever imports `cv2` or touches a keypoint, that has been broken.)*
- [x] Unknown labels are **inert, not crashes** — a backend inventing a label should
      degrade, not take the Jetson down mid-demo. *(`sitting` was listed as a bogus label
      in that test until MoveNet made it real — keep the parametrize in sync with §5.)*

---

## 3. The pose backend — and why there is only one

**Mode 3 is MoveNet keypoints. That is the whole mode.** *(Jeffry, 2026-07-16: "Mode 3 in
my goal was to use the keypoint-based method only.")* Contract in **SPEC-01 §5**.

| Backend | Status | |
|---|---|---|
| `movenet` | ✅ **the mode**, hardware-validated | MoveNet SinglePose Lightning, TFLite, CPU. `src/edge/pose.py` |
| ~~`bgsub`~~ | ⛔ **deleted 2026-07-16** | `posture.py` / `posture_selftest.py` / `test_posture_contract.py` removed |
| ~~`trt_pose`~~ | ⛔ **never built** | SPEC-05's design. MoveNet arrived first and replaced it |

There is **no `POSTURE_BACKEND` switch**. Not an omission — a boundary.

### 3.1 ⚠️ Why bgsub had to go — the fade was not even the decisive reason

§1.2 covers the fade. The reason bgsub could not merely be *demoted* is **coupling**:

> **bgsub cannot work without Mode 2's detector.** Its `walking` test is
> `motion_level >= WALK_MOTION_THRESH`, and `motion_level` comes from
> `common.features.video_motion_features` — Mode 2's frame-differencing. Every bgsub
> Mode 3 tick ran Mode 2's algorithm. **"Mode 3 = keypoints only" and "keep bgsub" are
> mutually exclusive**, so keeping it as a fallback was never actually on the table.

MoveNet has no such dependency: it decides `walking` from **keypoint centroid movement**
between seconds (`pose.py`'s `_prev_center` / `WALK_MOVE_THRESH`) — a better test anyway,
because it tracks *the person* rather than pixel churn, so a flickering light is not
walking.

- [x] `POSTURE_BACKEND` removed from `config.py`; `mode3_posture.py` no longer imports
      `common.features` **at all**; bgsub deleted (recoverable from git history).

> **The bug this cleanup killed.** The first integration kept the switch and computed
> `video_motion_features(frames)` every second to feed `pose.estimate(frames, motion)` —
> **which ignores it.** `motion_level` appears in `pose.py` only in the signature and
> docstring; the body never reads it. So the Nano ran frame differencing over 15 frames a
> second for a number nothing consumed. The parameter is a vestige of the bgsub interface;
> `pose.py` stays byte-identical to the colleague's validated file, so it stays too —
> just leave it defaulted and never pass it.

### 3.2 One frame per second, not fifteen

bgsub needed **every** frame (MOG2 only learns from what it is fed). MoveNet needs
**one**: inference costs ~0.08 s on a Nano and there is no model to train, so feeding the
whole second would burn 15× the CPU for the same answer.

---

## 4. `edge/mode3_posture.py` (new)

> ✅ **Built.** `src/edge/mode3_posture.py`. Wire format pinned by
> `tests/test_mode3_payload.py`.

Mirrors `mode2_edge.py` — same shape, same store-and-forward discipline. Note what is
**absent**: no `common.features`, no audio, no backend switch.

```python
sensor  = get_sensor(SENSOR_KIND)
est     = get_pose_estimator("movenet")
monitor = BehaviourMonitor()

while True:
    tick = time.time()
    frames, _audio, _ = sensor.read_second()   # audio read and DROPPED: camera-only
    result  = est.estimate(frames)             # ONE frame inferred, not 15 (§3.2)
    verdict = monitor.update(result["posture"])
    outbox.append(_payload(result, verdict))   # SPEC-01 §4.3
    flush(outbox)                              # buffer on failure
    sleep(SECONDS_PER_TICK - elapsed)          # pace on ELAPSED time
```

- [x] POST to **`/ingest_posture`** on the existing relay, payload per SPEC-01 §4.3.
- [x] Reuse `mode2_edge.py`'s `outbox` store-and-forward so Mode 3 survives a cable pull.
      *(Mode 3 is the mode a caregiver would rely on: a cable pull must **delay** the fall
      alarm, not delete it.)*
- [x] Print the same per-second terminal line as Mode 2 (terminal-first validation).
- [x] **Pace on elapsed time, not a flat `sleep(1)`.** MoveNet eats ~0.08 s of the second
      on a Nano; sleeping a further full second on top would halve the rate the fall rule
      sees and stretch `FALL_HOLD_S` into something longer than 3 real seconds.

### 4.1 ⚠️ Keypoints may travel — this reverses the original rule

**The old rule (and it was not silly):** *"Send only the verdict. Never keypoints, never
frames. Shipping skeletons to the laptop would repeat Mode 1's mistake in a new costume."*
It was pinned by a test written specifically to catch the day a pose backend landed.

**Jeffry reversed it on 2026-07-16, and the argument that won:**

| | Mode 1 | Mode 3 (Mode A) |
|---|---|---|
| What crosses the LAN | ~583,000 B of **recognisable faces** | **562 B** of joint coordinates |
| Can it identify anyone? | yes | no — 17 numbers |
| Ratio | — | **~1,037× smaller** |

A skeleton is not a face in a new costume; it is two orders of magnitude less data and it
identifies nobody. And it buys the single best artefact in the workshop: a **live stick
figure that proves the ML ran on the edge**. Verdict-only Mode 3 showed a text label —
true, but nothing a student could *see*.

**The privacy line MOVED; it did not disappear.** It is now exactly:

> **RAW PIXELS NEVER TRAVEL.** No frames, no audio, no JPEG, no mask.

- [x] `tests/test_mode3_payload.py::test_raw_pixels_never_travel` is now the load-bearing
      guard, and the old `test_pose_backend_keypoints_never_travel` is **gone by
      decision, not by accident** — the test file says so at the top, so nobody "repairs"
      it back.
- [x] `_payload()` still lists the wire fields **by hand** rather than splatting the
      estimator's dict. The splat is *still* a trap even now that keypoints are welcome:
      it would hand the wire whatever a future backend decides to return, which is exactly
      how a frame gets onto the LAN by accident. **That leak is invisible at the bench** —
      the dashboard renders identically either way.
- [x] **Round keypoints to 3 decimals on the wire.** MoveNet emits full-precision floats
      (~19 chars each); 17 joints × 3 numbers is most of the payload and buys 0.3 px on a
      320 px frame. Measured: **1,225 B → 562 B, a 2.2× saving for nothing visible.** In a
      workshop whose entire thesis is payload size, shipping invisible decimals would be
      undercutting the lesson with noise.

---

## 5. Relay & dashboard

> ✅ **Mostly pre-built** — SPEC-02 built the endpoint and SPEC-03 the panel, both ahead of
> the client that feeds them. MoveNet needed two additions: the skeleton fields and
> `sitting`. All confirmed in a real browser (playwright-cli), 2026-07-16.

- [x] `POST /ingest_posture` — auth + rate-limit like the others (SPEC-01 §4.1).
- [x] `PosturePayload` accepts the skeleton: `keypoints` (17 × `[x,y,score]`, 0..1),
      `bbox` (0..1), `score`. **No `image` field** — the absence is the contract (§4.1).
- [x] Flag mapping: `abnormal → "FALL?"`, else `walking`/`standing`/**`sitting`** →
      `person-active`, `absent` → `quiet`.
      > ⚠️ **`sitting` had to be added here.** The mapping predates MoveNet, so a seated
      > person fell through to `quiet` — the dashboard would report an **empty room** with
      > someone sitting in it. Invisible at the bench (it is one status word nobody is
      > watching) and pinned now by `test_sitting_is_a_person_not_an_empty_room`.
- [x] Fill the SSE event's `posture` field (SPEC-02 §5 reserved it as `null`).
- [x] **The relay does no inference and runs no rule** — it got a verdict and a skeleton
      and draws them. The asymmetry against `/ingest_raw`, which decodes frames and
      computes *everything* on the laptop, is the whole lesson sitting in one file.
- [x] Dashboard: posture label + `score`, alarm banner on `abnormal` showing `reason`,
      and **the live skeleton** (§5.1).
- [x] Video panel in Mode 3: **`/latest.jpg` → 404**, same as Mode 2 — verified *while a
      skeleton is streaming* (`test_latest_jpg_still_404s_while_a_skeleton_streams`). It
      would be easy to assume a richer payload meant the image came back. It did not.

### 5.1 The skeleton panel — why it goes in the *video* box

SPEC-03's video panel exists because **its emptiness in Mode 2 is the lesson**. Mode 3
does not undo that; it completes it into a three-way progression students can watch:

| | What the panel shows | What crossed the LAN |
|---|---|---|
| **Mode 1** | your face | ~583 KB of pixels |
| **Mode 2** | nothing at all | ~200 B feature vector |
| **Mode 3** | **a moving skeleton over an empty background** | 562 B of coordinates |

Mode 3's panel is not empty because nothing happened — it is **empty of pixels** while
still showing that the Jetson understood the person completely.

- [x] Hand-rolled `<canvas>` in `app.js`, for the same reason the chart is hand-rolled SVG
      (SPEC-03 §8): no Elements component draws a skeleton, and this one is load-bearing.
- [x] Draw joints only above `KP_DRAW_CONF` (0.2) — an unconfident joint invents a limb.
- [x] Skeleton turns **red** with the bbox on `abnormal`, NVIDIA green otherwise.
- [x] **A skeleton must never render over a leftover Mode 1 frame.** `/latest.jpg` 404s in
      Mode 3 so the frame does clear — but only on the *next poll*, and one frame of
      skeleton-over-face would contradict the exact claim the panel makes.
      `.has-skeleton img { display: none }` makes the skeleton win immediately.
      > ⚠️ **Narrowed to `.has-skeleton:not(.preview-on) img` — 2026-07-16.** As written,
      > this rule **broke SPEC-08 Part B**: with the setup preview on, the frame arrived,
      > sat in the DOM, and was hidden — the student pressed "show camera", the byte
      > counter climbed, and the panel looked **identical**. The guard is about a *stale*
      > frame nobody asked for; the preview is a frame the student deliberately requested,
      > whose whole purpose is to be seen **with the skeleton drawn on it** so they can
      > check the joints land on their body.
      >
      > **Found by Jeffry looking at the panel — not by the automated check**, which
      > asserted `has-frame === true` and passed. The class was right; the pixels were not.
      > A reminder that this file's own §6 warns the failure is invisible at the bench:
      > `test_preview_frame_is_not_hidden_by_the_stale_face_guard` now pins it.

> **Mode 3's motion/audio bars read `—`.** Correct, not a bug: Mode 3 is keypoints only
> and sends no feature vector, so motion/audio/blobs have nothing to show. Worth knowing
> before someone reports it at the bench.

---

## 6. Validation

The colleague's protocol is `MODE3_TEST_GUIDE.md` §6 (in the `mode3/` reference folder);
its §9 on camera framing is the single biggest accuracy factor and worth reading before
any bench attempt.

### Done on the laptop — 2026-07-16 (TDD)

**66 tests, all passing.** From the repo root — note `fastapi` + `httpx`: without them the
relay tests error at *collection*, which reads like a failure and is not one:

```bash
uv run --with pytest --with opencv-python-headless --with numpy --with requests \
  --with fastapi --with httpx python -m pytest tests/ -q
```

`tests/conftest.py` puts `src/` on the path so tests import `edge`/`common` exactly the
way the Jetson does (`python3 -m edge.x`).

- [x] `test_behaviour.py` (27) — fires on walk→lying held and on **sitting**→lying; does
      **not** fire when already lying at startup; `absent` cancels a pending fall and
      restarts the hold; latch releases on upright but survives `absent`; `reason` frozen
      at fire but **counting while building**, and a half-built count cleared on `absent`.
- [x] `test_mode3_payload.py` (12) — SPEC-01 §4.3 wire format; **raw pixels never travel**;
      keypoints **do** travel (the reversal, pinned); **no Mode 2 feature vector rides
      along**; rounded to 3 dp; payload under 1 KB.
- [x] `test_relay_posture.py` (7, **new**) — `sitting` → `person-active`; `/latest.jpg`
      still 404s **while a skeleton streams**; keypointless payloads accepted; bad token
      rejected.
- [x] **End-to-end in a real browser** (playwright-cli, per the standing rule): skeleton
      renders green when normal / red inside a red bbox on `abnormal`; banner reads
      `upright→lying held 3s`; `sitting (0.91)` → `person-active`; **no JS errors** (only
      the by-design `/latest.jpg` 404s).

### Done on the Jetson — 2026-07-16 ✅ **the real thing**

`jetson-2gNANO` (a **4 GB** Nano despite the hostname — RAM reads 3.9 GB), real C270
webcam → relay at `192.168.137.1:8000` over the ICS LAN.

| Measured | Result |
|---|---|
| **TFLite runtime** | `tflite_runtime` **absent** (the GLIBC 2.29 problem the guide §10 predicts); **TensorFlow 2.13.1 present** → `pose.py`'s `tf.lite` fallback is the *only* path here, and it works |
| **Model load** | **7.0 s** (guide says 10–30 s) |
| **Inference** | **0.08 s/frame ≈ 12.6 fps** vs the 1 fps the pipeline needs — ~12× headroom |
| **Wire payload** | **562 B** (~1,037× under Mode 1) |
| **Disk** | **unchanged at 5.2 GB free (88%)** — the model is 4.7 MB |
| **No fade** | a still upright person read `standing` for **20+ consecutive seconds** |
| **Live skeleton** | rendered on the laptop dashboard from real Jetson keypoints at 473 B/s |

- [x] **`standing` is now reachable** — under bgsub it appeared once in 90 rows; under
      MoveNet it is the dominant label and holds indefinitely. §1.2's fade is gone.
- [x] ✅ **THE FALL ALARM FIRED ON REAL HARDWARE** — the whole point, observed end to end
      with a real person, a real camera and real keypoints:

      ```
      walking → walking → walking            (upright, from MoveNet)
      lying 0/3s → lying 1/3s → lying 2/3s   (the hold building)
      abnormal=True  flag=FALL?  reason=upright→lying held 3s
      ```

      Every layer met at once: MoveNet produced the labels, `behaviour.py` held the rule,
      the relay mapped `FALL?`. Under bgsub this sequence was **unreachable** — `lying`
      never survived 3 s. The counting `reason` also works live, exactly as the
      colleague's guide §7 specifies.
- [ ] Sitting / lying label accuracy at a **proper camera distance**. The live runs had
      the subject close to the lens (guide §9 wants the camera metres back, full body,
      **side-on**), which produced a partial skeleton, `score` ~0.5–0.66, and occasional
      spurious `lying`. The rule fires correctly; the framing is what needs a bench pass.
- [ ] A **false-alarm** pass: start already lying → must not fire. Unit-tested (§6), not
      yet watched on hardware.

> **What the unit tests do NOT prove.** They pin the *rule*, never the *labels*. Green
> tests + a backend that never reports `lying` = a rule perfectly correct about a posture
> it never detects. Not hypothetical — that is precisely what bgsub was. Also: *"start
> already lying → must not fire"* and *"absent cancels"* are **absences of an event**, and
> at the bench you watch nothing happen and call it a pass — which is also what a broken
> rule looks like when the camera points at a wall.

### Also verified on the Jetson

- [x] **The `→` in `reason` prints safely** — Jetson locale is `zh_TW.UTF-8`,
      `sys.stdout.encoding` = `utf-8`, so no `UnicodeEncodeError`. (A real worry: the
      client `print()`s that string every second.)
- [x] Store-and-forward survives a network gap (0 buffered on a clean run).
- [x] **Mode 3 ran fine even while the mic was broken** — camera-only, it never asks the
      mic anything. Now historical rather than load-bearing: **the mic was fixed and
      persisted 2026-07-16** (`~/.config/pulse/default.pa`, verified across a PulseAudio
      restart; `audio_rms` 0.012–0.026, was 0.0 — see SPEC-01 §6 step 3). It remains a
      design fact worth knowing: Mode 3 has one dependency fewer than Modes 1/2.

**Operational lessons — these cost real time, keep them:**

- ⚠️ **The Jetson is HEADLESS** (no X, no monitor, `DISPLAY` empty) **and Mode 3 sends no
  image**, so a tester performing for the camera is **blind** — two bench passes were
  contaminated by exactly that. Give them a live view *before* asking them to perform.
  Note `/ingest_posture` calls `_latest_jpeg.pop()`, so posting frames to `/ingest_raw`
  alongside posture does NOT work (the posture POST wipes the frame each tick, the modes
  fight, and the Mode 1 byte totals behind the ratio get corrupted). A separate MJPEG
  server on the Jetson works and leaves the relay clean — **but it must never ship, and
  must never reach the golden image.**
- ⚠️ **Rapid camera re-open hands back empty frames** → every label `absent`. Give it a
  couple seconds to release (SPEC-07's supervisor bakes in a 2 s settle). Background
  `plink` also **orphans** the remote python; several piled up **fought over the one
  camera**, producing racing reads that looked like a code bug. Clean up between runs.
- ⚠️ **`pkill -f` / `pgrep -f` MATCH THEIR OWN plink SHELL** — killing it (exit 128, no
  output) or reporting a phantom process. Use the bracket trick (`pkill -9 -f '[e]dge\.'`)
  **and** keep it in its own call: the trick only stops the *pattern* self-matching, so a
  real `edge.` elsewhere in the command still triggers it. `pscp` won't expand `~` either.

---

## 7. Tuning knobs

All are **environment variables read in `edge/pose.py`** — no code edits, and deliberately
left with the model they belong to rather than hoisted into `config.py`. From the
colleague's `MODE3_TEST_GUIDE.md` §8:

| Symptom | Knob | Default | Change |
|---|---|---|---|
| Upright mislabelled `lying` | `UPRIGHT_MARGIN` | 0.03 | raise |
| Lying missed | `UPRIGHT_MARGIN` | 0.03 | lower |
| `sitting` missed | `SIT_DROP_RATIO` | 0.6 | raise |
| Standing reads `sitting` | `SIT_DROP_RATIO` | 0.6 | lower |
| Standing reads `walking` | `WALK_MOVE_THRESH` | 0.03 | raise |
| Walking never registers | `WALK_MOVE_THRESH` | 0.03 | lower |
| Label flickers | `SMOOTH_N` | 3 | raise to 5 (more stable, more lag) |
| In-frame person reads `absent` | `KP_CONF` | 0.3 | lower |
| Fall fires late / never | `FALL_HOLD_S` | 3 | lower (`config.py`) |

> The old bgsub knobs (`LYING_ASPECT`, `WALK_MOTION_THRESH`, `MIN_FG_FRACTION`) are **gone
> with the backend**. If you meet them in an old doc, it predates 2026-07-16.

---

## 8. Known limitations (2D single camera — state these in the demo)

The four bgsub limitations that used to live here (static camera, background warm-up, the
fade, box-shape posture) are **all gone with the backend**. What remains is inherent to
2D pose, from `MODE3_TEST_GUIDE.md` §11:

- **A fall straight AT or AWAY from the camera is ambiguous** — foreshortened, so head and
  hips project on top of each other and no 2D method can read it as lying. Someone curled
  in a tight ball facing the lens is likewise ambiguous. The guide's §9 is emphatic: camera
  **side-on** to where a fall happens, a few metres back, full body in view. **This is the
  single biggest accuracy factor**, and it is a *placement* problem, not a code problem.
- **Activity is a rule on DL keypoints**, not a trained action model — odd angles can
  misfire. Tuning (§7) plus framing handles most cases.

> Honest framing for the demo: MoveNet removed the *fade*, which was fatal. It did not
> remove *geometry*. The difference is that a well-placed camera now works reliably, where
> bgsub failed even when well-placed.

---

## 9. Open

- [x] ~~Measure the real fade time before fixing `FALL_HOLD_S`~~ — answered: there is no
      fade under MoveNet (§1.2).
- [ ] Does Mode 3 replace Mode 2 in the demo flow, or run as a fourth position after it?
- [x] ~~**Mode 3 has no audio, by design**~~ — **ANSWERED, AND REVERSED, 2026-07-16**
      (SPEC-08 Part A). This entry said the mode difference was "a teaching point to state
      out loud, not a bug to fix". Jeffry's counter, later the same day: the workshop is
      called **Multi-Modal** Posture Recognition, and the mode being showcased was the only
      uni-modal one — that is not a teaching point, it is a hole. Mode 3 now fuses sound as
      **corroboration** (faster, never gated). The modes *still* answer different questions
      and their `FALL?` flags are *still* not directly comparable — that part was right and
      remains worth saying out loud.
- [ ] Commit the 4.7 MB `movenet_lightning.tflite`, or bake it into the SD image? It lives
      at `src/models/`. The old SPEC-05 argued against committing 81 MB of weights; 4.7 MB
      is a different question, and committing keeps the repo self-contained for an offline
      LAN.
