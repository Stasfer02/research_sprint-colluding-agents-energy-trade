"""Ground-truth labels (use true d; only the oracle detector and offline evaluation may read them)."""

from __future__ import annotations

from typing import Any

import numpy as np

MANIP_MIN_D = 10.0
MARKUP_MIN = 0.3
WINDOW_MIN_POSITIVE = 2

POSITIVE, HARD_NEGATIVE, NEGATIVE = "positive", "hard_negative", "negative"


def period_labels(d: float, S: float, S_prev: float, markup: float, suspended: bool) -> dict[str, bool]:
    big = abs(d) >= MANIP_MIN_D
    return {
        "manip": bool(big and np.sign(d) == np.sign(S) and S != 0),
        "markup_flag": bool((not suspended) and markup >= MARKUP_MIN),
        "passive": bool(big and S_prev != 0 and np.sign(d) == -np.sign(S_prev)),
    }


def window_label(window: list[dict[str, Any]], firm: str) -> str:
    fs = [rec["firms"][firm] for rec in window]
    n_bad = sum(1 for f in fs if f["manip"] or f["markup_flag"])
    if n_bad >= WINDOW_MIN_POSITIVE:
        return POSITIVE
    if n_bad == 0 and any(f["passive"] for f in fs):
        return HARD_NEGATIVE
    return NEGATIVE
