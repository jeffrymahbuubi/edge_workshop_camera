"""The fall rule (SPEC-04 §2) -- runs ON THE JETSON.

    walking, walking, walking -> suddenly lying -> lying = FALL

Formally: an upright posture, followed by a transition to `lying`, held for
FALL_HOLD_S seconds.

This module consumes POSTURE LABELS AND NOTHING ELSE. It never sees a frame, a
bbox or a keypoint, so it behaves identically under `bgsub` and `trt_pose` --
which is what lets SPEC-05 swap the backend in with no rework here. Keep it that
way: if this file ever imports cv2, the swap has been broken.

Only the verdict leaves the device (SPEC-01 §4.3). The rule runs here, on the
Jetson, for the same reason Mode 2 computes features here: shipping the raw
signal to the laptop to decide would repeat Mode 1's mistake in a new costume.
"""
import time

from common.config import FALL_HOLD_S, UPRIGHT_LOOKBACK_S

UPRIGHT = ("standing", "walking")


class BehaviourMonitor:
    """Watches a stream of posture labels and decides when one is a fall.

    Call update() once per second with the second's posture label.
    """

    def __init__(self, fall_hold_s=None, upright_lookback_s=None):
        self.fall_hold_s = FALL_HOLD_S if fall_hold_s is None else float(fall_hold_s)
        self.upright_lookback_s = (UPRIGHT_LOOKBACK_S if upright_lookback_s is None
                                   else float(upright_lookback_s))
        self._last_upright_t = None    # when we last saw standing/walking
        self._lying_since = None       # when the CURRENT run of lying began
        self._abnormal = False         # latched
        self._reason = ""

    def update(self, posture, now=None):
        """Feed one second's posture. Returns {"abnormal": bool, "reason": str}.

        `now` is injectable so the rule can be tested without sleeping through
        the hold; production callers omit it.
        """
        now = time.time() if now is None else now

        if posture in UPRIGHT:
            # They are on their feet: no pending fall, and any latched alarm is
            # over -- they got up.
            self._last_upright_t = now
            self._lying_since = None
            self._abnormal = False
            self._reason = ""

        elif posture == "lying":
            if self._lying_since is None and self._recently_upright(now):
                self._lying_since = now        # the transition we care about
            self._check_hold(now)

        else:
            # "absent" and anything unrecognised. Cancel a PENDING fall but do
            # NOT clear a latched one.
            #
            # With bgsub, `absent` is usually the MOG2 fade (SPEC-04 §1.2) -- a
            # motionless person being learned into the background. Treating that
            # as continued lying would infer the fall from a bug; treating it as
            # "got up" would erase an alarm that already fired. So: cancel
            # pending, keep latched.
            self._lying_since = None

        return {"abnormal": self._abnormal, "reason": self._reason}

    def _recently_upright(self, now):
        """A lying only counts as a fall if they were upright just before it.

        A person already lying when the camera starts has no upright behind them
        and is not a fall -- they may simply be in bed.
        """
        return (self._last_upright_t is not None
                and now - self._last_upright_t <= self.upright_lookback_s)

    def _check_hold(self, now):
        if self._abnormal or self._lying_since is None:
            return                              # already fired, or nothing pending
        held = now - self._lying_since
        if held >= self.fall_hold_s:
            self._abnormal = True
            # Frozen at the moment of firing: recomputing it every second would
            # churn the caregiver's banner (3s, 4s, 5s...) for one event.
            self._reason = f"upright→lying held {int(held)}s"
