"""The Mode 3 setup preview (SPEC-08 Part B) -- the ONE way pixels may leave.

⚠️ READ THIS BEFORE RELAXING ANYTHING HERE.

Mode 3's whole argument is that the camera image stays on the Jetson. SPEC-04 §4.1
made that absolute ("RAW PIXELS NEVER TRAVEL") and rejected the colleague's Mode B
for breaking it. Jeffry reversed that on 2026-07-16 -- but narrowly, and every
narrowing is a test in this file:

  * DEFAULT OFF, and NOT STICKY. Mode 3's default behaviour -- what the workshop
    demonstrates, what the ratio quotes -- is unchanged and pure. A student who
    leaves the preview on must not silently teach the next student that Mode 3
    costs 583 KB/s.
  * SEPARATE ENDPOINT, SEPARATE PAYLOAD. No pixel may ever enter /ingest_posture's
    body -- see test_mode3_payload.py. The preview is deliberately a DIFFERENT
    THING, not a field someone can quietly add to the posture payload.
  * SEPARATE BYTE BUCKET. Mode 3's 562 B stays quotable and the ratio stays honest.
    Showing the two numbers side by side is the entire point (SPEC-08 §B3): the
    student moves the number with their own hand and watches it collapse back.

The failure mode this guards is INVISIBLE at the bench: the dashboard renders a
frame identically whether it arrived honestly or wrecked the accounting behind it.
"""
import base64

import pytest
from fastapi.testclient import TestClient

from relay.relay_server import app, _preview, _desired_mode

client = TestClient(app)
AUTH = {"X-Device-Token": "tok_demo_bench01"}

# The relay stores JPEG bytes verbatim and never decodes them, so a stub is
# honest here -- decoding is the browser's job.
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0-not-a-real-jpeg-but-the-relay-never-looks")


@pytest.fixture(autouse=True)
def clean_state():
    """Module-level relay state leaks between tests -- reset it explicitly.

    Without this, `test_a_mode_change_clears_the_preview` would pass purely
    because an earlier test happened to leave the preview off.
    """
    _preview["camera"] = False
    _desired_mode["mode"] = None
    client.post("/reset")
    yield
    _preview["camera"] = False
    _desired_mode["mode"] = None
    client.post("/reset")


def post_posture(**over):
    body = {"posture": "standing", "abnormal": False, "reason": "",
            "keypoints": None, "bbox": None, "score": None,
            "audio_rms": 0.0118, "loud_flag": False,
            "backend": "movenet", "context": ""}
    body.update(over)
    return client.post("/ingest_posture", json=body, headers=AUTH)


def post_preview(image=None):
    return client.post("/ingest_preview",
                       json={"image": (image or JPEG).decode()}, headers=AUTH)


# --- default OFF, and not sticky (SPEC-08 §B4) --------------------------

def test_preview_defaults_off():
    """The workshop's default must be the pure one."""
    assert client.get("/preview").json()["camera"] is False


def test_preview_can_be_turned_on_and_off():
    assert client.post("/preview", json={"camera": True}).json()["camera"] is True
    assert client.get("/preview").json()["camera"] is True
    assert client.post("/preview", json={"camera": False}).json()["camera"] is False


def test_a_mode_change_clears_the_preview():
    """NOT STICKY -- the toggle cannot outlive the Mode 3 session that set it.

    Every path into Mode 3 goes through POST /mode, so clearing here is what
    makes "default OFF" true on arrival rather than only on first boot.
    """
    client.post("/preview", json={"camera": True})
    client.post("/mode", json={"mode": 2})
    assert client.get("/preview").json()["camera"] is False


def test_even_reselecting_mode_3_clears_the_preview():
    """A student re-entering Mode 3 gets the pure default, every time."""
    client.post("/mode", json={"mode": 3})
    client.post("/preview", json={"camera": True})
    client.post("/mode", json={"mode": 3})
    assert client.get("/preview").json()["camera"] is False


# --- pixels may not travel unless explicitly enabled ---------------------

def test_a_frame_is_REFUSED_while_the_preview_is_off():
    """Defence in depth, and it is not theatre.

    The client polls the flag, so this should never fire -- but "should never"
    is how a raw frame ends up on the LAN. If the relay accepted frames whenever
    they arrived, the toggle would be a suggestion rather than a gate.
    """
    r = post_preview()
    assert r.status_code == 403
    assert client.get("/latest.jpg?device=bench01").status_code == 404


def test_a_frame_is_served_while_the_preview_is_on():
    client.post("/preview", json={"camera": True})
    assert post_preview().status_code == 200
    r = client.get("/latest.jpg?device=bench01")
    assert r.status_code == 200
    assert r.content.startswith(b"\xff\xd8")


def test_turning_the_preview_off_drops_the_frame_immediately():
    """Toggling off must blank the panel NOW, not on the next posture tick.

    A face lingering after the student turned pixels off would contradict the
    exact claim the panel makes at that moment.
    """
    client.post("/preview", json={"camera": True})
    post_preview()
    client.post("/preview", json={"camera": False})
    assert client.get("/latest.jpg?device=bench01").status_code == 404


# --- the endpoint fight SPEC-04 §6 already paid for ---------------------

def test_a_posture_tick_does_NOT_wipe_the_preview_frame():
    """⚠️ THE bug that killed the MJPEG-alongside-/ingest_raw idea.

    /ingest_posture calls _latest_jpeg.pop() every tick to clear stale Mode 1
    faces. With a preview live, that pop would delete the frame one tick after it
    arrived -- the panel would flicker or stay black, and it would look like a
    camera fault rather than a design collision. SPEC-04 §6 recorded this; it must
    not be re-derived at the bench.
    """
    client.post("/preview", json={"camera": True})
    post_preview()
    post_posture()                                    # the tick that used to wipe it
    assert client.get("/latest.jpg?device=bench01").status_code == 200


def test_posture_STILL_wipes_a_stale_frame_when_the_preview_is_off():
    """The pop must not simply be deleted -- with the preview off it is still the
    thing that stops a Mode 1 face lingering into Mode 3."""
    client.post("/preview", json={"camera": True})
    post_preview()
    client.post("/preview", json={"camera": False})
    client.post("/preview", json={"camera": True})    # frame already dropped
    post_posture()
    assert client.get("/latest.jpg?device=bench01").status_code == 404


# --- the accounting stays honest (SPEC-08 §B4) --------------------------

def test_preview_bytes_never_land_in_mode_3s_bucket():
    """Mode 3's 562 B is the number the whole workshop quotes. If a preview
    frame landed in it, Mode 3 would appear to cost ~583 KB/s and the mode's
    entire argument would evaporate -- silently, since the dashboard would just
    show a bigger number and nobody would know it was wrong.
    """
    client.post("/preview", json={"camera": True})
    post_posture()
    before = client.get("/health").status_code      # touch nothing
    from relay.relay_server import bandwidth
    mode3_before = bandwidth.snapshot("bench01")["mode3_total"]
    post_preview()
    post_preview()
    snap = bandwidth.snapshot("bench01")
    assert snap["mode3_total"] == mode3_before      # untouched by pixels
    assert snap["preview_total"] > 0                # but the cost IS recorded
    assert before == 200


def test_the_preview_cost_is_VISIBLE_not_hidden():
    """SPEC-08 §B3: the exception is the lesson. Hiding the cost would waste it --
    the student must be able to watch the number jump and collapse."""
    client.post("/preview", json={"camera": True})
    post_preview()
    from relay.relay_server import bandwidth
    snap = bandwidth.snapshot("bench01")
    assert snap["preview_total"] > 0
    assert "preview_bps" in snap


def test_the_preview_never_becomes_the_live_mode():
    """⚠️ live_mode() does int(mode_name[-1]) -- "preview"[-1] is "w".

    Beyond the crash: the relay is in Mode 3, and a preview frame must never flip
    the badge to Mode 1 or corrupt the Mode 1 totals behind the ratio.
    """
    client.post("/preview", json={"camera": True})
    post_posture()
    post_preview()
    from relay.relay_server import bandwidth
    assert bandwidth.live_mode("bench01") == 3


def test_preview_does_not_disturb_the_ratio():
    """The ratio is mode1/mode2. Pixels sent for setup are neither."""
    from relay.relay_server import bandwidth
    client.post("/preview", json={"camera": True})
    post_preview()
    assert bandwidth.snapshot("bench01")["ratio"] is None


def test_reset_clears_the_preview_frame_and_its_bytes():
    client.post("/preview", json={"camera": True})
    post_preview()
    client.post("/reset")
    from relay.relay_server import bandwidth
    assert bandwidth.snapshot("bench01")["preview_total"] == 0
    assert client.get("/latest.jpg?device=bench01").status_code == 404


# --- auth ---------------------------------------------------------------

def test_bad_token_cannot_push_pixels():
    client.post("/preview", json={"camera": True})
    r = client.post("/ingest_preview", json={"image": JPEG.decode()},
                    headers={"X-Device-Token": "nope"})
    assert r.status_code == 401


# --- the dashboard's modules -------------------------------------------

def test_the_three_dashboard_modules_are_served():
    """app.js imports content.js and compare.js. A 404 on either is a blank page
    with one console line -- and the relay's own tests would not have noticed."""
    for name in ("app", "content", "compare"):
        r = client.get(f"/{name}.js")
        assert r.status_code == 200, name
        assert "javascript" in r.headers["content-type"]


def test_the_js_route_is_a_whitelist_not_a_file_server():
    """⚠️ `name` comes straight off the URL. Serving WEB_DIR/f"{name}.js"
    unchecked would turn a convenience route into a file-read primitive."""
    for evil in ("../relay/relay_server", "..%2f..%2fsecrets", "unknown"):
        assert client.get(f"/{evil}.js").status_code == 404


# --- what the Jetson is told (SPEC-08 §B5) ------------------------------

def test_the_flag_reaches_mode_3_on_the_ingest_response():
    """Relay holds the state, the Jetson polls it -- same shape as SPEC-06/07,
    and it crosses the firewall exactly like the ingest path already does. If
    this key vanished, the toggle would move on screen and nothing would happen.
    """
    assert post_posture().json()["preview"] is False
    client.post("/preview", json={"camera": True})
    assert post_posture().json()["preview"] is True


def test_mode_3_defaults_to_no_pixels_if_the_key_is_missing():
    """The client does resp.get("preview", False) -- an older relay means "no
    pixels", which is the safe direction to fail."""
    from edge.mode3_posture import _flush
    preview = {"on": True}

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"flag": "quiet"}        # no `preview` key

    import edge.mode3_posture as m3
    real_post = m3.requests.post
    m3.requests.post = lambda *a, **k: FakeResp()
    try:
        from collections import deque
        box = deque([{"posture": "absent", "abnormal": False, "reason": "",
                      "keypoints": None, "bbox": None, "score": None,
                      "audio_rms": 0.01, "loud_flag": False,
                      "backend": "movenet", "context": ""}])
        _flush(box, "http://x/ingest_posture", {}, {"loud_rms_thresh": None},
               preview)
    finally:
        m3.requests.post = real_post
    assert preview["on"] is False
