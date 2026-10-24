"""LLM clients (Anthropic, OpenRouter / OpenAI-compatible, fake), retries and budget guards.

Every LLM call goes through LLMClient.complete, which checks and updates a persistent,
file-locked spend ledger against a cap. Calls are routed by model name: "claude-*" models go
to the Anthropic API (ledger runs/ledger.json, cap BUDGET_USD); everything else goes to
OpenRouter with a pinned provider (ledger runs/ledger_openrouter.json, cap OPENROUTER_BUDGET_USD).
Keys are read from environment variables and never logged.
"""

from __future__ import annotations

import fcntl
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .config import LLMConfig

DEFAULT_BUDGET_USD = 20.0
DEFAULT_OPENROUTER_BUDGET_USD = 10.0
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class BudgetExceeded(RuntimeError):
    """Raised by the budget guard once spend reaches the cap."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_s: float
    model: str
    stop_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # provider, seed/temperature sent, reasoning tokens, ...


class BudgetGuard:
    def __init__(self, ledger_path: str | Path, budget_usd: float, prices: dict[str, dict[str, float]]):
        self.path = Path(ledger_path)
        self.budget = float(budget_usd)
        self.prices = prices
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".lock")

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        if model not in self.prices:
            raise ValueError(f"no price for model {model!r}; add it to llm.prices or the OpenRouter registry")
        p = self.prices[model]
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1e6

    def _locked(self, fn):
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text()) if self.path.exists() else {"spent_usd": 0.0, "calls": 0, "by_model": {}}
                return fn(data)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def spent(self) -> float:
        return self._locked(lambda d: float(d["spent_usd"]))

    def check(self, estimate: float = 0.0) -> None:
        def f(d):
            if d["spent_usd"] + estimate >= self.budget:
                raise BudgetExceeded(f"{self.path.name}: spent ${d['spent_usd']:.4f} + est ${estimate:.4f} >= budget ${self.budget:.2f}")
        self._locked(f)

    def record(self, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        def f(d):
            d["spent_usd"] = float(d["spent_usd"]) + cost
            d["calls"] = int(d.get("calls", 0)) + 1
            m = d.setdefault("by_model", {}).setdefault(model, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0})
            m["input_tokens"] += input_tokens
            m["output_tokens"] += output_tokens
            m["cost_usd"] += cost
            m["calls"] += 1
            d["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, indent=2))
            tmp.replace(self.path)
        self._locked(f)


class RetryableError(Exception):
    pass


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, cfg: LLMConfig):
        import anthropic

        self._anthropic = anthropic
        key = os.environ.get(cfg.api_key_env)
        if not key:
            raise RuntimeError(f"{cfg.api_key_env} is not set (put it in .env)")
        # Keys not scoped to a workspace must name one per request.
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        headers = {"anthropic-workspace-id": workspace} if workspace else None
        self.client = anthropic.Anthropic(api_key=key, timeout=cfg.timeout_s, max_retries=0, default_headers=headers)
        self.cfg = cfg

    def call(self, system: str, messages: list[dict], model: str, max_tokens: int, seed: int | None = None):
        a = self._anthropic
        kwargs = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        # API version 2026-10-21 (SDK >= 2.0) rejects temperature/top_p/top_k and has no seed, so none are sent.
        if self.cfg.thinking == "disabled":
            kwargs["thinking"] = {"type": "disabled"}
        if self.cfg.effort:
            kwargs["output_config"] = {"effort": self.cfg.effort}
        try:
            resp = self.client.messages.create(**kwargs)
        except (a.RateLimitError, a.APITimeoutError, a.APIConnectionError, a.InternalServerError) as exc:
            raise RetryableError(type(exc).__name__) from exc
        except a.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code == 429:
                raise RetryableError(f"status {exc.status_code}") from exc
            raise
        text = "".join(b.text for b in resp.content if b.type == "text")
        meta = {"provider": "anthropic", "seed_sent": None, "temperature_sent": None, "thinking": self.cfg.thinking}
        return text, resp.usage.input_tokens, resp.usage.output_tokens, resp.stop_reason, meta


class OpenRouterBackend:
    """OpenAI-compatible chat completions via OpenRouter, pinned to one provider per model (no fallbacks)."""

    name = "openrouter"

    def __init__(self, cfg: LLMConfig, registry: dict[str, dict], key_env: str = "OPENROUTER_API_KEY",
                 base_url: str = OPENROUTER_BASE_URL):
        import openai

        self._openai = openai
        key = os.environ.get(key_env)
        if not key:
            raise RuntimeError(f"{key_env} is not set (put it in .env)")
        self.client = openai.OpenAI(api_key=key, base_url=base_url, timeout=cfg.timeout_s, max_retries=0,
                                    default_headers={"X-Title": "colluding-desks research sprint"})
        self.cfg = cfg
        self.registry = registry

    def request_kwargs(self, system: str, messages: list[dict], model: str, max_tokens: int, seed: int | None) -> tuple[dict, dict]:
        info = self.registry[model]
        kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens,
                                  "messages": [{"role": "system", "content": system}, *messages]}
        extra: dict[str, Any] = {"provider": {"order": [info["provider"]], "allow_fallbacks": False},
                                 "usage": {"include": True}}
        temperature = self.cfg.temperature if info.get("supports_temperature") else None
        if temperature is not None:
            kwargs["temperature"] = temperature
        seed_sent = seed if (seed is not None and info.get("supports_seed")) else None
        if seed_sent is not None:
            kwargs["seed"] = seed_sent
        if info.get("supports_reasoning"):
            mode = self.cfg.openrouter_reasoning
            if mode == "off":
                extra["reasoning"] = {"enabled": False}
            elif mode in ("low", "medium", "high"):
                # reasoning on at a fixed effort; the text is returned (not excluded) so it can be logged
                extra["reasoning"] = {"effort": mode, "exclude": False}
            elif mode != "default":
                raise ValueError(f"unknown openrouter_reasoning {mode!r} (off | low | medium | high | default)")
        kwargs["extra_body"] = extra
        meta = {"provider_pinned": info["provider"], "seed_sent": seed_sent, "temperature_sent": temperature,
                "reasoning_requested": extra.get("reasoning")}
        return kwargs, meta

    def call(self, system: str, messages: list[dict], model: str, max_tokens: int, seed: int | None = None):
        o = self._openai
        kwargs, meta = self.request_kwargs(system, messages, model, max_tokens, seed)
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except (o.RateLimitError, o.APITimeoutError, o.APIConnectionError, o.InternalServerError) as exc:
            raise RetryableError(type(exc).__name__) from exc
        except o.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 429):
                raise RetryableError(f"status {exc.status_code}") from exc
            raise
        if not resp.choices:  # OpenRouter can return 200 with an error body
            raise RetryableError(f"no choices: {str(getattr(resp, 'model_extra', ''))[:200]}")
        choice = resp.choices[0]
        usage = resp.usage
        extra = getattr(resp, "model_extra", None) or {}
        uextra = getattr(usage, "model_extra", None) or {}
        details = getattr(usage, "completion_tokens_details", None)
        msg = choice.message
        reasoning_text = getattr(msg, "reasoning", None) or (getattr(msg, "model_extra", None) or {}).get("reasoning")
        meta.update({
            "provider": extra.get("provider"),
            "generation_id": resp.id,
            "served_model": resp.model,
            "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
            "reasoning_text": reasoning_text,  # the model's visible reasoning when the provider returns it
            "cost_reported": uextra.get("cost"),
        })
        return choice.message.content or "", usage.prompt_tokens, usage.completion_tokens, choice.finish_reason, meta


class FakeBackend:
    """Deterministic stand-in for tests: `responder(system, messages, model) -> text`."""

    name = "fake"

    def __init__(self, responder: Callable[[str, list[dict], str], str]):
        self.responder = responder
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def call(self, system: str, messages: list[dict], model: str, max_tokens: int, seed: int | None = None):
        text = self.responder(system, messages, model)
        with self._lock:
            self.calls.append({"system": system, "messages": messages, "model": model, "seed": seed})
        n_in = (len(system) + sum(len(m["content"]) for m in messages)) // 4
        return text, n_in, len(text) // 4, "end_turn", {"provider": "fake", "seed_sent": seed}


class LLMClient:
    """One backend + one ledger."""

    def __init__(self, cfg: LLMConfig, backend, guard: BudgetGuard):
        self.cfg = cfg
        self.backend = backend
        self.guard = guard
        self._lock = threading.Lock()
        self.total_cost = 0.0
        self.total_calls = 0

    def complete(self, system: str, messages: list[dict], model: str | None = None, max_tokens: int | None = None,
                 seed: int | None = None) -> LLMResponse:
        model = model or self.cfg.model
        max_tokens = max_tokens or self.cfg.max_tokens
        self.guard.check(estimate=self.guard.cost(model, 0, max_tokens))
        delay = 2.0
        for attempt in range(self.cfg.max_retries + 1):
            t0 = time.time()
            try:
                out = self.backend.call(system, messages, model, max_tokens, seed=seed)
                break
            except RetryableError:
                if attempt == self.cfg.max_retries:
                    raise
                time.sleep(min(delay, 60.0) + random.uniform(0, 1))
                delay *= 2
        text, n_in, n_out, stop = out[:4]
        meta = dict(out[4]) if len(out) > 4 else {}
        # prefer the provider-reported cost (OpenRouter) over the price table
        cost = float(meta["cost_reported"]) if meta.get("cost_reported") is not None else self.guard.cost(model, n_in, n_out)
        self.guard.record(model, n_in, n_out, cost)
        with self._lock:
            self.total_cost += cost
            self.total_calls += 1
        return LLMResponse(text, n_in, n_out, cost, time.time() - t0, model, stop, meta)


class RouterClient:
    """Routes each call to the Anthropic or OpenRouter client by model name; same interface as LLMClient."""

    def __init__(self, routes: dict[str, LLMClient], default_model: str):
        self.routes = routes
        self.default_model = default_model

    @staticmethod
    def route_of(model: str) -> str:
        return "anthropic" if model.startswith("claude-") else "openrouter"

    def complete(self, system: str, messages: list[dict], model: str | None = None, max_tokens: int | None = None,
                 seed: int | None = None) -> LLMResponse:
        model = model or self.default_model
        return self.routes[self.route_of(model)].complete(system, messages, model=model, max_tokens=max_tokens, seed=seed)

    @property
    def total_cost(self) -> float:
        return sum(c.total_cost for c in self.routes.values())

    @property
    def total_calls(self) -> int:
        return sum(c.total_calls for c in self.routes.values())

    @property
    def guard(self) -> BudgetGuard:
        return self.routes[self.route_of(self.default_model)].guard


def budget_from_env(var: str = "BUDGET_USD", default: float = DEFAULT_BUDGET_USD) -> float:
    raw = os.environ.get(var)
    return float(raw) if raw else default


def load_openrouter_registry(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def models_in_use(cfg_llm: LLMConfig, firm_models: dict | None = None) -> set[str]:
    return {cfg_llm.model, cfg_llm.judge_model, *((firm_models or {}).values())}


def make_client(cfg: LLMConfig, backend=None, firm_models: dict | None = None):
    """Build the client for a run. With `backend` (tests), every model goes to that backend and the main ledger.

    For OpenRouter models, the pinned provider and prices from the registry are merged into `cfg`
    (cfg.providers / cfg.prices), so the run's config.json records exactly what was used.
    """
    if backend is not None:
        return LLMClient(cfg, backend, BudgetGuard(cfg.ledger_path, budget_from_env(), cfg.prices))
    used = models_in_use(cfg, firm_models)
    routes: dict[str, LLMClient] = {}
    if any(RouterClient.route_of(m) == "anthropic" for m in used):
        routes["anthropic"] = LLMClient(cfg, AnthropicBackend(cfg), BudgetGuard(cfg.ledger_path, budget_from_env(), cfg.prices))
    or_models = sorted(m for m in used if RouterClient.route_of(m) == "openrouter")
    if or_models:
        registry = load_openrouter_registry(cfg.openrouter_registry)
        missing = [m for m in or_models if m not in registry]
        if missing:
            raise ValueError(f"models not in {cfg.openrouter_registry}: {missing} (run scripts/openrouter_models.py)")
        for m in or_models:
            info = registry[m]
            cfg.prices[m] = {"input": info["price_input_per_m"], "output": info["price_output_per_m"]}
            cfg.providers[m] = dict(info)
        guard = BudgetGuard(cfg.openrouter_ledger_path, budget_from_env("OPENROUTER_BUDGET_USD", DEFAULT_OPENROUTER_BUDGET_USD), cfg.prices)
        routes["openrouter"] = LLMClient(cfg, OpenRouterBackend(cfg, registry), guard)
    return RouterClient(routes, cfg.model)
