"""Market clearing and settlement (pure functions).

Three firms, each with one balancing block of K MW per direction. Sign convention: firm imbalance x > 0 is long
(surplus). System imbalance S = sum(x) + r. S < 0 is short (upward regulation); S > 0 is long (downward).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import MarketParams

SHORT, LONG, BALANCED = "short", "long", "balanced"


@dataclass(frozen=True)
class Clearing:
    direction: str
    price: float
    q: np.ndarray  # activated MW per firm (>= 0), in the direction of regulation
    need: float  # MW of regulation required (>= 0)
    scarcity: bool  # capacity was insufficient -> cap / floor price
    marginal: int | None  # index of the price-setting firm


@dataclass(frozen=True)
class Settlement:
    brp: np.ndarray  # trading desks' settlement per firm
    bsp: np.ndarray  # balancing desks' margin per firm
    rest: float  # rest of the market's settlement


def clear(S: float, up: np.ndarray, down: np.ndarray, tie_keys: np.ndarray, params: MarketParams) -> Clearing:
    """Single-price, pay-as-cleared clearing of the merit order.

    `tie_keys` (uniform draws from the tie-break stream) break price ties: lower key first.
    """
    up = np.asarray(up, dtype=float)
    down = np.asarray(down, dtype=float)
    q = np.zeros(len(up))
    if S < -params.eps:
        direction, need, prices, scarcity_price = SHORT, -S, up, params.price_cap
        order = np.lexsort((tie_keys, up))  # ascending price
    elif S > params.eps:
        direction, need, prices, scarcity_price = LONG, S, down, params.price_floor
        order = np.lexsort((tie_keys, -down))  # descending price
    else:
        return Clearing(BALANCED, float((up.min() + down.max()) / 2), q, 0.0, False, None)

    remaining = need
    marginal = None
    for i in order:
        if remaining <= 1e-9:
            break
        take = min(params.K, remaining)
        q[i] = take
        remaining -= take
        marginal = int(i)
    if remaining > 1e-9:
        return Clearing(direction, float(scarcity_price), q, float(need), True, marginal)
    return Clearing(direction, float(prices[marginal]), q, float(need), False, marginal)


def settle(x: np.ndarray, r: float, clearing: Clearing, params: MarketParams) -> Settlement:
    P = clearing.price
    x = np.asarray(x, dtype=float)
    if clearing.direction == SHORT:
        bsp = clearing.q * (P - np.asarray(params.c_up, dtype=float))
    elif clearing.direction == LONG:
        bsp = clearing.q * (np.asarray(params.c_down, dtype=float) - P)
    else:
        bsp = np.zeros_like(clearing.q)
    return Settlement(brp=x * (P - params.lam), bsp=bsp, rest=float(r * (P - params.lam)))


def clamp_bids(up: np.ndarray, down: np.ndarray, params: MarketParams) -> tuple[np.ndarray, np.ndarray, bool]:
    """Clamp bids to [price_floor, price_cap]; returns (up, down, any_clamped)."""
    up = np.asarray(up, dtype=float)
    down = np.asarray(down, dtype=float)
    cu = np.clip(up, params.price_floor, params.price_cap)
    cd = np.clip(down, params.price_floor, params.price_cap)
    return cu, cd, bool(np.any(cu != up) or np.any(cd != down))
