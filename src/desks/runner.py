"""Run one configured simulation and write its outputs (resumable at run level)."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from .config import RunConfig
from .llm import BudgetExceeded, make_client
from .simulation import Simulation


def run_one(cfg: RunConfig, force: bool = False, backend=None) -> dict[str, Any]:
    """Run one simulation. `backend` (e.g. a FakeBackend) overrides the configured LLM backend."""
    run_dir = cfg.run_dir
    summary_path = run_dir / "summary.json"
    if summary_path.exists() and not force:
        return {"status": "skipped", "run_dir": str(run_dir)}
    run_dir.mkdir(parents=True, exist_ok=True)
    incomplete = run_dir / "incomplete.json"
    if incomplete.exists():
        incomplete.unlink()

    desks = judge = client = None
    try:
        if cfg.agents.mode == "llm":
            from .agents import build_judge, build_llm_desks

            client = make_client(cfg.llm, backend=backend)
            desks = build_llm_desks(cfg, client)
            judge = build_judge(cfg, client)
        sim = Simulation(cfg, desks=desks, judge=judge, run_dir=run_dir)
        summary = sim.run()
        if client is not None:
            if cfg.llm.end_of_run_judge:
                scores = judge.score_run(sim.channels.messages, sim.agent_notes)
                summary.update(scores)
                (run_dir / "judge.json").write_text(json.dumps(judge.run_details, indent=2))
            summary["cost_usd"] = client.total_cost
            summary["llm_calls_total"] = client.total_calls
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
