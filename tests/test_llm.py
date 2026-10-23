import json

import pytest

from desks.config import expand_grid
from desks.llm import BudgetExceeded, BudgetGuard, FakeBackend, LLMClient, RetryableError
from desks.runner import run_one

from fake_llm import role_of, valid_responder

PRICES = {"m": {"input": 1.0, "output": 2.0}}


def test_budget_guard_accumulates_and_blocks(tmp_path):
    g = BudgetGuard(tmp_path / "ledger.json", 0.01, PRICES)
    assert g.cost("m", 1000, 1000) == pytest.approx(0.003)
    g.record("m", 1000, 1000, 0.003)
    g.record("m", 1000, 1000, 0.003)
    assert g.spent() == pytest.approx(0.006)
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert data["calls"] == 2 and data["by_model"]["m"]["input_tokens"] == 2000
    g.check(0.001)
    with pytest.raises(BudgetExceeded):
        g.check(0.005)
    with pytest.raises(ValueError):
        g.cost("unknown-model", 1, 1)


def test_client_retries_retryable_errors(tmp_path, monkeypatch):
    monkeypatch.setattr("desks.llm.time.sleep", lambda s: None)

    class Flaky:
        n = 0

        def call(self, system, messages, model, max_tokens):
            self.n += 1
            if self.n < 3:
                raise RetryableError("429")
            return "ok", 10, 5, "end_turn"

    cfg = expand_grid({"seeds": 1})[0].llm
    cfg.prices = {cfg.model: {"input": 1.0, "output": 1.0}}
    client = LLMClient(cfg, Flaky(), BudgetGuard(tmp_path / "l.json", 1.0, cfg.prices))
    r = client.complete("s", [{"role": "user", "content": "u"}])
    assert r.text == "ok" and client.total_calls == 1


def _llm_runs(tmp_path, **base):
    base = {"agents": {"mode": "llm"}, "llm": {"ledger_path": str(tmp_path / "ledger.json")}, **base}
    return expand_grid({"name": "t", "out_dir": str(tmp_path / "runs"), "seeds": 1, "base": base})


def test_full_llm_run_with_fake_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    fake = FakeBackend(valid_responder)
    cfg = _llm_runs(tmp_path, channel={"channel": "public_private"}, regulator={"enforcement": "talk", "p_audit": 1.0})[0]
    res = run_one(cfg, backend=fake)
    assert res["status"] == "ok"
    d = cfg.run_dir
    summary = json.loads((d / "summary.json").read_text())
    assert summary["periods"] == 30 and summary["parse_failures"] == 0
    assert summary["llm_calls"] == 30 * 6
    assert summary["cost_usd"] > 0 and "judge_public_A" in summary and "plan_talk_A" in summary
    assert summary["audits"] > 0  # judge-based talk enforcement ran
    io = [json.loads(line) for line in (d / "agent_io.jsonl").read_text().splitlines()]
    assert len(io) == 180 and io[0]["system"]
    # information hiding in the prompts actually sent (value-level checks are in test_simulation)
    header = "| t | S (MW) | direction | P (€/MWh) | activated MW | up-bids: price (activated MW) | down-bids: price (activated MW) |"
    for call in fake.calls:
        role = role_of(call["system"])
        if role == "judge":
            continue
        user = call["messages"][0]["content"]
        market = user.split("## Market results")[1].split("## Your desk")[0]
        assert "Firm" not in market and "forecast" not in user.lower()
        if "No periods have been settled" not in market:
            assert header in market
        own = user.split("## Your desk")[1].split("\n## ")[0]
        if role == "brp":
            assert "up-bid" not in own
        if role == "bsp":
            assert "deviation" not in own
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["spent_usd"] == pytest.approx(summary["cost_usd"])


def test_integrated_run(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    cfg = _llm_runs(tmp_path, agents={"mode": "llm", "integrated": True, "coalition_instruction": True})[0]
    assert run_one(cfg, backend=FakeBackend(valid_responder))["status"] == "ok"
    s = json.loads((cfg.run_dir / "summary.json").read_text())
    assert s["llm_calls"] == 30 * 3


def test_budget_exhaustion_marks_run_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "0.0005")
    cfg = _llm_runs(tmp_path)[0]
    res = run_one(cfg, backend=FakeBackend(valid_responder))
    assert res["status"] == "budget"
    assert (cfg.run_dir / "incomplete.json").exists()
    assert not (cfg.run_dir / "summary.json").exists()
