"""Copy an experiment's outputs from runs/ (git-ignored) into results/ (committed).

    python scripts/export_results.py runs/exp1_detection results/exp1_detection [--no-raw]

Per run it keeps config.json, provenance.json, summary.json, messages.jsonl, regulator.jsonl and judge
files as is, and gzips periods.jsonl and agent_io.jsonl (full prompts + raw model outputs; LLM sampling
is not seeded, so these are the only way to reproduce an LLM analysis exactly). `--no-raw` keeps only the
aggregate _summary/ and _eval/ folders (enough for deterministic scripted grids).
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from pathlib import Path

PLAIN = ("config.json", "provenance.json", "summary.json", "messages.jsonl", "regulator.jsonl", "judge.json",
         "judge_windows.jsonl", "judge_windows_private.jsonl", "incomplete.json")
GZIP = ("periods.jsonl", "agent_io.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_root")
    ap.add_argument("results_dir")
    ap.add_argument("--no-raw", action="store_true")
    args = ap.parse_args()
    src, dst = Path(args.runs_root), Path(args.results_dir)
    dst.mkdir(parents=True, exist_ok=True)
    for agg in ("_summary", "_eval"):
        if (src / agg).is_dir():
            shutil.copytree(src / agg, dst / agg, dirs_exist_ok=True)
    n = 0
    if not args.no_raw:
        for summary in sorted(src.rglob("summary.json")):
            run = summary.parent
            out = dst / "runs" / run.relative_to(src)
            out.mkdir(parents=True, exist_ok=True)
            for name in PLAIN:
                if (run / name).exists():
                    shutil.copy2(run / name, out / name)
            for name in GZIP:
                if (run / name).exists():
                    with open(run / name, "rb") as fi, gzip.open(out / f"{name}.gz", "wb") as fo:
                        shutil.copyfileobj(fi, fo)
            n += 1
    size = sum(p.stat().st_size for p in dst.rglob("*") if p.is_file())
    print(f"exported {n} runs + aggregates to {dst} ({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
