"""Posture estimation for the camera pipeline (Mode 3 groundwork).

Adds a POSTURE signal -- standing / walking / lying / absent -- on top of the
existing model-free motion features, so a later "Mode 3" can watch for an
abnormal sequence (e.g. upright then lying) and raise a text alarm.

Like the sensor layer, posture is a PLUGGABLE BACKEND, so everything downstream
is identical no matter how posture is computed:

  POSTURE_BACKEND=bgsub   (default) -- model-free OpenCV background subtraction
  POSTURE_BACKEND=trt               -- TensorRT person detector (Jetson; step 2)

Every backend returns the same dict:
  {"posture": "standing"|"walking"|"lying"|"absent",
   "bbox":    (x, y, w, h) or None,
   "aspect":  h/w of the bbox (0 if none),
   "fill":    foreground area as a fraction of the frame (0..1)}

Posture is inferred from the person's bounding-box GEOMETRY plus the MOTION level
the frame-difference features already compute:
  * wide / flat box            -> lying
  * tall-ish box + moving      -> walking
  * tall-ish box + still       -> standing
  * no significant box         -> absent (empty scene / out of frame)

This keeps the workshop's model-free spirit: no neural net, just OpenCV.
"""
import os

import cv2

from common.config import FRAME_W, FRAME_H

POSTURE_BACKEND = os.environ.get("POSTURE_BACKEND", "bgsub")

# --- geometry / motion thresholds (tune these while running posture_selftest.py) ---
MIN_FG_FRACTION = 0.02     # ignore foreground smaller than this fraction of the frame
LYING_ASPECT = 0.8         # bbox h/w at or below this = lying (wider than tall)
WALK_MOTION_THRESH = 0.02  # motion_level above this = walking (else standing)


class BgSubPosture:
    """Model-free posture: MOG2 background subtraction + bbox aspect ratio.

    Feed frames in order (call estimate() on each frame of the second); the
    background model learns the empty scene, and the largest foreground blob is
    taken to be the person. Needs a mostly-static camera and a few seconds of an
    empty scene at startup to learn the background.
    """

    def __init__(self):
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=120, varThreshold=25, detectShadows=False)
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def estimate(self, frame, motion_level=0.0):
        mask = self._bg.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.dilate(mask, self._kernel, iterations=2)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return {"posture": "absent", "bbox": None, "aspect": 0.0, "fill": 0.0}

        c = max(contours, key=cv2.contourArea)
        fill = float(cv2.contourArea(c)) / float(FRAME_W * FRAME_H)
        if fill < MIN_FG_FRACTION:
            return {"posture": "absent", "bbox": None, "aspect": 0.0,
                    "fill": round(fill, 4)}

        x, y, w, h = cv2.boundingRect(c)
        aspect = h / float(w) if w else 0.0

        if aspect <= LYING_ASPECT:
            posture = "lying"                       # wide / flat = on the ground
        elif motion_level >= WALK_MOTION_THRESH:
            posture = "walking"                     # upright + moving
        else:
            posture = "standing"                    # upright + still

        return {"posture": posture, "bbox": (x, y, w, h),
                "aspect": round(aspect, 2), "fill": round(fill, 4)}


class TrtPosture:
    """TensorRT person-detector backend (Jetson only) -- STEP 2, not built yet.

    Planned: jetson-inference detectNet('ssd-mobilenet-v2'), take the 'person'
    box, and apply the SAME aspect-ratio posture logic as BgSubPosture. Kept as a
    placeholder so the backend switch is already wired up.
    """

    def __init__(self):
        raise NotImplementedError(
            "POSTURE_BACKEND=trt is not implemented yet (step 2). "
            "Use POSTURE_BACKEND=bgsub for now.")


def get_posture_estimator(kind=None):
    kind = kind or POSTURE_BACKEND
    if kind == "bgsub":
        return BgSubPosture()
    if kind == "trt":
        return TrtPosture()
    raise ValueError(f"unknown POSTURE_BACKEND: {kind!r} (use 'bgsub' or 'trt')")
