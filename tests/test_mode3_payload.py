"""What Mode 3 is allowed to put on the wire (SPEC-01 §4.3, SPEC-04 §4).

This is the privacy contract as a test. Mode 3's whole claim is that it runs ML
on the Jetson and still sends less than Mode 2 -- "only the verdict, never
keypoints, never frames". That claim is one careless dict-splat away from being
false, and the failure is INVISIBLE at the bench: the dashboard renders exactly
the same whether or not a skeleton rode along in the payload. Nothing else in
the system would notice. So it is pinned here.

The load-bearing case is `test_pose_backend_keypoints_never_travel`: bgsub has
no keypoints to leak, so a payload builder that leaks them still looks correct
today and only starts leaking when SPEC-05 lands trt_pose.
"""
import json

from edge.mode3_posture import _payload

# SPEC-01 §4.3, exactly.
WIRE = {"posture", "abnormal", "reason", "torso_angle", "confidence",
        "backend", "context"}

# Things the estimator knows that must never leave the device.
FORBIDDEN = {"keypoints", "bbox", "aspect", "fill", "frames", "audio", "mask"}


def bgsub_result(posture="standing"):
    return {"posture": posture, "bbox": (10, 20, 30, 90), "aspect": 3.0,
            "fill": 0.11, "keypoints": None, "torso_angle": None}


def pose_result(posture="lying"):
    """What SPEC-05's trt_pose backend will return -- 18 keypoints and an angle."""
    return {"posture": posture, "bbox": (10, 20, 90, 30), "aspect": 0.33,
            "fill": 0.14,
            "keypoints": {str(i): (i * 3, i * 5) for i in range(18)},
            "torso_angle": 78.4, "confidence": 0.91}


VERDICT = {"abnormal": True, "reason": "upright→lying held 3s"}
CALM = {"abnormal": False, "reason": ""}


def test_payload_is_exactly_the_contract():
    assert set(_payload(bgsub_result(), CALM)) == WIRE


def test_bgsub_payload_leaks_nothing():
    p = _payload(bgsub_result(), CALM)
    assert FORBIDDEN.isdisjoint(p)


def test_pose_backend_keypoints_never_travel():
    """The one that matters. Even when the backend HAS a skeleton, the wire must
    not. Shipping keypoints to the laptop would repeat Mode 1's mistake in a new
    costume (SPEC-04 §4)."""
    p = _payload(pose_result(), VERDICT, backend="trt_pose")
    assert FORBIDDEN.isdisjoint(p)
    assert "keypoints" not in json.dumps(p)


def test_pose_backend_summary_fields_do_travel():
    """torso_angle and confidence are verdict-scale summaries, not raw signal --
    they are the two fields the contract adds for pose backends."""
    p = _payload(pose_result(), VERDICT, backend="trt_pose")
    assert p["torso_angle"] == 78.4
    assert p["confidence"] == 0.91


def test_bgsub_reports_pose_fields_as_none():
    p = _payload(bgsub_result(), CALM)
    assert p["torso_angle"] is None
    assert p["confidence"] is None


def test_verdict_fields_come_from_the_monitor():
    p = _payload(bgsub_result("lying"), VERDICT)
    assert p["abnormal"] is True
    assert p["reason"] == "upright→lying held 3s"
    assert p["posture"] == "lying"


def test_backend_name_is_reported():
    assert _payload(bgsub_result(), CALM, backend="bgsub")["backend"] == "bgsub"
    assert _payload(pose_result(), VERDICT, backend="trt_pose")["backend"] == "trt_pose"


def test_missing_optional_fields_do_not_crash():
    """SPEC-01 §5: downstream must treat the pose fields as optional, never
    assume. A backend that omits them entirely must not take the Jetson down."""
    p = _payload({"posture": "standing"}, CALM)
    assert p["torso_angle"] is None and p["confidence"] is None


def test_payload_is_json_serialisable_and_tiny():
    """Mode 3 must stay Mode 2-scale. If this ever fails, something big got in."""
    body = json.dumps(_payload(pose_result(), VERDICT, backend="trt_pose"))
    assert len(body.encode()) < 300
