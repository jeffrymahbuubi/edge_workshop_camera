"""Encoding helpers shared by the Mode 1 client, the relay, and compare.py.

Frames are JPEG-compressed then base64'd; audio is quantized to int16 then
base64'd. Keeping this in one place means every component measures and decodes
raw data identically.
"""
import base64

import cv2
import numpy as np

from common import JPEG_QUALITY


def encode_frame(frame) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return base64.b64encode(buf).decode("ascii")


def decode_frame(b64: str):
    buf = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def encode_audio(audio) -> str:
    a = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    i16 = (a * 32767.0).astype(np.int16)
    return base64.b64encode(i16.tobytes()).decode("ascii")


def decode_audio(b64: str):
    raw = base64.b64decode(b64)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
