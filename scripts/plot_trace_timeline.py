"""Report figure: within-firm coordination intent in the private reasoning over the run, EXP2 vs EXP3.

    python scripts/plot_trace_timeline.py [--runs] [--out results/trace_analysis/figures/intent_over_time]

Writes <out>.svg, <out>.pdf, <out>.png (300 dpi) and <out>.md (the plotted values with n and the per-run range).
EXP2 and EXP3 are the report's names for the runs in results/exp8_* and results/exp9_*.

Two panels, both from the Haiku codes of the reasoning traces (scripts/code_traces.py loader, so the same filters and
score rule as coder_v3/counts.md): (a) own-desk score >= 2, a concrete within-firm strategy; (b) own-desk score 3, a
plan to signal or solicit coordination with the firm's own other desk (a subset of (a)). Periods are grouped into six
blocks of five. Each point is the share of the block's 150 decisions (5 runs x 6 desks x 5 periods); every run
contributes 30, so this equals the mean of the five runs' shares. The figure shows no uncertainty band. With --runs,
each run's share is drawn as a faint dot (variation across runs, not a confidence interval).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

import code_traces  # noqa: E402  (scripts/ is on the path when run as a script)

BLOCK, T = 5, 30
INK, MUTED, GRID = "#1f1f1e", "#5b5a55", "#e4e3df"
CONDITIONS = {  # colour (colour-blind safe pair), line style and marker, so the lines also differ in grayscale
    "exp8": ("EXP2: reasoning", "#eb6834", "-", "o"),
    "exp9": ("EXP3: reasoning + stated rules", "#2a78d6", "--", "s"),
}
PANELS = [  # (threshold on the own-desk score, title, y-axis maximum)
    (2, "(a) Concrete within-firm strategy (score ≥ 2)", 100),
    (3, "(b) Plan to signal or solicit (score 3)", 50),
]


def shares(rows: list[dict], thr: int) -> tuple[list[float], list[int], list[list[float]]]:
    """Per block: pooled share of decisions with own-desk score >= thr, number of decisions, and each run's share."""
    pooled, ns, per_run = [], [], []
    seeds = sorted({r["seed"] for r in rows})
    for lo in range(1, T + 1, BLOCK):
        block = [r for r in rows if lo <= r["t"] < lo + BLOCK]
        ns.append(len(block))
        pooled.append(100 * sum(r["score_own_desk"] >= thr for r in block) / len(block))
        per_run.append([100 * sum(r["score_own_desk"] >= thr for r in block if r["seed"] == s)
                        / sum(r["seed"] == s for r in block) for s in seeds])
    return pooled, ns, per_run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", action="store_true", help="also draw each run's share as a faint dot")
    ap.add_argument("--out", default="results/trace_analysis/figures/intent_over_time")
    args = ap.parse_args()
    data = {exp: code_traces.coded(exp) for exp in CONDITIONS}
    labels = [f"{lo}–{lo + BLOCK - 1}" for lo in range(1, T + 1, BLOCK)]
    x = list(range(len(labels)))

    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"], "font.size": 8,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5,
        "ytick.major.size": 2.5, "pdf.fonttype": 42, "svg.fonttype": "path",
    })
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.6))
    table = []
    for ax, (thr, title, ymax) in zip(axes, PANELS):
        for exp, (name, color, style, marker) in CONDITIONS.items():
            pooled, ns, per_run = shares(data[exp], thr)
            if args.runs:
                for i, vals in enumerate(per_run):
                    off = -0.09 if exp == "exp8" else 0.09
                    ax.scatter([i + off] * len(vals), vals, s=4, color=color, alpha=0.35, lw=0, zorder=1)
            ax.plot(x, pooled, color=color, ls=style, lw=1.6, marker=marker, ms=3.8, label=name, zorder=3,
                    markeredgewidth=0)
            ax.annotate(f"{pooled[-1]:.0f}%", (x[-1], pooled[-1]), xytext=(5, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=7.5, color=color, fontweight="bold")
            table.append((title, name, pooled, ns, per_run))
        ax.set_title(title, fontsize=8.5, loc="left", color=INK, pad=4)
        if args.runs:  # never clip a run: extend the scale to the highest run (EXP8 reaches 67% in panel b)
            top = max(v for _, _, _, _, per_run in table[-2:] for vals in per_run for v in vals)
            ymax = max(ymax, 10 * int(-(-top // 10)))
        ax.set_ylim(0, ymax)
        ax.set_yticks(range(0, ymax + 1, 25 if ymax == 100 else 10))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.set_xlim(-0.3, len(x) - 1 + 0.6)  # room for the end labels
        ax.set_xticks(x, labels)
        ax.set_xlabel("Settlement periods", color=INK)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Share of decisions")
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="upper center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 1.0),
               handlelength=2.6, columnspacing=2.0)
    fig.tight_layout(rect=(0, 0, 1, 0.9), w_pad=2.5)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "pdf"):
        fig.savefig(out.with_suffix(f".{ext}"), bbox_inches="tight", pad_inches=0.02)
    fig.savefig(out.with_suffix(".png"), dpi=300, bbox_inches="tight", pad_inches=0.02)
    lines = ["# Within-firm coordination intent over time (figure data)", "",
             "Generated by `scripts/plot_trace_timeline.py` from the Haiku codes of the private reasoning traces. Each value "
             "is the share of the block's decisions; n is the number of decisions (5 runs x 6 desks x 5 periods). The range "
             "is the lowest to highest run (variation across runs, not a confidence interval) and is not drawn in the figure.", "",
             "| Panel | Condition | " + " | ".join(labels) + " |", "|---|---|" + "---|" * len(labels)]
    for title, name, pooled, ns, per_run in table:
        cells = [f"{p:.0f}% (n={n}; runs {min(r):.0f}–{max(r):.0f})" for p, n, r in zip(pooled, ns, per_run)]
        lines.append(f"| {title} | {name} | " + " | ".join(cells) + " |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
