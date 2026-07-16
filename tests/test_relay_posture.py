"""The relay's Mode 3 ingest (SPEC-01 §4.3, SPEC-02 §5) -- driven through the app.

Two things are pinned here that the bench cannot show you:

  * `sitting` must read `person-active`, not `quiet`. MoveNet introduced the
    label and the relay's mapping predates it, so a seated person would have
    been reported as an empty room -- visible on the dashboard only as a status
    word nobody is watching.
  * `/latest.jpg` must still 404 while a skeleton is streaming. Mode 3 sends
    keypoints now, and it would be easy to assume "richer payload" meant the
    image came back. It did not, and that is the privacy claim.
"""
from fastapi.testclient import TestClient

from relay.relay_server import app

client = TestClient(app)
AUTH = {"X-Device-Token": "tok_demo_bench01"}

KEYPOINTS = [[0.5 + i / 100, 0.4 + i / 100, 0.9] for i in range(17)]


def post(**over):
    body = {"posture": "standing", "abnormal": False, "reason": "",
            "keypoints": KEYPOINTS, "bbox": [0.4, 0.1, 0.2, 0.86],
            "score": 0.88, "backend": "movenet", "context": ""}
    body.update(over)
    return client.post("/ingest_posture", json=body, headers=AUTH)


def test_accepts_the_movenet_payload():
    r = post()
    assert r.status_code == 200
    assert r.json()["flag"] == "person-active"


def test_sitting_is_a_person_not_an_empty_room():
    assert post(posture="sitting").json()["flag"] == "person-active"


def test_absent_is_quiet():
    assert post(posture="absent", keypoints=None, bbox=None,
                score=None).json()["flag"] == "quiet"


def test_abnormal_wins_over_the_posture_label():
    """A fall is a fall even though the posture underneath it is `lying`."""
    r = post(posture="lying", abnormal=True, reason="upright→lying held 3s")
    assert r.json()["flag"] == "FALL?"


def test_latest_jpg_still_404s_while_a_skeleton_streams():
    """Keypoints travel; pixels do not. Mode 3's video panel stays empty."""
    post()
    assert client.get("/latest.jpg?device=bench01").status_code == 404


def test_keypointless_payload_still_accepted():
    """An `absent` second carries no skeleton -- the fields are optional and the
    relay must never assume they are there."""
    r = post(posture="absent", keypoints=None, bbox=None, score=None)
    assert r.status_code == 200


def test_bad_token_is_rejected():
    r = client.post("/ingest_posture", json={"posture": "standing"},
                    headers={"X-Device-Token": "nope"})
    assert r.status_code == 401
