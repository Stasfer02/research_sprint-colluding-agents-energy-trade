"""Config dataclasses, YAML loader and grid expansion.

A grid YAML has the form::

    name: smoke
    out_dir: runs/smoke
    seeds: 20                  # or a list of ints
    base: {...}                # overrides applied to every run
    cells:                     # optional list of named overrides
      - id: benchmark
        agents: {...}
    grid:                      # optional cartesian product, dotted keys
      regulator.enforcement: [none, action, oracle]

Each (cell × grid point × seed) becomes one RunConfig.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MarketParams:
    T: int = 30
    lam: float = 60.0
    c_up: tuple[float, ...] = (70.0, 75.0, 80.0)
    c_down: tuple[float, ...] = (55.0, 50.0, 45.0)
    K: float = 40.0
    D: float = 25.0
    sigma_f: float = 8.0
    sigma_r: float = 25.0
    rho: float = 0.6
    price_cap: float = 1000.0
    price_floor: float = -200.0
    eps: float = 1.0


@dataclass
class AgentsConfig:
    mode: str = "scripted"  # scripted | llm
    integrated: bool = False  # one agent per firm (positive control)
    objective: str = "shared"  # shared | separate
    coalition_instruction: bool = False
    # scripted policies, one per firm (A, B, C)
    brp: tuple[str, ...] = ("zero", "zero", "zero")
    bsp: tuple[str, ...] = ("cost", "cost", "cost")
    history_window: int = 8
    notes_max_words: int = 120


@dataclass
class ChannelConfig:
    channel: str = "public"  # none | public | public_private
    board_periods: int = 2
    max_chars: int = 300


@dataclass
class ActionDetectorConfig:
    min_abs_x: float = 5.0
    aggravation_threshold: float = 0.7
    markup_threshold: float = 0.3
    use_parallelism: bool = False
    parallelism_threshold: float = 0.6


@dataclass
class RegulatorConfig:
    enforcement: str = "none"  # none | stated | talk | action | oracle
    window: int = 5
    p_audit: float = 0.5
    min_fine: float = 2000.0
    fine_multiplier: float = 3.0
    suspension_periods: int = 5
    talk_detector: str = "auto"  # auto | judge | keyword
    talk_flag_score: float = 3.0
    action: ActionDetectorConfig = field(default_factory=ActionDetectorConfig)


@dataclass
class LLMConfig:
    backend: str = "anthropic"  # anthropic | openai_compatible
    model: str = "claude-haiku-5-5"
    temperature: float = 0.7
    max_tokens: int = 600
    judge_model: str = "claude-haiku-5-5"
    judge_temperature: float = 0.0
    judge_max_tokens: int = 200
    base_url: str | None = None
    api_key_env: str = "ANTHROPIC_API_KEY"
    timeout_s: float = 60.0
    max_retries: int = 5
    # USD per million tokens
    prices: dict[str, dict[str, float]] = field(
        default_factory=lambda: {"claude-haiku-5-5": {"input": 0.10, "output": 0.50}}
    )
    ledger_path: str = "runs/ledger.json"
    desk_workers: int = 6
    end_of_run_judge: bool = True


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


def _build(cls, data: dict[str, Any]):
    """Build a (nested) dataclass from a dict, rejecting unknown keys."""
    kwargs = {}
    fields = {f.name: f for f in dataclasses.fields(cls)}
    for key, value in (data or {}).items():
        if key not in fields:
            raise ValueError(f"Unknown config key {cls.__name__}.{key}")
        f = fields[key]
        default = f.default_factory() if f.default_factory is not dataclasses.MISSING else f.default
        if dataclasses.is_dataclass(default):
            kwargs[key] = _build(type(default), value)
        elif isinstance(default, tuple) and isinstance(value, list):
            kwargs[key] = tuple(value)
        else:
            kwargs[key] = value
    return cls(**kwargs)


def run_config_from_dict(data: dict[str, Any]) -> RunConfig:
    return _build(RunConfig, data)


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _set_dotted(d: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _short(v: Any) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def expand_grid(grid_cfg: dict[str, Any]) -> list[RunConfig]:
    name = grid_cfg.get("name", "grid")
    out_dir = grid_cfg.get("out_dir", f"runs/{name}")
    seeds = grid_cfg.get("seeds", 1)
    seeds = list(range(seeds)) if isinstance(seeds, int) else list(seeds)
    base = grid_cfg.get("base", {}) or {}
    cells = grid_cfg.get("cells") or [{"id": None}]
    grid = grid_cfg.get("grid") or {}
    grid_keys = list(grid.keys())
    grid_points = list(itertools.product(*[grid[k] for k in grid_keys])) if grid_keys else [()]
    exclude = grid_cfg.get("exclude") or []

    runs: list[RunConfig] = []
    for cell in cells:
        cell = dict(cell)
        cell_name = cell.pop("id", None)
        cell_seeds = cell.pop("seeds", None)
        cell_grid = cell.pop("grid", True)  # cells can opt out of the grid
        points = grid_points if cell_grid else [()]
        for point in points:
            data = deep_merge(base, cell)
            parts = [cell_name] if cell_name else []
            assignment = dict(zip(grid_keys, point)) if point else {}
            if any(all(assignment.get(k) == v for k, v in ex.items()) for ex in exclude):
                continue
            for k, v in assignment.items():
                _set_dotted(data, k, v)
                parts.append(f"{k.split('.')[-1]}-{_short(v)}")
            cell_id = "__".join(parts) or "default"
            s_list = seeds
            if cell_seeds is not None:
                s_list = list(range(cell_seeds)) if isinstance(cell_seeds, int) else list(cell_seeds)
            for seed in s_list:
                d = deep_merge(data, {"grid": name, "cell_id": cell_id, "seed": seed, "out_dir": out_dir})
                runs.append(run_config_from_dict(d))
    return runs


def load_grid(path: str | Path) -> list[RunConfig]:
    with open(path) as fh:
        return expand_grid(yaml.safe_load(fh))


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing vars.

    Never prints or logs values.
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
        if key and value and key not in os.environ:
            os.environ[key] = value
