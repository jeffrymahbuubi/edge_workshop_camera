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
**raw pixels never travel.** No frames, no audio, no JPEG, no mask. That is what
`test_raw_pixels_never_travel` guards, and it is now the load-bearing test in this
file. The colleague's Mode B (MODE3_SEND_IMAGE=1, ~15 KB JPEG) was NOT adopted
for this reason -- if it ever is, this test is the one that must be argued with.
"""
import json

from edge.mode3_posture import _payload

# SPEC-01 §4.3, exactly.
WIRE = {"posture", "abnormal", "reason", "keypoints", "bbox", "score",
        "backend", "context"}

# Raw signal. The one thing that must never leave the Jetson.
FORBIDDEN = {"frames", "audio", "image", "jpeg", "mask"}


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
    assert set(_payload(movenet_result(), VERDICT)) == WIRE


def test_raw_pixels_never_travel():
    """THE load-bearing test. Keypoints are allowed now; pixels are not.

    Mode 3 runs ML on the device precisely so the camera image can stay there.
    A frame, a JPEG or an audio buffer appearing here would end that claim -- and
    the failure is INVISIBLE at the bench, because the dashboard renders the same
    either way. Nothing else in the system would notice.
    """
    p = _payload(movenet_result(), VERDICT)
    assert FORBIDDEN.isdisjoint(p)
    body = json.dumps(p)
    for banned in FORBIDDEN:
        assert banned not in body


def test_no_mode2_feature_vector_rides_along():
    """Mode 3 is keypoints. It must not grow Mode 2's detector on the wire.

    Mode 3 answers "was this person upright, and are they now lying?"; Mode 2
    answers "was there a thump, and did motion stop?". Shipping Mode 2's fields
    from Mode 3 would blur two different questions into one payload and quietly
    re-couple the modes -- which is exactly what was cleaned out of this client.
    """
    p = _payload(movenet_result(), VERDICT)
    for mode2_field in ("motion_level", "motion_flag", "n_blobs",
                        "audio_rms", "loud_flag", "fall_suspected"):
        assert mode2_field not in p


def test_keypoints_do_travel_now_mode_a():
    """The reversal, pinned. Mode A's whole point is the skeleton."""
    p = _payload(movenet_result(), VERDICT)
    assert p["keypoints"] is not None
    assert len(p["keypoints"]) == 17
    assert "keypoints" in json.dumps(p)


def test_mode_a_payload_stays_two_orders_under_mode_1():
    """~0.5 KB of joints vs Mode 1's ~583 KB of faces IS the bandwidth argument.

    If this ever fails, the skeleton stopped being cheap and the lesson breaks.
    """
    body = json.dumps(_payload(movenet_result(), VERDICT))
    assert len(body.encode()) < 1000


def test_keypoints_are_rounded_onto_the_wire():
    """Full-precision floats would spend ~19 chars per number for a third of a
    pixel of accuracy -- roughly 3x the payload, for nothing visible."""
    p = _payload(movenet_result(), VERDICT)
    for x, y, s in p["keypoints"]:
        assert len(str(x).split(".")[-1]) <= 3
        assert len(str(y).split(".")[-1]) <= 3
        assert len(str(s).split(".")[-1]) <= 3


def test_rounding_does_not_move_a_joint_visibly():
    """0.001 of a 320px frame is 0.32px -- under the width of the drawn line."""
    raw = movenet_result()
    p = _payload(raw, VERDICT)
    for (rx, ry, _), (wx, wy, _) in zip(raw["keypoints"], p["keypoints"]):
        assert abs(rx - wx) * 320 < 0.5
        assert abs(ry - wy) * 240 < 0.5


def test_bbox_stays_normalised():
    """pose.py already emits 0..1; the wire carries it through untouched so the
    dashboard can draw it against a canvas without knowing the frame size."""
    p = _payload(movenet_result(), VERDICT)
    assert all(0.0 <= v <= 1.0 for v in p["bbox"])


def test_verdict_fields_come_from_the_monitor():
    p = _payload(movenet_result("lying"), VERDICT)
    assert p["abnormal"] is True
    assert p["reason"] == "upright→lying held 3s"
    assert p["posture"] == "lying"


def test_backend_is_reported_as_movenet():
    assert _payload(movenet_result(), VERDICT)["backend"] == "movenet"


def test_missing_optional_fields_do_not_crash():
    """SPEC-01 §5: downstream treats these as optional and never assumes. An
    estimator that sees no person returns no box -- that must not crash."""
    p = _payload({"posture": "absent"}, CALM)
    assert p["keypoints"] is None and p["bbox"] is None and p["score"] is None


def test_payload_is_json_serialisable():
    json.dumps(_payload(movenet_result(), VERDICT))
