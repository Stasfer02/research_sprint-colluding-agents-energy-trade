"""Features added for exp1–exp3: scripted firms inside LLM runs, pressure ladder, provenance, lean metrics."""

import json

import pytest

from desks.agents import COALITION_TEXT, EXPLICIT_TEXT, LLMDesk, pressure_texts
from desks.config import expand_grid, load_grid, run_config_from_dict
from desks.llm import BudgetGuard, FakeBackend, LLMClient
from desks.runner import run_one

from fake_llm import role_of, valid_responder


def _runs(tmp_path, **base):
    base = {"agents": {"mode": "llm"}, "llm": {"ledger_path": str(tmp_path / "ledger.json")}, **base}
    return expand_grid({"name": "t", "out_dir": str(tmp_path / "runs"), "seeds": 1, "base": base})


def test_scripted_firm_inside_llm_run(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    fake = FakeBackend(valid_responder)
    cfg = _runs(tmp_path, channel={"channel": "public_private"},
                agents={"mode": "llm", "scripted_firms": {"C": {"brp": "zero", "bsp": "cartel", "posts": "silent"}}})[0]
    assert run_one(cfg, backend=fake)["status"] == "ok"
    d = cfg.run_dir
    periods = [json.loads(line) for line in (d / "periods.jsonl").read_text().splitlines()]
    assert all(p["firms"]["C"]["u"] == 300 and p["firms"]["C"]["v"] == 0 for p in periods)
    msgs = [json.loads(line) for line in (d / "messages.jsonl").read_text().splitlines()]
    c_posts = {m["text"] for m in msgs if m["author_firm"] == "C" and m["desk"] == "bsp"}
    assert c_posts == {"Bidding balancing energy in line with our costs and current market conditions."}
    assert not any(m["author_firm"] == "C" and m["channel"] == "private" for m in msgs)  # silent: no proposals
    s = json.loads((d / "summary.json").read_text())
    assert s["llm_calls"] == 30 * 4 and s["parse_failure_rate"] == 0
    assert s["scripted_firms"] == {"C": {"brp": "zero", "bsp": "cartel", "posts": "silent"}}
    desk_calls = [c for c in fake.calls if role_of(c["system"]) != "judge"]
    assert not any("Firm C" in c["system"].splitlines()[0] for c in desk_calls)


def test_loud_scripted_colluder_posts_privately(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    cfg = _runs(tmp_path, channel={"channel": "public_private"},
                agents={"mode": "llm", "scripted_firms": {"C": {"brp": "aggravate", "bsp": "cartel", "posts": "loud"}}},
                llm={"ledger_path": str(tmp_path / "l.json"), "end_of_run_judge": False})[0]
    assert run_one(cfg, backend=FakeBackend(valid_responder))["status"] == "ok"
    msgs = [json.loads(line) for line in (cfg.run_dir / "messages.jsonl").read_text().splitlines()]
    priv = [m for m in msgs if m["author_firm"] == "C" and m["channel"] == "private"]
    assert len(priv) == 60 and "not undercut" in priv[0]["text"] + priv[1]["text"]


@pytest.mark.parametrize("level,has_holding,n_extra", [
    ("none", False, 0), ("permission", False, 1), ("holding", True, 1), ("target", True, 2), ("explicit", True, 3),
])
def test_pressure_ladder_is_cumulative(level, has_holding, n_extra):
    cfg = run_config_from_dict({"agents": {"pressure": level, "integrated": True}})
    objective, extra = pressure_texts(cfg)
    assert (objective is not None) == has_holding
    assert sum(t in extra for t in (COALITION_TEXT, "combined profit of at least €40,000", EXPLICIT_TEXT[:40])) == n_extra


def test_holding_profit_shown_in_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    fake = FakeBackend(valid_responder)
    cfg = _runs(tmp_path, agents={"mode": "llm", "integrated": True, "pressure": "target"},
                llm={"ledger_path": str(tmp_path / "l.json"), "end_of_run_judge": False})[0]
    assert run_one(cfg, backend=fake)["status"] == "ok"
    user = fake.calls[-1]["messages"][0]["content"]
    assert "Holding company total profit (Firms A, B and C combined)" in user
    assert "holding company's total profit" in fake.calls[-1]["system"]
    legacy = run_config_from_dict({"agents": {"coalition_instruction": True}})
    assert pressure_texts(legacy)[1] == COALITION_TEXT


def test_provenance_and_lean_metrics(tmp_path):
    cfg = expand_grid({"name": "t", "out_dir": str(tmp_path), "seeds": 1,
                       "base": {"agents": {"brp": ["passive", "aggravate", "zero"]}}})[0]
    assert run_one(cfg)["status"] == "ok"
    prov = json.loads((cfg.run_dir / "provenance.json").read_text())
    assert prov["git_commit"] and len(prov["prompt_sha256"]) == 16
    s = json.loads((cfg.run_dir / "summary.json").read_text())
    assert s["lean_against_volume"] > 0 and s["lean_with_volume"] > 0
    assert s["git_commit"] == prov["git_commit"]


@pytest.mark.parametrize("path", ["configs/experiments/exp1_detection.yaml", "configs/experiments/exp2_pressure.yaml",
                                  "configs/experiments/exp3_enforcement.yaml"])
def test_experiment_configs_load(path):
    runs = load_grid(path)
    assert runs and all(r.agents.mode == "llm" for r in runs)
    assert len({(r.cell_id, r.seed) for r in runs}) == len(runs)
