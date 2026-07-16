"""Cloud relay server (camera + audio).

Runs on the STUDENT LAPTOP -- the "cloud" side of the edge/cloud split. The
Jetson is the sensing edge and points RELAY_URL here across the LAN cable.

Security model is identical to the PPG version: the relay holds any real API
key server-side; devices carry only a revocable token.

Endpoints (ingest endpoints require header X-Device-Token):
  POST /ingest_raw       <- Mode 1 sends base64 JPEG frames + audio here
  POST /ingest_features  <- Mode 2 sends the small feature vector here
  POST /ingest_posture   <- Mode 3 sends posture + abnormal verdict here
  GET  /events           -> SSE stream for the dashboard
  GET  /latest.jpg       -> most recent Mode 1 frame (404 in Modes 2/3 -- by design)
  POST /reset            -> clear byte totals
  GET  /health
"""
import asyncio
import base64
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from common.codec import decode_frame, decode_audio
from common.config import LOUD_RMS_THRESH, MOTION_LEVEL_THRESH
from common.features import extract_features
from relay.bandwidth import BandwidthTracker

app = FastAPI(title="Camera Workshop Relay")

# The dashboard is served by the LAPTOP, never the Jetson (Role A). Assets are
# vendored locally -- the workshop LAN has no internet.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/vendor", StaticFiles(directory=WEB_DIR / "vendor"), name="vendor")

DEVICE_TOKENS = {
    "tok_demo_bench01": {"device": "bench01", "active": True},
    "tok_demo_bench02": {"device": "bench02", "active": True},
}

_calls = defaultdict(deque)
RATE_LIMIT, WINDOW_S = 300, 60

# remember each device's last motion state, for the fusion rule in Mode 1
_last_motion = defaultdict(bool)

# Live-tunable fall thresholds (SPEC-06). Seeded from the boss's reference
# constants, adjustable at runtime from the dashboard. Mode 1 (features computed
# here) applies them directly; Mode 2 pulls them back in each ingest response and
# applies them ON THE EDGE next tick, so the Jetson stays the one computing the
# fusion -- only the numbers are fed from the dashboard.
_live_cfg = {
    "loud_rms_thresh": LOUD_RMS_THRESH,
    "motion_level_thresh": MOTION_LEVEL_THRESH,
}
# Sane bounds so a stray slider value can't wedge the demo.
_CFG_BOUNDS = {"loud_rms_thresh": (0.0, 1.0), "motion_level_thresh": (0.0, 1.0)}

# Which mode the student has selected from the dashboard (SPEC-07). A supervisor
# on the Jetson polls GET /mode and starts/stops the matching client -- so the
# THREE separate programs stay separate (the boss's structure), and the button
# just picks which one runs. None = nothing selected / all stopped.
_desired_mode = {"mode": None}          # 1 | 2 | 3 | None

LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5")

# --- dashboard state -------------------------------------------------------
bandwidth = BandwidthTracker()

# Last 60 s per device, replayed to each new SSE client. Students open the
# dashboard mid-demo and refresh constantly; without this every one of them
# starts at an empty chart and misses the fall that just happened.
HISTORY_S = 60
_history = defaultdict(lambda: deque(maxlen=HISTORY_S))

# Most recent Mode 1 frame per device, as raw JPEG bytes.
# In Modes 2/3 this stays None and /latest.jpg returns 404 -- that is not a
# failure, it is the privacy lesson: no image ever crossed the LAN, so there is
# nothing to show.
_latest_jpeg = {}

# One queue per connected browser. A single shared generator would deadlock the
# second client.
_subscribers = set()


def auth(token: str):
    info = DEVICE_TOKENS.get(token)
    if not info or not info["active"]:
        raise HTTPException(401, "invalid or revoked device token")
    return info


def rate(device: str):
    now = time.time()
    q = _calls[device]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "rate limit exceeded")
    q.append(now)


def flag_for(feats) -> str:
    """Map features to the caregiver-facing flag.

    Lifted out of /ingest_features so BOTH modes can use it. Previously this
    lived inline in the Mode 2 handler only, which left Mode 1 with no flag to
    display -- one dashboard serving both modes needs one mapping.
    """
    if feats.get("fall_suspected"):
        return "FALL?"
    return "person-active" if feats.get("motion_flag") else "quiet"


def _content_length(request: Request):
    """Bytes the LAN actually carried. See bandwidth.py for why not len(body)."""
    try:
        return int(request.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        return 0


async def _publish(event: dict):
    """Record in history and fan out to every connected browser."""
    _history[event["device"]].append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass          # a slow browser must never stall ingest


def _event(device, mode, flag, feats=None, posture=None):
    return {
        "t": time.time(),
        "device": device,
        "mode": mode,
        "flag": flag,
        "feats": feats,
        "posture": posture,
        "bandwidth": bandwidth.snapshot(device),
    }


class RawBatch(BaseModel):
    frames: List[str]          # base64 JPEGs, one second's worth
    audio: str                 # base64 int16 audio for this second
    t_start: float


class FeaturePayload(BaseModel):
    motion_level: Optional[float] = None
    n_blobs: Optional[int] = None
    motion_flag: Optional[bool] = None
    audio_rms: Optional[float] = None
    loud_flag: Optional[bool] = None
    fall_suspected: Optional[bool] = None
    context: str = ""


class PosturePayload(BaseModel):
    posture: str                       # standing|walking|sitting|lying|absent
    abnormal: bool = False
    reason: str = ""
    # The skeleton (SPEC-01 §4.3, Mode A). 17 COCO keypoints as [x, y, score],
    # normalised 0..1. These DO cross the LAN by decision: ~1 KB of joints is not
    # Mode 1's ~583 KB of faces, and it is what the dashboard draws. Raw pixels
    # still never travel -- there is deliberately no `image` field here.
    keypoints: Optional[List[List[float]]] = None
    bbox: Optional[List[float]] = None          # [x, y, w, h], normalised 0..1
    score: Optional[float] = None               # mean confidence of trusted joints
    backend: str = "movenet"
    context: str = ""


class ConfigPatch(BaseModel):
    """Live fall-threshold tweak from the dashboard (SPEC-06). Both optional so a
    slider can move one knob without touching the other."""
    loud_rms_thresh: Optional[float] = None
    motion_level_thresh: Optional[float] = None


class ModePatch(BaseModel):
    """Student's mode choice from the dashboard (SPEC-07). None stops everything."""
    mode: Optional[int] = None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def dashboard():
    return FileResponse(WEB_DIR / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/app.js")
def dashboard_js():
    return FileResponse(WEB_DIR / "app.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-store"})


@app.post("/ingest_raw")
async def ingest_raw(batch: RawBatch, request: Request,
                     x_device_token: str = Header(...)):
    """Mode 1: cloud does ALL the work. Decode raw frames + audio, then run the
    exact same feature extractor the edge would have run."""
    info = auth(x_device_token)
    device = info["device"]
    rate(device)
    bandwidth.record(device, "mode1", _content_length(request))

    def work():
        frames = [decode_frame(b) for b in batch.frames]
        audio = decode_audio(batch.audio)
        # Mode 1's fusion runs HERE, so the live thresholds apply immediately --
        # no round-trip to the edge (the edge sent raw pixels, not a verdict).
        feats = extract_features(frames, audio, _last_motion[device],
                                 motion_level_thresh=_live_cfg["motion_level_thresh"],
                                 loud_rms_thresh=_live_cfg["loud_rms_thresh"])
        _last_motion[device] = feats["motion_flag"]
        return len(frames), feats

    # Decoding 15 JPEGs + features is CPU-bound; keep it off the event loop or
    # it stalls the SSE stream it is meant to feed.
    n_frames, feats = await run_in_threadpool(work)

    # The incoming base64 IS a JPEG -- decode the base64 and serve it as-is.
    # Re-encoding would waste CPU and change what the student sees.
    if batch.frames:
        _latest_jpeg[device] = base64.b64decode(batch.frames[-1])

    flag = flag_for(feats)
    await _publish(_event(device, 1, flag, feats=feats))
    return {"received_frames": n_frames, "cloud_features": feats, "flag": flag}


@app.post("/ingest_features")
async def ingest_features(f: FeaturePayload, request: Request,
                          x_device_token: str = Header(...)):
    """Mode 2: device already did the work; we interpret / enrich."""
    info = auth(x_device_token)
    device = info["device"]
    rate(device)
    bandwidth.record(device, "mode2", _content_length(request))

    # Mode 2 sent no image. Drop any frame Mode 1 left behind -- a stale face
    # lingering here would wreck the privacy demo.
    _latest_jpeg.pop(device, None)

    feats = f.dict()
    flag = flag_for(feats)
    await _publish(_event(device, 2, flag, feats=feats))
    # Hand the live thresholds back so the edge applies them next tick. This is
    # what keeps the FUSION on the Jetson (the boss's design) while the numbers
    # are tuned from the dashboard.
    return {"device": device, "flag": flag, "note": _maybe_llm_note(f),
            "config": dict(_live_cfg)}


@app.post("/ingest_posture")
async def ingest_posture(p: PosturePayload, request: Request,
                         x_device_token: str = Header(...)):
    """Mode 3: the edge ran MoveNet AND the fall rule; we only display it.

    Note what this handler does NOT do: no inference, no rule, no decision. The
    Jetson sent a verdict and a skeleton; the laptop is a screen. That asymmetry
    against /ingest_raw -- which decodes frames and computes everything here -- is
    the whole lesson, sitting in one file.
    """
    info = auth(x_device_token)
    device = info["device"]
    rate(device)
    bandwidth.record(device, "mode3", _content_length(request))
    # Mode 3 sends no image, so drop any frame Mode 1 left behind: a stale face
    # lingering in the video panel would wreck the privacy demo. The skeleton
    # arrives as coordinates and is drawn by the browser -- never as pixels.
    _latest_jpeg.pop(device, None)

    if p.abnormal:
        flag = "FALL?"
    elif p.posture in ("walking", "standing", "sitting"):
        # `sitting` is a person, present and fine -- it must read person-active,
        # not "quiet". MoveNet introduced this label; under bgsub it never
        # occurred, which is why this list used to have two entries.
        flag = "person-active"
    else:
        flag = "quiet"

    await _publish(_event(device, 3, flag, posture=p.dict()))
    return {"device": device, "flag": flag, "note": None}


@app.get("/latest.jpg")
def latest_jpg(device: str = "bench01"):
    """Most recent Mode 1 frame.

    404 in Modes 2/3 is CORRECT, not an error: those modes never send an image,
    so there is nothing to serve. The dashboard's video panel blanks by itself
    and the privacy lesson needs no special-casing.
    """
    jpeg = _latest_jpeg.get(device)
    if not jpeg:
        raise HTTPException(404, "no frame -- this mode sends no image")
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/config")
def get_config():
    """Current live fall thresholds -- the dashboard reads this to seed sliders."""
    return dict(_live_cfg)


@app.post("/config")
def set_config(patch: ConfigPatch):
    """Update a live fall threshold (SPEC-06). Ignores omitted fields; clamps to
    sane bounds so a bad slider value can't wedge the demo. Mode 1 picks it up on
    the next frame; Mode 2's edge on its next tick."""
    updates = patch.dict(exclude_none=True)
    for k, v in updates.items():
        lo, hi = _CFG_BOUNDS[k]
        _live_cfg[k] = max(lo, min(hi, float(v)))
    return dict(_live_cfg)


@app.get("/mode")
def get_mode():
    """The selected mode -- the Jetson supervisor polls this (SPEC-07)."""
    return dict(_desired_mode)


@app.post("/mode")
def set_mode(patch: ModePatch):
    """Pick the running mode from the dashboard. 1/2/3, or null to stop all.
    The supervisor on the Jetson swaps clients to match within a couple seconds;
    the live-mode badge then updates itself once data flows."""
    if patch.mode not in (1, 2, 3, None):
        raise HTTPException(422, "mode must be 1, 2, 3 or null")
    _desired_mode["mode"] = patch.mode
    return dict(_desired_mode)


@app.post("/reset")
def reset(device: Optional[str] = None):
    """Clear byte totals so the next student pair gets a clean 689x demo."""
    bandwidth.reset(device)
    if device:
        _history[device].clear()
        _latest_jpeg.pop(device, None)
    else:
        _history.clear()
        _latest_jpeg.clear()
    return {"reset": device or "all"}


@app.get("/events")
async def events(device: str = "bench01"):
    """SSE: replay the last 60 s, then stream live. Data only -- no frames."""
    q = asyncio.Queue(maxsize=200)
    _subscribers.add(q)

    async def gen():
        try:
            for past in list(_history[device]):
                yield f"data: {json.dumps(dict(past, replay=True))}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"      # idle proxies hang up without this
                    continue
                if ev.get("device") == device:
                    yield f"data: {json.dumps(ev)}\n\n"
        finally:
            _subscribers.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


def _maybe_llm_note(f: FeaturePayload):
    """Optional LLM enrichment; runs only if ANTHROPIC_API_KEY is set here."""
    if not f.fall_suspected:
        return None                     # save tokens: only escalate real events
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        prompt = ("A home monitoring edge device flagged a possible fall "
                  "(loud sound then motion stopped). Context: "
                  f"{f.context or 'none'}. One short sentence for the caregiver.")
        msg = client.messages.create(
            model=LLM_MODEL, max_tokens=120,
            messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip()
    except Exception as e:
        return f"(llm unavailable: {e})"
