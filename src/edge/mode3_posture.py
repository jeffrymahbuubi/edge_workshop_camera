"""MODE 3 -- pose + the fall rule, both ON THE JETSON.

Grab a second of video, estimate posture from DEEP-LEARNING KEYPOINTS (MoveNet),
run the fall rule, and POST the verdict + the skeleton. No frames, no audio.
Mode 3 is Mode 2's philosophy with a better brain: the extra intelligence buys a
better answer, not a bigger payload.

Run:  python3 -m edge.mode3_posture      (Ctrl-C to stop and see the summary)

MODE 3 IS KEYPOINTS. THAT IS THE WHOLE MODE.
It shares the sensor and the relay with Modes 1/2 and NOTHING ELSE. In
particular it does not import `common.features` -- no frame differencing, no
audio RMS, no `fall_suspected`. That is Mode 2's detector answering Mode 2's
question ("was there a thump, and did motion stop?"), and Mode 3 asks a
different one ("was this person upright, and are they now lying down?").

This mattered in practice, not just conceptually: an earlier version computed
`video_motion_features(frames)` every second and passed the result to
`pose.estimate(frames, motion_level)` -- which IGNORES it (MoveNet decides
`walking` from keypoint centroid movement, see pose.py `_prev_center`). So the
Nano was running frame differencing over 15 frames per second, for a number
nothing read. The parameter is a vestige of the bgsub interface; leave it
defaulted.

WHY THE SKELETON IS ALLOWED ON THE WIRE (this reverses an earlier rule):
Mode A sends ~560 B of joint coordinates. Mode 1 sends ~583 KB of recognisable
faces. A skeleton identifies nobody, and it is the only way a student SEES that
the ML ran on the device. The line that still holds absolutely is that RAW
PIXELS NEVER LEAVE -- see tests/test_mode3_payload.py. The colleague's Mode B
(MODE3_SEND_IMAGE=1, a JPEG per second) is deliberately NOT carried over: it
would put the camera image back on the LAN and undo Mode 3's whole argument.
"""
import collections
import json
import time

import requests

from edge.sensor import get_sensor
from edge.pose import get_pose_estimator
from edge.behaviour import BehaviourMonitor
from common.config import (RELAY_URL, DEVICE_TOKEN, SECONDS_PER_TICK,
                           SENSOR_KIND)

BACKEND = "movenet"


def _round_kp(kps):
    """Round the skeleton to 3 decimals before it goes on the wire.

    MoveNet returns full-precision floats, and json.dumps spends ~19 characters
    on each ("0.5123456789012345"). At 17 joints x 3 numbers that is most of the
    payload, and it buys NOTHING: 0.001 of a 320px frame is a third of a pixel,
    well under the width of the line the dashboard draws with it.

    This is not micro-optimisation. Mode 3's payload size is the argument the
    whole workshop rests on, so paying 3x for invisible decimals would be
    undercutting the lesson with noise.
    """
    if kps is None:
        return None
    return [[round(float(x), 3), round(float(y), 3), round(float(s), 3)]
            for x, y, s in kps]


def _payload(result, verdict):
    """The wire format -- SPEC-01 §4.3.

    Built by hand, field by field, ON PURPOSE. The obvious shortcut is to splat
    the estimator's dict and add the verdict; the splat is a trap even now that
    keypoints are allowed, because the estimator also carries whatever a future
    backend decides to return. Listing the fields means a new estimator field
    cannot silently become a new wire field -- which is exactly how a frame
    would get onto the LAN by accident.
    """
    return {
        "posture": result["posture"],
        "abnormal": verdict["abnormal"],
        "reason": verdict["reason"],
        # .get(): SPEC-01 §5 says downstream treats these as optional and never
        # assumes -- an estimator that cannot see a person returns no box.
        "keypoints": _round_kp(result.get("keypoints")),
        "bbox": result.get("bbox"),          # already normalised 0..1 by pose.py
        "score": result.get("score"),
        "backend": BACKEND,
        "context": "",
    }


def main():
    sensor = get_sensor(SENSOR_KIND)          # SENSOR=webcam for a real camera
    est = get_pose_estimator("movenet")
    monitor = BehaviourMonitor()
    url = f"{RELAY_URL}/ingest_posture"
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "application/json"}

    outbox = collections.deque()
    total_bytes, t0 = 0, time.time()

    print(f"[Mode 3] posture verdicts -> {url}  backend={BACKEND}"
          f"  (Ctrl-C to stop)")
    try:
        while True:
            tick = time.time()
            # The audio is read and dropped: the sensor hands back a second of
            # both, and Mode 3 is camera-only. This is also why Mode 3 is the
            # one mode that still works while the Jetson's microphone is
            # misrouted -- it never asks the mic anything.
            frames, _audio, _ = sensor.read_second()

            # ONE frame, not fifteen. Inference costs ~0.08s on a Nano and there
            # is no background model to train, so feeding the whole second would
            # burn 15x the CPU for the same answer. (bgsub needed every frame;
            # that requirement died with it.)
            result = est.estimate(frames)
            if result is None:                 # empty read; nothing to report
                time.sleep(SECONDS_PER_TICK)
                continue

            verdict = monitor.update(result["posture"])
            outbox.append(_payload(result, verdict))
            total_bytes += _flush(outbox, url, headers)

            # Pace on ELAPSED time, not a flat sleep: inference eats a slice of
            # the second, and sleeping a further full second on top would halve
            # the rate the fall rule sees -- stretching FALL_HOLD_S into
            # something longer than 3 real seconds.
            dt = time.time() - tick
            if dt < SECONDS_PER_TICK:
                time.sleep(SECONDS_PER_TICK - dt)
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
            score = "" if p["score"] is None else f" score={p['score']:.2f}"
            print(f"  posture={p['posture']:<9}{score} abnormal={p['abnormal']}"
                  f"  {len(body.encode())/1024:.1f}KB -> flag={resp.get('flag')}{reason}")
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
