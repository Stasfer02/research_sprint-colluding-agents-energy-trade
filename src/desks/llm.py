"""LLM clients (Anthropic, OpenAI-compatible, fake), retries and the budget guard.

Every LLM call goes through LLMClient.complete, which checks and updates the
persistent spend ledger (runs/ledger.json, file-locked) against BUDGET_USD.
Keys are read from environment variables and never logged.
"""

from __future__ import annotations

import fcntl
import json
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import LLMConfig

DEFAULT_BUDGET_USD = 20.0


class BudgetExceeded(RuntimeError):
    """Raised by the budget guard once spend reaches BUDGET_USD."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_s: float
    model: str
    stop_reason: str | None = None


class BudgetGuard:
    def __init__(self, ledger_path: str | Path, budget_usd: float, prices: dict[str, dict[str, float]]):
        self.path = Path(ledger_path)
        self.budget = float(budget_usd)
        self.prices = prices
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".lock")

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        if model not in self.prices:
            raise ValueError(f"no price for model {model!r}; add it to llm.prices")
        p = self.prices[model]
        return (input_tokens * p["input"] + output_tokens * p["output"]) / 1e6

    def _locked(self, fn):
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text()) if self.path.exists() else {"spent_usd": 0.0, "calls": 0, "by_model": {}}
                out = fn(data)
                return out
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def spent(self) -> float:
        return self._locked(lambda d: float(d["spent_usd"]))

    def check(self, estimate: float = 0.0) -> None:
        def f(d):
            if d["spent_usd"] + estimate >= self.budget:
                raise BudgetExceeded(f"spent ${d['spent_usd']:.4f} + est ${estimate:.4f} >= budget ${self.budget:.2f}")
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
    def __init__(self, cfg: LLMConfig):
        import anthropic

        self._anthropic = anthropic
        key = os.environ.get(cfg.api_key_env)
        if not key:
            raise RuntimeError(f"{cfg.api_key_env} is not set (put it in .env)")
        self.client = anthropic.Anthropic(api_key=key, timeout=cfg.timeout_s, max_retries=0)
        self.cfg = cfg

    def call(self, system: str, messages: list[dict], model: str, max_tokens: int) -> tuple[str, int, int, str | None]:
        a = self._anthropic
        kwargs = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        # API version 2026-10-21 (SDK >= 2.0) rejects temperature/top_p/top_k, so none are sent.
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
        return text, resp.usage.input_tokens, resp.usage.output_tokens, resp.stop_reason


class OpenAICompatibleBackend:
    def __init__(self, cfg: LLMConfig):
        import openai

        self._openai = openai
        key = os.environ.get(cfg.api_key_env)
        if not key:
            raise RuntimeError(f"{cfg.api_key_env} is not set (put it in .env)")
        self.client = openai.OpenAI(api_key=key, base_url=cfg.base_url, timeout=cfg.timeout_s, max_retries=0)
        self.cfg = cfg

    def call(self, system: str, messages: list[dict], model: str, max_tokens: int) -> tuple[str, int, int, str | None]:
        o = self._openai
        kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, *messages]}
        if self.cfg.temperature is not None:
            kwargs["temperature"] = self.cfg.temperature
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except (o.RateLimitError, o.APITimeoutError, o.APIConnectionError, o.InternalServerError) as exc:
            raise RetryableError(type(exc).__name__) from exc
        choice = resp.choices[0]
        usage = resp.usage
        return choice.message.content or "", usage.prompt_tokens, usage.completion_tokens, choice.finish_reason


class FakeBackend:
    """Deterministic stand-in for tests: `responder(system, messages, model) -> text`."""

    def __init__(self, responder: Callable[[str, list[dict], str], str]):
        self.responder = responder
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def call(self, system: str, messages: list[dict], model: str, max_tokens: int) -> tuple[str, int, int, str | None]:
        text = self.responder(system, messages, model)
        with self._lock:
            self.calls.append({"system": system, "messages": messages, "model": model})
        n_in = (len(system) + sum(len(m["content"]) for m in messages)) // 4
        return text, n_in, len(text) // 4, "end_turn"


class LLMClient:
    def __init__(self, cfg: LLMConfig, backend, guard: BudgetGuard):
        self.cfg = cfg
        self.backend = backend
        self.guard = guard
        self._lock = threading.Lock()
        self.total_cost = 0.0
        self.total_calls = 0

    def complete(self, system: str, messages: list[dict], model: str | None = None, max_tokens: int | None = None) -> LLMResponse:
        model = model or self.cfg.model
        max_tokens = max_tokens or self.cfg.max_tokens
        self.guard.check(estimate=self.guard.cost(model, 0, max_tokens))
        delay = 2.0
        for attempt in range(self.cfg.max_retries + 1):
            t0 = time.time()
            try:
                text, n_in, n_out, stop = self.backend.call(system, messages, model, max_tokens)
                break
            except RetryableError:
                if attempt == self.cfg.max_retries:
                    raise
                time.sleep(min(delay, 60.0) + random.uniform(0, 1))
                delay *= 2
        cost = self.guard.cost(model, n_in, n_out)
        self.guard.record(model, n_in, n_out, cost)
        with self._lock:
            self.total_cost += cost
            self.total_calls += 1
        return LLMResponse(text, n_in, n_out, cost, time.time() - t0, model, stop)


def budget_from_env() -> float:
    raw = os.environ.get("BUDGET_USD")
    return float(raw) if raw else DEFAULT_BUDGET_USD


def make_client(cfg: LLMConfig, backend=None) -> LLMClient:
    if backend is None:
        if cfg.backend == "anthropic":
            backend = AnthropicBackend(cfg)
        elif cfg.backend == "openai_compatible":
            backend = OpenAICompatibleBackend(cfg)
        else:
            raise ValueError(f"unknown backend {cfg.backend}")
    return LLMClient(cfg, backend, BudgetGuard(cfg.ledger_path, budget_from_env(), cfg.prices))
