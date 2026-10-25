"""Clearing and settlement against hand-computed cases."""

import numpy as np
import pytest

from desks.config import MarketParams
from desks.market import BALANCED, LONG, SHORT, clamp_bids, clear, settle

P = MarketParams()
COST_UP = np.array(P.c_up)  # 70, 75, 80
COST_DOWN = np.array(P.c_down)  # 55, 50, 45
KEYS = np.array([0.1, 0.2, 0.3])


def test_short_partial_marginal():
    cl = clear(-50, COST_UP, COST_DOWN, KEYS, P)
    assert cl.direction == SHORT and cl.price == 75
    np.testing.assert_allclose(cl.q, [40, 10, 0])
    assert cl.marginal == 1 and not cl.scarcity
    st = settle(np.array([10, -5, 0]), -55, cl, P)
    np.testing.assert_allclose(st.bsp, [200, 0, 0])
    np.testing.assert_allclose(st.brp, [150, -75, 0])
    assert st.rest == pytest.approx(-825)


def test_short_exactly_one_block():
    cl = clear(-40, COST_UP, COST_DOWN, KEYS, P)
    assert cl.price == 70
    np.testing.assert_allclose(cl.q, [40, 0, 0])


def test_long_descending_down_bids():
    cl = clear(90, COST_UP, COST_DOWN, KEYS, P)
    assert cl.direction == LONG and cl.price == 45
    np.testing.assert_allclose(cl.q, [40, 40, 10])
    st = settle(np.zeros(3), 90, cl, P)
    np.testing.assert_allclose(st.bsp, [400, 200, 0])
    assert st.rest == pytest.approx(90 * (45 - 60))


def test_balanced_mid_price_and_band_edges():
    cl = clear(0.5, COST_UP, COST_DOWN, KEYS, P)
    assert cl.direction == BALANCED and cl.price == pytest.approx((70 + 55) / 2)
    np.testing.assert_allclose(settle(np.array([1, 2, 3]), 0, cl, P).bsp, 0)
    assert clear(-1.0, COST_UP, COST_DOWN, KEYS, P).direction == BALANCED
    assert clear(-1.01, COST_UP, COST_DOWN, KEYS, P).direction == SHORT


def test_scarcity_cap_and_floor():
    cl = clear(-130, COST_UP, COST_DOWN, KEYS, P)
    assert cl.scarcity and cl.price == P.price_cap
    np.testing.assert_allclose(cl.q, [40, 40, 40])
    cl = clear(130, COST_UP, COST_DOWN, KEYS, P)
    assert cl.scarcity and cl.price == P.price_floor
    np.testing.assert_allclose(settle(np.zeros(3), 130, cl, P).bsp, 40 * (COST_DOWN - P.price_floor))


def test_ties_use_tie_keys():
    up = np.array([300.0, 300.0, 300.0])
    cl = clear(-50, up, COST_DOWN, np.array([0.9, 0.1, 0.5]), P)
    np.testing.assert_allclose(cl.q, [0, 40, 10])
    assert cl.price == 300
    np.testing.assert_allclose(clear(-50, up, COST_DOWN, np.array([0.2, 0.3, 0.1]), P).q, [10, 0, 40])


def test_clamp_bids():
    u, v, clamped = clamp_bids(np.array([2000, 70, 80]), np.array([-500, 50, 45]), P)
    assert clamped
    np.testing.assert_allclose(u, [1000, 70, 80])
    np.testing.assert_allclose(v, [-200, 50, 45])
    assert not clamp_bids(COST_UP, COST_DOWN, P)[2]
