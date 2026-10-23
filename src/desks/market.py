"""Market clearing, settlement and the competitive benchmark (pure functions).

Sign convention: firm imbalance x > 0 is long (surplus). System imbalance
S = sum(x) + r. S < 0 is short (upward regulation); S > 0 is long (downward).
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
    q: np.ndarray  # activated MW per BSP (>= 0), in the direction of regulation
    need: float  # MW of regulation required (>= 0)
    scarcity: bool  # capacity was insufficient -> cap / floor price
    marginal: int | None  # index of the price-setting BSP


@dataclass(frozen=True)
class Settlement:
    brp: np.ndarray
    bsp: np.ndarray
    rest: float


def clear(
    S: float,
    up: np.ndarray,
    down: np.ndarray,
    K: np.ndarray | float,
    eligible: np.ndarray,
    tie_keys: np.ndarray,
    params: MarketParams,
) -> Clearing:
    """Single-price, pay-as-cleared clearing of the aFRR merit order.

    `tie_keys` (uniform draws from the tie-break stream) break price ties: lower key first.
    """
    up = np.asarray(up, dtype=float)
    down = np.asarray(down, dtype=float)
    n = len(up)
    K = np.broadcast_to(np.asarray(K, dtype=float), (n,))
    eligible = np.asarray(eligible, dtype=bool)
    idx = np.flatnonzero(eligible)
    q = np.zeros(n)

    if S < -params.eps:
        direction, need, prices, cap_price = SHORT, -S, up, params.price_cap
        order = idx[np.lexsort((tie_keys[idx], up[idx]))]  # ascending price
    elif S > params.eps:
        direction, need, prices, cap_price = LONG, S, down, params.price_floor
        order = idx[np.lexsort((tie_keys[idx], -down[idx]))]  # descending price
    else:
        if len(idx):
            price = (up[idx].min() + down[idx].max()) / 2
        else:
            price = params.lam
        return Clearing(BALANCED, float(price), q, 0.0, False, None)

    remaining = need
    marginal = None
    for i in order:
        if remaining <= 1e-9:
            break
        take = min(K[i], remaining)
        q[i] = take
        remaining -= take
        marginal = int(i)
    if remaining > 1e-9:
        return Clearing(direction, float(cap_price), q, float(need), True, marginal)
    return Clearing(direction, float(prices[marginal]), q, float(need), False, marginal)


def settle(
    x: np.ndarray,
    r: float,
    clearing: Clearing,
    c_up: np.ndarray,
    c_down: np.ndarray,
    lam: float,
) -> Settlement:
    P = clearing.price
    x = np.asarray(x, dtype=float)
    brp = x * (P - lam)
    if clearing.direction == SHORT:
        bsp = clearing.q * (P - np.asarray(c_up, dtype=float))
    elif clearing.direction == LONG:
        bsp = clearing.q * (np.asarray(c_down, dtype=float) - P)
    else:
        bsp = np.zeros_like(x)
    return Settlement(brp=brp, bsp=bsp, rest=float(r * (P - lam)))


def clamp_bids(up: np.ndarray, down: np.ndarray, params: MarketParams) -> tuple[np.ndarray, np.ndarray, bool]:
    """Clamp bids to [price_floor, price_cap]; returns (up, down, any_clamped)."""
    up = np.asarray(up, dtype=float)
    down = np.asarray(down, dtype=float)
    cu = np.clip(up, params.price_floor, params.price_cap)
    cd = np.clip(down, params.price_floor, params.price_cap)
    return cu, cd, bool(np.any(cu != up) or np.any(cd != down))


def benchmark(e: np.ndarray, r: float, tie_keys: np.ndarray, params: MarketParams) -> tuple[float, Clearing, Settlement]:
    """Competitive benchmark: d = 0, cost bids, all BSPs eligible, same noise."""
    c_up = np.asarray(params.c_up, dtype=float)
    c_down = np.asarray(params.c_down, dtype=float)
    S = float(np.sum(e) + r)
    cl = clear(S, c_up, c_down, params.K, np.ones(len(e), bool), tie_keys, params)
    return S, cl, settle(e, r, cl, c_up, c_down, params.lam)


def bid_markup(u: float, v: float, c_up: float, c_down: float, direction: str) -> float:
    """Direction-relevant bid markup: up markup if short, down markup if long, max of both if balanced."""
    up_mk = (u - c_up) / c_up
    down_mk = (c_down - v) / c_down
    if direction == SHORT:
        return float(up_mk)
    if direction == LONG:
        return float(down_mk)
    return float(max(up_mk, down_mk))
