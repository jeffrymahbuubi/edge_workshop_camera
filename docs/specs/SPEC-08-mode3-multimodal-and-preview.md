# SPEC-08 — Mode 3: Multi-Modal Fusion & Setup Preview

> # ⚠️ THIS SPEC REVERSES TWO OF SPEC-04's RULES — 2026-07-16
>
> Both reversals are **Jeffry's explicit decisions**, made after he tried to run the
> live test himself and hit the limits of the current design. They are recorded here
> rather than in SPEC-04 because that file is already at the 500-line ceiling
> (CLAUDE.md), and because each reversal deserves its argument written down — the
> code alone will read like drift.
>
> | SPEC-04 said | SPEC-08 says | Why it changed |
> |---|---|---|
> | §3.1 "Mode 3 is keypoints only. **No sound.**" `mode3_posture.py` imports **nothing** from `common.features` | Mode 3 **reads the mic** and fuses `loud_flag` into the fall rule (§1) | The workshop's theme is **Multi-Modal** Posture Recognition, and Mode 3 — the mode you showcase — was the only uni-modal one |
> | §4.1 "**RAW PIXELS NEVER TRAVEL.** No frames, no audio, no JPEG, no mask." Mode B (`MODE3_SEND_IMAGE=1`) **not adopted** | Pixels may travel **only** behind an explicit, default-OFF, non-sticky toggle (§2) | The Jetson is headless and Mode 3 sends no frames, so a student performing for the camera is **blind**. This killed two bench passes and one live-test attempt |

> **Live document.** Tick as you build.

| | |
|---|---|
| **Status** | 🟡 **Parts A + B BUILT on the laptop (TDD, 101 tests pass, was 66) — NOT yet hardware-validated, and Part B has NO DASHBOARD UI yet** (toggle + banner + preview byte row still to do). See §C for what is unproven |
| **Priority** | Part A (fusion) then Part B (preview), then SPEC-03's teaching content |
| **Runs on** | The **Jetson** (fusion) + the **relay** (preview state & accounting) |
| **Depends on** | SPEC-01 (contract), SPEC-04 (the fall rule), SPEC-06 (live thresholds) |
| **Supersedes** | SPEC-04 §3.1 (no-audio) and §4.1 (no-pixels), **partially** — see the banner |

---

## Part A — Multi-modal fusion

### A1. The problem this fixes

The workshop is called **Multi-Modal Posture Recognition**. Today:

| Mode | Senses | Fuses? |
|---|---|---|
| 1 | camera + mic | yes — `loud_flag AND motion stopped` (in the relay) |
| 2 | camera + mic | yes — same rule, on the Jetson |
| 3 | camera **only** | **no** — `mode3_posture.py:109` reads audio and throws it away |

So the **most advanced mode is the only uni-modal one**. A student or an instructor
who notices reads it as an oversight. It was not — it was a deliberate boundary
(SPEC-04 §3.1) — but the theme makes it indefensible to leave unexplained.

### A2. ⚠️ The rule that was REJECTED, and why — read before "simplifying" this

The obvious implementation is **`lying AND loud`**. It was considered and **rejected**:

> **It is a safety regression.** A person who slumps silently — faints, slides off a
> chair onto carpet — makes no thump. Today Mode 3 catches that with vision alone.
> Gating on sound would trade a **real detection** for a tidier theme.

It also **couples Mode 3 to the microphone**, and the mic is this project's single
most likely per-board failure (SPEC-01 §6 step 3: PulseAudio defaults to the empty
onboard jack; the persisted fix embeds a webcam serial, so a board that enumerates
differently **boots deaf with no error**). Under `lying AND loud`, a deaf board takes
down **all three modes** instead of one — silently, which is this bug's signature.

### A3. The rule: **corroboration, never a gate**

> **Sound buys SPEED, not permission.**

```
upright → lying, held 3s                → FALL?   (vision alone, unchanged)
upright → lying + a thump near the drop → FALL?   (in 1s — corroborated)
```

```
t-1     t       t+1
walk    LYING   lying          → fires at t+3   (vision only)
walk    LYING   lying          → fires at t+1   (a thump landed at t)
        +THUMP
```

- [x] `FALL_HOLD_FAST_S` = **1.0 s** (`config.py`, env-configurable) — the hold when
      two senses agree.
- [x] `LOUD_CORROBORATION_S` = **2.0 s** — a thump counts if it lands within this of
      the `upright→lying` transition. **Not "any loud sound ever"**: a person lying in
      bed for ten minutes who then coughs must not be upgraded to a fall. The thump
      must belong to *the drop*.
      *(`test_thump_outside_the_window_does_not_upgrade`,
      `test_a_cough_while_already_lying_in_bed_never_fires`)*
- [x] The window is **two-sided**. The impact and the first `lying` label usually land
      in the same 1 s tick, but which one wins the tick is a race — the thump can be
      sampled a tick late. A one-sided window would drop real corroborations for no
      reason. *(`test_thump_just_BEFORE_the_drop_still_counts`)*
- [x] **Corroboration latches for the run of `lying`.** Once a thump has upgraded a
      pending fall, it stays upgraded; it must not flicker back to the 3 s hold because
      the next second was quiet. (A fall is quiet *after* the impact — that is the
      whole signature.) *(`test_corroboration_latches_across_a_quiet_second`)*
- [x] **Never blocks.** With no thump, or a dead mic, the rule is **byte-identical to
      today's**. This is the property that makes the change safe: the worst case is
      the current behaviour. *(`test_a_deaf_board_behaves_EXACTLY_like_today` asserts
      the deaf monitor and a pre-fusion monitor return **equal verdicts** across a
      whole script — not merely that it "still works")*

### A4. Why this is honest teaching, not a fudge

`lying AND loud` would have taught students that fusion means **AND**. It does not.
Fusion means *two independent senses agreeing raises confidence* — and higher
confidence buys you the right to act **sooner**. That is what a real caregiver system
does, and it is visible on the dashboard in one line:

```
lying 1/3s                      ← vision is still building its case
thump + upright→lying held 1s   ← both senses agreed; it fired in a third of the time
```

- [x] `reason` must **name the thump** when it corroborated. The fusion is invisible
      otherwise — the banner would read identically and the student would learn
      nothing. This string is the only place fusion becomes watchable.
      → `thump + upright→lying held 1s`, and `thump + lying 0/1s` while building.

### A5. Wire format — SPEC-01 §4.3 changes

- [x] Payload gains **`audio_rms`** (float) and **`loud_flag`** (bool). SPEC-01 §4.3
      updated; `PosturePayload` declares both **Optional**, so a Jetson running
      yesterday's client does not start 422-ing the moment the relay is upgraded.
- [x] These are **scalar features, not raw audio.** ~20 B. The Part B line
      ("raw pixels never travel") is untouched by them — an RMS number is not a
      recording, exactly as Mode 2 has always argued.
- [x] **`test_no_mode2_feature_vector_rides_along` revised, not deleted** — renamed
      `test_no_mode2_VIDEO_detector_rides_along`, with the reversal written at the top
      of the file so nobody "repairs" it back.
      > ⚠️ **A trap worth knowing:** `test_raw_pixels_never_travel` greps the serialised
      > JSON for the word `audio` — and **`audio_rms` contains it**. The substring guard
      > had to be split (`FORBIDDEN` keys vs `FORBIDDEN_IN_BODY` substrings) or a correct
      > field would fail a correct test. `test_audio_rms_is_a_number_not_a_recording`
      > replaces the lost coverage by asserting the field is a scalar, not a list.
- [x] Payload stays **under 1 KB** (`test_mode_a_payload_stays_two_orders_under_mode_1`).
      **Measured: 611 B, up from 562 B — the two scalars cost 49 B.** Mode 1 is ~583,000 B,
      so Mode 3 is still **~955×** smaller. The bandwidth lesson is intact; multi-modality
      cost it 0.008% of Mode 1's payload.
- [x] ⚠️ **Pydantic silently drops undeclared fields.** Mode 3 would have posted the
      scalars, the relay would have returned 200, and the dashboard would simply never
      have seen them — no error anywhere. `test_the_audio_scalars_survive_the_round_trip`
      exists because that failure looks exactly like success.

### A6. `common.features` — the import SPEC-04 §3.1 forbade

- [x] `mode3_posture.py` imports **`audio_energy_features` only**. Not
      `extract_features`, not `video_motion_features`.
- [ ] ⚠️ **The §3.1 ban was about CPU, not purity.** The bug it killed was Mode 3
      running `video_motion_features` over 15 frames every second to feed a `pose.py`
      parameter that *is never read* (`motion_level` is vestigial — see SPEC-04 §3.1).
      `audio_energy_features` is an RMS over one array: **microseconds, and its result
      is actually consumed.** The ban's *reason* does not reach it.
- [x] `behaviour.py` still imports **nothing** from `common.features` and still sees no
      frame, no bbox, no keypoint. It takes `loud: bool` — a plain flag, decided by the
      caller. **SPEC-04 §2's backend-agnostic property survives**, and that property is
      what made the MoveNet swap cost one line. Do not spend it here.
      *(`test_consumes_labels_only_no_backend_coupling` still passes untouched.)*

### A7. Live threshold — Mode 3 joins SPEC-06

Once Mode 3 reads the mic, the dashboard's **loud threshold slider must drive it**, or
the slider silently lies in one of three modes.

- [x] Mode 3 pulls `loud_rms_thresh` from the **`/ingest_posture` response**, exactly as
      `mode2_edge.py:61-66` does from `/ingest_features`. Same channel, no new poll, no
      new endpoint. *(`test_the_loud_slider_reaches_mode_3`)*
- [x] Fusion still happens **on the Jetson**. The relay supplies a number; the edge
      decides. SPEC-06's design intact.
- [ ] Measured ambient on this board is **0.0105–0.0120** against `LOUD_RMS_THRESH`
      **0.05** — roughly 4× headroom, so a clap clears it and room noise does not.
      **Unverified for the FAST path**: nobody has yet clapped at a real drop.

---

## Part B — The setup preview

### B1. The problem this fixes

> *"It's quite difficult for me to test if there is no live-feed."* — Jeffry, twice.

The Jetson is **headless** (no X, no monitor, `DISPLAY` empty) and Mode 3 sends no
frames, so **there is no live view anywhere**. A student performing for the camera
cannot tell whether they are in frame, whether the floor is visible, or whether they
are side-on. SPEC-04 §6 already records that this contaminated **two bench passes**;
it then cost a **third** live-test attempt on 2026-07-16 before this spec existed.

Framing is not a detail: SPEC-04 §8 calls it **"the single biggest accuracy factor"**.
The system currently makes the single biggest accuracy factor **unobservable**.

### B2. The two attempts that failed, and why this is different

| Attempt | Why it died |
|---|---|
| Colleague's **Mode B** (`MODE3_SEND_IMAGE=1`, ~15 KB JPEG every second) | Always-on pixels. Undoes Mode 3's whole argument, permanently, for everyone |
| **MJPEG server** on the Jetson :8080 | Worked, relay stayed clean — but it must ship on the **golden image** to be useful, cloning a raw-frame streamer to every student board forever. Built, used, **deliberately deleted** |

**What is different here: the pixels are opt-in, non-sticky, and their cost is on
screen.** Mode 3's default behaviour — what the workshop demonstrates, what the ratio
quotes, what a student sees unless they press a button — is **unchanged and pure**.

### B3. ⚠️ The reframe — the exception IS the lesson

This is not a compromise of the bandwidth lesson. It is the strongest delivery of it
available:

```
Mode 3                    562 B/s      ← press "show camera"
Mode 3 + setup preview  ~583 KB/s      ← ~1,037× more, on screen, instantly
                                          press it again → collapses back
```

A student **moves that number with their own hand** and watches it collapse back. That
beats any claim on a slide. The cost of pixels stops being asserted and becomes
*demonstrated*.

### B4. Rules — all of them load-bearing

- [x] **Default OFF.** Every time Mode 3 starts. Not remembered, not in localStorage,
      not sticky across a mode switch. A student who leaves it on must not silently
      teach the next student that Mode 3 costs 583 KB/s.
- [x] **Relay resets `preview=false` on every mode change** — the toggle cannot outlive
      the Mode 3 session that turned it on. *(`test_a_mode_change_clears_the_preview`,
      `test_even_reselecting_mode_3_clears_the_preview` — every path into Mode 3 goes
      through `POST /mode`, which is what makes "default OFF" true on **arrival** rather
      than only on first boot.)*
- [x] **The toggle is a GATE, not a suggestion** — `/ingest_preview` **403s** while the
      preview is off. The client polls the flag and should never post while off, but
      "should never" is how a raw frame ends up on the LAN. *(Not in the original spec;
      added during the build.)*
- [x] **Turning it off drops the frame immediately**, not on the next posture tick — a
      face lingering after the student turned pixels off would contradict the exact
      claim the panel is making at that moment.
- [ ] **A loud banner while ON.** "⚠ Pixels are leaving the device — setup only."
      The panel must never quietly look like Mode 1 while claiming to be Mode 3.
      *(Dashboard — not built yet.)*
- [x] **Separate byte accounting.** Preview bytes get their **own bucket**, never
      Mode 3's. Two reasons: Mode 3's 562 B stays quotable and the ratio stays honest,
      **and** showing the two numbers side by side is the entire point of §B3.
      *(`test_preview_bytes_never_land_in_mode_3s_bucket`, `test_preview_does_not_disturb_the_ratio`)*
- [x] **Never touches `live_mode`.** The relay is in Mode 3; a preview frame must not
      flip it to Mode 1 and corrupt the Mode 1 totals behind the ratio.
      > ⚠️ **A landmine found during the build:** `live_mode()` does `int(name[-1])` to
      > turn `"mode3"` into `3`. Adding `"preview"` to `MODES` would evaluate
      > `int("w")` and **crash the relay**. Membership in `MODES` is load-bearing in a
      > way the name does not advertise — hence `PREVIEW`/`TRACKED` alongside it, and
      > `test_the_preview_never_becomes_the_live_mode`.

### B5. The endpoint — and why not the obvious one

⚠️ **`POST /ingest_raw` alongside posture does NOT work.** `/ingest_posture` calls
`_latest_jpeg.pop()` (`relay_server.py:276`), so the posture POST **wipes the frame
every tick**; the two endpoints publish conflicting `live_mode`s and the Mode 1 byte
totals behind the ratio get corrupted. This is recorded in SPEC-04 §6 as an already-paid
lesson — do not re-derive it.

- [x] New **`POST /ingest_preview`** — sets `_latest_jpeg`, counts into the **preview**
      bucket, and leaves `live_mode` **and** the Mode 1/2/3 buckets alone. Its own
      `PreviewPayload` model: the obvious design (an optional `image` on
      `PosturePayload`) was rejected because a field that is *usually* absent is one
      bad default away from always present.
- [x] `/ingest_posture` must **stop popping** `_latest_jpeg` when a preview is live, or
      the preview dies on the next posture tick — the exact fight described above.
      The pop is **not deleted**: with the preview off it is still what stops a Mode 1
      face lingering into Mode 3. *(Both directions pinned:
      `test_a_posture_tick_does_NOT_wipe_the_preview_frame`,
      `test_posture_STILL_wipes_a_stale_frame_when_the_preview_is_off`.)*
- [x] New **`GET/POST /preview`** for the toggle state, mirroring SPEC-07's `/mode` and
      SPEC-06's `/config`. Same pattern: **relay holds state, Jetson polls it.**
- [x] Mode 3 reads the flag from the **`/ingest_posture` response** (same channel as
      A7's threshold). No second poll. `resp.get("preview", False)` — an older relay
      means "no pixels", the safe direction to fail.
- [x] The client's preview post is **fire-and-forget**: no outbox, no retry, unlike the
      posture path. A stale setup frame is worthless (the student is looking at where
      they are *now*), and buffering pixels would mean a cable pull produces a **burst
      of faces on reconnect** — precisely what Mode 3 exists to avoid. A `403` is
      normal, not an error: the student turned the camera off mid-tick.

### B6. Invariants that MOVE, and the tests that must move with them

- [ ] `test_raw_pixels_never_travel` **stays, unchanged**, and stays load-bearing. It
      tests `_payload()` — the posture wire format — and **no pixel ever enters it**.
      The preview is a *separate* endpoint carrying a *separate* payload. That
      separation is deliberate: **Mode 3's contract stays absolute**, and the preview is
      visibly a different thing rather than a field someone can quietly add to.
- [ ] `test_latest_jpg_still_404s_while_a_skeleton_streams` (SPEC-04 §5) **must gain a
      precondition**: it holds *while preview is OFF*, which is the default. Add its
      mirror — `/latest.jpg` **serves** while preview is ON — so both directions are
      pinned rather than one being an accident.
- [ ] New: preview **defaults OFF** on Mode 3 start; a mode change **clears** it;
      preview bytes **never** land in Mode 3's bucket.

---

## C. Validation

- [x] Unit: the fusion fast-path fires at 1 s; **vision-only still fires at 3 s**; a
      thump outside `LOUD_CORROBORATION_S` does **not** upgrade; corroboration latches
      across a quiet second; **`loud=False` throughout is byte-identical to today's
      behaviour** (the safety property from A3 — pin it explicitly).
      ✅ **DONE 2026-07-16 — 84 tests pass** (was 66; +12 fusion in `test_behaviour.py`,
      +2 payload, +4 relay). Written **before** the code, red first, per the TDD rule.
- [x] Unit: preview OFF by default; mode change clears it; preview bytes stay out of
      Mode 3's bucket; `_payload()` still carries no pixels.
      ✅ **DONE 2026-07-16 — `tests/test_relay_preview.py`, 17 tests**, written before
      the code. `test_raw_pixels_never_travel` needed **no change at all** — which is
      the evidence the separate-endpoint design was right rather than merely tidy.
- [ ] Browser (the standing rule — playwright-cli, load it and look): toggle ON → frame
      appears + banner + the byte counter jumps; toggle OFF → skeleton only, counter
      collapses; **Mode 3's own total unmoved by the whole exercise**.
- [ ] **Hardware, with a person**: clap at the moment of a controlled lie-down → fires
      in ~1 s with `thump +` in the reason. Lie down silently → still fires at 3 s.
      ⚠️ Fix framing **first** (SPEC-04 §8: camera metres back, full body, **side-on**)
      — and the preview from Part B is now the tool that makes that possible.
- [ ] **Hardware, deaf-board simulation**: unset the PulseAudio default source → Mode 3
      must degrade to today's 3 s vision-only rule, **not** stop alarming. This is A2's
      whole argument; if it is never tested, the argument was decoration.

---

## D. Open

- [ ] `FALL_HOLD_FAST_S` = 1 s is a **guess**, unlike `FALL_HOLD_S` = 3 s which was
      hardware-validated. It needs a bench pass. Too low and a thump + a stumble that
      is not a fall fires; the corroboration window is doing the real work of keeping
      it honest.
- [ ] Should the **loud threshold slider** show a live `audio_rms` readout in Mode 3 the
      way it effectively does in Modes 1/2? Ambient is 0.0105–0.0120 against a 0.05
      threshold; a student who cannot see the number is tuning blind.
- [ ] Does the preview want an **auto-off timer** (e.g. 2 min)? §B4's non-sticky rule
      covers the mode switch, but not a student who turns it on and simply forgets.
      Deferred: a timer that kills the view mid-experiment may be worse than the
      problem.
