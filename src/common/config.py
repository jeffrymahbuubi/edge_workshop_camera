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
# Which microphone to record from. Leave unset to use the system default -- but
# BEWARE: on the Jetson the default routes to the onboard codec, which has NO
# microphone attached and returns PURE SILENCE. audio_rms then stays 0.0, so
# loud_flag never fires, so fall_suspected can never fire -- silently.
#
# Accepts either a NAME SUBSTRING (preferred) or a numeric index:
#     AUDIO_DEVICE=C270      <- matched by name, survives re-enumeration
#     AUDIO_DEVICE=11        <- brittle, see below
#
# Prefer the name. PortAudio indices are only valid for the enumeration that
# produced them: with the camera open, or another process holding the mic, the
# list shifts and index 11 silently becomes something else (observed: it landed
# on "pulse", which records silence). List devices with: python3 -m sounddevice
AUDIO_DEVICE = os.environ.get("AUDIO_DEVICE", "").strip() or None
if AUDIO_DEVICE and AUDIO_DEVICE.isdigit():
    AUDIO_DEVICE = int(AUDIO_DEVICE)

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

# --- mode 3: the fall rule (SPEC-04) ---
# Mode 3 is MoveNet keypoints and nothing else -- there is no backend switch.
# The pose knobs (KP_CONF, WALK_MOVE_THRESH, SIT_DROP_RATIO, SMOOTH_N, ...) are
# env vars read in edge/pose.py, deliberately left there with the model they
# belong to rather than hoisted here.
#
# How long "lying" must persist after an upright posture before it is a fall.
# 3s was originally a compromise forced by background subtraction, which faded a
# motionless person into the background within ~2s (measured) -- the exact state
# the hold needs. MoveNet does not fade, so that ceiling is gone and this could
# now go 5-10s. It stays at 3 because that is what was validated on hardware,
# and because a caregiver alarm that waits 10s to fire is a worse product. The
# number is now a CHOICE rather than a compromise.
FALL_HOLD_S = float(os.environ.get("FALL_HOLD_S", "3"))
# An upright posture must have been seen this recently for a "lying" to count as
# a fall. Without it, a person already lying when the camera starts reads as a
# fall and every demo boots into a false alarm.
UPRIGHT_LOOKBACK_S = float(os.environ.get("UPRIGHT_LOOKBACK_S", "10"))

# --- mode 3: multi-modal fusion (SPEC-08 Part A) ---
# Sound CORROBORATES the fall rule; it never gates it. Two senses agreeing buy
# SPEED, not permission.
#
# The rejected design was `lying AND loud`. It reads as the obvious one and it is
# a SAFETY REGRESSION: a person who slumps silently -- faints, slides off a chair
# onto carpet -- makes no thump, and vision alone catches them today. It would
# also couple Mode 3 to the microphone, which is this project's most likely
# per-board failure and one that fails SILENTLY (SPEC-01 §6 step 3).
#
# The hold once a thump has corroborated the drop. UNLIKE FALL_HOLD_S=3, this
# number is a GUESS -- it has no hardware behind it yet (SPEC-08 §D). Too low and
# a thump plus a stumble fires; the corroboration window below is what keeps it
# honest.
FALL_HOLD_FAST_S = float(os.environ.get("FALL_HOLD_FAST_S", "1"))
# How close to the upright->lying transition a thump must land to count as part
# of THE DROP. Not "any loud sound, ever": someone lying in bed for ten minutes
# who then coughs must never be upgraded to a fall. Two-sided, because the impact
# and the first `lying` label usually share a 1s tick and which one wins that tick
# is a race.
LOUD_CORROBORATION_S = float(os.environ.get("LOUD_CORROBORATION_S", "2"))

# --- cadence: both modes wake up once per second ---
SECONDS_PER_TICK = 1.0
