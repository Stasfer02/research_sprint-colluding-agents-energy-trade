"""Run one configured simulation and write its outputs (resumable: a run with a summary.json is skipped)."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from .agents import build_llm_desks
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
    for pkg in ("anthropic", "openai", "numpy", "jinja2"):
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
    """Run one simulation. `backend` (e.g. a FakeBackend in tests) overrides the real LLM backends."""
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
    try:
        client = make_client(cfg.llm, backend=backend)
        sim = Simulation(cfg, desks=build_llm_desks(cfg, client), run_dir=run_dir)
        summary = sim.run()
        summary["cost_usd"] = client.total_cost
        summary["llm_calls_total"] = client.total_calls
    except BudgetExceeded as exc:
        incomplete.write_text(json.dumps({"reason": "budget", "detail": str(exc)}))
        return {"status": "budget", "run_dir": str(run_dir)}
    except Exception as exc:  # keep the grid going; record the failure
        incomplete.write_text(json.dumps({"reason": "error", "detail": repr(exc), "traceback": traceback.format_exc()}))
        return {"status": "error", "run_dir": str(run_dir), "error": repr(exc)}
    summary.update({k: prov[k] for k in ("git_commit", "git_dirty", "prompt_sha256")})
    summary_path.write_text(json.dumps(summary, indent=2, default=float))
    return {"status": "ok", "run_dir": str(run_dir)}
