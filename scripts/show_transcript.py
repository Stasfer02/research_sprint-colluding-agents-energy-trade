"""Print a readable transcript of one run: market results, each desk's action, posts, plan and notes.

    python scripts/show_transcript.py runs/llm_single/default/seed_0 [--periods 1-5] [--desk A:brp]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--periods", default=None, help="e.g. 1-5")
    ap.add_argument("--desk", default=None, help="e.g. A:brp")
    ap.add_argument("--system", action="store_true", help="also print each desk's system prompt")
    args = ap.parse_args()
    d = Path(args.run_dir)
    periods = {p["t"]: p for p in map(json.loads, (d / "periods.jsonl").read_text().splitlines())}
    io = defaultdict(list)
    for row in map(json.loads, (d / "agent_io.jsonl").read_text().splitlines()):
        io[row["t"]].append(row)
    msgs = defaultdict(list)
    for m in map(json.loads, (d / "messages.jsonl").read_text().splitlines()):
        msgs[m["t"]].append(m)
    reg = defaultdict(list)
    if (d / "regulator.jsonl").exists():
        for e in map(json.loads, (d / "regulator.jsonl").read_text().splitlines()):
            reg[e["t"]].append(e)
    lo, hi = 1, max(periods)
    if args.periods:
        lo, hi = (int(x) for x in args.periods.split("-"))
    for t in range(lo, hi + 1):
        p = periods[t]
        print(f"\n=== t={t}  S={p['S']:+.1f} ({p['direction']})  P={p['P']:.1f}  P_comp={p['P_comp']:.1f}  r={p['r']:+.1f}")
        for f, fr in p["firms"].items():
            print(f"    {f}: e={fr['e']:+.1f} d={fr['d']:+.1f} x={fr['x']:+.1f} u={fr['u']:.0f} v={fr['v']:.0f} q={fr['q']:.0f} "
                  f"brp={fr['brp']:+.0f} bsp={fr['bsp']:+.0f} comp={fr['comp']:+.0f} fine={fr['fine']:.0f}"
                  f"{' MANIP' if fr['manip'] else ''}{' MARKUP' if fr['markup_flag'] else ''}{' PASSIVE' if fr['passive'] else ''}"
                  f"{' SUSP' if fr['suspended'] else ''}")
        for row in io[t]:
            key = f"{row['firm']}:{row['desk']}"
            if args.desk and key != args.desk:
                continue
            if row.get("skipped"):
                print(f"  [{key}] skipped ({row['skipped']})")
                continue
            if args.system and row.get("system"):
                print(f"  [{key}] SYSTEM:\n{row['system']}")
            parsed = row.get("parsed") or {}
            ok = "" if row["parse_ok"] else f"  PARSE FAIL (attempt {row['attempt']}): {row['raw_output'][:200]!r}"
            print(f"  [{key}] {row['action']}{ok}")
            for k in ("reflection", "plan", "notes"):
                if parsed.get(k):
                    print(f"      {k}: {parsed[k]}")
        for m in msgs[t]:
            print(f"  <{m['channel']}> {m['author']}: {m['text']}")
        for e in reg[t]:
            if e["flag"]:
                print(f"  REGULATOR: {e['notice']}")
    if (d / "summary.json").exists():
        s = json.loads((d / "summary.json").read_text())
        keys = ["excess_A", "excess_B", "excess_C", "rest_harm", "price_markup_mean", "mean_abs_S", "mean_abs_S_comp",
                "manip_rate", "markup_rate", "bid_markup_mean", "passive_volume", "flags", "parse_failures", "cost_usd"]
        print("\nSUMMARY " + "  ".join(f"{k}={s[k]:.3g}" for k in keys if k in s))
        print("judge: " + "  ".join(f"{k}={v}" for k, v in s.items() if k.startswith(("judge_", "plan_talk"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
