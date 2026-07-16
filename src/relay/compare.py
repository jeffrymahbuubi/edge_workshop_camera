"""Deterministic bandwidth comparison + detection check for camera + audio.

No network, no webcam needed. Simulates a representative window of the scene,
measures how many bytes each mode would upload, and checks that motion/fall
detection matches the scene's known ground truth.

Run:  python compare.py
"""
import json

from edge.sensor import SyntheticScene
from common.codec import encode_frame, encode_audio
from common.features import extract_features

SIM_SECONDS = 12          # two full move/still cycles -> representative average


def main():
    scene = SyntheticScene(seed=0)
    mode1_bytes = mode2_bytes = 0
    prev_motion = False
    hits = total = fall_detected = fall_truth = 0

    for _ in range(SIM_SECONDS):
        frames, audio, truth = scene.read_second()

        # Mode 1: raw upload = base64 JPEG frames + base64 audio
        raw = json.dumps({"frames": [encode_frame(f) for f in frames],
                          "audio": encode_audio(audio), "t_start": 0.0})
        mode1_bytes += len(raw.encode())

        # Mode 2: only the small feature vector
        feats = extract_features(frames, audio, prev_motion)
        prev_motion = feats["motion_flag"]
        mode2_bytes += len(json.dumps(feats).encode())

        # validation against ground truth
        total += 1
        if feats["motion_flag"] == truth["gt_moving"]:
            hits += 1
        if truth["gt_impact"]:
            fall_truth += 1
        if feats["fall_suspected"]:
            fall_detected += 1

    # project to per-day from the average second
    m1_day = mode1_bytes / SIM_SECONDS * 86400 / 1e6
    m2_day = mode2_bytes / SIM_SECONDS * 86400 / 1e6
    ratio = mode1_bytes / max(mode2_bytes, 1)

    print(f"=== {SIM_SECONDS}s of {320}x{240} @15fps video + 16kHz audio ===")
    print(f"Mode 1 (raw stream) : {mode1_bytes/1024:9.1f} KB /"
          f"{SIM_SECONDS}s   ~ {m1_day:8.0f} MB/day")
    print(f"Mode 2 (edge feats) : {mode2_bytes/1024:9.2f} KB /"
          f"{SIM_SECONDS}s   ~ {m2_day:8.3f} MB/day")
    print(f"--> Mode 1 sends about {ratio:,.0f}x more data than Mode 2\n")

    print(f"Validation vs ground truth:")
    print(f"  motion_flag matched truth in {hits}/{total} seconds")
    print(f"  fall events: {fall_detected} detected vs {fall_truth} in scene")


if __name__ == "__main__":
    main()
