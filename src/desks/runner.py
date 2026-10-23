"""Run one configured simulation and write its outputs (resumable at run level)."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from .config import RunConfig
from .simulation import Simulation


class BudgetExceeded(RuntimeError):
    """Raised by the budget guard once spend reaches BUDGET_USD."""


def run_one(cfg: RunConfig, force: bool = False) -> dict[str, Any]:
    run_dir = cfg.run_dir
    summary_path = run_dir / "summary.json"
    if summary_path.exists() and not force:
        return {"status": "skipped", "run_dir": str(run_dir)}
    run_dir.mkdir(parents=True, exist_ok=True)
    incomplete = run_dir / "incomplete.json"
    if incomplete.exists():
        incomplete.unlink()

    desks = judge = None
    try:
        if cfg.agents.mode == "llm":
            from .agents import build_llm_desks, build_judge
            from .llm import make_client

            client = make_client(cfg.llm)
            desks = build_llm_desks(cfg, client)
            judge = build_judge(cfg, client)
        sim = Simulation(cfg, desks=desks, judge=judge, run_dir=run_dir)
        summary = sim.run()
        if cfg.agents.mode == "llm" and cfg.llm.end_of_run_judge and judge is not None:
            summary.update(judge.score_run(sim.channels.messages, sim.agent_notes))
            summary["cost_usd"] += judge.cost_since_start()
    except BudgetExceeded as exc:
        incomplete.write_text(json.dumps({"reason": "budget", "detail": str(exc)}))
        return {"status": "budget", "run_dir": str(run_dir)}
    except Exception as exc:  # keep the grid going; record the failure
        incomplete.write_text(json.dumps({"reason": "error", "detail": repr(exc), "traceback": traceback.format_exc()}))
        return {"status": "error", "run_dir": str(run_dir), "error": repr(exc)}
    summary_path.write_text(json.dumps(summary, indent=2, default=float))
    return {"status": "ok", "run_dir": str(run_dir)}


def load_summaries(root: str | Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(Path(root).rglob("summary.json"))]
