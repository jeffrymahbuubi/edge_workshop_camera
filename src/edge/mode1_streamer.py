"""MODE 1 -- dumb streamer (camera + audio).

Grab a second of video + audio and POST it RAW (base64 JPEG frames + audio) to
the relay. The laptop does NO analysis; the cloud decodes and does everything.
Maximum bandwidth, maximum privacy exposure (raw faces + voices leave the room).

Run:  python mode1_streamer.py     (Ctrl-C to stop and see the bandwidth summary)
"""
import json
import time

import requests

from edge.sensor import get_sensor
from common.codec import encode_frame, encode_audio
from common.config import RELAY_URL, DEVICE_TOKEN, SECONDS_PER_TICK, SENSOR_KIND


def main():
    sensor = get_sensor(SENSOR_KIND)      # SENSOR=webcam to use a real camera
    url = f"{RELAY_URL}/ingest_raw"
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "application/json"}

    total_bytes, t0 = 0, time.time()
    print(f"[Mode 1] streaming RAW video+audio to {url}  (Ctrl-C to stop)")
    try:
        while True:
            frames, audio, _ = sensor.read_second()
            body = json.dumps({
                "frames": [encode_frame(f) for f in frames],
                "audio": encode_audio(audio),
                "t_start": time.time(),
            })
            total_bytes += len(body.encode())
            try:
                r = requests.post(url, data=body, headers=headers, timeout=10)
                cf = r.json().get("cloud_features", {})
                print(f"  cloud: motion={cf.get('motion_flag')} "
                      f"loud={cf.get('loud_flag')} fall={cf.get('fall_suspected')}"
                      f"   (all compute in the cloud)")
            except requests.RequestException as e:
                print(f"  [network error] {e}  -> raw data lost (no buffer!)")
            time.sleep(SECONDS_PER_TICK)
    except KeyboardInterrupt:
        _summary(total_bytes, time.time() - t0)
    finally:
        getattr(sensor, "close", lambda: None)()


def _summary(total_bytes, dur):
    per_min = total_bytes / dur * 60 if dur else 0
    print(f"\n[Mode 1 summary] sent {total_bytes/1024:.0f} KB in {dur:.1f}s"
          f"  =  {per_min/1024:.0f} KB/min  =  {per_min*60*24/1e6:.0f} MB/day")


if __name__ == "__main__":
    main()
