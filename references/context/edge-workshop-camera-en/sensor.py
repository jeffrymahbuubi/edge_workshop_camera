"""Sensor abstraction layer for camera + audio.

The DEFAULT source is a SYNTHETIC SCENE, so the whole pipeline runs on any
laptop with no webcam and no microphone. The scene has a KNOWN pattern:

  * a colored block that moves for 4 s, then STOPS for 2 s, repeating;
  * at each moment it stops, a short LOUD burst is injected into the audio.

That known pattern is the "ground truth": students can check that motion
detection fires while the block moves and goes quiet when it stops, and that
the loud-burst-at-stop looks like a fall (loud sound + motion suddenly ends).

Each read_second() returns:
  frames : list of FPS BGR uint8 frames for this second
  audio  : float32 array of AUDIO_SR samples for this second
  truth  : dict of ground-truth labels for this second (for validation)

To use a real USB webcam + microphone, see WebcamMicSource below and select it
via get_sensor("webcam").
"""
import collections
import threading
import time

import cv2
import numpy as np

from common import FRAME_W, FRAME_H, FPS, AUDIO_SR, CAMERA_INDEX

# scene timing (seconds): move for MOVE_S, then stay still for STILL_S
MOVE_S, STILL_S = 4, 2
CYCLE = MOVE_S + STILL_S


class SyntheticScene:
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)
        self.sec = 0
        self.x = 40.0
        self.vx = 8.0                       # px per frame while moving
        self.block = 40                     # block size (px)

    def _render(self, x):
        # gray background with light noise (won't trigger motion by itself)
        frame = np.full((FRAME_H, FRAME_W, 3), 120, dtype=np.uint8)
        noise = self.rng.integers(-3, 4, size=(FRAME_H, FRAME_W, 1), dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        # draw a bright block
        x0 = int(np.clip(x, 0, FRAME_W - self.block))
        y0 = FRAME_H // 2 - self.block // 2
        frame[y0:y0 + self.block, x0:x0 + self.block] = (230, 230, 230)
        return frame

    def read_second(self):
        phase_moving = (self.sec % CYCLE) < MOVE_S
        just_stopped = (self.sec % CYCLE) == MOVE_S   # first still second

        frames = []
        for _ in range(FPS):
            if phase_moving:
                self.x += self.vx
                if self.x > FRAME_W - self.block or self.x < 0:   # bounce
                    self.vx = -self.vx
                    self.x += self.vx
            frames.append(self._render(self.x))

        # audio: low-energy background, plus a loud impact when the block stops
        audio = self.rng.normal(0, 0.01, AUDIO_SR).astype(np.float32)
        if just_stopped:
            n = int(0.3 * AUDIO_SR)
            burst = self.rng.normal(0, 0.3, n).astype(np.float32)
            burst *= np.linspace(1.0, 0.0, n)     # decaying impact
            audio[:n] += burst

        truth = {"gt_moving": bool(phase_moving), "gt_impact": bool(just_stopped)}
        self.sec += 1
        return frames, audio, truth


class WebcamMicSource:
    """Real USB webcam + microphone source.

    Video: cv2.VideoCapture(camera_index), each frame resized to FRAME_W x
    FRAME_H. Audio: a persistent sounddevice InputStream fills a ring buffer;
    read_second() returns one second of video + audio, same shape as the
    synthetic scene, so the rest of the pipeline is unchanged.

    Graceful degradation: if no microphone is available (or sounddevice is not
    installed), it runs VIDEO-ONLY with silent audio and prints a warning -- a
    laptop with a working camera but a flaky mic still completes the workshop.

    Real frames have no ground truth, so truth is {"gt_moving": None,
    "gt_impact": None}. (compare.py uses the synthetic scene, not this source.)
    """

    def __init__(self, camera_index=None, audio_device=None, warmup_frames=5):
        idx = CAMERA_INDEX if camera_index is None else camera_index
        self.cap = cv2.VideoCapture(idx)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera at index {idx}. Try another index "
                f"(0/1/2) via CAMERA_INDEX=<n>, close other apps using the "
                f"camera, or check OS camera permissions.")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
        for _ in range(warmup_frames):        # first frames are often dark
            self.cap.read()

        # --- audio: background input stream into a ring buffer (~2 s) ---
        self._audio_buf = collections.deque(maxlen=AUDIO_SR * 2)
        self._audio_lock = threading.Lock()
        self._stream = None
        try:
            import sounddevice as sd

            def _cb(indata, frames, time_info, status):
                with self._audio_lock:
                    self._audio_buf.extend(indata[:, 0].copy())

            self._stream = sd.InputStream(
                samplerate=AUDIO_SR, channels=1, dtype="float32",
                device=audio_device, callback=_cb)
            self._stream.start()
        except Exception as e:
            print(f"[WebcamMicSource] microphone unavailable ({e}); "
                  f"running VIDEO-ONLY with silent audio.")

    def read_second(self):
        # align audio to this second's video: drop stale buffered samples first
        with self._audio_lock:
            self._audio_buf.clear()

        frames = []
        t0 = time.time()
        while time.time() - t0 < 1.0:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.005)
                continue
            frames.append(cv2.resize(frame, (FRAME_W, FRAME_H)))

        # fast cameras may give >FPS frames: subsample to ~FPS to bound cost
        if len(frames) > FPS:
            keep = np.linspace(0, len(frames) - 1, FPS).astype(int)
            frames = [frames[i] for i in keep]
        if len(frames) < 2:                    # keep motion features well-defined
            frames = (frames * 2 if frames
                      else [np.zeros((FRAME_H, FRAME_W, 3), np.uint8)] * 2)

        # snapshot one second of audio, padded/truncated to exactly AUDIO_SR
        with self._audio_lock:
            audio = np.array(self._audio_buf, dtype=np.float32)
        if audio.size >= AUDIO_SR:
            audio = audio[-AUDIO_SR:]
        else:
            audio = np.pad(audio, (0, AUDIO_SR - audio.size))

        return frames, audio, {"gt_moving": None, "gt_impact": None}

    def close(self):
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        try:
            self.cap.release()
        except Exception:
            pass

    def __del__(self):
        self.close()


def get_sensor(kind="synthetic", **kw):
    if kind == "synthetic":
        return SyntheticScene(**kw)
    if kind == "webcam":
        return WebcamMicSource(**kw)
    raise ValueError(f"unknown sensor kind: {kind}")
