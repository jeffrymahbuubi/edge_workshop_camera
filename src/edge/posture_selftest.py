"""Posture self-test (Mode 3 groundwork).

Validates the POSTURE signal in isolation BEFORE building the full Mode 3 client,
relay, and dashboard. Run it on the real camera and watch the 'posture' column:

  SENSOR=webcam python3 posture_selftest.py
  SENSOR=webcam POSTURE_BACKEND=bgsub python3 posture_selftest.py   # explicit

What to do in front of the camera (background-subtraction backend):
  1. Step OUT of frame for ~5 s so it learns the empty background
     (during warm-up you may see 'lying'/'absent' noise -- ignore it).
  2. STAND still            -> expect  standing
  3. WALK / wave around     -> expect  walking
  4. LIE DOWN (or hold something wide & low) -> expect  lying

Once these labels are reliable, the next step wires in the abnormal-behavior
rule (upright -> lying held for N seconds) and the Mode 3 upload + dashboard.

Tune in posture.py if labels are off:
  MIN_FG_FRACTION, LYING_ASPECT, WALK_MOTION_THRESH.
"""
import sys

from edge.sensor import get_sensor
from common.features import video_motion_features
from edge.posture import (get_posture_estimator, POSTURE_BACKEND,
                     MIN_FG_FRACTION, LYING_ASPECT, WALK_MOTION_THRESH)
from common.config import SENSOR_KIND


def main(seconds=30):
    print(f"[posture self-test] backend={POSTURE_BACKEND}  sensor={SENSOR_KIND}")
    try:
        sensor = get_sensor(SENSOR_KIND)
    except RuntimeError as e:
        print(f"CAMERA ERROR: {e}")
        sys.exit(1)

    est = get_posture_estimator()
    print("Step OUT of frame ~5 s to learn the background, then "
          "stand / walk / lie down.\n")
    print(f"{'sec':>3} {'motion':>8} {'fill':>6} {'bbox(WxH)':>11} "
          f"{'aspect':>7} {'posture':>9}")

    try:
        for s in range(seconds):
            frames, audio, _ = sensor.read_second()
            motion_level = video_motion_features(frames)["motion_level"]

            # feed every frame so the background model learns; keep the last result
            result = {"posture": "absent", "bbox": None, "aspect": 0.0, "fill": 0.0}
            for f in frames:
                result = est.estimate(f, motion_level)

            bbox = result["bbox"]
            bstr = f"{bbox[2]}x{bbox[3]}" if bbox else "-"
            print(f"{s:>3} {motion_level:>8.4f} {result['fill']:>6.3f} "
                  f"{bstr:>11} {result['aspect']:>7.2f} {result['posture']:>9}")
    finally:
        getattr(sensor, "close", lambda: None)()

    print(f"\nThresholds in use (edit in posture.py): "
          f"MIN_FG_FRACTION={MIN_FG_FRACTION}, LYING_ASPECT={LYING_ASPECT}, "
          f"WALK_MOTION_THRESH={WALK_MOTION_THRESH}")
    print("If 'lying' never appears when you lie down, raise LYING_ASPECT.")
    print("If 'standing' shows while walking, lower WALK_MOTION_THRESH.")
    print("If a still person reads 'absent', lower MIN_FG_FRACTION "
          "(or you held still long enough to become background).")


if __name__ == "__main__":
    main()
