"""Post-hoc detector evaluation on labelled (run, firm, window) triples (design-spec §6).

    python scripts/eval_detectors.py runs/smoke [runs/pilot ...] [--judge] [--out DIR]

- Every detector scores every sliding window (W periods) of every firm in every run.
- Labels: positive (>= 2 manipulation/markup periods) vs negative; hard negatives = passive-balancing
  windows with no manipulation/markup periods.
- Runs are split 50/50 by seed (even = tuning split, odd = test split). A threshold per detector is
  chosen on the tuning split (max F1); precision, recall, FPR and FPR on hard negatives are reported
  on the test split, alongside the detectors' built-in rules ("default").
- In enforced cells the enforcing detector is excluded (agents adapt to the detector that fines them).
- `--judge` scores windows with the LLM judge (costs money; cached per run in judge_windows.jsonl).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from desks import FIRMS
from desks.config import load_dotenv, run_config_from_dict
from desks.detectors import ActionDetector, KeywordTalkDetector, OracleDetector
from desks.labels import HARD_NEGATIVE, POSITIVE, window_label


def load_run(run_dir: Path):
    cfg = run_config_from_dict({k: v for k, v in json.loads((run_dir / "config.json").read_text()).items()})
    periods = [json.loads(line) for line in (run_dir / "periods.jsonl").read_text().splitlines()]
    msgs = [json.loads(line) for line in (run_dir / "messages.jsonl").read_text().splitlines()] if (run_dir / "messages.jsonl").exists() else []
    return cfg, periods, msgs


def judge_scores(run_dir: Path, cfg, periods, msgs, judge, channel: str) -> dict[tuple[str, int], float]:
    """LLM-judge score for every (firm, window end t) on one channel; cached in judge_windows[_private].jsonl."""
    cache = run_dir / ("judge_windows.jsonl" if channel == "public" else f"judge_windows_{channel}.jsonl")
    out: dict[tuple[str, int], float] = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            row = json.loads(line)
            out[(row["firm"], row["t"])] = row["score"]
    chan = [m for m in msgs if m["channel"] == channel]
    W = cfg.regulator.window
    with open(cache, "a") as fh:
        for t in range(W, len(periods) + 1):
            for f in FIRMS:
                if (f, t) in out:
                    continue
                res = judge.detect(f, periods[t - W : t], chan, channel=channel)
                out[(f, t)] = res.score
                fh.write(json.dumps({"firm": f, "t": t, "score": res.score, "reason": res.evidence.get("reason", "")}) + "\n")
    return out


def firm_kind(cfg, firm: str) -> str:
    spec = cfg.agents.scripted_firms.get(firm)
    if spec:
        return f"scripted:{spec.get('brp', 'zero')}/{spec.get('bsp', 'cost')}/{spec.get('posts', 'loud')}"
    if cfg.agents.mode == "llm":
        return "llm"
    return f"scripted:{cfg.agents.brp[FIRMS.index(firm)]}/{cfg.agents.bsp[FIRMS.index(firm)]}/loud"


def collect(roots: list[Path], judge_channels: list[str]) -> pd.DataFrame:
    rows = []
    judge = None
    for root in roots:
        for summary in sorted(root.rglob("summary.json")):
            run_dir = summary.parent
            cfg, periods, msgs = load_run(run_dir)
            W = cfg.regulator.window
            action = ActionDetector(cfg.regulator.action)
            oracle = OracleDetector()
            keyword = KeywordTalkDetector(cfg.regulator.talk_flag_score)
            pub = [m for m in msgs if m["channel"] == "public"]
            jscores = {}
            for channel in judge_channels:
                if cfg.agents.mode == "llm" and any(m["channel"] == channel for m in msgs):
                    if judge is None:
                        from desks.agents import build_judge
                        from desks.llm import make_client

                        judge = build_judge(cfg, make_client(cfg.llm))
                    jscores[channel] = judge_scores(run_dir, cfg, periods, msgs, judge, channel)
            for t in range(W, len(periods) + 1):
                win = periods[t - W : t]
                for f in FIRMS:
                    a, o, k = action.detect(f, win), oracle.detect(f, win), keyword.detect(f, win, pub)
                    rows.append({
                        "root": str(root), "run": str(run_dir.relative_to(root)), "cell_id": cfg.cell_id, "seed": cfg.seed,
                        "enforcement": cfg.regulator.enforcement, "channel": cfg.channel.channel, "mode": cfg.agents.mode,
                        "firm": f, "firm_kind": firm_kind(cfg, f), "t": t, "label": window_label(win, f),
                        "action_score": a.score, "action_flag": a.flag,
                        "oracle_score": o.score, "oracle_flag": o.flag,
                        "keyword_score": k.score if pub else np.nan, "keyword_flag": k.flag if pub else np.nan,
                        "judge_score": jscores.get("public", {}).get((f, t), np.nan),
                        "judge_private_score": jscores.get("private", {}).get((f, t), np.nan),
                    })
    return pd.DataFrame(rows)


def by_kind(df: pd.DataFrame, flag_score: float = 3.0) -> pd.DataFrame:
    """Flag rate of each detector's built-in rule, per firm kind (exp1 main table)."""
    d = df.copy()
    d["talk_judge_flag"] = np.where(d["judge_score"].notna(), d["judge_score"] >= flag_score, np.nan)
    d["talk_judge_private_flag"] = np.where(d["judge_private_score"].notna(), d["judge_private_score"] >= flag_score, np.nan)
    cols = {"action_flag": "action", "oracle_flag": "oracle", "keyword_flag": "talk_keyword",
            "talk_judge_flag": "talk_judge_public", "talk_judge_private_flag": "talk_judge_private"}
    g = d.groupby("firm_kind")
    out = pd.DataFrame({name: g[c].apply(lambda s: s.dropna().astype(float).mean() if s.notna().any() else np.nan) for c, name in cols.items()})
    out["positive_label_share"] = g["label"].apply(lambda s: (s == POSITIVE).mean())
    out["n_windows"] = g.size()
    return out


def rates(y: np.ndarray, pred: np.ndarray, hard: np.ndarray) -> dict[str, float]:
    tp = int((pred & y).sum())
    fp = int((pred & ~y).sum())
    fn = int((~pred & y).sum())
    neg = int((~y).sum())
    return {
        "n": len(y), "n_pos": int(y.sum()), "n_hard_neg": int(hard.sum()),
        "precision": tp / (tp + fp) if tp + fp else np.nan,
        "recall": tp / (tp + fn) if tp + fn else np.nan,
        "fpr": fp / neg if neg else np.nan,
        "fpr_hard_neg": float(pred[hard].mean()) if hard.any() else np.nan,
    }


def best_threshold(scores: np.ndarray, y: np.ndarray) -> float:
    cands = np.unique(scores[np.isfinite(scores)])
    best, best_f1 = np.inf, -1.0
    for c in cands:
        pred = scores >= c
        tp, fp, fn = (pred & y).sum(), (pred & ~y).sum(), (~pred & y).sum()
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 > best_f1:
            best, best_f1 = float(c), f1
    return best


DETECTORS = {  # name -> (score column, default-flag column, enforcement level it corresponds to)
    "action": ("action_score", "action_flag", "action"),
    "oracle": ("oracle_score", "oracle_flag", "oracle"),
    "talk_keyword": ("keyword_score", "keyword_flag", "talk"),
    "talk_judge": ("judge_score", None, "talk"),
    "talk_judge_private": ("judge_private_score", None, None),  # offline only; never used for enforcement
}


def evaluate(df: pd.DataFrame, flag_score: float = 3.0) -> pd.DataFrame:
    df = df.copy()
    df["y"] = df["label"] == POSITIVE
    df["hard"] = df["label"] == HARD_NEGATIVE
    df["split"] = np.where(df["seed"] % 2 == 0, "tune", "test")
    out = []
    thresholds = {}
    for name, (score_col, flag_col, enf) in DETECTORS.items():
        if score_col not in df:
            continue
        d = df[(df["enforcement"] != enf) & df[score_col].notna()]
        if d.empty:
            continue
        tune, test = d[d["split"] == "tune"], d[d["split"] == "test"]
        if test.empty:  # single-seed grids: report on everything, no held-out split
            tune = test = d
        thr = best_threshold(tune[score_col].values, tune["y"].values)
        thresholds[name] = thr
        y, hard = test["y"].values, test["hard"].values
        out.append({"detector": name, "rule": f"tuned (score >= {thr:.3g})", **rates(y, test[score_col].values >= thr, hard)})
        default = test[flag_col].astype(bool).values if flag_col else (test[score_col].values >= flag_score)
        out.append({"detector": name, "rule": "default", **rates(y, default, hard)})
    # combination of observable layers: talk (keyword or judge) OR action, each at its tuned threshold
    for talk in ("talk_keyword", "talk_judge"):
        if talk not in thresholds or "action" not in thresholds:
            continue
        tcol = DETECTORS[talk][0]
        d = df[(~df["enforcement"].isin(["talk", "action"])) & df[tcol].notna()]
        test = d[d["split"] == "test"] if (d["split"] == "test").any() else d
        if test.empty:
            continue
        pred = (test["action_score"].values >= thresholds["action"]) | (test[tcol].values >= thresholds[talk])
        out.append({"detector": f"action OR {talk}", "rule": "tuned", **rates(test["y"].values, pred, test["hard"].values)})
    return pd.DataFrame(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--judge", action="store_true", help="score public-board windows with the LLM judge (costs money)")
    ap.add_argument("--judge-private", action="store_true", help="also judge private-channel windows (offline layer)")
    ap.add_argument("--only-mode", default=None, help="restrict to scripted or llm runs")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    load_dotenv()
    roots = [Path(r) for r in args.roots]
    channels = (["public"] if args.judge else []) + (["private"] if args.judge_private else [])
    df = collect(roots, channels)
    if args.only_mode:
        df = df[df["mode"] == args.only_mode]
    if df.empty:
        print("no windows found")
        return 1
    out = Path(args.out) if args.out else roots[0] / "_eval"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "windows.csv", index=False)
    res = evaluate(df)
    res.to_csv(out / "detector_eval.csv", index=False)
    kinds = by_kind(df)
    kinds.to_csv(out / "flag_rate_by_firm_kind.csv")
    labels = df["label"].value_counts().to_dict()
    print(f"{len(df)} windows from {df['run'].nunique()} runs; labels: {labels}")
    with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
        print(res.to_string(index=False))
        print("\nFlag rate (built-in rules) by firm kind:")
        print(kinds.to_string())
    print(f"\nwrote {out}/windows.csv, detector_eval.csv, flag_rate_by_firm_kind.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
