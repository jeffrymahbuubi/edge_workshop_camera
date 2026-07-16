"""The fall rule (SPEC-04 §1-2), tested without a Jetson.

Why these tests exist: the rule's two most important behaviours are the ones a
bench test is WORST at proving. "Start already lying -> must not fire" and
"absent cancels a pending fall" are absences of an event -- at the bench you
watch nothing happen for a few seconds and call it a pass, which is also what a
broken rule looks like when the camera is pointed at a wall. Here they are
scripted and exact.

Time is injected (`now=`) rather than slept: a 3-second hold would otherwise
cost 3 real seconds per case, and `time.sleep` in a test suite measures the
clock, not the rule.
"""
import pytest

from edge.behaviour import BehaviourMonitor

HOLD = 3.0
LOOKBACK = 10.0


def monitor():
    return BehaviourMonitor(fall_hold_s=HOLD, upright_lookback_s=LOOKBACK)


def feed(m, script):
    """Run (posture, t) pairs through the monitor; return the last verdict."""
    verdict = None
    for posture, t in script:
        verdict = m.update(posture, now=t)
    return verdict


# --- the rule fires -----------------------------------------------------

def test_walk_then_lying_held_fires():
    """walking -> lying, held FALL_HOLD_S = the fall. SPEC-04 §1."""
    m = monitor()
    v = feed(m, [("walking", 0), ("walking", 1), ("lying", 2),
                 ("lying", 3), ("lying", 4), ("lying", 5)])
    assert v["abnormal"] is True
    assert "lying" in v["reason"]


def test_standing_counts_as_upright():
    """UPRIGHT = {standing, walking, sitting} -- a fall from standing is a fall."""
    m = monitor()
    v = feed(m, [("standing", 0), ("lying", 1), ("lying", 4)])
    assert v["abnormal"] is True


def test_sitting_counts_as_upright_so_a_fall_from_a_chair_fires():
    """MoveNet added `sitting` (SPEC-01 §5). Sitting is UPRIGHT for this rule.

    This is the colleague's validated semantics (`mode3_edge.py` counts sitting in
    its upright lookback), and it matters: falling out of a chair is the archetypal
    elderly fall. If sitting were inert, the most likely real fall would never fire.
    """
    m = monitor()
    v = feed(m, [("sitting", 0), ("lying", 1), ("lying", 4)])
    assert v["abnormal"] is True


def test_sitting_releases_the_latch():
    """Sitting up after a fall means they recovered -- clear the alarm.

    The colleague's rule clears on ANY non-lying label; ours clears only on
    UPRIGHT, and `sitting` joining UPRIGHT is what makes the two agree here.
    """
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])       # fired
    v = feed(m, [("sitting", 5)])
    assert v["abnormal"] is False
    assert v["reason"] == ""


def test_does_not_fire_before_hold_elapses():
    """Held 2s with FALL_HOLD_S=3 -> not yet. The hold is what rejects a stumble."""
    m = monitor()
    v = feed(m, [("walking", 0), ("lying", 1), ("lying", 2), ("lying", 2.9)])
    assert v["abnormal"] is False


def test_fires_exactly_at_hold_boundary():
    m = monitor()
    v = feed(m, [("walking", 0), ("lying", 1), ("lying", 1 + HOLD)])
    assert v["abnormal"] is True


# --- the rule must NOT fire ---------------------------------------------

def test_already_lying_at_startup_never_fires():
    """SPEC-04 §2: a person already lying when the camera starts is NOT a fall.

    Without the lookback every demo boots into a false alarm.
    """
    m = monitor()
    v = feed(m, [("lying", 0), ("lying", 1), ("lying", 5), ("lying", 60)])
    assert v["abnormal"] is False
    assert v["reason"] == ""


def test_upright_too_long_ago_does_not_count():
    """Upright seen, but outside UPRIGHT_LOOKBACK_S -> the lying is not a fall."""
    m = monitor()
    v = feed(m, [("walking", 0), ("absent", 1), ("lying", 20), ("lying", 30)])
    assert v["abnormal"] is False


def test_absent_cancels_a_pending_fall():
    """SPEC-04 §2: absent CANCELS -- do not treat it as continued lying.

    With bgsub, `absent` is the MOG2 fade (§1.2). Inferring a fall from a fade
    is inferring it from a bug.
    """
    m = monitor()
    v = feed(m, [("walking", 0), ("lying", 1), ("lying", 2),
                 ("absent", 2.5),          # fade -- pending fall dies here
                 ("lying", 3), ("lying", 3.5)])
    assert v["abnormal"] is False


def test_absent_restarts_the_hold_rather_than_resuming_it():
    """After absent, the clock restarts: 1s of lying is not 'held 3s'."""
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("absent", 2)])
    v = feed(m, [("lying", 3), ("lying", 4)])      # only 1s of new lying
    assert v["abnormal"] is False
    v = feed(m, [("lying", 6)])                    # now 3s since lying resumed
    assert v["abnormal"] is True


def test_walking_never_fires():
    m = monitor()
    v = feed(m, [("walking", t) for t in range(0, 30)])
    assert v["abnormal"] is False


# --- the latch ----------------------------------------------------------

def test_abnormal_latches_while_lying_continues():
    """SPEC-04 §2: latch so the dashboard banner does not flicker."""
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])
    v = feed(m, [("lying", 5), ("lying", 6), ("lying", 90)])
    assert v["abnormal"] is True


def test_absent_does_not_release_the_latch():
    """A fallen person fading to absent must not clear the alarm -- that is the
    fade erasing the very event it confirmed."""
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])       # fired
    v = feed(m, [("absent", 5), ("absent", 9)])
    assert v["abnormal"] is True


def test_returning_upright_releases_the_latch():
    """SPEC-04 §2: latch until posture returns to upright -- they got up."""
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])       # fired
    v = feed(m, [("standing", 5)])
    assert v["abnormal"] is False
    assert v["reason"] == ""


def test_reason_is_frozen_at_the_moment_it_fires():
    """The banner text must not churn (3s, 4s, 5s...) while latched."""
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1)])
    at_fire = m.update("lying", now=4)["reason"]
    later = m.update("lying", now=40)["reason"]
    assert at_fire == later


def test_reason_counts_up_while_the_fall_is_still_building():
    """Before firing, `reason` shows the hold building: "lying 1/3s".

    Freezing applies AFTER the alarm fires (that is what would churn the banner).
    While it is still building, counting up is the opposite of noise -- it is the
    only visible evidence the rule is working, and the colleague's guide §7 makes
    it a pass criterion.
    """
    m = monitor()
    feed(m, [("walking", 0)])
    m.update("lying", now=1)                                # episode begins, held=0
    building = m.update("lying", now=2)["reason"]           # held=1s
    assert "1" in building and "3" in building              # "lying 1/3s"
    assert m.update("lying", now=3)["reason"] != building   # advances to 2/3s
    assert m.update("lying", now=4)["abnormal"] is True     # then fires


def test_building_reason_does_not_claim_abnormal():
    """A counting reason must never be mistaken for a fired alarm."""
    m = monitor()
    feed(m, [("walking", 0)])
    v = m.update("lying", now=2)
    assert v["abnormal"] is False
    assert "upright" not in v["reason"]      # the fired text says "upright→lying"


def test_a_building_count_is_cleared_when_they_go_absent():
    """A half-built "lying 1/3s" must not outlive the person it was counting.

    Introduced with the counting reason: cancelling a pending fall has to clear
    its text too, or the panel keeps counting someone who has left the frame.
    """
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 2)])       # building
    v = m.update("absent", now=3)
    assert v["abnormal"] is False
    assert v["reason"] == ""


def test_absent_keeps_a_FIRED_reason_not_just_the_flag():
    """The latch survives absent (tested above) -- so must its text, or the
    banner goes blank while still claiming abnormal."""
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])       # fired
    v = m.update("absent", now=5)
    assert v["abnormal"] is True
    assert "upright" in v["reason"]


def test_reason_is_human_text_naming_the_transition():
    """`reason` goes straight to the caregiver panel (SPEC-04 §2)."""
    m = monitor()
    v = feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])
    assert "upright" in v["reason"] and "lying" in v["reason"]
    assert "3" in v["reason"]


# --- a second fall after recovery ---------------------------------------

def test_second_fall_after_getting_up_fires_again():
    m = monitor()
    feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])       # fall 1
    feed(m, [("standing", 5)])                                  # got up
    v = feed(m, [("lying", 6), ("lying", 9)])                   # fall 2
    assert v["abnormal"] is True


# --- backend agnosticism (SPEC-04 §2) -----------------------------------

def test_consumes_labels_only_no_backend_coupling():
    """The monitor must work identically under bgsub and trt_pose -- it may only
    ever see a posture string. This is what lets SPEC-05 swap in with no rework.
    """
    m = monitor()
    v = m.update("lying", now=0)
    assert set(v) == {"abnormal", "reason"}


@pytest.mark.parametrize("bogus", ["", None, "LYING", "crouching"])
def test_unknown_labels_are_inert_not_crashes(bogus):
    """An unrecognised label must not fire and must not raise -- a backend that
    invents a label should degrade, not take the Jetson down mid-demo.

    `sitting` used to be listed here as bogus. It is now a REAL label (MoveNet,
    SPEC-01 §5) and has its own tests above -- the exact kind of drift this
    parametrize exists to catch, so keep it in sync with the contract.
    """
    m = monitor()
    feed(m, [("walking", 0)])
    v = m.update(bogus, now=1)
    assert v["abnormal"] is False


def test_default_hold_is_three_seconds():
    """SPEC-04 §1.2: default N=3s with bgsub, to fire before the ~8s fade."""
    assert BehaviourMonitor().fall_hold_s == 3.0


# --- multi-modal fusion (SPEC-08 Part A) --------------------------------
#
# Sound CORROBORATES; it never gates. Two senses agreeing buy SPEED, not
# permission. The `lying AND loud` rule was rejected because a person who
# slumps silently makes no thump -- gating on sound would trade a real
# detection for a tidier workshop theme (SPEC-08 §A2).

FAST = 1.0
WINDOW = 2.0


def fusion_monitor():
    return BehaviourMonitor(fall_hold_s=HOLD, upright_lookback_s=LOOKBACK,
                            fall_hold_fast_s=FAST, loud_corroboration_s=WINDOW)


def test_thump_at_the_drop_fires_at_the_fast_hold():
    """walk -> lying + a thump = both senses agree = fire in 1s, not 3s."""
    m = fusion_monitor()
    m.update("walking", now=0)
    m.update("lying", loud=True, now=1)          # the impact
    v = m.update("lying", now=2)                 # held 1s -> fast hold met
    assert v["abnormal"] is True


def test_a_thump_does_not_fire_before_even_the_fast_hold():
    """Corroboration lowers the bar to 1s. It does not remove it -- a thump plus
    an instant of lying is a stumble, not a confirmed fall."""
    m = fusion_monitor()
    m.update("walking", now=0)
    v = m.update("lying", loud=True, now=1)      # held 0s
    assert v["abnormal"] is False


def test_thump_just_BEFORE_the_drop_still_counts():
    """The window is two-sided (SPEC-08 §A3).

    The impact and the first `lying` label usually land in the same 1s tick, but
    which one wins the tick is a race -- the thump can be sampled a tick early or
    a tick late. A one-sided window would drop real corroborations for no reason.
    """
    m = fusion_monitor()
    m.update("walking", loud=True, now=0)        # thump lands while still upright
    m.update("lying", now=1)
    v = m.update("lying", now=2)                 # held 1s
    assert v["abnormal"] is True


def test_thump_outside_the_window_does_not_upgrade():
    """A thump only counts if it belongs to THE DROP.

    At t=3.5 the person has been lying 2.5s. Corroborated that would have fired
    (>= 1s); un-corroborated it must not (< 3s). This is the assertion that keeps
    `_last_loud_t` from meaning "any loud sound, ever".
    """
    m = fusion_monitor()
    m.update("walking", now=0)
    m.update("lying", now=1)
    v = m.update("lying", loud=True, now=3.5)    # thump 2.5s late -- outside 2.0s
    assert v["abnormal"] is False
    assert m.update("lying", now=4)["abnormal"] is True      # still fires at 3s


def test_a_cough_while_already_lying_in_bed_never_fires():
    """THE false-positive this window exists to prevent.

    Someone lying in bed has no upright behind them, so the lookback already
    rejects it -- but a naive "loud + lying" fusion would resurrect it. Sound must
    never manufacture a fall the vision rule rejected.
    """
    m = fusion_monitor()
    v = feed(m, [("lying", 0), ("lying", 1)])
    v = m.update("lying", loud=True, now=2)      # coughs
    assert v["abnormal"] is False
    assert m.update("lying", loud=True, now=60)["abnormal"] is False


def test_corroboration_latches_across_a_quiet_second():
    """A fall is QUIET after the impact -- that is the whole signature.

    If corroboration were re-evaluated each tick from the current `loud`, the
    silence that follows every real fall would demote it back to the 3s hold and
    the fast path would never fire.
    """
    m = fusion_monitor()
    m.update("walking", now=0)
    m.update("lying", loud=True, now=1)          # thump
    v = m.update("lying", loud=False, now=2)     # silence after impact
    assert v["abnormal"] is True


def test_reason_names_the_thump_when_corroborated():
    """SPEC-08 §A4: the fusion is INVISIBLE otherwise.

    Both senses agreeing and vision alone would print identical banners, and the
    student would learn nothing about what fusion bought them. This string is the
    only place fusion becomes watchable.
    """
    m = fusion_monitor()
    m.update("walking", now=0)
    m.update("lying", loud=True, now=1)
    v = m.update("lying", now=2)
    assert "thump" in v["reason"]
    assert "upright" in v["reason"]


def test_vision_only_reason_does_NOT_claim_a_thump():
    m = fusion_monitor()
    v = feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])
    assert v["abnormal"] is True
    assert "thump" not in v["reason"]


# --- the safety property (SPEC-08 §A2/§A3) ------------------------------
#
# THE argument for corroboration over `lying AND loud`. If these fail, the
# change stopped being safe and became a regression.

def test_a_silent_fall_still_fires_at_the_normal_hold():
    """The person who slumps silently -- faints, slides onto carpet. THE case
    that killed the `lying AND loud` design."""
    m = fusion_monitor()
    v = feed(m, [("walking", 0), ("lying", 1), ("lying", 4)])
    assert v["abnormal"] is True
    assert "3" in v["reason"]


def test_a_deaf_board_behaves_EXACTLY_like_today():
    """SPEC-08 §A2: the mic is this project's most likely per-board failure, and
    it fails SILENTLY (PulseAudio defaults to the empty onboard jack; the
    persisted fix embeds a webcam serial). Under `lying AND loud` a deaf board
    could never alarm at all. Under corroboration it degrades to vision-only.

    `loud` is never passed here -- exactly what a caller with a dead mic sends.
    """
    deaf = fusion_monitor()
    vision_only = monitor()
    script = [("walking", 0), ("walking", 1), ("lying", 2), ("lying", 3),
              ("lying", 5), ("absent", 6), ("standing", 7)]
    for posture, t in script:
        assert deaf.update(posture, now=t) == vision_only.update(posture, now=t)


def test_loud_defaults_to_false_so_existing_callers_are_unchanged():
    """The whole suite above calls update() without `loud`. If that ever stopped
    meaning "vision only", every one of those tests would silently change meaning.
    """
    m = fusion_monitor()
    m.update("walking", now=0)
    m.update("lying", now=1)
    assert m.update("lying", now=2)["abnormal"] is False      # NOT the fast hold


def test_defaults_come_from_config():
    m = BehaviourMonitor()
    assert m.fall_hold_fast_s == 1.0
    assert m.loud_corroboration_s == 2.0
    assert m.fall_hold_fast_s < m.fall_hold_s      # or corroboration buys nothing
