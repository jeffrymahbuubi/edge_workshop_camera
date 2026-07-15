"""Shared configuration for the camera+audio edge-sensing workshop.

For LOCAL TESTING (no webcam, no mic): the defaults work as-is with the
synthetic scene source and a relay on localhost. On a real laptop, select the
USB-webcam source in sensor.py.
"""
import os

RELAY_URL = os.environ.get("RELAY_URL", "http://localhost:8000")
DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "tok_demo_bench01")

# Which sensor the clients use. "synthetic" (default, no hardware) or "webcam".
# Switch without editing code:  SENSOR=webcam python mode1_streamer.py
SENSOR_KIND = os.environ.get("SENSOR", "synthetic")
# Webcam device index for the real source (external cams are often 1 or 2).
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))

# --- video ---
FRAME_W, FRAME_H = 320, 240   # small on purpose: keep the workshop light
FPS = 15
JPEG_QUALITY = 60             # used when Mode 1 streams raw frames

# --- audio ---
AUDIO_SR = 16000              # samples per second
LOUD_RMS_THRESH = 0.05        # audio energy above this = "loud / speech" event

# --- motion detection (frame differencing) ---
PIX_DIFF_THRESH = 25          # per-pixel gray-level change counted as motion
MOTION_LEVEL_THRESH = 0.006   # fraction of changed pixels above which = moving
MIN_BLOB_AREA = 60            # ignore motion blobs smaller than this (px)

# --- cadence: both modes wake up once per second ---
SECONDS_PER_TICK = 1.0
