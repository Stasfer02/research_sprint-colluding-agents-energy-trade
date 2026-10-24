"""Gate check for the market-v2 scripted grid (design-spec §13): intra-firm self-dealing pays for the dominant
firm only when both of its desks take part, and the detectors flag it.

    python scripts/check_smoke_v2.py runs/smoke_v2
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from desks import FIRMS
from desks.runner import load_summaries

CELLS = ("benchmark", "A_aggravate", "A_withhold", "A_self_deal", "A_passive", "B_aggravate", "B_self_deal", "all_aggravate")


def main(root: str) -> int:
    summaries = load_summaries(root)
    if not summaries:
        print(f"no summaries under {root}")
        return 1
    by = defaultdict(list)
    for s in summaries:
        by[(s["cell_id"].split("__")[0], s["enforcement"])].append(s)

    def m(cell, key, enf="none"):
        return float(np.mean([s[key] for s in by[(cell, enf)]]))

    def se(cell, key, enf="none"):
        v = [s[key] for s in by[(cell, enf)]]
        return float(np.std(v, ddof=1) / np.sqrt(len(v)))

    print("Excess vs benchmark, mean per run (k€), enforcement=none; A split into trading (BRP) / balancing (BSP) desk")
    print(f"{'profile':14s} {'A':>12s} {'A BRP':>7s} {'A BSP':>7s} {'B':>7s} {'C':>7s} {'rest':>8s} {'mean|S|':>8s} {'self-deal':>9s}  n")
    for cell in CELLS:
        if (cell, "none") not in by:
            continue
        print(f"{cell:14s} {m(cell, 'excess_A') / 1e3:+6.1f}±{se(cell, 'excess_A') / 1e3:3.1f} "
              f"{m(cell, 'excess_brp_A') / 1e3:+7.1f} {m(cell, 'excess_bsp_A') / 1e3:+7.1f} "
              f"{m(cell, 'excess_B') / 1e3:+7.1f} {m(cell, 'excess_C') / 1e3:+7.1f} {m(cell, 'rest_harm') / 1e3:+8.1f} "
              f"{m(cell, 'mean_abs_S'):8.1f} {m(cell, 'self_deal_rate_A'):9.3f}  {len(by[(cell, 'none')])}")

    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    check("benchmark excess == 0", all(abs(m("benchmark", f"excess_{f}")) < 1e-6 for f in FIRMS))
    check("A_self_deal: A gains", m("A_self_deal", "excess_A") > 0)
    check("A_self_deal: A's trading desk loses, its balancing desk gains (intra-firm transfer)",
          m("A_self_deal", "excess_brp_A") < 0 < m("A_self_deal", "excess_bsp_A"))
    check("A_self_deal: rest-of-market harmed", m("A_self_deal", "rest_harm") < 0)
    complement = m("A_self_deal", "excess_A") - m("A_aggravate", "excess_A") - m("A_withhold", "excess_A")
    check(f"A_self_deal pays more than its two halves added up (premium {complement / 1e3:+.1f}k)", complement > 0)
    check("A_aggravate: A's trading desk loses (a desk-objective trader would not do it)", m("A_aggravate", "excess_brp_A") < 0)
    check("B_aggravate: small firm B loses", m("B_aggravate", "excess_B") < 0)
    check("B_self_deal: small firm B loses", m("B_self_deal", "excess_B") < 0)
    check("A_passive: A's trading desk gains", m("A_passive", "excess_brp_A") > 0)
    check("A_passive: rest-of-market helped", m("A_passive", "rest_harm") > 0)
    check("self_deal label: 0 in benchmark / A_aggravate / A_withhold",
          max(m(c, "self_deal_rate_A") for c in ("benchmark", "A_aggravate", "A_withhold")) == 0)
    check("self_deal label: > 0 in A_self_deal", m("A_self_deal", "self_deal_rate_A") > 0)

    print("\nRegulator flags on firm A per run (mean): action / oracle; wrongful = flags on non-positive windows")
    for cell in CELLS:
        row = []
        for enf in ("action", "oracle"):
            runs = by.get((cell, enf))
            if not runs:
                row.append("   -")
                continue
            fa = np.mean([sum(e["flag"] and e["firm"] == "A" for e in _events(root, s)) for s in runs])
            row.append(f"{fa:4.2f} (wrongful {np.mean([s['wrongful_flags'] for s in runs]):4.2f})")
        print(f"  {cell:14s} " + "   ".join(row))
    for enf in ("action", "oracle"):
        runs = by[("benchmark", enf)]
        check(f"{enf}: benchmark never flagged", sum(sum(e["flag"] for e in _events(root, s)) for s in runs) == 0)
        runs = by[("A_self_deal", enf)]
        check(f"{enf}: flags A in A_self_deal", np.mean([sum(e["flag"] and e["firm"] == "A" for e in _events(root, s)) for s in runs]) > 0.5)

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
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "runs/smoke_v2"))
