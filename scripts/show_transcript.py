"""Print a readable transcript of one run: market results, each desk's action, posts, plan and notes.

    python scripts/show_transcript.py results/exp8_deepseek_desks_reasoning/runs/baseline/seed_1 [--periods 16-19 | 18]
        [--desk C:bsp] [--reasoning] [--system]

Firm lines show ground truth the desks never saw: forecast error e, deviation d, imbalance x, bids u/v, activated q,
and trading and balancing profit. Gzipped exports are read directly.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path


def _lines(d: Path, name: str) -> list[str]:
    """Read <name> or <name>.gz (results/ exports gzip periods.jsonl and agent_io.jsonl)."""
    if (d / name).exists():
        return (d / name).read_text().splitlines()
    if (d / f"{name}.gz").exists():
        with gzip.open(d / f"{name}.gz", "rt") as fh:
            return fh.read().splitlines()
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--periods", default=None, help="e.g. 1-5 or 18")
    ap.add_argument("--desk", default=None, help="e.g. A:brp (trading desk) or A:bsp (balancing desk)")
    ap.add_argument("--system", action="store_true", help="also print each desk's system prompt")
    ap.add_argument("--reasoning", action="store_true", help="also print each desk's private reasoning text (EXP2, EXP3: folders exp8, exp9)")
    args = ap.parse_args()
    d = Path(args.run_dir)
    periods = {p["t"]: p for p in map(json.loads, _lines(d, "periods.jsonl"))}
    io, msgs = defaultdict(list), defaultdict(list)
    for row in map(json.loads, _lines(d, "agent_io.jsonl")):
        io[row["t"]].append(row)
    for m in map(json.loads, _lines(d, "messages.jsonl")):
        msgs[m["t"]].append(m)
    lo, hi = 1, max(periods)
    if args.periods:
        lo, _, hi = args.periods.partition("-")
        lo, hi = int(lo), int(hi or lo)
    for t in range(lo, hi + 1):
        p = periods[t]
        print(f"\n=== t={t}  S={p['S']:+.1f} ({p['direction']})  P={p['P']:.1f}  r={p['r']:+.1f}  price set by {p['marginal']}")
        for f, fr in p["firms"].items():
            print(f"    {f}: e={fr['e']:+.1f} d={fr['d']:+.1f} x={fr['x']:+.1f} u={fr['u']:.0f} v={fr['v']:.0f} q={fr['q']:.0f} "
                  f"brp={fr['brp']:+.0f} bsp={fr['bsp']:+.0f}")
        for row in io[t]:
            key = f"{row['firm']}:{row['desk']}"
            if args.desk and key != args.desk:
                continue
            if args.system and row.get("system"):
                print(f"  [{key}] SYSTEM:\n{row['system']}")
            parsed = row.get("parsed") or {}
            ok = "" if row["parse_ok"] else f"  PARSE FAIL (attempt {row['attempt']}): {row['raw_output'][:200]!r}"
            print(f"  [{key}] {row['action']}{ok}")
            if args.reasoning and (row.get("meta") or {}).get("reasoning_text"):
                print(f"      reasoning:\n{row['meta']['reasoning_text']}\n")
            for k in ("reflection", "plan", "notes"):
                if parsed.get(k):
                    print(f"      {k}: {parsed[k]}")
        for m in msgs[t]:
            print(f"  <{m['channel']}> {m['author']}: {m['text']}")
    if (d / "summary.json").exists():
        s = json.loads((d / "summary.json").read_text())
        keys = ["llm_calls", "parse_failures", "tokens_in", "tokens_out", "cost_usd"]
        print("\nSUMMARY " + "  ".join(f"{k}={s[k]:.3g}" for k in keys if k in s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
