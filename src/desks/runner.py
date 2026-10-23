"""Run one configured simulation and write its outputs (resumable at run level)."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from .config import RunConfig
from .llm import BudgetExceeded, make_client
from .simulation import Simulation


PROMPTS_DIR = Path(__file__).parent / "prompts"


def provenance() -> dict[str, Any]:
    """Code and environment identity for a run: git commit, dirty flag, prompt hash, package versions."""
    import datetime
    import hashlib
    import importlib.metadata as md
    import platform
    import subprocess

    def git(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10, cwd=Path(__file__).parent).stdout.strip()
        except Exception:  # noqa: BLE001
            return None

    h = hashlib.sha256()
    for p in sorted(PROMPTS_DIR.glob("*.j2")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    h.update(Path(__file__).with_name("agents.py").read_bytes())  # prompt constants live there
    versions = {}
    for pkg in ("anthropic", "openai", "numpy", "pandas", "jinja2"):
        try:
            versions[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            versions[pkg] = None
    status = git("status", "--porcelain", "--untracked-files=no")
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "prompt_sha256": h.hexdigest()[:16],
        "python": platform.python_version(),
        "packages": versions,
        "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def run_one(cfg: RunConfig, force: bool = False, backend=None) -> dict[str, Any]:
    """Run one simulation. `backend` (e.g. a FakeBackend) overrides the configured LLM backend."""
    run_dir = cfg.run_dir
    summary_path = run_dir / "summary.json"
    if summary_path.exists() and not force:
        return {"status": "skipped", "run_dir": str(run_dir)}
    run_dir.mkdir(parents=True, exist_ok=True)
    prov = provenance()
    (run_dir / "provenance.json").write_text(json.dumps(prov, indent=2))
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
    summary["git_commit"] = prov["git_commit"]
    summary["git_dirty"] = prov["git_dirty"]
    summary["prompt_sha256"] = prov["prompt_sha256"]
    summary_path.write_text(json.dumps(summary, indent=2, default=float))
    return {"status": "ok", "run_dir": str(run_dir)}


def load_summaries(root: str | Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(Path(root).rglob("summary.json"))]
