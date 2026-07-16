"""Model-free feature extraction for camera + audio.

NO neural networks, NO TensorRT, NO model downloads -- just OpenCV frame
differencing and audio RMS. This same code runs on the edge (Mode 2) AND in the
relay as a golden reference (Mode 1), so edge features can be validated against
a cloud-side recomputation.

Features per second:
  motion_level   fraction of pixels that changed (0..1)
  n_blobs        number of distinct motion regions
  motion_flag    True if motion_level exceeds a threshold
  audio_rms      audio energy this second
  loud_flag      True if audio is loud (speech / impact)
  fall_suspected True if a loud sound coincides with motion suddenly ending
"""
import cv2
import numpy as np

from common.config import (PIX_DIFF_THRESH, MOTION_LEVEL_THRESH, MIN_BLOB_AREA,
                    AUDIO_SR, LOUD_RMS_THRESH)


def _gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def video_motion_features(frames, motion_level_thresh=None):
    """frames: list of BGR uint8 frames. Uses frame differencing.

    motion_level_thresh: override the module default so the dashboard can tune
    live (SPEC-06). None = the reference value, so callers that pass nothing get
    exactly the boss's original behaviour.
    """
    if motion_level_thresh is None:
        motion_level_thresh = MOTION_LEVEL_THRESH
    if len(frames) < 2:
        return {"motion_level": 0.0, "n_blobs": 0, "motion_flag": False}

    grays = [_gray(f) for f in frames]
    h, w = grays[0].shape
    motion_any = np.zeros((h, w), dtype=np.uint8)
    fractions = []
    for a, b in zip(grays[:-1], grays[1:]):
        diff = cv2.absdiff(a, b)
        mask = (diff > PIX_DIFF_THRESH).astype(np.uint8)
        fractions.append(float(mask.mean()))
        motion_any |= mask

    motion_level = float(np.mean(fractions)) if fractions else 0.0

    # count motion blobs above a minimum area
    n_labels, _, stats, _ = cv2.connectedComponentsWithStats(motion_any * 255, 8)
    n_blobs = int(sum(1 for i in range(1, n_labels)
                      if stats[i, cv2.CC_STAT_AREA] >= MIN_BLOB_AREA))

    return {
        "motion_level": round(motion_level, 4),
        "n_blobs": n_blobs,
        "motion_flag": bool(motion_level > motion_level_thresh),
    }


def audio_energy_features(audio, loud_rms_thresh=None):
    """audio: float32 array. Simple RMS energy + loud/speech flag.

    loud_rms_thresh: override the module default for live tuning (SPEC-06);
    None = the reference value.
    """
    if loud_rms_thresh is None:
        loud_rms_thresh = LOUD_RMS_THRESH
    a = np.asarray(audio, dtype=np.float32)
    rms = float(np.sqrt(np.mean(a * a))) if a.size else 0.0
    return {
        "audio_rms": round(rms, 4),
        "loud_flag": bool(rms > loud_rms_thresh),
    }


def extract_features(frames, audio, prev_motion_flag=False,
                     motion_level_thresh=None, loud_rms_thresh=None):
    """Combine video + audio features and a simple multimodal fusion rule.

    prev_motion_flag: whether motion was detected in the PREVIOUS second.
    Used to spot 'motion just stopped' -- which, paired with a loud sound,
    is a crude fall signature.

    motion_level_thresh / loud_rms_thresh: live-tunable overrides (SPEC-06).
    Both None -> the boss's reference thresholds, unchanged.
    """
    v = video_motion_features(frames, motion_level_thresh)
    a = audio_energy_features(audio, loud_rms_thresh)
    fall = bool(a["loud_flag"] and prev_motion_flag and not v["motion_flag"])
    return {
        "motion_level": v["motion_level"],
        "n_blobs": v["n_blobs"],
        "motion_flag": v["motion_flag"],
        "audio_rms": a["audio_rms"],
        "loud_flag": a["loud_flag"],
        "fall_suspected": fall,
    }
