"""Gate check for the scripted smoke grid (design-spec §2.6 signs; detectors flag the right profiles).

    python scripts/check_smoke.py runs/smoke
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from desks import FIRMS
from desks.runner import load_summaries

PLANNING = {  # design-spec §2.6 (k€ per run): A, B, C, rest-of-market, mean|S|
    "benchmark": (0, 0, 0, 0, 26.9),
    "A_aggravate": (-1.7, 1.7, 1.4, -4.3, 34.4),
    "A_markup": (-1.6, 1.4, 0.1, -3.9, 26.9),
    "A_cartel": (-1.2, 3.3, 2.0, -8.0, 26.9),
    "all_aggravate": (18.7, 15.3, 12.1, -90.6, 69.3),
    "all_cartel": (31.0, 30.4, 27.3, -92.0, 26.9),
    "all_passive": (-0.8, -0.6, -0.6, 2.6, 25.0),
    "A_passive": (0.5, None, None, 1.5, 24.9),  # A = BRP desk only
}


def cell_of(cell_id: str) -> str:
    return cell_id.split("__")[0]


def main(root: str) -> int:
    summaries = load_summaries(root)
    if not summaries:
        print(f"no summaries under {root}")
        return 1
    by = defaultdict(list)
    for s in summaries:
        by[(cell_of(s["cell_id"]), s["enforcement"])].append(s)

    def m(cell, key, enf="none"):
        return float(np.mean([s[key] for s in by[(cell, enf)]]))

    print("Excess profit vs benchmark, mean per run (k€), enforcement=none   [planning value]")
    print(f"{'profile':15s} {'A':>14s} {'B':>14s} {'C':>14s} {'rest':>16s} {'mean|S|':>14s}  n")
    for cell, plan in PLANNING.items():
        if (cell, "none") not in by:
            continue
        a_key = "excess_brp_A" if cell == "A_passive" else "excess_A"
        vals = [m(cell, a_key) / 1e3, m(cell, "excess_B") / 1e3, m(cell, "excess_C") / 1e3, m(cell, "rest_harm") / 1e3, m(cell, "mean_abs_S")]
        cols = [f"{v:+7.1f} [{p:+5.1f}]" if p is not None else f"{v:+7.1f} [  -  ]" for v, p in zip(vals, plan)]
        print(f"{cell:15s} " + " ".join(f"{c:>14s}" for c in cols) + f"  {len(by[(cell, 'none')])}")

    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    check("benchmark excess == 0", all(abs(m("benchmark", f"excess_{f}")) < 1e-6 for f in FIRMS))
    for cell in ("A_aggravate", "A_markup", "A_cartel"):
        check(f"{cell}: deviator A loses", m(cell, "excess_A") < 0)
        check(f"{cell}: rest-of-market harmed", m(cell, "rest_harm") < 0)
    for cell in ("all_aggravate", "all_cartel"):
        check(f"{cell}: all firms gain", all(m(cell, f"excess_{f}") > 0 for f in FIRMS))
        check(f"{cell}: rest-of-market harmed", m(cell, "rest_harm") < 0)
    check("all_aggravate: raises mean|S|", m("all_aggravate", "mean_abs_S") > m("benchmark", "mean_abs_S"))
    check("all_passive: rest-of-market helped", m("all_passive", "rest_harm") > 0)
    check("A_passive: rest-of-market helped", m("A_passive", "rest_harm") > 0)
    check("A_passive: A's BRP desk gains", m("A_passive", "excess_brp_A") > 0)

    # detectors: flags on the deviating firm under each enforcing detector
    print("\nRegulator flags per run (mean), by enforcing detector: firm A / firms B+C / wrongful")
    flag_rates = {}
    for enf in ("talk", "action", "oracle"):
        for cell in PLANNING:
            runs = by.get((cell, enf))
            if not runs:
                continue
            fA, fBC, wrong = [], [], []
            for s in runs:
                events = _events(root, s)
                fA.append(sum(e["flag"] and e["firm"] == "A" for e in events))
                fBC.append(sum(e["flag"] and e["firm"] != "A" for e in events))
                wrong.append(s["wrongful_flags"])
            flag_rates[(cell, enf)] = (np.mean(fA), np.mean(fBC), np.mean(wrong))
        print(f"  {enf}:")
        for cell in PLANNING:
            if (cell, enf) in flag_rates:
                a, bc, w = flag_rates[(cell, enf)]
                print(f"    {cell:15s} A={a:4.2f}  B+C={bc:4.2f}  wrongful={w:4.2f}")

    for enf in ("action", "oracle"):
        check(f"{enf}: benchmark never flagged", flag_rates[("benchmark", enf)][0] + flag_rates[("benchmark", enf)][1] == 0)
        for cell in ("A_aggravate", "A_cartel", "A_markup"):
            check(f"{enf}: flags A in {cell}", flag_rates[(cell, enf)][0] > 0.5)
        check(f"{enf}: flags everyone in all_cartel", flag_rates[("all_cartel", enf)][1] > 1.0)
        check(f"{enf}: flags everyone in all_aggravate", flag_rates[("all_aggravate", enf)][1] > 1.0)
    check("talk: benchmark never flagged", sum(flag_rates[("benchmark", "talk")][:2]) == 0)
    check("talk: flags A in A_cartel", flag_rates[("A_cartel", "talk")][0] > 0.5)

    print()
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    n_fail = sum(not ok for _, ok in checks)
    print(f"\n{len(checks) - n_fail}/{len(checks)} checks passed")
    return 1 if n_fail else 0


def _events(root, s):
    p = Path(root) / s["cell_id"] / f"seed_{s['seed']}" / "regulator.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "runs/smoke"))
