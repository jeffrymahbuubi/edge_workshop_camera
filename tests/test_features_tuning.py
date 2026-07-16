"""Tunable fall thresholds (Modes 1+2) -- the override must change the flags
while the DEFAULTS stay byte-for-byte what the boss's reference produced.

Modes 1/2 are additive-only. These tests pin both halves: (a) passing an override
flips the flag, and (b) calling with no override is identical to before, so the
live-tuning feature can never silently shift the default demo behaviour.
"""
import numpy as np
import pytest

from common.config import (FRAME_H, FRAME_W, MOTION_LEVEL_THRESH,
                           LOUD_RMS_THRESH)
from common.features import (video_motion_features, audio_energy_features,
                            extract_features)


def const_audio(rms):
    """A signal whose RMS is exactly `rms` (constant amplitude)."""
    return np.full(1600, rms, dtype=np.float32)


def frame_pair(changed_fraction):
    """Two frames differing in `changed_fraction` of pixels (0->255)."""
    base = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
    moved = base.copy()
    n_rows = int(FRAME_H * changed_fraction)
    moved[:n_rows, :] = 255
    return [base, moved]


# --- audio / loud_flag ---------------------------------------------------

def test_loud_flag_default_unchanged():
    """rms just under the default stays quiet; just over is loud. Baseline."""
    assert audio_energy_features(const_audio(0.04))["loud_flag"] is False
    assert audio_energy_features(const_audio(0.06))["loud_flag"] is True


def test_loud_threshold_override_makes_quiet_audio_loud():
    """A 0.03 signal is quiet at the 0.05 default but loud at a 0.02 override."""
    quiet = const_audio(0.03)
    assert audio_energy_features(quiet)["loud_flag"] is False
    assert audio_energy_features(quiet, loud_rms_thresh=0.02)["loud_flag"] is True


def test_loud_threshold_override_can_raise_the_bar():
    loud_default = const_audio(0.06)
    assert audio_energy_features(loud_default)["loud_flag"] is True
    assert audio_energy_features(loud_default, loud_rms_thresh=0.1)["loud_flag"] is False


def test_audio_rms_value_is_unaffected_by_threshold():
    """Only the flag moves; the measured energy is the same number."""
    a = const_audio(0.03)
    assert (audio_energy_features(a)["audio_rms"]
            == audio_energy_features(a, loud_rms_thresh=0.01)["audio_rms"])


# --- video / motion_flag -------------------------------------------------

def test_motion_threshold_override_flips_motion_flag():
    frames = frame_pair(0.03)          # ~3% of rows change
    hi = video_motion_features(frames)                          # default 0.006
    lo = video_motion_features(frames, motion_level_thresh=0.5)  # very high bar
    assert hi["motion_flag"] is True
    assert lo["motion_flag"] is False


def test_motion_level_value_is_unaffected_by_threshold():
    frames = frame_pair(0.03)
    assert (video_motion_features(frames)["motion_level"]
            == video_motion_features(frames, motion_level_thresh=0.9)["motion_level"])


# --- extract_features passes overrides through to the fall rule ----------

def test_fall_fires_only_with_a_lowered_loud_threshold():
    """Was moving, motion stopped, and a QUIET-but-present sound. At the default
    loud bar it is not a fall; lower the bar and it becomes one -- exactly the
    live-tuning demo."""
    moving = frame_pair(0.03)
    still = frame_pair(0.0)            # identical frames -> no motion
    quiet_sound = const_audio(0.03)

    # prev second: moving. this second: still + quiet sound.
    default = extract_features(still, quiet_sound, prev_motion_flag=True)
    tuned = extract_features(still, quiet_sound, prev_motion_flag=True,
                             loud_rms_thresh=0.02)
    assert default["fall_suspected"] is False
    assert tuned["fall_suspected"] is True


def test_raising_motion_threshold_lets_a_twitch_count_as_stopped():
    """A small residual motion blocks the fall at the default; raise the motion
    bar and that twitch reads as 'stopped', so the fall can fire. This is the
    fix for the solo-demo coupling problem."""
    twitch = frame_pair(0.02)         # small motion, above default 0.006
    loud = const_audio(0.06)
    default = extract_features(twitch, loud, prev_motion_flag=True)
    tuned = extract_features(twitch, loud, prev_motion_flag=True,
                             motion_level_thresh=0.1)
    assert default["fall_suspected"] is False   # twitch counts as still-moving
    assert tuned["fall_suspected"] is True       # twitch now reads as stopped


def test_defaults_match_the_module_constants():
    """No override == the reference. If this fails, the boss's demo changed."""
    frames = frame_pair(0.03)
    audio = const_audio(0.06)
    explicit = extract_features(frames, audio, prev_motion_flag=False,
                                motion_level_thresh=MOTION_LEVEL_THRESH,
                                loud_rms_thresh=LOUD_RMS_THRESH)
    implicit = extract_features(frames, audio, prev_motion_flag=False)
    assert explicit == implicit
