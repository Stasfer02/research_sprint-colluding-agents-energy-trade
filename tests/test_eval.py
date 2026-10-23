import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("eval_detectors", Path(__file__).parents[1] / "scripts" / "eval_detectors.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def test_rates_and_threshold():
    y = np.array([True, True, False, False, False])
    hard = np.array([False, False, True, False, False])
    r = ev.rates(y, np.array([True, False, True, False, False]), hard)
    assert r["precision"] == 0.5 and r["recall"] == 0.5 and r["fpr"] == 1 / 3 and r["fpr_hard_neg"] == 1.0
    assert ev.best_threshold(np.array([0.9, 0.8, 0.1, 0.2, 0.3]), y) == 0.8


def test_evaluate_excludes_enforcing_detector_and_splits_by_seed():
    rows = []
    for seed in (0, 1):
        for enf in ("none", "action"):
            for i in range(20):
                pos = i < 10
                rows.append({
                    "seed": seed, "enforcement": enf, "label": "positive" if pos else ("hard_negative" if i == 19 else "negative"),
                    "action_score": 1.5 if pos else 0.2, "action_flag": pos,
                    "oracle_score": 1.0 if pos else 0.0, "oracle_flag": pos,
                    "keyword_score": np.nan, "keyword_flag": np.nan, "judge_score": np.nan,
                })
    res = ev.evaluate(pd.DataFrame(rows))
    act = res[(res["detector"] == "action") & (res["rule"] == "default")].iloc[0]
    assert act["n"] == 20  # test split (seed 1), enforcement=action excluded
    assert act["precision"] == 1.0 and act["recall"] == 1.0 and act["fpr_hard_neg"] == 0.0
    orc = res[(res["detector"] == "oracle") & (res["rule"] == "default")].iloc[0]
    assert orc["n"] == 40  # oracle is not the enforcing detector in either cell
