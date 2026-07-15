"""Cloud relay server (camera + audio).

Security model is identical to the PPG version: the relay holds any real API
key server-side; devices carry only a revocable token.

Endpoints (both require header X-Device-Token):
  POST /ingest_raw       <- Mode 1 sends base64 JPEG frames + audio here
  POST /ingest_features  <- Mode 2 sends the small feature vector here
  GET  /health
"""
import os
import time
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from codec import decode_frame, decode_audio
from features import extract_features

app = FastAPI(title="Camera Workshop Relay")

DEVICE_TOKENS = {
    "tok_demo_bench01": {"device": "bench01", "active": True},
    "tok_demo_bench02": {"device": "bench02", "active": True},
}

_calls = defaultdict(deque)
RATE_LIMIT, WINDOW_S = 300, 60

# remember each device's last motion state, for the fusion rule in Mode 1
_last_motion = defaultdict(bool)

LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5")


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


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ingest_raw")
def ingest_raw(batch: RawBatch, x_device_token: str = Header(...)):
    """Mode 1: cloud does ALL the work. Decode raw frames + audio, then run the
    exact same feature extractor the edge would have run."""
    info = auth(x_device_token)
    rate(info["device"])
    frames = [decode_frame(b) for b in batch.frames]
    audio = decode_audio(batch.audio)
    feats = extract_features(frames, audio, _last_motion[info["device"]])
    _last_motion[info["device"]] = feats["motion_flag"]
    return {"received_frames": len(frames), "cloud_features": feats}


@app.post("/ingest_features")
def ingest_features(f: FeaturePayload, x_device_token: str = Header(...)):
    """Mode 2: device already did the work; we interpret / enrich."""
    info = auth(x_device_token)
    rate(info["device"])
    flag = "FALL?" if f.fall_suspected else ("person-active" if f.motion_flag
                                             else "quiet")
    return {"device": info["device"], "flag": flag, "note": _maybe_llm_note(f)}


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
