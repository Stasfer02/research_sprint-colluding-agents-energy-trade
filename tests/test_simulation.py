"""Full runs with a fake LLM: outputs, determinism, what desks may see, board timing, budget, resumability, configs."""

import json
import re

import pytest

from desks.agents import build_llm_desks
from desks.config import expand_grid, load_grid, run_config_from_dict
from desks.llm import FakeBackend, make_client
from desks.runner import run_one
from desks.simulation import Simulation

from fake_llm import role_of, valid_responder

EXPERIMENTS = {"7": "exp7_deepseek_desks", "8": "exp8_deepseek_desks_reasoning", "9": "exp9_deepseek_desks_rules"}


def _run_cfg(tmp_path, **base):
    base = {"llm": {"ledger_path": str(tmp_path / "ledger.json")}, **base}
    return expand_grid({"name": "t", "out_dir": str(tmp_path / "runs"), "seeds": [3], "base": base})[0]


def _sim(tmp_path, **cfg):
    cfg = run_config_from_dict({"seed": 7, "llm": {"ledger_path": str(tmp_path / "l.json")}, **cfg})
    sim = Simulation(cfg, desks=build_llm_desks(cfg, make_client(cfg.llm, backend=FakeBackend(valid_responder))))
    sim.run()
    return sim


def test_full_run_writes_outputs_and_records_spend(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    fake = FakeBackend(valid_responder)
    cfg = _run_cfg(tmp_path)
    assert run_one(cfg, backend=fake)["status"] == "ok"
    d = cfg.run_dir
    for name in ("config.json", "provenance.json", "periods.jsonl", "messages.jsonl", "agent_io.jsonl", "summary.json"):
        assert (d / name).exists()
    summary = json.loads((d / "summary.json").read_text())
    assert summary["periods"] == 30 and summary["parse_failures"] == 0 and summary["llm_calls"] == 30 * 6
    io = [json.loads(line) for line in (d / "agent_io.jsonl").read_text().splitlines()]
    assert len(io) == 180 and io[0]["system"]
    seeds = [c["seed"] for c in fake.calls]
    assert len(set(seeds)) == len(seeds)  # one deterministic seed per call
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["spent_usd"] == pytest.approx(summary["cost_usd"])
    assert run_one(cfg, backend=fake)["status"] == "skipped"  # resumable


def test_same_seed_same_run(tmp_path):
    a, b = _sim(tmp_path), _sim(tmp_path)
    assert json.dumps(a.records) == json.dumps(b.records)


def test_desks_never_see_ground_truth(tmp_path):
    def distinct(system, messages, model):  # firm-specific deviations, so a leak of B's or C's would be visible
        if role_of(system) == "bsp":
            return valid_responder(system, messages, model)
        firm = re.search(r"of Firm ([ABC])", system).group(1)
        return json.dumps({"deviation_mw": {"A": 3.25, "B": -7.75, "C": 11.5}[firm], "public_post": "p"})
    cfg = run_config_from_dict({"seed": 7, "llm": {"ledger_path": str(tmp_path / "l.json")}})
    sim = Simulation(cfg, desks=build_llm_desks(cfg, make_client(cfg.llm, backend=FakeBackend(distinct))))
    sim.run()
    hidden = {"e", "r", "d", "x", "marginal", "rest"}
    for role in ("brp", "bsp"):
        obs = sim._observation("A", role, 31)
        for row in obs.public_history:
            assert not hidden & set(row)
            for bid in row["merit_up"] + row["merit_down"]:
                assert set(bid) == {"price", "mw", "activated_mw"}  # no firm IDs in the merit order
        text = json.dumps(obs.__dict__)
        for rec in sim.records[-8:]:
            assert repr(rec["r"]) not in text and repr(rec["firms"]["A"]["e"]) not in text
            for f in "BC":
                assert abs(rec["firms"][f]["d"]) < 1e-6 or repr(rec["firms"][f]["d"]) not in text
    assert all("up_bid" not in row for row in sim._observation("A", "brp", 31).own_history)
    assert all("deviation_mw" not in row for row in sim._observation("A", "bsp", 31).own_history)


def test_posts_shown_from_next_period_for_two_periods(tmp_path):
    sim = _sim(tmp_path)
    assert {m["t"] for m in sim._board(10)} == {8, 9} and not sim._board(1)


def test_rules_only_mentioned_in_exp9_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    pat = re.compile(r"\b(fines?|regulat\w*|REMIT|complian\w*)\b", re.IGNORECASE)
    fake = FakeBackend(valid_responder)
    assert run_one(_run_cfg(tmp_path), backend=fake)["status"] == "ok"
    for call in fake.calls:
        text = (call["system"] + call["messages"][0]["content"]).replace(
            "All market participants and the regulator can read the Public Board.", "")  # the channel rule
        assert pat.search(text) is None
    fake = FakeBackend(valid_responder)
    cfg = _run_cfg(tmp_path, regulator={"enforcement": "stated"})
    cfg.out_dir = str(tmp_path / "runs_stated")
    assert run_one(cfg, backend=fake)["status"] == "ok"
    user = fake.calls[-1]["messages"][0]["content"]
    assert "after fines" in user and "fines: €0" in user and "firm fine" in user


def test_budget_exhaustion_marks_run_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "0.0005")
    cfg = _run_cfg(tmp_path)
    assert run_one(cfg, backend=FakeBackend(valid_responder))["status"] == "budget"
    assert (cfg.run_dir / "incomplete.json").exists() and not (cfg.run_dir / "summary.json").exists()


def test_configs_differ_only_as_designed():
    """EXP7 -> EXP8 changes only the reasoning settings; EXP8 -> EXP9 only the stated rules (plus retries)."""
    exp = {n: load_grid(f"configs/experiments/{name}.yaml") for n, name in EXPERIMENTS.items()}
    assert all([r.seed for r in runs] == [0, 1, 2, 3, 4] for runs in exp.values())

    def diff(a, b):
        da, db = a.to_dict(), b.to_dict()
        return {f"{s}.{k}" for s in ("market", "agents", "channel", "regulator", "llm") for k in da[s] if da[s][k] != db[s][k]}

    assert diff(exp["7"][0], exp["8"][0]) == {"llm.openrouter_reasoning", "llm.max_tokens", "llm.timeout_s"}
    assert diff(exp["8"][0], exp["9"][0]) == {"regulator.enforcement", "llm.max_retries"}


@pytest.mark.parametrize("n", EXPERIMENTS)
def test_configs_reproduce_the_committed_runs(n):
    """Each experiment YAML still yields the settings its committed runs recorded (except run-time fields)."""
    for cfg in load_grid(f"configs/experiments/{EXPERIMENTS[n]}.yaml"):
        run = f"results/{EXPERIMENTS[n]}/runs/baseline/seed_{cfg.seed}/config.json"
        logged = run_config_from_dict(json.load(open(run)), legacy=True).to_dict()
        new = cfg.to_dict()
        for d in (logged, new):
            d["llm"].pop("providers"), d["llm"].pop("prices")  # filled in from the registry at run time
        if n == "9":
            logged["llm"]["max_retries"] = new["llm"]["max_retries"]  # seeds 1, 3 started before the retry raise
        assert new == logged
