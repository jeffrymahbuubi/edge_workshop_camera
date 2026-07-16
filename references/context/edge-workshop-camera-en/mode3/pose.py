"""Deep-learning pose estimation for Mode 3 (MoveNet SinglePose, CPU).

Runs MoveNet to get 17 body keypoints, then classifies the activity with ROBUST,
temporally-smoothed rules (built to survive a small room / partial-body view):

  * lying    -- torso clearly HORIZONTAL (shoulders<->hips span sideways)
  * sitting  -- upright torso BUT thighs (hips->knees) roughly horizontal
  * walking  -- upright AND the body's centroid is translating across the frame
  * standing -- upright and roughly stationary
  * absent   -- too few confident keypoints

Robustness features (vs the naive single-frame rule):
  - walking is decided by CENTROID MOVEMENT over time, not frame-difference noise,
    so a still person no longer reads as "walking";
  - a MAJORITY VOTE over the last SMOOTH_N seconds debounces one-frame glitches;
  - only confident joints are used, and lying/sitting need a minimum torso/thigh
    length + a clear orientation margin, so noise can't flip the label.

estimate(frames, motion_level) -> {"keypoints","bbox","posture","score"}   (0..1 coords)
"""
import collections
import os

import numpy as np

MOVENET_MODEL = os.environ.get("MOVENET_MODEL", "models/movenet_lightning.tflite")
KP_CONF = float(os.environ.get("KP_CONF", "0.3"))            # min keypoint score to trust
MIN_KEYPOINTS = int(os.environ.get("MIN_KEYPOINTS", "4"))
MIN_BODY = float(os.environ.get("MIN_BODY", "0.15"))         # min body span to judge lying
UPRIGHT_MARGIN = float(os.environ.get("UPRIGHT_MARGIN", "0.03"))  # bias toward upright when head~hip (anti false-lying)
MIN_TORSO = float(os.environ.get("MIN_TORSO", "0.05"))       # min torso length for the sitting calc
LYING_RATIO = float(os.environ.get("LYING_RATIO", "0.8"))    # fallback: body dy < dx*ratio -> lying
SIT_DROP_RATIO = float(os.environ.get("SIT_DROP_RATIO", "0.6"))  # knee drop < torso*ratio -> sitting
WALK_MOVE_THRESH = float(os.environ.get("WALK_MOVE_THRESH", "0.03"))  # centroid move -> walking
SMOOTH_N = int(os.environ.get("SMOOTH_N", "3"))              # majority-vote window (seconds)

# COCO / MoveNet keypoint indices
L_SHO, R_SHO, L_HIP, R_HIP, L_KNEE, R_KNEE = 5, 6, 11, 12, 13, 14


def _load_interpreter(path):
    # Prefer the light tflite_runtime; fall back to full TensorFlow's tf.lite.
    # `except Exception` also catches a tflite_runtime wheel that imports but fails
    # to load its native lib (e.g. GLIBC mismatch on JetPack 4).
    Interpreter = None
    try:
        from tflite_runtime.interpreter import Interpreter
    except Exception:
        import tensorflow as tf
        Interpreter = tf.lite.Interpreter
    interp = Interpreter(model_path=path)
    interp.allocate_tensors()
    return interp


class MoveNetPose:
    def __init__(self):
        if not os.path.exists(MOVENET_MODEL):
            raise FileNotFoundError(
                f"MoveNet model not found at {MOVENET_MODEL}. Download MoveNet "
                "SinglePose Lightning (.tflite) into models/ or set MOVENET_MODEL.")
        self._it = _load_interpreter(MOVENET_MODEL)
        self._in = self._it.get_input_details()[0]
        self._out = self._it.get_output_details()[0]
        _, self._h, self._w, _ = self._in["shape"]
        self._hist = collections.deque(maxlen=SMOOTH_N)     # recent raw labels
        self._prev_center = None                            # for movement detection
        self._last_label = "absent"                         # last output (for hysteresis)

    def _infer(self, frame):
        import cv2
        img = cv2.cvtColor(cv2.resize(frame, (self._w, self._h)), cv2.COLOR_BGR2RGB)
        inp = img.astype(np.uint8 if self._in["dtype"] == np.uint8 else np.float32)
        self._it.set_tensor(self._in["index"], np.expand_dims(inp, 0))
        self._it.invoke()
        return self._it.get_tensor(self._out["index"])[0, 0]   # [17,3] = (y,x,score)

    def estimate(self, frames, motion_level=0.0):
        raw = self._infer(frames[-1])
        kps = [[float(x), float(y), float(s)] for (y, x, s) in raw]   # -> (x,y,score)

        static, center = _static_posture(kps)               # lying/sitting/upright/absent

        # walking = the person's centroid actually moved since last second
        moving = False
        if center is not None and self._prev_center is not None:
            dx = center[0] - self._prev_center[0]
            dy = center[1] - self._prev_center[1]
            moving = (dx * dx + dy * dy) ** 0.5 >= WALK_MOVE_THRESH
        self._prev_center = center

        label = static
        if static == "upright":
            label = "walking" if moving else "standing"
        # hysteresis: you can't go straight from sitting to walking even while moving
        # (a chair shuffle). Reaching walking requires first standing up.
        if label == "walking" and self._last_label == "sitting":
            label = "sitting"

        # majority vote over the last SMOOTH_N seconds -> stable output
        self._hist.append(label)
        smooth = collections.Counter(self._hist).most_common(1)[0][0]
        self._last_label = smooth

        good = [k for k in kps if k[2] >= KP_CONF]
        score = round(float(np.mean([k[2] for k in good])) if good else 0.0, 2)
        return {"keypoints": kps, "bbox": _bbox_from_keypoints(kps),
                "posture": smooth, "score": score}


def _pt(kps, idxs):
    """Mean (x, y) of the confident keypoints among idxs, or None."""
    pts = [(kps[i][0], kps[i][1]) for i in idxs if kps[i][2] >= KP_CONF]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _static_posture(kps):
    """Single-frame static pose (no walking): absent / lying / sitting / upright.
    Also returns the body centroid (for movement detection) or None.
    """
    good = [k for k in kps if k[2] >= KP_CONF]
    if len(good) < MIN_KEYPOINTS:
        return "absent", None
    xs, ys = [k[0] for k in good], [k[1] for k in good]
    center = (float(np.mean(xs)), float(np.mean(ys)))
    body_dx, body_dy = max(xs) - min(xs), max(ys) - min(ys)
    body = max(body_dx, body_dy)

    head = _pt(kps, (0,)) or _pt(kps, (L_SHO, R_SHO))   # nose, else shoulder midpoint
    hip = _pt(kps, (L_HIP, R_HIP))

    # LYING: the head is BESIDE (or below) the hips rather than clearly ABOVE them.
    # Compares the head->hip horizontal gap vs its vertical gap, so it's orientation-
    # agnostic and catches curled / non-straight poses. Fallback (head or hips not
    # visible): whole body wider than tall.
    if head is not None and hip is not None and body >= MIN_BODY:
        if abs(hip[0] - head[0]) > (hip[1] - head[1]) + UPRIGHT_MARGIN:
            return "lying", center
    elif body >= MIN_BODY and body_dy < body_dx * LYING_RATIO:
        return "lying", center

    # SITTING: upright torso, but a knee is folded up near hip height. Needs a hip,
    # a shoulder (for torso scale) and at least ONE knee (relaxed from both) -> more
    # forgiving when the far leg is hidden/foreshortened facing the camera.
    sh = _pt(kps, (L_SHO, R_SHO))
    knees = [kps[i][1] for i in (L_KNEE, R_KNEE) if kps[i][2] >= KP_CONF]
    if hip is not None and sh is not None and knees:
        torso_len = abs(hip[1] - sh[1])
        knee_drop = min(abs(ky - hip[1]) for ky in knees)   # smallest drop among knees
        if torso_len >= MIN_TORSO and knee_drop < torso_len * SIT_DROP_RATIO:
            return "sitting", center

    return "upright", center


def _bbox_from_keypoints(kps, pad=0.03):
    good = [k for k in kps if k[2] >= KP_CONF]
    if len(good) < 2:
        return None
    xs, ys = [k[0] for k in good], [k[1] for k in good]
    x0, y0 = max(0.0, min(xs) - pad), max(0.0, min(ys) - pad)
    x1, y1 = min(1.0, max(xs) + pad), min(1.0, max(ys) + pad)
    return [round(x0, 3), round(y0, 3), round(x1 - x0, 3), round(y1 - y0, 3)]


def get_pose_estimator(kind="movenet"):
    if kind == "movenet":
        return MoveNetPose()
    raise ValueError(f"unknown pose backend: {kind!r}")
