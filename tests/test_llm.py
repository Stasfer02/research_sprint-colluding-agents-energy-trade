"""Budget guard, retries, OpenRouter request construction and model routing (no network calls)."""

import json

import pytest
import yaml

from desks.config import LLMConfig
from desks.llm import (BudgetExceeded, BudgetGuard, FakeBackend, LLMClient, OpenRouterBackend, RetryableError,
                       RouterClient, load_openrouter_registry, make_client)

PRICES = {"m": {"input": 1.0, "output": 2.0}}
REG = {
    "x/with-temp": {"provider": "prov/fp8", "supports_temperature": True, "supports_seed": True, "supports_reasoning": True,
                    "price_input_per_m": 0.1, "price_output_per_m": 0.3},
    "x/no-temp": {"provider": "openai", "supports_temperature": False, "supports_seed": True, "supports_reasoning": False,
                  "price_input_per_m": 0.1, "price_output_per_m": 0.5},
}


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

        def call(self, system, messages, model, max_tokens, seed=None):
            self.n += 1
            if self.n < 3:
                raise RetryableError("429")
            return "ok", 10, 5, "end_turn"

    cfg = LLMConfig()
    client = LLMClient(cfg, Flaky(), BudgetGuard(tmp_path / "l.json", 1.0, cfg.prices))
    assert client.complete("s", [{"role": "user", "content": "u"}]).text == "ok" and client.total_calls == 1


def _backend(monkeypatch, **cfg):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    return OpenRouterBackend(LLMConfig(**cfg), REG)


def test_request_pins_provider_and_sends_seed_and_temperature(monkeypatch):
    kw, meta = _backend(monkeypatch, temperature=0.7).request_kwargs("sys", [{"role": "user", "content": "u"}], "x/with-temp", 600, seed=123)
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["temperature"] == 0.7 and kw["seed"] == 123 and kw["max_tokens"] == 600
    assert kw["extra_body"]["provider"] == {"order": ["prov/fp8"], "allow_fallbacks": False}
    assert kw["extra_body"]["reasoning"] == {"enabled": False} and kw["extra_body"]["usage"] == {"include": True}
    assert meta == {"provider_pinned": "prov/fp8", "seed_sent": 123, "temperature_sent": 0.7, "reasoning_requested": {"enabled": False}}


def test_request_omits_unsupported_temperature_and_reasoning(monkeypatch):
    kw, meta = _backend(monkeypatch, temperature=0.7).request_kwargs("s", [{"role": "user", "content": "u"}], "x/no-temp", 600, seed=5)
    assert "temperature" not in kw and meta["temperature_sent"] is None
    assert "reasoning" not in kw["extra_body"] and kw["seed"] == 5


def test_reasoning_levels(monkeypatch):
    kw, _ = _backend(monkeypatch, openrouter_reasoning="default").request_kwargs("s", [], "x/with-temp", 600, seed=None)
    assert "reasoning" not in kw["extra_body"] and "temperature" not in kw and "seed" not in kw
    kw, meta = _backend(monkeypatch, temperature=1.0, openrouter_reasoning="high").request_kwargs("s", [], "x/with-temp", 4000, seed=1)
    assert kw["extra_body"]["reasoning"] == meta["reasoning_requested"] == {"effort": "high", "exclude": False}
    with pytest.raises(ValueError, match="openrouter_reasoning"):
        _backend(monkeypatch, openrouter_reasoning="maximum").request_kwargs("s", [], "x/with-temp", 600, seed=None)


def test_router_dispatches_by_model_name(tmp_path):
    a, o = FakeBackend(lambda *_: "a"), FakeBackend(lambda *_: "o")
    prices = {"claude-haiku-5-5": {"input": 1, "output": 1}, "x/with-temp": {"input": 1, "output": 1}}
    cfg = LLMConfig()
    r = RouterClient({"anthropic": LLMClient(cfg, a, BudgetGuard(tmp_path / "a.json", 5, prices)),
                      "openrouter": LLMClient(cfg, o, BudgetGuard(tmp_path / "o.json", 5, prices))}, "x/with-temp")
    assert r.complete("s", [{"role": "user", "content": "u"}]).text == "o"
    assert r.complete("s", [{"role": "user", "content": "u"}], model="claude-haiku-5-5").text == "a"
    assert r.total_calls == 2 and json.loads((tmp_path / "a.json").read_text())["calls"] == 1


def test_make_client_merges_registry_into_config(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump(REG))
    cfg = LLMConfig(model="x/with-temp", openrouter_registry=str(reg), openrouter_ledger_path=str(tmp_path / "lo.json"))
    client = make_client(cfg)
    assert set(client.routes) == {"openrouter"}
    assert cfg.prices["x/with-temp"] == {"input": 0.1, "output": 0.3} and cfg.providers["x/with-temp"]["provider"] == "prov/fp8"
    with pytest.raises(ValueError, match="not in"):
        make_client(LLMConfig(model="x/unknown", openrouter_registry=str(reg)))


def test_registry_file_is_valid():
    reg = load_openrouter_registry("configs/models_openrouter.yaml")
    assert reg and all({"provider", "price_input_per_m", "price_output_per_m", "supports_seed"} <= set(v) for v in reg.values())
