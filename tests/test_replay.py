"""The current code reproduces the committed EXP7-9 results. No API calls.

1. Market: for every exported period, regenerate the noise from the run seed, re-clear and re-settle the logged
   actions, and compare with what the run recorded.
2. End to end: re-run each committed run through the simulation and the LLM desks, with a stand-in LLM that returns
   each desk's logged reply. Every prompt the desks render (system and user, all 2,700 decisions) must equal the
   logged prompt, and every period record, public post and run summary must match the log. Fields the code no
   longer records are allowed; changed values are not.
"""

import gzip
import json
import zlib
from pathlib import Path

import numpy as np
import pytest

from desks.agents import build_llm_desks
from desks.config import run_config_from_dict
from desks.llm import LLMResponse
from desks.market import clear, settle
from desks.simulation import Simulation, make_streams

ROOTS = ["results/exp7_deepseek_desks", "results/exp8_deepseek_desks_reasoning", "results/exp9_deepseek_desks_rules"]
RUNS = sorted(p.parent for root in ROOTS for p in Path(root).glob("runs/*/seed_*/config.json"))


def jsonl(run: Path, name: str) -> list[dict]:
    path = run / name if (run / name).exists() else run / f"{name}.gz"
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as fh:
        return [json.loads(line) for line in fh]


@pytest.mark.parametrize("run", RUNS, ids=[str(r) for r in RUNS])
def test_committed_run_replays_exactly(run):
    cfg = run_config_from_dict(json.loads((run / "config.json").read_text()), legacy=True)
    m = cfg.market
    e, r, tie = make_streams(cfg.seed, m.T, 3, m.sigma_f, m.sigma_r, m.rho)
    recs = jsonl(run, "periods.jsonl")
    assert len(recs) == m.T
    for k, rec in enumerate(recs):
        firms = [rec["firms"][f] for f in "ABC"]
        assert np.allclose([f["e"] for f in firms], e[k]) and np.isclose(rec["r"], r[k])
        d = np.array([f["d"] for f in firms])
        u, v = np.array([f["u"] for f in firms]), np.array([f["v"] for f in firms])
        x = e[k] + d
        S = float(x.sum() + r[k])
        cl = clear(S, u, v, tie[k], m)
        st = settle(x, r[k], cl, m)
        assert np.isclose(rec["S"], S) and np.isclose(rec["P"], cl.price) and rec["direction"] == cl.direction
        assert np.isclose(rec["rest"], st.rest)
        assert np.allclose([f["brp"] for f in firms], st.brp) and np.allclose([f["bsp"] for f in firms], st.bsp)


class LoggedLLM:
    """Stands in for the LLM: returns the logged reply to each call and records any prompt that differs from the log.

    Calls are identified by their deterministic per-call seed (run seed, firm, desk, period, attempt), not by the
    prompt text, which is what is being checked."""

    def __init__(self, run: Path, seed: int, T: int):
        rows = jsonl(run, "agent_io.jsonl")
        by_seed = {zlib.crc32(f"{seed}|{f}|{d}|{t}|{a}".encode()) & 0x7FFFFFFF: (f, d, t, a)
                   for f in "ABC" for d in ("brp", "bsp") for t in range(1, T + 1) for a in (0, 1)}
        self.calls = {by_seed[r["meta"]["seed_sent"]]: r for r in rows}
        self.system = {(r["firm"], r["desk"]): r["system"] for r in rows if r.get("system")}
        self.mismatches: list[str] = []

    def complete(self, system, messages, model=None, max_tokens=None, seed=None):
        f, d, t, a = key = next(k for k, r in self.calls.items() if r["meta"]["seed_sent"] == seed)
        row = self.calls[key]
        if system != self.system[(f, d)]:
            self.mismatches.append(f"system prompt of {f}:{d}")
        if messages[-1]["content"] != row["prompt"]:
            self.mismatches.append(f"user prompt of {f}:{d} at t={t}, attempt {a}")
        return LLMResponse(row["raw_output"], row["input_tokens"], row["output_tokens"], row["cost"], 0.0,
                           row["model"], row["stop_reason"], {})


def assert_subset(new, old, path="record"):
    """Every value the code produces equals the logged value (floats to 1e-9); extra logged keys are ignored."""
    if isinstance(new, dict):
        for k, v in new.items():
            assert k in old, f"{path}.{k} not in the log"
            assert_subset(v, old[k], f"{path}.{k}")
    elif isinstance(new, (list, tuple)):
        assert len(new) == len(old), f"{path}: length differs"
        for i, (a, b) in enumerate(zip(new, old)):
            assert_subset(a, b, f"{path}[{i}]")
    elif isinstance(new, float) and isinstance(old, (int, float)):
        assert np.isclose(new, old, rtol=0, atol=1e-9), f"{path}: {new} != {old}"
    else:
        assert new == old, f"{path}: {new!r} != {old!r}"


@pytest.mark.parametrize("run", RUNS, ids=[str(r) for r in RUNS])
def test_committed_run_reruns_end_to_end(run):
    cfg = run_config_from_dict(json.loads((run / "config.json").read_text()), legacy=True)
    llm = LoggedLLM(run, cfg.seed, cfg.market.T)
    sim = Simulation(cfg, desks=build_llm_desks(cfg, llm), run_dir=None)
    summary = sim.run()
    assert not llm.mismatches, llm.mismatches[:5]
    recs = jsonl(run, "periods.jsonl")
    assert len(sim.records) == len(recs)
    for new, old in zip(sim.records, recs):
        assert_subset(json.loads(json.dumps(new, default=float)), old, f"t={old['t']}")
    msgs = jsonl(run, "messages.jsonl")
    assert len(sim.messages) == len(msgs)
    for new, old in zip(sim.messages, msgs):
        assert_subset(new, old, f"message t={old['t']}")
    logged = json.loads((run / "summary.json").read_text())
    # not compared: wall time; the grid name; cost_usd, which in the committed runs also counted the end-of-run judge
    summary = {k: v for k, v in summary.items() if k not in ("wall_time_s", "grid", "cost_usd")}
    assert_subset(json.loads(json.dumps(summary, default=float)), logged, "summary")
