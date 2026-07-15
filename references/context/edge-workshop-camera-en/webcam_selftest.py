"""Webcam + microphone self-test. Run this on the REAL laptop before the
workshop to confirm the camera and mic work and the thresholds make sense.

  python webcam_selftest.py            # uses CAMERA_INDEX (default 0)
  CAMERA_INDEX=1 python webcam_selftest.py

For ~6 seconds it prints, once per second: how many frames were captured, the
frame size, the motion level, and the audio RMS. WAVE YOUR HAND to see
motion_flag=True, and CLAP to see loud_flag=True. If motion/loud never flip,
adjust MOTION_LEVEL_THRESH / LOUD_RMS_THRESH in common.py.
"""
import sys

from sensor import WebcamMicSource
from features import extract_features
from common import FRAME_W, FRAME_H, MOTION_LEVEL_THRESH, LOUD_RMS_THRESH


def main(seconds=6):
    print(f"Opening camera... (target {FRAME_W}x{FRAME_H})")
    try:
        src = WebcamMicSource()
    except RuntimeError as e:
        print(f"CAMERA ERROR: {e}")
        sys.exit(1)

    print("Wave your hand to trigger motion; clap to trigger a loud event.\n")
    print(f"{'sec':>3} {'frames':>6} {'size':>9} {'motion':>8} {'motion?':>8}"
          f" {'audio_rms':>10} {'loud?':>6}")
    prev = False
    try:
        for s in range(seconds):
            frames, audio, _ = src.read_second()
            f = extract_features(frames, audio, prev)
            prev = f["motion_flag"]
            size = f"{frames[0].shape[1]}x{frames[0].shape[0]}"
            print(f"{s:>3} {len(frames):>6} {size:>9} {f['motion_level']:>8.4f}"
                  f" {str(f['motion_flag']):>8} {f['audio_rms']:>10.4f}"
                  f" {str(f['loud_flag']):>6}")
    finally:
        src.close()

    print(f"\nThresholds in use: MOTION_LEVEL_THRESH={MOTION_LEVEL_THRESH}, "
          f"LOUD_RMS_THRESH={LOUD_RMS_THRESH}")
    print("If motion never went True while moving, lower MOTION_LEVEL_THRESH.")
    print("If loud never went True while clapping, lower LOUD_RMS_THRESH.")


if __name__ == "__main__":
    main()
