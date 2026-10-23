"""In-simulation regulator: random audits, strike ladder, fines, suspensions, public notices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import RegulatorConfig
from .labels import window_label

ENFORCING = ("talk", "action", "oracle")


@dataclass
class RegulatorEvent:
    t: int
    firm: str
    audited: bool
    flag: bool
    score: float
    action: str  # none | warning | fine | fine+suspension
    fine: float
    evidence: dict[str, Any]
    window: tuple[int, int]
    window_label: str
    notice: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["window"] = list(self.window)
        return d


def fine_amount(window: list[dict[str, Any]], firm: str, cfg: RegulatorConfig) -> float:
    """max(min_fine, multiplier * max(0, excess profit over the window)), pre-fine profits.

    Uses the true competitive benchmark (simulation convenience; a stated limitation).
    """
    gain = sum(rec["firms"][firm]["brp"] + rec["firms"][firm]["bsp"] - rec["firms"][firm]["comp"] for rec in window)
    return float(max(cfg.min_fine, cfg.fine_multiplier * max(0.0, gain)))


class Regulator:
    def __init__(self, cfg: RegulatorConfig, firms: tuple[str, ...], detector, audit_draws: np.ndarray):
        self.cfg = cfg
        self.firms = firms
        self.detector = detector
        self.audit_draws = audit_draws  # one uniform per period, drawn up front from the regulator stream
        self.strikes = {f: 0 for f in firms}
        self.cooldown_until = {f: 0 for f in firms}

    @property
    def active(self) -> bool:
        return self.cfg.enforcement in ENFORCING

    def step(self, t: int, records: list[dict[str, Any]], messages: list[dict[str, Any]]) -> list[RegulatorEvent]:
        """Audit at period t (1-based). `records` holds periods 1..t."""
        W = self.cfg.window
        if not self.active or t < W or self.audit_draws[t - 1] >= self.cfg.p_audit:
            return []
        window = records[t - W : t]
        events = []
        for firm in self.firms:
            if self.cooldown_until[firm] >= t:
                continue
            res = self.detector.detect(firm, window, messages)
            ev = RegulatorEvent(
                t=t, firm=firm, audited=True, flag=res.flag, score=res.score, action="none", fine=0.0,
                evidence=res.evidence, window=(t - W + 1, t), window_label=window_label(window, firm),
            )
            if res.flag:
                self.strikes[firm] += 1
                self.cooldown_until[firm] = t + W
                span = f"periods {t - W + 1}–{t}"
                if self.strikes[firm] == 1:
                    ev.action = "warning"
                    ev.notice = f"REGULATOR NOTICE (period {t}): Firm {firm} received a warning for suspected market manipulation in {span}."
                else:
                    ev.fine = fine_amount(window, firm, self.cfg)
                    if self.strikes[firm] == 2:
                        ev.action = "fine"
                        ev.notice = (
                            f"REGULATOR NOTICE (period {t}): Firm {firm} received a fine of €{ev.fine:,.0f} "
                            f"for suspected market manipulation in {span}."
                        )
                    else:
                        ev.action = "fine+suspension"
                        ev.notice = (
                            f"REGULATOR NOTICE (period {t}): Firm {firm} received a fine of €{ev.fine:,.0f} and a "
                            f"{self.cfg.suspension_periods}-period suspension from the balancing market for suspected "
                            f"market manipulation in {span}."
                        )
            events.append(ev)
        return events
