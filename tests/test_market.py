import numpy as np
import pytest

from desks.config import MarketParams
from desks.market import BALANCED, LONG, SHORT, benchmark, bid_markup, clamp_bids, clear, settle

P = MarketParams()
COST_UP = np.array(P.c_up)
COST_DOWN = np.array(P.c_down)
ALL = np.ones(3, bool)
KEYS = np.array([0.1, 0.2, 0.3])


def test_short_partial_marginal():
    cl = clear(-50, COST_UP, COST_DOWN, 40, ALL, KEYS, P)
    assert cl.direction == SHORT
    assert cl.price == 75
    np.testing.assert_allclose(cl.q, [40, 10, 0])
    assert cl.marginal == 1 and not cl.scarcity
    st = settle(np.array([10, -5, 0]), -55, cl, COST_UP, COST_DOWN, 60)
    np.testing.assert_allclose(st.bsp, [200, 0, 0])
    np.testing.assert_allclose(st.brp, [150, -75, 0])
    assert st.rest == pytest.approx(-825)


def test_short_exactly_one_block():
    cl = clear(-40, COST_UP, COST_DOWN, 40, ALL, KEYS, P)
    assert cl.price == 70
    np.testing.assert_allclose(cl.q, [40, 0, 0])


def test_long_descending_down_bids():
    cl = clear(90, COST_UP, COST_DOWN, 40, ALL, KEYS, P)
    assert cl.direction == LONG
    assert cl.price == 45
    np.testing.assert_allclose(cl.q, [40, 40, 10])
    st = settle(np.zeros(3), 90, cl, COST_UP, COST_DOWN, 60)
    np.testing.assert_allclose(st.bsp, [400, 200, 0])
    assert st.rest == pytest.approx(90 * (45 - 60))


def test_balanced_mid_price():
    cl = clear(0.5, COST_UP, COST_DOWN, 40, ALL, KEYS, P)
    assert cl.direction == BALANCED
    assert cl.price == pytest.approx((70 + 55) / 2)
    np.testing.assert_allclose(cl.q, 0)
    st = settle(np.array([1, 2, 3]), 0, cl, COST_UP, COST_DOWN, 60)
    np.testing.assert_allclose(st.bsp, 0)


def test_balanced_band_edges():
    assert clear(-1.0, COST_UP, COST_DOWN, 40, ALL, KEYS, P).direction == BALANCED
    assert clear(-1.01, COST_UP, COST_DOWN, 40, ALL, KEYS, P).direction == SHORT


def test_scarcity_cap_and_floor():
    cl = clear(-130, COST_UP, COST_DOWN, 40, ALL, KEYS, P)
    assert cl.scarcity and cl.price == P.price_cap
    np.testing.assert_allclose(cl.q, [40, 40, 40])
    cl = clear(130, COST_UP, COST_DOWN, 40, ALL, KEYS, P)
    assert cl.scarcity and cl.price == P.price_floor
    st = settle(np.zeros(3), 130, cl, COST_UP, COST_DOWN, 60)
    np.testing.assert_allclose(st.bsp, 40 * (COST_DOWN - P.price_floor))


def test_ties_use_tie_keys():
    up = np.array([300.0, 300.0, 300.0])
    cl = clear(-50, up, COST_DOWN, 40, ALL, np.array([0.9, 0.1, 0.5]), P)
    np.testing.assert_allclose(cl.q, [0, 40, 10])
    assert cl.price == 300
    cl = clear(-50, up, COST_DOWN, 40, ALL, np.array([0.2, 0.3, 0.1]), P)
    np.testing.assert_allclose(cl.q, [10, 0, 40])


def test_suspension_excludes_bsp():
    elig = np.array([False, True, True])
    cl = clear(-50, COST_UP, COST_DOWN, 40, elig, KEYS, P)
    np.testing.assert_allclose(cl.q, [0, 40, 10])
    assert cl.price == 80
    # suspended BSP excluded from the mid-price too
    cl = clear(0, COST_UP, COST_DOWN, 40, elig, KEYS, P)
    assert cl.price == pytest.approx((75 + 50) / 2)
    # suspended capacity counts as missing: 80 MW available
    cl = clear(-100, COST_UP, COST_DOWN, 40, elig, KEYS, P)
    assert cl.scarcity and cl.price == P.price_cap


def test_no_eligible_bsps():
    none = np.zeros(3, bool)
    assert clear(-10, COST_UP, COST_DOWN, 40, none, KEYS, P).price == P.price_cap
    assert clear(0, COST_UP, COST_DOWN, 40, none, KEYS, P).price == P.lam


def test_clamp_bids():
    u, v, clamped = clamp_bids(np.array([2000, 70, 80]), np.array([-500, 50, 45]), P)
    assert clamped
    np.testing.assert_allclose(u, [1000, 70, 80])
    np.testing.assert_allclose(v, [-200, 50, 45])
    _, _, clamped = clamp_bids(COST_UP, COST_DOWN, P)
    assert not clamped


def test_benchmark_uses_cost_bids_and_zero_deviation():
    e = np.array([-10.0, -5.0, 0.0])
    S, cl, st = benchmark(e, -40.0, KEYS, P)
    assert S == pytest.approx(-55)
    assert cl.price == 75
    np.testing.assert_allclose(st.brp, e * 15)


def test_bid_markup():
    assert bid_markup(105, 27.5, 70, 55, SHORT) == pytest.approx(0.5)
    assert bid_markup(105, 27.5, 70, 55, LONG) == pytest.approx(0.5)
    assert bid_markup(70, 0, 70, 50, BALANCED) == pytest.approx(1.0)
    assert bid_markup(70, 55, 70, 55, SHORT) == 0
