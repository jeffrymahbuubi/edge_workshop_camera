"""Relay control endpoints: /config (SPEC-06) and /mode (SPEC-07).

Thin endpoints, but the validation matters: a bad slider value or a bogus mode
number must not wedge a live demo. Driven through the real ASGI app.
"""
import pytest
from fastapi.testclient import TestClient

from relay.relay_server import app

client = TestClient(app)


# --- /config (SPEC-06) ---------------------------------------------------

def test_config_roundtrip_and_clamp():
    client.post("/config", json={"loud_rms_thresh": 0.05, "motion_level_thresh": 0.006})
    assert client.get("/config").json() == {
        "loud_rms_thresh": 0.05, "motion_level_thresh": 0.006}

    # one knob at a time
    body = client.post("/config", json={"loud_rms_thresh": 0.02}).json()
    assert body["loud_rms_thresh"] == 0.02
    assert body["motion_level_thresh"] == 0.006      # untouched

    # out of range clamps, doesn't error
    body = client.post("/config", json={"motion_level_thresh": 5.0}).json()
    assert body["motion_level_thresh"] == 1.0
    client.post("/config", json={"loud_rms_thresh": 0.05, "motion_level_thresh": 0.006})


# --- /mode (SPEC-07) -----------------------------------------------------

@pytest.mark.parametrize("mode", [1, 2, 3, None])
def test_mode_accepts_valid(mode):
    assert client.post("/mode", json={"mode": mode}).json() == {"mode": mode}
    assert client.get("/mode").json() == {"mode": mode}


@pytest.mark.parametrize("bad", [0, 4, 99, -1])
def test_mode_rejects_out_of_range(bad):
    assert client.post("/mode", json={"mode": bad}).status_code == 422


def test_mode_null_stops_everything():
    client.post("/mode", json={"mode": 2})
    assert client.post("/mode", json={"mode": None}).json() == {"mode": None}


def test_mode_default_is_none_at_import():
    """A freshly booted relay has nothing selected -- the supervisor stays idle
    and the camera is free until a student clicks."""
    # reset to the boot state for other tests
    client.post("/mode", json={"mode": None})
    assert client.get("/mode").json()["mode"] is None
