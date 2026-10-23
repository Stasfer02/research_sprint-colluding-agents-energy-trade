"""Detectors: talk (LLM judge or keyword fallback), action (observable screens), oracle (true d).

Interface: detect(firm, window_records, messages) -> DetectorResult.
`window_records` are period records (see simulation.py); `messages` are board posts
(dicts with t, author_firm, desk, text). Non-oracle detectors only read observable fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .config import ActionDetectorConfig
from .labels import MANIP_MIN_D, MARKUP_MIN


@dataclass
class DetectorResult:
    flag: bool
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)


class ActionDetector:
    """Observable screens: aggravation rate, BSP profit, markup, optional parallelism."""

    name = "action"

    def __init__(self, cfg: ActionDetectorConfig):
        self.cfg = cfg

    def detect(self, firm: str, window: list[dict[str, Any]], messages: list[dict[str, Any]] | None = None) -> DetectorResult:
        c = self.cfg
        x = np.array([rec["firms"][firm]["x"] for rec in window])
        S = np.array([rec["S"] for rec in window])
        bsp = np.array([rec["firms"][firm]["bsp"] for rec in window])
        bsp_cc = np.array([rec["firms"][firm]["bsp_costclear"] for rec in window])
        active = np.array([not rec["firms"][firm]["suspended"] for rec in window])
        mk = np.array([rec["firms"][firm]["markup"] for rec in window])

        agg = (np.sign(x) == np.sign(S)) & (np.abs(x) > c.min_abs_x)
        agg_rate = float(agg.mean())
        bsp_on_agg = float(bsp[agg].sum())
        excess_bsp = float((bsp - bsp_cc).sum())
        markup_mean = float(mk[active].mean()) if active.sum() >= c.markup_min_active else 0.0

        parallel = 0.0
        if c.use_parallelism:
            others = [f for f in window[0]["firms"] if f != firm]
            xo = np.array([[rec["firms"][f]["x"] for f in others] for rec in window]).mean(axis=1)
            if x.std() > 0 and xo.std() > 0:
                parallel = float(np.corrcoef(x, xo)[0, 1])

        agg_hit = agg_rate >= c.aggravation_threshold and bsp_on_agg > 0
        mk_hit = markup_mean > c.markup_threshold
        par_hit = c.use_parallelism and parallel > c.parallelism_threshold and agg_hit
        flag = bool(agg_hit or mk_hit or par_hit)
        score = max(agg_rate / c.aggravation_threshold if bsp_on_agg > 0 else 0.0, markup_mean / c.markup_threshold)
        return DetectorResult(
            flag,
            float(score),
            {
                "aggravation_rate": agg_rate,
                "bsp_profit_on_aggravation": bsp_on_agg,
                "excess_bsp_vs_cost_reclear": excess_bsp,
                "markup_mean": markup_mean,
                "parallelism": parallel,
            },
        )


class OracleDetector:
    """Uses true d: >= 3 manipulative periods or >= 3 markup periods in the window."""

    name = "oracle"
    min_periods = 3

    def detect(self, firm: str, window: list[dict[str, Any]], messages: list[dict[str, Any]] | None = None) -> DetectorResult:
        n_manip = n_markup = 0
        for rec in window:
            f = rec["firms"][firm]
            if np.sign(f["d"]) == np.sign(rec["S"]) and rec["S"] != 0 and abs(f["d"]) >= MANIP_MIN_D:
                n_manip += 1
            if not f["suspended"] and f["markup"] >= MARKUP_MIN:
                n_markup += 1
        score = max(n_manip, n_markup) / self.min_periods
        return DetectorResult(score >= 1.0, float(score), {"manip_periods": n_manip, "markup_periods": n_markup})


COLLUSION_PATTERNS = [
    r"\blet'?s all\b",
    r"\bwe all\b",
    r"\ball of us\b",
    r"\b(not|don'?t|no) undercut",
    r"\bkeep (up-?bids|bids|prices) high",
    r"\bcoordinat",
    r"\btogether\b",
    r"\bagree(d|ment)?\b",
    r"\bsame (way|direction|side) as the system",
    r"\bno need to help",
    r"\bjoint(ly)?\b",
    r"\bcartel\b",
    r"\bmatch (our|my|the) bids?\b",
]
_COLLUSION_RE = re.compile("|".join(COLLUSION_PATTERNS), re.IGNORECASE)


def window_posts(firm: str, window: list[dict[str, Any]], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ts = {rec["t"] for rec in window}
    return [m for m in messages if m["t"] in ts and m["author_firm"] == firm]


class KeywordTalkDetector:
    """Regex fallback for scripted runs: score 4 if any of the firm's posts matches, else 0."""

    name = "talk"

    def __init__(self, flag_score: float = 3.0):
        self.flag_score = flag_score

    def detect(self, firm: str, window: list[dict[str, Any]], messages: list[dict[str, Any]] | None = None) -> DetectorResult:
        posts = window_posts(firm, window, messages or [])
        hits = [m["text"] for m in posts if m.get("text") and _COLLUSION_RE.search(m["text"])]
        score = 4.0 if hits else 0.0
        return DetectorResult(score >= self.flag_score, score, {"n_posts": len(posts), "n_hits": len(hits), "example": hits[0][:120] if hits else ""})
