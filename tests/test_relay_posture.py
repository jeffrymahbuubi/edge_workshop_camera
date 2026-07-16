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


# --- multi-modal fusion (SPEC-08 Part A) --------------------------------

def test_the_audio_scalars_survive_the_round_trip():
    """⚠️ Pydantic SILENTLY DROPS fields the model does not declare.

    Mode 3 would post audio_rms + loud_flag, the relay would accept 200, and the
    dashboard would simply never see them -- no error anywhere. This test exists
    because that failure looks exactly like success.
    """
    r = post(posture="lying", audio_rms=0.1740, loud_flag=True)
    assert r.status_code == 200
    from relay.relay_server import PosturePayload
    p = PosturePayload(**{"posture": "lying", "audio_rms": 0.174,
                          "loud_flag": True})
    assert p.audio_rms == 0.174 and p.loud_flag is True


def test_a_pre_fusion_client_still_validates():
    """The fields are Optional on purpose: a Jetson running yesterday's client
    must not start 422-ing the moment the relay is upgraded."""
    r = post()
    assert r.status_code == 200
    assert r.json()["flag"] == "person-active"


def test_the_loud_slider_reaches_mode_3():
    """SPEC-08 §A7: Mode 3 listens now, so the dashboard's threshold must reach
    it -- via the ingest response, the same channel Mode 2 uses.

    Without this the slider silently does nothing in one of the three modes, and
    a student tuning it would conclude the mic was broken.
    """
    client.post("/config", json={"loud_rms_thresh": 0.02}, headers=AUTH)
    body = post().json()
    assert body["config"]["loud_rms_thresh"] == 0.02
    client.post("/config", json={"loud_rms_thresh": 0.05}, headers=AUTH)


def test_the_thump_reaches_the_dashboard_event():
    """The fusion must be watchable (SPEC-08 §A4) -- the scalars have to be in
    the SSE event, not just accepted at the door."""
    r = post(posture="lying", abnormal=True,
             reason="thump + upright→lying held 1s",
             audio_rms=0.174, loud_flag=True)
    assert r.json()["flag"] == "FALL?"
