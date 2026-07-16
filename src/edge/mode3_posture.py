"""MODE 3 -- pose + audio + the fall rule, all ON THE JETSON.

Grab a second of video and audio, estimate posture from DEEP-LEARNING KEYPOINTS
(MoveNet), fuse in whether the second was loud, run the fall rule, and POST the
verdict + the skeleton + two audio scalars. NO FRAMES. Mode 3 is Mode 2's
philosophy with a better brain: the extra intelligence buys a better answer, not
a bigger payload.

Run:  python3 -m edge.mode3_posture      (Ctrl-C to stop and see the summary)

⚠️ SPEC-08 REVERSED "KEYPOINTS ONLY" -- 2026-07-16, Jeffry's call.
This file used to read the audio and DROP it, and this docstring used to say
Mode 3 imports nothing from `common.features`. The workshop's theme is
MULTI-MODAL Posture Recognition, and Mode 3 -- the mode being showcased -- was
the only uni-modal one.

WHAT FUSION MEANS HERE, EXACTLY: sound CORROBORATES, it never GATES. A thump near
the drop fires the alarm in ~1s instead of 3s. No thump, or a dead mic, and the
rule is byte-identical to the old vision-only one. The `lying AND loud` version
was REJECTED: it misses the silent slump (faint, slide onto carpet), and it would
couple Mode 3 to the mic -- this project's most likely per-board failure, which
fails SILENTLY. See SPEC-08 §A2-A3 and `behaviour.py`'s docstring.

STILL FORBIDDEN, and this has NOT moved: Mode 2's VIDEO detector. No
`video_motion_features`, no `motion_level`, no `fall_suspected`. That is Mode 2's
verdict answering Mode 2's question ("did motion stop?"); Mode 3 asks a different
one ("was this person upright, and are they now lying down?"), and two fall
verdicts in one payload is ambiguity, not multi-modality.

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
# ⚠️ SPEC-04 §3.1 banned `common.features` from this file outright; SPEC-08 §A6
# narrowed that ban. `audio_energy_features` ONLY -- never `extract_features`,
# never `video_motion_features`. The ban's reason was CPU, not purity: Mode 3
# once ran frame differencing over 15 frames a second to feed a pose.py
# parameter that is never read. An RMS over one array costs microseconds and its
# result is actually consumed.
from common.features import audio_energy_features
from common.codec import encode_frame
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


def _payload(result, verdict, audio):
    """The wire format -- SPEC-01 §4.3.

    Built by hand, field by field, ON PURPOSE. The obvious shortcut is to splat
    the estimator's dict and add the verdict; the splat is a trap even now that
    keypoints are allowed, because the estimator also carries whatever a future
    backend decides to return. Listing the fields means a new estimator field
    cannot silently become a new wire field -- which is exactly how a frame
    would get onto the LAN by accident.

    `audio` carries TWO SCALARS, never samples (SPEC-08 §A5). ~20 B of energy is
    not a recording of the room, exactly as Mode 2 has always argued.
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
        "audio_rms": audio["audio_rms"],
        "loud_flag": audio["loud_flag"],
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

    # The dashboard's live loud threshold, fed back from the relay each tick
    # (SPEC-06, SPEC-08 §A7). None = the reference default. Mode 3 joins this the
    # moment it starts listening, or the slider would silently lie in one of the
    # three modes. The FUSION still happens HERE, on the Jetson -- the dashboard
    # only supplies the number.
    cfg = {"loud_rms_thresh": None}
    # Does the student want the setup camera? Fed back by the relay each tick
    # (SPEC-08 §B5), same channel as cfg -- no second poll. Starts FALSE and the
    # relay clears it on every mode change, so Mode 3 always begins pure.
    preview = {"on": False}
    preview_url = f"{RELAY_URL}/ingest_preview"

    print(f"[Mode 3] posture verdicts -> {url}  backend={BACKEND}"
          f"  (Ctrl-C to stop)")
    try:
        while True:
            tick = time.time()
            # The audio is READ AND USED as of SPEC-08 Part A. It used to be
            # dropped here (Mode 3 was camera-only), which made Mode 3 the one
            # mode immune to the misrouted-mic bug. That immunity is preserved
            # deliberately: a dead mic yields loud_flag=False forever, and
            # behaviour.py treats that as vision-only -- i.e. exactly the old
            # rule. Sound can only ever make this mode FASTER, never blind.
            frames, audio, _ = sensor.read_second()

            # ONE frame, not fifteen. Inference costs ~0.08s on a Nano and there
            # is no background model to train, so feeding the whole second would
            # burn 15x the CPU for the same answer. (bgsub needed every frame;
            # that requirement died with it.)
            result = est.estimate(frames)
            if result is None:                 # empty read; nothing to report
                time.sleep(SECONDS_PER_TICK)
                continue

            # An RMS over one array: microseconds, and unlike the vestigial
            # video_motion_features call SPEC-04 §3.1 deleted, its result is
            # actually consumed. That is why §3.1's ban does not reach it.
            feats = audio_energy_features(audio, cfg["loud_rms_thresh"])
            verdict = monitor.update(result["posture"], loud=feats["loud_flag"])
            outbox.append(_payload(result, verdict, feats))
            total_bytes += _flush(outbox, url, headers, cfg, preview)

            # The setup frame goes LAST, on its own endpoint, and its bytes are
            # NOT added to total_bytes -- Mode 3's figure is the one the workshop
            # quotes and setup pixels are not part of it (SPEC-08 §B4). The relay
            # counts them in their own bucket so the dashboard can show both.
            if preview["on"] and frames:
                _send_preview(preview_url, headers, frames[-1])

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


def _send_preview(url, headers, frame):
    """Post ONE setup frame. Fire-and-forget, deliberately.

    No outbox, no retry, unlike the posture path. Two reasons: a stale preview
    frame is worthless (the student is looking at where they are NOW), and
    buffering pixels would mean a cable pull produces a burst of faces on
    reconnect -- the exact thing Mode 3 exists to avoid.

    A 403 here is NORMAL and not an error: the student turned the camera off
    between our last tick and this post, and the relay is refusing pixels it was
    not asked for. That is the gate doing its job.
    """
    try:
        requests.post(url, data=json.dumps({"image": encode_frame(frame)}),
                      headers=headers, timeout=5)
    except requests.RequestException:
        pass          # setup aid, not the mission -- never let it stall the rule


def _flush(outbox, url, headers, cfg, preview):
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
            # Pull the dashboard's live loud threshold for the NEXT tick --
            # same channel mode2_edge.py uses, no second poll (SPEC-08 §A7).
            new_cfg = resp.get("config") or {}
            if new_cfg.get("loud_rms_thresh") is not None:
                cfg["loud_rms_thresh"] = float(new_cfg["loud_rms_thresh"])
            # Whether the student wants the setup camera, same channel (§B5).
            # Defaults to False if the key is absent, so an older relay simply
            # means "no pixels" -- the safe direction to fail.
            preview["on"] = bool(resp.get("preview", False))
            reason = f"  reason={p['reason']}" if p["reason"] else ""
            score = "" if p["score"] is None else f" score={p['score']:.2f}"
            loud = " LOUD" if p["loud_flag"] else ""
            print(f"  posture={p['posture']:<9}{score} abnormal={p['abnormal']}"
                  f"  rms={p['audio_rms']:.4f}{loud}"
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
