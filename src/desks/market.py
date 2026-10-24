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
class Units:
    """Bid blocks in the merit order. Market v1: one block of K MW per firm; v2: `MarketParams.blocks`."""

    owner: np.ndarray  # firm index of each block
    mw: np.ndarray
    c_up: np.ndarray
    c_down: np.ndarray

    @property
    def one_per_firm(self) -> bool:
        return bool(np.array_equal(self.owner, np.arange(len(self.owner))))

    def of(self, i: int) -> np.ndarray:
        """Block indices of firm i, in the firm's own order."""
        return np.flatnonzero(self.owner == i)

    def by_firm(self, values: np.ndarray, n_firms: int) -> np.ndarray:
        """Sum per-block values per firm. With one block per firm the array is returned as is (v1 bit-identical)."""
        values = np.asarray(values, dtype=float)
        if self.one_per_firm:
            return values
        return np.bincount(self.owner, weights=values, minlength=n_firms)


def make_units(params: MarketParams, n_firms: int) -> Units:
    if params.blocks is None:
        return Units(
            owner=np.arange(n_firms),
            mw=np.broadcast_to(np.asarray(params.K, dtype=float), (n_firms,)).copy(),
            c_up=np.asarray(params.c_up, dtype=float),
            c_down=np.asarray(params.c_down, dtype=float),
        )
    if len(params.blocks) != n_firms:
        raise ValueError(f"market.blocks needs one block list per firm ({n_firms}), got {len(params.blocks)}")
    rows = [(i, *map(float, b)) for i, firm_blocks in enumerate(params.blocks) for b in firm_blocks]
    if any(len(r) != 4 for r in rows) or {i for i, *_ in rows} != set(range(n_firms)):
        raise ValueError("market.blocks: every firm needs >= 1 block of [MW, c_up, c_down]")
    owner, mw, cu, cd = (np.array(col) for col in zip(*rows))
    return Units(owner=owner.astype(int), mw=mw, c_up=cu, c_down=cd)


def bsp_costs(params: MarketParams, units: Units, i: int):
    """Costs for firm i's BSP desk: scalars for a single block, per-block lists for a ladder (market v2)."""
    if params.blocks is None:
        return params.c_up[i], params.c_down[i]
    idx = units.of(i)
    if len(idx) == 1:
        return float(units.c_up[idx[0]]), float(units.c_down[idx[0]])
    return [float(c) for c in units.c_up[idx]], [float(c) for c in units.c_down[idx]]


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
        bsp = np.zeros_like(clearing.q)  # per block, like the other branches
    return Settlement(brp=brp, bsp=bsp, rest=float(r * (P - lam)))


def clamp_bids(up: np.ndarray, down: np.ndarray, params: MarketParams) -> tuple[np.ndarray, np.ndarray, bool]:
    """Clamp bids to [price_floor, price_cap]; returns (up, down, any_clamped)."""
    up = np.asarray(up, dtype=float)
    down = np.asarray(down, dtype=float)
    cu = np.clip(up, params.price_floor, params.price_cap)
    cd = np.clip(down, params.price_floor, params.price_cap)
    return cu, cd, bool(np.any(cu != up) or np.any(cd != down))


def benchmark(e: np.ndarray, r: float, tie_keys: np.ndarray, params: MarketParams) -> tuple[float, Clearing, Settlement]:
    """Competitive benchmark: d = 0, cost bids, all BSPs eligible, same noise.

    `clearing.q` and `settlement.bsp` are per block (per firm in market v1).
    """
    units = make_units(params, len(e))
    S = float(np.sum(e) + r)
    cl = clear(S, units.c_up, units.c_down, units.mw, np.ones(len(units.mw), bool), tie_keys, params)
    return S, cl, settle(e, r, cl, units.c_up, units.c_down, params.lam)


def bid_markup(u: float, v: float, c_up: float, c_down: float, direction: str) -> float:
    """Direction-relevant bid markup: up markup if short, down markup if long, max of both if balanced."""
    up_mk = (u - c_up) / c_up
    down_mk = (c_down - v) / c_down
    if direction == SHORT:
        return float(up_mk)
    if direction == LONG:
        return float(down_mk)
    return float(max(up_mk, down_mk))


def firm_markup(u: np.ndarray, v: np.ndarray, units: Units, i: int, direction: str) -> float:
    """Firm i's markup: the highest direction-relevant markup over its blocks (v1: its single block)."""
    return max(bid_markup(u[j], v[j], units.c_up[j], units.c_down[j], direction) for j in units.of(i))
