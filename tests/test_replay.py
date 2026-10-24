"""The current code reproduces the committed EXP7-9 results.

For every exported period: regenerate the noise from the run seed, re-clear and re-settle the logged actions
(deviations and bids), recompute the competitive benchmark, and compare with what the run recorded. No API calls.
"""

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from desks.config import run_config_from_dict
from desks.market import benchmark, clear, make_units, settle
from desks.simulation import make_streams

ROOTS = ["results/exp7_deepseek_desks", "results/exp8_deepseek_desks_reasoning", "results/exp9_deepseek_desks_rules"]
RUNS = sorted(p.parent for root in ROOTS for p in Path(root).glob("runs/*/seed_*/config.json"))


@pytest.mark.parametrize("run", RUNS, ids=[str(r) for r in RUNS])
def test_committed_run_replays_exactly(run):
    cfg = run_config_from_dict(json.loads((run / "config.json").read_text()))
    m = cfg.market
    units = make_units(m, 3)
    e, r, tie, _, _ = make_streams(cfg.seed, m.T, 3, m.sigma_f, m.sigma_r, m.rho, n_units=len(units.mw))
    with gzip.open(run / "periods.jsonl.gz", "rt") as fh:
        recs = [json.loads(line) for line in fh]
    assert len(recs) == m.T
    for k, rec in enumerate(recs):
        firms = [rec["firms"][f] for f in "ABC"]
        assert np.allclose([f["e"] for f in firms], e[k]) and np.isclose(rec["r"], r[k])
        d = np.array([f["d"] for f in firms])
        u, v = np.array([f["u"] for f in firms]), np.array([f["v"] for f in firms])
        x = e[k] + d
        S = float(x.sum() + r[k])
        cl = clear(S, u, v, units.mw, np.ones(3, bool), tie[k], m)
        st = settle(x, r[k], cl, units.c_up, units.c_down, m.lam)
        _, cl_c, st_c = benchmark(e[k], r[k], tie[k], m)
        assert np.isclose(rec["S"], S) and np.isclose(rec["P"], cl.price) and rec["direction"] == cl.direction
        assert np.isclose(rec["P_comp"], cl_c.price) and np.isclose(rec["rest"], st.rest)
        assert np.allclose([f["brp"] for f in firms], st.brp) and np.allclose([f["bsp"] for f in firms], st.bsp)
        assert np.allclose([f["comp"] for f in firms], st_c.brp + st_c.bsp)
