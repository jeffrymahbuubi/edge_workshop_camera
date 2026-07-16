"""MODE 3 -- posture + the fall rule, both ON THE JETSON.

Grab a second of video, estimate posture, run the fall rule, and POST only the
VERDICT: {posture, abnormal, reason, ...}. No frames, no keypoints. Mode 3 is
Mode 2's philosophy with a better brain -- the extra intelligence buys a better
answer, not a bigger payload.

Run:  python3 -m edge.mode3_posture      (Ctrl-C to stop and see the summary)

  POSTURE_BACKEND=bgsub   (default) model-free OpenCV -- fades on a still person
  POSTURE_BACKEND=trt               pose backend (SPEC-05; not built yet)

That switch is the demo: same client, same rule, same dashboard -- change one
env var and watch the fade disappear.
"""
import collections
import json
import time

import requests

from edge.sensor import get_sensor
from edge.posture import get_posture_estimator, POSTURE_BACKEND
from edge.behaviour import BehaviourMonitor
from common.features import video_motion_features
from common.config import RELAY_URL, DEVICE_TOKEN, SECONDS_PER_TICK, SENSOR_KIND


def _payload(result, verdict, backend=None):
    """The wire format -- SPEC-01 §4.3.

    Built by hand, field by field, ON PURPOSE. The obvious shortcut is to splat
    the estimator's dict and add the verdict, but the estimator's dict carries
    bbox/fill and (under a pose backend) 18 keypoints, and splatting would put a
    skeleton of the person on the LAN. Listing the fields means a new estimator
    field cannot silently become a new wire field.
    """
    return {
        "posture": result["posture"],
        "abnormal": verdict["abnormal"],
        "reason": verdict["reason"],
        # .get(): bgsub has no such keys at all, and SPEC-01 §5 says downstream
        # treats the pose fields as optional and never assumes.
        "torso_angle": result.get("torso_angle"),
        "confidence": result.get("confidence"),
        "backend": POSTURE_BACKEND if backend is None else backend,
        "context": "",
    }


def main():
    sensor = get_sensor(SENSOR_KIND)          # SENSOR=webcam for a real camera
    est = get_posture_estimator()             # POSTURE_BACKEND
    monitor = BehaviourMonitor()
    url = f"{RELAY_URL}/ingest_posture"
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "application/json"}

    outbox = collections.deque()
    total_bytes, t0 = 0, time.time()

    print(f"[Mode 3] posture verdicts -> {url}  backend={POSTURE_BACKEND}"
          f"  (Ctrl-C to stop)")
    if POSTURE_BACKEND == "bgsub":
        print("  (bgsub: keep the scene EMPTY for ~5s so the background is learned)")
    try:
        while True:
            frames, audio, _ = sensor.read_second()
            motion = video_motion_features(frames)["motion_level"]

            # EVERY frame goes to the estimator, not one per second: MOG2 learns
            # the background from the frames it is fed, so sampling one in
            # fifteen would leave it permanently untrained. We keep the last
            # frame's result as the second's answer.
            result = None
            for f in frames:
                result = est.estimate(f, motion)
            if result is None:                # empty read; nothing to report
                time.sleep(SECONDS_PER_TICK)
                continue

            verdict = monitor.update(result["posture"])
            outbox.append(_payload(result, verdict))
            total_bytes += _flush(outbox, url, headers)
            time.sleep(SECONDS_PER_TICK)
    except KeyboardInterrupt:
        _summary(total_bytes, time.time() - t0, len(outbox))
    finally:
        getattr(sensor, "close", lambda: None)()


def _flush(outbox, url, headers):
    """Store-and-forward, same discipline as Mode 2.

    Mode 3 is the mode a caregiver would actually rely on, so a cable pull must
    delay the fall alarm, not delete it.
    """
    sent = 0
    while outbox:
        p = outbox[0]
        body = json.dumps(p)
        try:
            r = requests.post(url, data=body, headers=headers, timeout=5)
            r.raise_for_status()
            resp = r.json()
            reason = f"  reason={p['reason']}" if p["reason"] else ""
            angle = "" if p["torso_angle"] is None else f" angle={p['torso_angle']}"
            print(f"  posture={p['posture']}{angle} abnormal={p['abnormal']}"
                  f"  -> flag={resp.get('flag')}{reason}")
            sent += len(body.encode())
            outbox.popleft()
        except requests.RequestException as e:
            print(f"  [network down] buffering {len(outbox)} item(s): {e}")
            break
    return sent


def _summary(total_bytes, dur, pending):
    per_min = total_bytes / dur * 60 if dur else 0
    print(f"\n[Mode 3 summary] sent {total_bytes} bytes in {dur:.1f}s"
          f"  =  {per_min/1024:.2f} KB/min  =  {per_min*60*24/1e6:.3f} MB/day"
          f"   | {pending} item(s) still buffered")


if __name__ == "__main__":
    main()
