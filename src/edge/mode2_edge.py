"""MODE 2 -- edge processing (camera + audio).

Grab a second of video + audio, compute motion + audio-energy features ON THE
LAPTOP, and POST only the tiny feature vector. Faces and voices never leave the
device. Includes a store-and-forward buffer so a Wi-Fi drop does not lose data.

Run:  python mode2_edge.py     (Ctrl-C to stop and see the bandwidth summary)
"""
import collections
import json
import time

import requests

from edge.sensor import get_sensor
from common.features import extract_features
from common.config import RELAY_URL, DEVICE_TOKEN, SECONDS_PER_TICK, SENSOR_KIND


def main():
    sensor = get_sensor(SENSOR_KIND)      # SENSOR=webcam to use a real camera
    url = f"{RELAY_URL}/ingest_features"
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "application/json"}

    outbox = collections.deque()
    prev_motion = False
    total_bytes, t0 = 0, time.time()

    # Live fall thresholds, fed back from the relay each tick (SPEC-06). None =
    # the reference defaults. The FUSION still runs HERE on the edge -- the
    # dashboard only supplies the numbers, so the boss's "edge decides" design
    # is intact.
    cfg = {"loud_rms_thresh": None, "motion_level_thresh": None}

    print(f"[Mode 2] edge features -> {url}  (Ctrl-C to stop)")
    try:
        while True:
            frames, audio, _ = sensor.read_second()
            feats = extract_features(
                frames, audio, prev_motion,
                motion_level_thresh=cfg["motion_level_thresh"],
                loud_rms_thresh=cfg["loud_rms_thresh"])
            prev_motion = feats["motion_flag"]
            outbox.append(feats)
            total_bytes += _flush(outbox, url, headers, cfg)
            time.sleep(SECONDS_PER_TICK)
    except KeyboardInterrupt:
        _summary(total_bytes, time.time() - t0, len(outbox))
    finally:
        getattr(sensor, "close", lambda: None)()


def _flush(outbox, url, headers, cfg):
    sent = 0
    while outbox:
        feats = outbox[0]
        body = json.dumps(feats)
        try:
            r = requests.post(url, data=body, headers=headers, timeout=5)
            r.raise_for_status()
            resp = r.json()
            # Pull the dashboard's live thresholds for the NEXT tick.
            new_cfg = resp.get("config") or {}
            for k in ("loud_rms_thresh", "motion_level_thresh"):
                if new_cfg.get(k) is not None:
                    cfg[k] = float(new_cfg[k])
            note = f"  note={resp['note']}" if resp.get("note") else ""
            print(f"  motion={feats['motion_flag']} loud={feats['loud_flag']} "
                  f"fall={feats['fall_suspected']}  -> flag={resp.get('flag')}{note}")
            sent += len(body.encode())
            outbox.popleft()
        except requests.RequestException as e:
            print(f"  [network down] buffering {len(outbox)} item(s): {e}")
            break
    return sent


def _summary(total_bytes, dur, pending):
    per_min = total_bytes / dur * 60 if dur else 0
    print(f"\n[Mode 2 summary] sent {total_bytes} bytes in {dur:.1f}s"
          f"  =  {per_min/1024:.2f} KB/min  =  {per_min*60*24/1e6:.3f} MB/day"
          f"   | {pending} item(s) still buffered")


if __name__ == "__main__":
    main()
