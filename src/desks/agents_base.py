"""Shared desk interface: what a desk sees (Observation) and what it does (Action)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Observation:
    """Everything a desk may see when acting in period t (information up to t-1).

    Built by the simulation per desk; it never contains forecast noise e, the
    rest-of-market imbalance r, other firms' deviations d, or firm IDs in the merit order.
    """

    firm: str
    role: str  # brp | bsp | integrated
    t: int
    T: int
    S_prev: float
    public_history: list[dict[str, Any]]
    own_history: list[dict[str, Any]]
    cum_profit: float
    profit_label: str
    board: list[dict[str, Any]] = field(default_factory=list)
    private: list[dict[str, Any]] = field(default_factory=list)
    notices: list[dict[str, Any]] = field(default_factory=list)
    suspended: bool = False
    c_up: float | None = None
    c_down: float | None = None
    # cumulative breakdown of the firm's profit, so a desk can see how much is its own
    brp_profit: float = 0.0
    bsp_profit: float = 0.0
    fines_total: float = 0.0
    show_fines: bool = False  # False when enforcement is "none": no mention of fines at all
    holding_profit: float | None = None  # all three firms combined (exp2 holding-company pressure levels)


@dataclass
class Action:
    deviation: float | None = None
    up_bid: float | None = None
    down_bid: float | None = None
    public_post: str | None = None
    private_message: str | None = None
    notes: str | None = None
    parse_ok: bool = True
    io: list[dict[str, Any]] = field(default_factory=list)  # raw LLM exchanges for agent_io.jsonl


class Desk:
    firm: str
    role: str

    def act(self, obs: Observation) -> Action:  # pragma: no cover - interface
        raise NotImplementedError
