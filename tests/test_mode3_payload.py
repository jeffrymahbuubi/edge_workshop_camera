"""What Mode 3 is allowed to put on the wire (SPEC-01 §4.3, SPEC-04 §4).

⚠️ THE CONTRACT CHANGED 2026-07-16 — read this before "fixing" a failure here.

This file used to assert the OPPOSITE: that keypoints must NEVER travel. That was
a deliberate, reasoned rule, and Jeffry deliberately reversed it when Mode 3
moved to MoveNet. The argument that won: ~1 KB of joint coordinates is not
Mode 1's mistake in a new costume -- Mode 1 shipped ~583 KB of recognisable
FACES; a skeleton is 17 numbers that cannot identify anyone, and it buys the
single best artefact in the workshop (a live stick figure that proves ML ran on
the edge). Mode A stays two orders of magnitude under Mode 1, so the bandwidth
lesson is intact and the privacy lesson gets *sharper*: pixels stayed home.

So the privacy line MOVED; it did not disappear. It is now exactly this:
**raw pixels never travel.** No frames, no JPEG, no mask, no audio buffer. That is
what `test_raw_pixels_never_travel` guards, and it is the load-bearing test here.

⚠️ IT MOVED A SECOND TIME -- 2026-07-16, SPEC-08. Two changes, and neither one
touches the line above:

1. **Sound is fused in** (SPEC-08 Part A). `audio_rms` + `loud_flag` now travel:
   two scalars, ~20 B, exactly the argument Mode 2 has always made. The mic's
   SAMPLES still never leave -- `test_audio_rms_is_a_number_not_a_recording`.
2. **Mode B was argued with, and it WON -- narrowly** (SPEC-08 Part B). Pixels may
   now travel from Mode 3, but ONLY behind an explicit, default-OFF, non-sticky
   toggle, on a SEPARATE endpoint with a SEPARATE payload and its own byte bucket.
   That separation is the whole point: **this file's contract stays absolute.**
   No pixel may ever enter `_payload()`. If you are here because you want to add
   an `image` field to the posture payload, the answer is still no -- the preview
   is deliberately a different thing rather than a field someone can quietly add.
"""
import json

from edge.mode3_posture import _payload

# SPEC-01 §4.3, exactly. `audio_rms` + `loud_flag` joined 2026-07-16 (SPEC-08 §A5).
WIRE = {"posture", "abnormal", "reason", "keypoints", "bbox", "score",
        "backend", "context", "audio_rms", "loud_flag"}

# Raw signal. The one thing that must never leave the Jetson. These are KEYS.
FORBIDDEN = {"frames", "audio", "image", "jpeg", "mask"}

# ⚠️ A SUBSET of FORBIDDEN, and the difference is deliberate -- do not "tidy" it
# back into one set.
#
# The pixel guard below greps the serialised JSON for these words, which is
# stronger than checking keys (it catches a frame smuggled inside a nested dict).
# But "audio" cannot be greped for any more: `audio_rms` legitimately CONTAINS
# it, and SPEC-08 §A5 put that field on the wire on purpose. A substring test
# would fail on a field that is correct.
#
# So `audio` stays a forbidden KEY -- no raw buffer -- while the scalar RMS
# derived from it is allowed, exactly as Mode 2 has always argued. What replaces
# the lost substring check is `test_audio_rms_is_a_number_not_a_recording`.
FORBIDDEN_IN_BODY = {"frames", "image", "jpeg", "mask"}

# What the mic contributed this second: two scalars, never samples.
QUIET = {"audio_rms": 0.0118, "loud_flag": False}
THUMP = {"audio_rms": 0.1740, "loud_flag": True}


def movenet_result(posture="lying"):
    """What pose.py ACTUALLY returns: 17 COCO keypoints, normalised 0..1.

    The coordinates are deliberately full-precision floats, because that is what
    `float(x)` on a TFLite output gives you. Using tidy 2-decimal values here
    would make the size test below pass trivially and hide the very thing it is
    supposed to measure.
    """
    return {"posture": posture, "bbox": [0.14, 0.68, 0.82, 0.18],
            "keypoints": [[0.5123456789012345 + i / 97, 0.4987654321098765 + i / 89,
                           0.9123456789012345] for i in range(17)],
            "score": 0.88}


VERDICT = {"abnormal": True, "reason": "upright→lying held 3s"}
CALM = {"abnormal": False, "reason": ""}


def test_payload_is_exactly_the_contract():
    assert set(_payload(movenet_result(), VERDICT, QUIET)) == WIRE


def test_raw_pixels_never_travel():
    """THE load-bearing test. Keypoints are allowed now; pixels are not.

    Mode 3 runs ML on the device precisely so the camera image can stay there.
    A frame, a JPEG or an audio buffer appearing here would end that claim -- and
    the failure is INVISIBLE at the bench, because the dashboard renders the same
    either way. Nothing else in the system would notice.
    """
    p = _payload(movenet_result(), VERDICT, QUIET)
    assert FORBIDDEN.isdisjoint(p)
    body = json.dumps(p)
    for banned in FORBIDDEN_IN_BODY:
        assert banned not in body


def test_audio_rms_is_a_number_not_a_recording():
    """SPEC-08 §A5: Mode 3 hears, but it never SENDS what it heard.

    This replaces the substring guard on "audio" that `audio_rms` made
    impossible (see FORBIDDEN_IN_BODY). The distinction is the same one Mode 2
    has always rested on: an RMS is ~20 B of energy, a recording is the room's
    conversation. If this field ever becomes a list, someone has put a microphone
    on the LAN and the workshop's privacy claim is dead -- and, exactly like the
    frame leak, NOTHING at the bench would notice.
    """
    for audio in (QUIET, THUMP):
        p = _payload(movenet_result(), VERDICT, audio)
        assert isinstance(p["audio_rms"], float)
        assert isinstance(p["loud_flag"], bool)


def test_the_thump_travels_so_the_dashboard_can_show_the_fusion():
    """Both scalars reach the relay -- SPEC-08 §A4 wants fusion watchable."""
    p = _payload(movenet_result(), VERDICT, THUMP)
    assert p["loud_flag"] is True
    assert p["audio_rms"] == 0.174


def test_no_mode2_VIDEO_detector_rides_along():
    """⚠️ THE BOUNDARY MOVED 2026-07-16 (SPEC-08 §A5) -- read before "fixing".

    This test used to forbid `audio_rms`/`loud_flag` too. Jeffry reversed that:
    the workshop's theme is MULTI-MODAL Posture Recognition and Mode 3 was the
    only uni-modal mode. Sound is now fused in (as corroboration, never a gate).

    What did NOT change is the video half. Mode 2's frame-differencing answers
    Mode 2's question ("did motion stop?") and Mode 3 answers a different one
    ("was this person upright, and are they now lying?"). Shipping these would
    re-couple the modes and resurrect the vestigial-CPU bug SPEC-04 §3.1 killed --
    Mode 3 once ran frame differencing every second for a number nothing read.

    `fall_suspected` is forbidden for a sharper reason: it is MODE 2's VERDICT.
    Two different fall verdicts in one payload is not multi-modal, it is
    ambiguous -- the relay would not know which one raises the alarm.
    """
    p = _payload(movenet_result(), VERDICT, QUIET)
    for mode2_video_field in ("motion_level", "motion_flag", "n_blobs",
                              "fall_suspected"):
        assert mode2_video_field not in p


def test_keypoints_do_travel_now_mode_a():
    """The reversal, pinned. Mode A's whole point is the skeleton."""
    p = _payload(movenet_result(), VERDICT, QUIET)
    assert p["keypoints"] is not None
    assert len(p["keypoints"]) == 17
    assert "keypoints" in json.dumps(p)


def test_mode_a_payload_stays_two_orders_under_mode_1():
    """~0.5 KB of joints vs Mode 1's ~583 KB of faces IS the bandwidth argument.

    If this ever fails, the skeleton stopped being cheap and the lesson breaks.
    """
    body = json.dumps(_payload(movenet_result(), VERDICT, QUIET))
    assert len(body.encode()) < 1000


def test_keypoints_are_rounded_onto_the_wire():
    """Full-precision floats would spend ~19 chars per number for a third of a
    pixel of accuracy -- roughly 3x the payload, for nothing visible."""
    p = _payload(movenet_result(), VERDICT, QUIET)
    for x, y, s in p["keypoints"]:
        assert len(str(x).split(".")[-1]) <= 3
        assert len(str(y).split(".")[-1]) <= 3
        assert len(str(s).split(".")[-1]) <= 3


def test_rounding_does_not_move_a_joint_visibly():
    """0.001 of a 320px frame is 0.32px -- under the width of the drawn line."""
    raw = movenet_result()
    p = _payload(raw, VERDICT, QUIET)
    for (rx, ry, _), (wx, wy, _) in zip(raw["keypoints"], p["keypoints"]):
        assert abs(rx - wx) * 320 < 0.5
        assert abs(ry - wy) * 240 < 0.5


def test_bbox_stays_normalised():
    """pose.py already emits 0..1; the wire carries it through untouched so the
    dashboard can draw it against a canvas without knowing the frame size."""
    p = _payload(movenet_result(), VERDICT, QUIET)
    assert all(0.0 <= v <= 1.0 for v in p["bbox"])


def test_verdict_fields_come_from_the_monitor():
    p = _payload(movenet_result("lying"), VERDICT, QUIET)
    assert p["abnormal"] is True
    assert p["reason"] == "upright→lying held 3s"
    assert p["posture"] == "lying"


def test_backend_is_reported_as_movenet():
    assert _payload(movenet_result(), VERDICT, QUIET)["backend"] == "movenet"


def test_missing_optional_fields_do_not_crash():
    """SPEC-01 §5: downstream treats these as optional and never assumes. An
    estimator that sees no person returns no box -- that must not crash."""
    p = _payload({"posture": "absent"}, CALM, QUIET)
    assert p["keypoints"] is None and p["bbox"] is None and p["score"] is None


def test_payload_is_json_serialisable():
    json.dumps(_payload(movenet_result(), VERDICT, QUIET))
