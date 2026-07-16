"""The fall rule (SPEC-04 §2, SPEC-08 Part A) -- runs ON THE JETSON.

    walking, walking, walking -> suddenly lying -> lying = FALL

Formally: an upright posture, followed by a transition to `lying`, held for
FALL_HOLD_S seconds -- or only FALL_HOLD_FAST_S if a thump corroborated the drop.

MULTI-MODAL, BUT SOUND NEVER GATES (SPEC-08 §A2-A3).
Sound buys SPEED, not permission. The obvious `lying AND loud` rule was
considered and REJECTED: a person who slumps silently -- faints, slides off a
chair onto carpet -- makes no thump, and vision alone catches them today.
Gating on sound would trade a REAL DETECTION for a tidier workshop theme. It
would also couple this rule to the microphone, the project's most likely
per-board failure, and one that fails silently. With `loud=False` throughout,
this file behaves EXACTLY as it did before fusion existed -- that property is the
safety argument, and `test_a_deaf_board_behaves_EXACTLY_like_today` pins it.

This module consumes POSTURE LABELS AND A BOOLEAN, AND NOTHING ELSE. It never
sees a frame, a bbox, a keypoint or an audio sample -- `loud` is a plain flag the
caller decided. It therefore still behaves identically under `bgsub` and
`movenet`. That design was speculative when written; it PAID OFF when Mode 3
swapped from background subtraction to MoveNet keypoints -- this file needed one
line (adding `sitting`) and nothing else. Keep it that way: if this file ever
imports cv2, `common.features`, or touches a keypoint, the swap has been broken.

The rule runs here, on the Jetson, for the same reason Mode 2 computes features
here: shipping the raw signal to the laptop to decide would repeat Mode 1's
mistake in a new costume.
"""
import time

from common.config import (FALL_HOLD_S, UPRIGHT_LOOKBACK_S, FALL_HOLD_FAST_S,
                           LOUD_CORROBORATION_S)

# `sitting` is UPRIGHT, not a posture of its own concern: falling out of a chair
# is the archetypal fall this workshop is about, so a sitting->lying transition
# must fire. This matches the colleague's hardware-validated rule, which counts
# standing/walking/sitting alike in its upright lookback.
UPRIGHT = ("standing", "walking", "sitting")


class BehaviourMonitor:
    """Watches a stream of posture labels and decides when one is a fall.

    Call update() once per second with the second's posture label.
    """

    def __init__(self, fall_hold_s=None, upright_lookback_s=None,
                 fall_hold_fast_s=None, loud_corroboration_s=None):
        self.fall_hold_s = FALL_HOLD_S if fall_hold_s is None else float(fall_hold_s)
        self.upright_lookback_s = (UPRIGHT_LOOKBACK_S if upright_lookback_s is None
                                   else float(upright_lookback_s))
        self.fall_hold_fast_s = (FALL_HOLD_FAST_S if fall_hold_fast_s is None
                                 else float(fall_hold_fast_s))
        self.loud_corroboration_s = (LOUD_CORROBORATION_S if loud_corroboration_s is None
                                     else float(loud_corroboration_s))
        self._last_upright_t = None    # when we last saw standing/walking
        self._lying_since = None       # when the CURRENT run of lying began
        self._last_loud_t = None       # when we last heard a loud sound
        self._corroborated = False     # did a thump belong to THIS drop?
        self._abnormal = False         # latched
        self._reason = ""

    def update(self, posture, loud=False, now=None):
        """Feed one second's posture (+ whether it was loud). Returns
        {"abnormal": bool, "reason": str}.

        `loud` DEFAULTS TO FALSE, and that default is load-bearing: it is what a
        caller with a dead microphone sends, and it must mean "vision only",
        i.e. exactly the pre-fusion rule. Sound may only ever make this rule
        FASTER, never blind -- see the class docstring.

        `now` is injectable so the rule can be tested without sleeping through
        the hold; production callers omit it.
        """
        now = time.time() if now is None else now

        # Recorded BEFORE the posture branches: the impact and the first `lying`
        # label routinely land in the same tick, so a thump must be visible to
        # the transition being detected in this very call.
        if loud:
            self._last_loud_t = now

        if posture in UPRIGHT:
            # They are on their feet: no pending fall, and any latched alarm is
            # over -- they got up.
            self._last_upright_t = now
            self._lying_since = None
            self._corroborated = False
            self._abnormal = False
            self._reason = ""

        elif posture == "lying":
            if self._lying_since is None and self._recently_upright(now):
                self._lying_since = now        # the transition we care about
                self._corroborated = False     # a new drop earns its own thump
            self._corroborate(now)
            self._check_hold(now)

        else:
            # "absent" and anything unrecognised. Cancel a PENDING fall but do
            # NOT clear a latched one.
            #
            # Under bgsub `absent` was usually the MOG2 fade (SPEC-04 §1.2) -- a
            # motionless person learned into the background. Under MoveNet there
            # is no fade, so `absent` means the keypoints genuinely went away
            # (left the frame, or occluded). Either way the reasoning holds:
            # treating it as continued lying would invent a fall from missing
            # data; treating it as "got up" would erase an alarm that already
            # fired. So: cancel pending, keep latched.
            self._lying_since = None
            self._corroborated = False
            if not self._abnormal:
                # A half-built count ("lying 1/3s") must not outlive the person
                # it was counting -- but a FIRED alarm's reason must survive, or
                # absent would quietly blank the banner it just raised.
                self._reason = ""

        return {"abnormal": self._abnormal, "reason": self._reason}

    def _corroborate(self, now):
        """Did a thump belong to THIS drop? (SPEC-08 §A3.)

        Two-sided around the transition, because the impact and the first `lying`
        label usually share a tick and which one wins it is a race.

        Once set it LATCHES for the run of lying. Re-deciding it every tick from
        the current `loud` would demote every real fall back to the slow hold on
        the very next second -- a fall is SILENT after the impact, which is the
        whole signature. The fast path would then never fire.
        """
        if self._lying_since is None or self._corroborated:
            return
        if self._last_loud_t is None:
            return
        if abs(self._last_loud_t - self._lying_since) <= self.loud_corroboration_s:
            self._corroborated = True

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
        # Two senses agreeing lower the bar; they never remove it. A thump plus
        # an instant of lying is a stumble, not a confirmed fall.
        hold = self.fall_hold_fast_s if self._corroborated else self.fall_hold_s
        # Naming the thump is not decoration. Without it a corroborated fall and
        # a vision-only fall print IDENTICAL banners, the fusion becomes
        # invisible, and the student learns nothing about what the second sense
        # bought them (SPEC-08 §A4). This string is the only place fusion shows.
        thump = "thump + " if self._corroborated else ""
        if held >= hold:
            self._abnormal = True
            # Frozen at the moment of firing: recomputing it every second would
            # churn the caregiver's banner (3s, 4s, 5s...) for ONE event.
            self._reason = f"{thump}upright→lying held {int(held)}s"
        else:
            # Still building. Counting up here is not the churn the freeze above
            # guards against -- that is about the text moving AFTER the alarm has
            # fired. Before it fires, "lying 1/3s" is the only visible evidence
            # the rule is armed and working, which is why the colleague's guide
            # §7 makes it a pass criterion. It must never read like a fired
            # alarm: no "upright→lying" wording until `abnormal` is actually True.
            self._reason = f"{thump}lying {int(held)}/{int(hold)}s"
