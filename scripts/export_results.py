"""Copy an experiment's outputs from runs/ (git-ignored) into results/ (committed).

    python scripts/export_results.py runs/exp9_deepseek_desks_rules results/exp9_deepseek_desks_rules

Per run it copies config.json, provenance.json, summary.json and messages.jsonl, and gzips periods.jsonl and
agent_io.jsonl (full prompts, raw model outputs and reasoning text: LLM sampling cannot be reproduced exactly, so
these logs are the record that every analysis reads).
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from pathlib import Path

PLAIN = ("config.json", "provenance.json", "summary.json", "messages.jsonl", "incomplete.json")
GZIP = ("periods.jsonl", "agent_io.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_root")
    ap.add_argument("results_dir")
    args = ap.parse_args()
    src, dst = Path(args.runs_root), Path(args.results_dir)
    n = 0
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
    print(f"exported {n} runs to {dst} ({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
