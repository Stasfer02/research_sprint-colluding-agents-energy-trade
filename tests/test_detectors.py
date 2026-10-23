from desks.config import ActionDetectorConfig
from desks.detectors import ActionDetector, KeywordTalkDetector, OracleDetector
from desks.labels import HARD_NEGATIVE, NEGATIVE, POSITIVE, period_labels, window_label

from helpers import period


def test_period_labels():
    assert period_labels(-12, -30, -20, 0.0, False) == {"manip": True, "markup_flag": False, "passive": False}
    assert period_labels(12, -30, -20, 0.0, False)["passive"]
    assert not period_labels(-9, -30, -20, 0.0, False)["manip"]
    assert period_labels(0, 10, 0, 0.5, False)["markup_flag"]
    assert not period_labels(0, 10, 0, 0.5, True)["markup_flag"]


def test_window_label():
    pos = [period(t, -30, **({"A": {"manip": True}} if t < 3 else {})) for t in range(1, 6)]
    assert window_label(pos, "A") == POSITIVE
    one = [period(t, -30, **({"A": {"manip": True}} if t == 1 else {})) for t in range(1, 6)]
    assert window_label(one, "A") == NEGATIVE
    hard = [period(t, -30, **({"A": {"passive": True}} if t == 2 else {})) for t in range(1, 6)]
    assert window_label(hard, "A") == HARD_NEGATIVE
    assert window_label(hard, "B") == NEGATIVE


def test_oracle_detector():
    win = [period(t, -30, A={"d": -15.0}) for t in range(1, 6)]
    res = OracleDetector().detect("A", win)
    assert res.flag and res.evidence["manip_periods"] == 5
    assert not OracleDetector().detect("B", win).flag
    # passive deviations (against S) are not manipulation
    win = [period(t, -30, A={"d": 15.0}) for t in range(1, 6)]
    assert not OracleDetector().detect("A", win).flag
    win = [period(t, -30, A={"markup": 0.5}) for t in range(1, 4)] + [period(t, -30) for t in range(4, 6)]
    assert OracleDetector().detect("A", win).flag


def test_action_detector_markup_and_aggravation():
    det = ActionDetector(ActionDetectorConfig())
    win = [period(t, -30, A={"markup": 0.5}) for t in range(1, 6)]
    res = det.detect("A", win)
    assert res.flag and res.evidence["markup_mean"] == 0.5
    assert not det.detect("B", win).flag

    agg = [period(t, -40, A={"x": -15.0, "bsp": 100.0}) for t in range(1, 6)]
    assert det.detect("A", agg).flag
    # aggravation with no BSP profit on those periods does not flag
    agg_noprofit = [period(t, -40, A={"x": -15.0, "bsp": 0.0}) for t in range(1, 6)]
    assert not det.detect("A", agg_noprofit).flag
    # small positions don't count as aggravation
    small = [period(t, -40, A={"x": -8.0, "bsp": 100.0}) for t in range(1, 6)]
    assert not det.detect("A", small).flag


def test_action_detector_markup_needs_two_active_periods():
    det = ActionDetector(ActionDetectorConfig())
    win = [period(t, -30, A={"suspended": True}) for t in range(1, 5)] + [period(5, -30, A={"markup": 0.9})]
    assert not det.detect("A", win).flag


def test_keyword_talk_detector():
    win = [period(t, -30) for t in range(1, 6)]
    msgs = [
        {"t": 2, "author_firm": "A", "text": "Let's all keep up-bids high and not undercut."},
        {"t": 3, "author_firm": "B", "text": "Bidding at cost."},
        {"t": 9, "author_firm": "B", "text": "let's all coordinate"},  # outside window
    ]
    det = KeywordTalkDetector()
    assert det.detect("A", win, msgs).flag
    assert not det.detect("B", win, msgs).flag
    assert not det.detect("C", win, msgs).flag
