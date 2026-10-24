"""OpenRouter request construction and model routing (no network calls)."""

import json

import pytest

from desks.config import LLMConfig, expand_grid, load_grid
from desks.llm import BudgetGuard, FakeBackend, LLMClient, OpenRouterBackend, RouterClient, load_openrouter_registry, make_client
from desks.runner import run_one

from fake_llm import valid_responder

REG = {
    "x/with-temp": {"provider": "prov/fp8", "supports_temperature": True, "supports_seed": True, "supports_reasoning": True,
                    "price_input_per_m": 0.1, "price_output_per_m": 0.3},
    "x/no-temp": {"provider": "openai", "supports_temperature": False, "supports_seed": True, "supports_reasoning": False,
                  "price_input_per_m": 0.1, "price_output_per_m": 0.5},
}


def _backend(monkeypatch, **cfg):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    return OpenRouterBackend(LLMConfig(**cfg), REG)


def test_request_pins_provider_and_sends_seed_and_temperature(monkeypatch):
    b = _backend(monkeypatch, temperature=0.7)
    kw, meta = b.request_kwargs("sys", [{"role": "user", "content": "u"}], "x/with-temp", 600, seed=123)
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["temperature"] == 0.7 and kw["seed"] == 123 and kw["max_tokens"] == 600
    assert kw["extra_body"]["provider"] == {"order": ["prov/fp8"], "allow_fallbacks": False}
    assert kw["extra_body"]["reasoning"] == {"enabled": False}
    assert kw["extra_body"]["usage"] == {"include": True}
    assert meta == {"provider_pinned": "prov/fp8", "seed_sent": 123, "temperature_sent": 0.7, "reasoning_requested": {"enabled": False}}


def test_request_omits_unsupported_temperature_and_reasoning(monkeypatch):
    b = _backend(monkeypatch, temperature=0.7)
    kw, meta = b.request_kwargs("s", [{"role": "user", "content": "u"}], "x/no-temp", 600, seed=5)
    assert "temperature" not in kw and meta["temperature_sent"] is None
    assert "reasoning" not in kw["extra_body"] and kw["seed"] == 5


def test_reasoning_default_leaves_model_default(monkeypatch):
    b = _backend(monkeypatch, temperature=None, openrouter_reasoning="default")
    kw, meta = b.request_kwargs("s", [{"role": "user", "content": "u"}], "x/with-temp", 600, seed=None)
    assert "reasoning" not in kw["extra_body"] and "temperature" not in kw and "seed" not in kw


def test_reasoning_on_requests_effort_and_returns_text(monkeypatch):
    b = _backend(monkeypatch, temperature=1.0, openrouter_reasoning="high")
    kw, meta = b.request_kwargs("s", [{"role": "user", "content": "u"}], "x/with-temp", 4000, seed=1)
    assert kw["extra_body"]["reasoning"] == {"effort": "high", "exclude": False}
    assert meta["reasoning_requested"] == {"effort": "high", "exclude": False}
    b_bad = _backend(monkeypatch, openrouter_reasoning="maximum")
    with pytest.raises(ValueError, match="openrouter_reasoning"):
        b_bad.request_kwargs("s", [{"role": "user", "content": "u"}], "x/with-temp", 600, seed=None)


def test_router_dispatches_by_model_name(tmp_path):
    a, o = FakeBackend(lambda *_: "a"), FakeBackend(lambda *_: "o")
    prices = {"claude-haiku-5-5": {"input": 1, "output": 1}, "x/with-temp": {"input": 1, "output": 1}}
    cfg = LLMConfig()
    r = RouterClient({"anthropic": LLMClient(cfg, a, BudgetGuard(tmp_path / "a.json", 5, prices)),
                      "openrouter": LLMClient(cfg, o, BudgetGuard(tmp_path / "o.json", 5, prices))}, "x/with-temp")
    assert r.complete("s", [{"role": "user", "content": "u"}]).text == "o"
    assert r.complete("s", [{"role": "user", "content": "u"}], model="claude-haiku-5-5").text == "a"
    assert len(a.calls) == 1 and len(o.calls) == 1 and r.total_calls == 2
    assert json.loads((tmp_path / "a.json").read_text())["calls"] == 1


def test_make_client_merges_registry_into_config(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    reg = tmp_path / "reg.yaml"
    import yaml
    reg.write_text(yaml.safe_dump(REG))
    cfg = LLMConfig(model="x/with-temp", openrouter_registry=str(reg), ledger_path=str(tmp_path / "l.json"),
                    openrouter_ledger_path=str(tmp_path / "lo.json"))
    client = make_client(cfg, firm_models={"A": "claude-haiku-5-5"})
    assert set(client.routes) == {"anthropic", "openrouter"}
    assert cfg.prices["x/with-temp"] == {"input": 0.1, "output": 0.3}
    assert cfg.providers["x/with-temp"]["provider"] == "prov/fp8"
    with pytest.raises(ValueError, match="not in"):
        make_client(LLMConfig(model="x/unknown", openrouter_registry=str(reg)))


def test_desks_send_deterministic_seeds_and_use_firm_models(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_USD", "5")
    fake = FakeBackend(valid_responder)
    base = {"agents": {"mode": "llm", "firm_models": {"A": "claude-haiku-5-5"}},
            "llm": {"ledger_path": str(tmp_path / "l.json"), "end_of_run_judge": False}}
    cfg = expand_grid({"name": "t", "out_dir": str(tmp_path / "r"), "seeds": [3], "base": base})[0]
    assert run_one(cfg, backend=fake)["status"] == "ok"
    seeds = [c["seed"] for c in fake.calls]
    assert all(isinstance(s, int) for s in seeds) and len(set(seeds)) == len(seeds)
    fake2 = FakeBackend(valid_responder)
    cfg.out_dir = str(tmp_path / "r2")
    assert run_one(cfg, backend=fake2)["status"] == "ok"
    assert sorted(seeds) == sorted(c["seed"] for c in fake2.calls)  # same run seed -> same call seeds
    io = [json.loads(line) for line in (cfg.run_dir / "agent_io.jsonl").read_text().splitlines()]
    assert io[0]["meta"]["seed_sent"] == io[0]["meta"]["seed_sent"] and "meta" in io[0]


def test_registry_file_is_valid():
    reg = load_openrouter_registry("configs/models_openrouter.yaml")
    assert reg and all({"provider", "price_input_per_m", "price_output_per_m", "supports_seed"} <= set(v) for v in reg.values())


def test_model_screen_config_loads():
    runs = load_grid("configs/experiments/exp4_model_screen.yaml")
    reg = load_openrouter_registry("configs/models_openrouter.yaml")
    assert runs and all(r.llm.model in reg for r in runs)
    assert all("/" not in r.cell_id for r in runs)
