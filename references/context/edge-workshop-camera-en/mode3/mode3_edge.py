"""MODE 3 -- edge pose + activity (Jetson) -> live server dashboard.

Each second on the Jetson: run MoveNet pose, classify the activity from joint
geometry, apply the abnormal-behaviour rule (was UPRIGHT, then LYING held for
N seconds), and upload the keypoints + bbox + condition to the PC dashboard
(mode3_dashboard.py). Only a tiny JSON leaves the device -- the edge-computing point.

Run (on the Jetson):
  SENSOR=webcam DASHBOARD_URL=http://<pc-ip>:8090/pose python3 mode3_edge.py
"""
import collections
import json
import os
import time

import requests

from sensor import get_sensor
from features import video_motion_features
from pose import get_pose_estimator
from codec import encode_frame
from common import SENSOR_KIND, SECONDS_PER_TICK

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://192.168.1.1:8090/pose")
DEVICE = os.environ.get("DEVICE_NAME", "jetson01")
LYING_HOLD_S = float(os.environ.get("LYING_HOLD_S", "3"))   # seconds of lying before alarm
UPRIGHT_LOOKBACK = int(os.environ.get("UPRIGHT_LOOKBACK", "10"))  # secs to look back for "was upright"
# Mode A (default): upload only keypoints (~1 KB, raw video stays on device).
# Mode B (MODE3_SEND_IMAGE=1): ALSO upload the JPEG frame so the dashboard shows
# the real camera image -- heavier, like Mode 1. Good for a small room where the
# skeleton alone is hard to trust.
SEND_IMAGE = os.environ.get("MODE3_SEND_IMAGE", "0") == "1"


def main():
    sensor = get_sensor(SENSOR_KIND)
    pose = get_pose_estimator("movenet")

    recent = collections.deque(maxlen=UPRIGHT_LOOKBACK)   # posture history (1/sec)
    lying_since, from_upright, alarm = None, False, False

    print(f"[Mode 3] pose -> {DASHBOARD_URL}   (Ctrl-C to stop)")
    try:
        while True:
            t0 = time.time()
            frames, audio, _ = sensor.read_second()
            motion = video_motion_features(frames)["motion_level"]
            r = pose.estimate(frames, motion)
            posture = r["posture"]

            # ---- Abnormal-behaviour rule (a "fall" = was up, now down and staying down) ----
            # 1. When a LYING episode begins, note the start time and whether the person
            #    was UP (standing/walking/sitting) at any point in the last UPRIGHT_LOOKBACK s.
            # 2. Once they've been lying continuously for >= LYING_HOLD_S s AND that episode
            #    began from being upright -> raise the alarm (latched).
            # 3. The alarm clears as soon as they stop lying (they got back up).
            condition, reason = "normal", ""
            if posture == "lying":
                if lying_since is None:                        # lying episode just started
                    lying_since = t0
                    from_upright = any(p in ("standing", "walking", "sitting")
                                       for p in recent)
                lying_dur = t0 - lying_since
                if from_upright and lying_dur >= LYING_HOLD_S:
                    alarm = True                               # latched for this episode
                if alarm:
                    condition, reason = "ABNORMAL", f"upright then lying {lying_dur:.0f}s"
                else:
                    reason = (f"lying {lying_dur:.0f}/{LYING_HOLD_S:.0f}s"
                              + ("" if from_upright else " (not from upright)"))
            else:                                              # not lying -> reset the episode
                lying_since, from_upright, alarm = None, False, False
            recent.append(posture)

            payload = {"device": DEVICE, "posture": posture, "condition": condition,
                       "reason": reason, "bbox": r["bbox"],
                       "keypoints": r["keypoints"], "score": r["score"],
                       "mode": "B" if SEND_IMAGE else "A"}
            if SEND_IMAGE:
                payload["image"] = encode_frame(frames[-1])   # base64 JPEG (Mode B)
            body = json.dumps(payload)
            sent_kb = len(body.encode()) / 1024.0
            try:
                requests.post(DASHBOARD_URL, data=body, timeout=3)
            except requests.RequestException as e:
                print(f"  [dashboard unreachable] {e}")

            flag = "  <== ALARM" if condition == "ABNORMAL" else ""
            note = f"  [{reason}]" if reason else ""
            print(f"  posture={posture:<9} score={r['score']:.2f} "
                  f"cond={condition}{note}  up={sent_kb:.1f}KB(mode {payload['mode']}){flag}")

            dt = time.time() - t0
            if dt < SECONDS_PER_TICK:
                time.sleep(SECONDS_PER_TICK - dt)
    except KeyboardInterrupt:
        pass
    finally:
        getattr(sensor, "close", lambda: None)()


if __name__ == "__main__":
    main()
