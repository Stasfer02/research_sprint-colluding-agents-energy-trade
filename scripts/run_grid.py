"""Run every (cell × seed) of a grid config. Resumable: skips runs that have summary.json.

    python scripts/run_grid.py configs/smoke.yaml [--workers 4] [--only CELL_SUBSTR] [--dry-run] [--force]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed

from desks.config import load_dotenv, load_grid
from desks.runner import provenance, run_one


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--only", default=None, help="only run cells whose id contains this substring")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-run even if summary.json exists")
    ap.add_argument("--allow-dirty", action="store_true", help="allow LLM runs from uncommitted code")
    args = ap.parse_args()

    load_dotenv()
    runs = load_grid(args.config)
    if any(r.agents.mode == "llm" for r in runs) and not args.dry_run and not args.allow_dirty:
        prov = provenance()
        if prov["git_dirty"]:
            print("Refusing to run LLM experiments from a dirty working tree (commit first, or --allow-dirty).")
            return 2
    if args.only:
        runs = [r for r in runs if args.only in r.cell_id]
    cells = sorted({r.cell_id for r in runs})
    print(f"{len(runs)} runs in {len(cells)} cells -> {runs[0].out_dir if runs else '-'}", flush=True)
    if args.dry_run:
        for c in cells:
            print("  ", c)
        return 0

    t0 = time.time()
    status: Counter = Counter()
    if args.workers <= 1:
        for i, cfg in enumerate(runs, 1):
            res = run_one(cfg, force=args.force)
            status[res["status"]] += 1
            _report(i, len(runs), cfg, res, t0)
            if res["status"] == "budget":
                print("Budget exhausted; stopping.", flush=True)
                break
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_one, cfg, args.force): cfg for cfg in runs}
            for i, fut in enumerate(as_completed(futs), 1):
                cfg = futs[fut]
                res = fut.result()
                status[res["status"]] += 1
                _report(i, len(runs), cfg, res, t0)
                if res["status"] == "budget":
                    print("Budget exhausted; cancelling remaining runs.", flush=True)
                    for f in futs:
                        f.cancel()
    print(f"done in {time.time() - t0:.0f}s: {dict(status)}", flush=True)
    return 1 if status.get("error") else 0


def _report(i, n, cfg, res, t0):
    every = max(1, n // 20)
    if res["status"] in ("error", "budget") or i % every == 0 or i == n:
        extra = f" {res.get('error', '')}" if res["status"] == "error" else ""
        print(f"[{i}/{n}] {res['status']:7s} {cfg.cell_id}/seed_{cfg.seed} ({time.time() - t0:.0f}s){extra}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
