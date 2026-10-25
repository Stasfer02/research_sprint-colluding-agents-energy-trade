"""Config dataclasses, YAML loader and grid expansion.

An experiment YAML has the form::

    name: exp8_deepseek_desks_reasoning
    out_dir: runs/exp8_deepseek_desks_reasoning
    seeds: [0, 1, 2, 3, 4]
    base: {...}                # overrides applied to every run
    cells:                     # named variants (EXP7-9 have one, "baseline")
      - id: baseline

Each (cell x seed) becomes one RunConfig.
"""

from __future__ import annotations

import copy
import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MarketParams:
    T: int = 30  # periods
    lam: float = 60.0  # day-ahead reference price (EUR/MWh)
    c_up: tuple[float, ...] = (70.0, 75.0, 80.0)  # firms A, B, C: upward marginal cost
    c_down: tuple[float, ...] = (55.0, 50.0, 45.0)  # downward marginal cost (fuel saved)
    K: float = 40.0  # each firm's balancing block, MW per direction
    D: float = 25.0  # maximum deliberate deviation of a trading desk, MW
    sigma_f: float = 8.0  # forecast-error s.d., MW
    sigma_r: float = 25.0  # rest-of-market shock s.d., MW
    rho: float = 0.6  # rest-of-market persistence
    price_cap: float = 1000.0
    price_floor: float = -200.0
    eps: float = 1.0  # |S| <= eps: balanced, nothing activated


@dataclass
class AgentsConfig:
    history_window: int = 8  # periods of market results shown to each desk
    notes_max_words: int = 120


@dataclass
class ChannelConfig:
    board_periods: int = 2  # public posts shown from the last n periods
    max_chars: int = 300


@dataclass
class RegulatorConfig:
    # none: no mention of rules (EXP7, EXP8). stated: the compliance text is in the prompt and the desks' tables show
    # a fine column (EXP9). No regulator acts in either case: there are no audits, notices or fines.
    enforcement: str = "none"


@dataclass
class LLMConfig:
    model: str = "claude-haiku-5-5"
    max_tokens: int = 600
    temperature: float | None = None  # sent to OpenRouter models only (the Anthropic API takes no temperature)
    thinking: str = "disabled"  # Anthropic: disabled | adaptive
    effort: str | None = None  # Anthropic: None = model default
    api_key_env: str = "ANTHROPIC_API_KEY"
    timeout_s: float = 60.0
    max_retries: int = 5
    # USD per million tokens; OpenRouter prices are added from the registry at run time
    prices: dict[str, dict[str, float]] = field(
        default_factory=lambda: {"claude-haiku-5-5": {"input": 0.10, "output": 0.50}}
    )
    ledger_path: str = "runs/ledger.json"
    desk_workers: int = 6  # the six desks of a period are queried in parallel
    # OpenRouter (any model not starting with "claude-"): pinned provider and prices come from this registry
    openrouter_registry: str = "configs/models_openrouter.yaml"
    openrouter_ledger_path: str = "runs/ledger_openrouter.json"
    openrouter_reasoning: str = "off"  # off | low | medium | high | default
    seed_calls: bool = True  # send a deterministic per-call seed where the provider supports it
    providers: dict = field(default_factory=dict)  # filled in at run time and written to config.json


@dataclass
class RunConfig:
    grid: str = "default"
    cell_id: str = "default"
    seed: int = 0
    out_dir: str = "runs/default"
    market: MarketParams = field(default_factory=MarketParams)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    regulator: RegulatorConfig = field(default_factory=RegulatorConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    @property
    def run_dir(self) -> Path:
        return Path(self.out_dir) / self.cell_id / f"seed_{self.seed}"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# Keys in the committed EXP7-9 config.json files that belong to options removed in the cleanup (other experiments).
# A legacy config may contain them only with the value EXP7-9 used; ANY means the value never mattered for EXP7-9.
ANY = object()
LEGACY = {
    "market.blocks": None,
    "agents.mode": "llm", "agents.integrated": False, "agents.objective": "shared",
    "agents.coalition_instruction": False, "agents.pressure": "none", "agents.firm_models": {},
    "agents.scripted_firms": {}, "agents.holding_target": ANY, "agents.brp": ANY, "agents.bsp": ANY,
    "channel.channel": "public",
    "regulator.window": ANY, "regulator.p_audit": ANY, "regulator.min_fine": ANY, "regulator.fine_multiplier": ANY,
    "regulator.suspension_periods": ANY, "regulator.talk_detector": ANY, "regulator.talk_flag_score": ANY,
    "regulator.action": ANY,
    "llm.backend": ANY, "llm.base_url": ANY, "llm.judge_model": ANY, "llm.judge_max_tokens": ANY,
    "llm.end_of_run_judge": ANY,
}


def _build(cls, data: dict[str, Any], legacy: bool, path: str = ""):
    """Build a (nested) dataclass from a dict, rejecting unknown keys (except checked legacy keys)."""
    kwargs = {}
    fields = {f.name: f for f in dataclasses.fields(cls)}
    for key, value in (data or {}).items():
        dotted = f"{path}{key}"
        if key not in fields:
            if legacy and dotted in LEGACY and (LEGACY[dotted] is ANY or LEGACY[dotted] == value):
                continue
            raise ValueError(f"Unsupported config key or value: {dotted} = {value!r}")
        f = fields[key]
        default = f.default_factory() if f.default_factory is not dataclasses.MISSING else f.default
        if dataclasses.is_dataclass(default):
            kwargs[key] = _build(type(default), value, legacy, f"{dotted}.")
        elif isinstance(default, tuple) and isinstance(value, list):
            kwargs[key] = tuple(value)
        else:
            kwargs[key] = value
    return cls(**kwargs)


def run_config_from_dict(data: dict[str, Any], legacy: bool = False) -> RunConfig:
    """`legacy=True` reads a committed run's config.json, which also records options removed in the cleanup."""
    cfg = _build(RunConfig, data, legacy)
    if cfg.regulator.enforcement not in ("none", "stated"):
        raise ValueError(f"regulator.enforcement must be none or stated, not {cfg.regulator.enforcement!r}")
    return cfg


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def expand_grid(grid_cfg: dict[str, Any]) -> list[RunConfig]:
    name = grid_cfg.get("name", "grid")
    out_dir = grid_cfg.get("out_dir", f"runs/{name}")
    seeds = grid_cfg.get("seeds", 1)
    seeds = list(range(seeds)) if isinstance(seeds, int) else list(seeds)
    base = grid_cfg.get("base", {}) or {}
    runs: list[RunConfig] = []
    for cell in grid_cfg.get("cells") or [{"id": "default"}]:
        cell = dict(cell)
        cell_id = cell.pop("id", None) or "default"
        data = deep_merge(base, cell)
        for seed in seeds:
            runs.append(run_config_from_dict(deep_merge(data, {"grid": name, "cell_id": cell_id, "seed": seed,
                                                               "out_dir": out_dir})))
    return runs


def load_grid(path: str | Path) -> list[RunConfig]:
    with open(path) as fh:
        return expand_grid(yaml.safe_load(fh))


def load_dotenv(path: str | Path = ".env", override: bool = True) -> None:
    """Load KEY=VALUE lines into os.environ. The project's .env wins over the shell by default
    (a stale key exported in a shell profile once shadowed a new one). Never prints or logs values.
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and (override or key not in os.environ):
            os.environ[key] = value
