"""The posture backend contract (SPEC-01 §5) -- shape only, no hardware.

These tests pin the SHAPE, not the labels. Whether a given frame reads `lying`
or `standing` is a threshold question that only a real camera in a real room can
answer (SPEC-04 §6, the bench protocol). What can be pinned here is that every
backend returns the same keys, so downstream never branches on backend name --
the thing that has to hold for SPEC-05 to swap trt_pose in without rework.
"""
import numpy as np
import pytest

from common.config import FRAME_H, FRAME_W
from edge.posture import BgSubPosture, get_posture_estimator

CONTRACT = {"posture", "bbox", "aspect", "fill", "keypoints", "torso_angle"}


def blank():
    return np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)


def with_box(x, y, w, h):
    f = blank()
    f[y:y + h, x:x + w] = 255
    return f


def test_empty_scene_has_the_full_contract():
    """Even the early `absent` return -- the one that fires before any contour
    exists -- must carry the pose fields, or downstream hits a KeyError only on
    an empty room."""
    est = BgSubPosture()
    assert set(est.estimate(blank())) == CONTRACT


def test_below_threshold_return_has_the_full_contract():
    """The second `absent` return: a blob too small to be a person."""
    est = BgSubPosture()
    for _ in range(5):
        est.estimate(blank())
    r = est.estimate(with_box(0, 0, 4, 4))       # far under MIN_FG_FRACTION
    assert set(r) == CONTRACT


def test_detected_person_return_has_the_full_contract():
    est = BgSubPosture()
    for _ in range(30):                          # let MOG2 learn the empty scene
        est.estimate(blank())
    r = est.estimate(with_box(40, 40, 120, 160))
    assert set(r) == CONTRACT


@pytest.mark.parametrize("frame", [blank(), with_box(40, 40, 120, 160)])
def test_bgsub_reports_pose_fields_as_none(frame):
    """SPEC-01 §5: bgsub keeps the original 4 fields and reports the pose fields
    as None -- present but empty, never absent."""
    est = BgSubPosture()
    r = est.estimate(frame)
    assert r["keypoints"] is None
    assert r["torso_angle"] is None


def test_posture_label_is_always_from_the_contract():
    est = BgSubPosture()
    for _ in range(30):
        est.estimate(blank())
    for frame in (blank(), with_box(40, 40, 120, 160), with_box(20, 100, 200, 40)):
        assert est.estimate(frame)["posture"] in {
            "standing", "walking", "lying", "absent"}


def test_backend_switch_still_works():
    """SPEC-04 §3: keep get_posture_estimator() and POSTURE_BACKEND exactly as
    the colleague built them -- that switch IS the demo."""
    assert isinstance(get_posture_estimator("bgsub"), BgSubPosture)


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        get_posture_estimator("nonsense")


def test_trt_backend_is_still_an_honest_stub():
    """SPEC-04 §3 / SPEC-05: the trt backend must keep refusing loudly until the
    ML actually exists. A silent fallback to bgsub here would make the workshop's
    central contrast a lie."""
    with pytest.raises(NotImplementedError):
        get_posture_estimator("trt")
