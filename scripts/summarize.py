"""Collect summary.json files into CSVs and draw the three diagnostic plots.

    python scripts/summarize.py runs/pilot [--out runs/pilot/_summary]

Writes runs.csv (one row per run), cells.csv (mean / sd / n per cell) and
markup_by_cell.png, talk_vs_action.png, passive_by_enforcement.png.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from desks.runner import load_summaries  # noqa: E402

# Reference palette (dataviz skill), fixed categorical order; light mode.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
MARKERS = ["o", "s", "^", "D", "v"]
ENFORCEMENT_ORDER = ["none", "stated", "talk", "action", "oracle"]
CHANNEL_ORDER = ["none", "public", "public_private"]

KEY_METRICS = [
    "price_markup_mean", "price_markup_short", "price_markup_long", "excess_total", "excess_A", "excess_B", "excess_C",
    "rest_harm", "mean_abs_S", "manip_rate", "markup_rate", "aggravation_rate", "passive_volume", "bid_markup_mean",
    "bid_cv_up", "flags", "wrongful_flags", "fines_total", "suspensions", "judge_public_max", "judge_private_max",
    "notes_regulator_words", "parse_failure_rate", "cost_usd",
]


def _style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    ax.set_ylabel(ylabel, color=INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_markup_by_cell(df: pd.DataFrame, out: Path) -> None:
    g = df.groupby("cell_id")["price_markup_mean"].agg(["mean", "std", "count"]).sort_index()
    fig, ax = plt.subplots(figsize=(max(6, 0.55 * len(g) + 2), 4), facecolor=SURFACE)
    x = np.arange(len(g))
    err = (g["std"].fillna(0) / np.sqrt(g["count"])).values
    ax.bar(x, g["mean"], width=0.7, color=SERIES[0], edgecolor=SURFACE, linewidth=2)
    ax.errorbar(x, g["mean"], yerr=err, fmt="none", ecolor=INK2, elinewidth=1, capsize=2)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_xticks(x, g.index, rotation=60, ha="right")
    _style(ax, "Imbalance price markup vs competitive benchmark (mean ± s.e. over seeds)", "P − P_comp (€/MWh)")
    fig.tight_layout()
    fig.savefig(out / "markup_by_cell.png", dpi=150)
    plt.close(fig)


def plot_talk_vs_action(df: pd.DataFrame, out: Path) -> None:
    talk_col = "judge_public_max" if "judge_public_max" in df and df["judge_public_max"].notna().any() else None
    fig, ax = plt.subplots(figsize=(6, 4.5), facecolor=SURFACE)
    action = df["manip_rate"] + df["markup_rate"]
    if talk_col is None:
        ax.text(0.5, 0.5, "no judge scores (scripted runs)", ha="center", va="center", color=INK2, transform=ax.transAxes)
    else:
        for i, enf in enumerate([e for e in ENFORCEMENT_ORDER if e in set(df["enforcement"])]):
            m = df["enforcement"] == enf
            ax.scatter(df.loc[m, talk_col], action[m], s=48, color=SERIES[i % len(SERIES)], marker=MARKERS[i % len(MARKERS)],
                       edgecolor=SURFACE, linewidth=1.5, label=enf)
        ax.legend(title="enforcement", frameon=False, fontsize=8, title_fontsize=8, labelcolor=INK2)
        ax.set_xlim(-0.2, 4.2)
        ax.set_xlabel("talk: max LLM-judge score on public posts (0–4)", color=INK2)
    _style(ax, "Talk vs action coordination, per run", "action: manipulation + markup period share")
    fig.tight_layout()
    fig.savefig(out / "talk_vs_action.png", dpi=150)
    plt.close(fig)


def plot_passive_by_enforcement(df: pd.DataFrame, out: Path) -> None:
    enfs = [e for e in ENFORCEMENT_ORDER if e in set(df["enforcement"])]
    chans = [c for c in CHANNEL_ORDER if c in set(df["channel"])]
    fig, ax = plt.subplots(figsize=(6.5, 4), facecolor=SURFACE)
    w = 0.8 / max(1, len(chans))
    for j, ch in enumerate(chans):
        means = [df[(df["enforcement"] == e) & (df["channel"] == ch)]["passive_volume"].mean() for e in enfs]
        xs = np.arange(len(enfs)) + (j - (len(chans) - 1) / 2) * w
        ax.bar(xs, np.nan_to_num(means), width=w, color=SERIES[j], edgecolor=SURFACE, linewidth=2, label=ch)
    ax.set_xticks(np.arange(len(enfs)), enfs)
    if len(chans) > 1:
        ax.legend(title="channel", frameon=False, fontsize=8, title_fontsize=8, labelcolor=INK2)
    _style(ax, "Passive balancing volume by enforcement (mean per run)", "Σ|d| over passive periods (MW)")
    fig.tight_layout()
    fig.savefig(out / "passive_by_enforcement.png", dpi=150)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    root = Path(args.root)
    out = Path(args.out) if args.out else root / "_summary"
    out.mkdir(parents=True, exist_ok=True)
    rows = load_summaries(root)
    if not rows:
        print(f"no summary.json under {root}")
        return 1
    df = pd.DataFrame(rows)
    df.to_csv(out / "runs.csv", index=False)
    metrics = [k for k in KEY_METRICS if k in df]
    cells = df.groupby("cell_id")[metrics].agg(["mean", "std", "count"])
    cells.columns = [f"{a}_{b}" for a, b in cells.columns]
    cells.to_csv(out / "cells.csv")
    plot_markup_by_cell(df, out)
    plot_talk_vs_action(df, out)
    plot_passive_by_enforcement(df, out)

    show = [k for k in ("price_markup_mean", "excess_total", "rest_harm", "mean_abs_S", "manip_rate", "markup_rate",
                        "bid_markup_mean", "passive_volume", "flags", "wrongful_flags", "judge_public_max",
                        "judge_private_max", "parse_failure_rate", "cost_usd") if k in df]
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.3g}".format):
        print(df.groupby("cell_id")[show].mean())
    print(f"\n{len(df)} runs; wrote {out}/runs.csv, cells.csv and 3 plots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
