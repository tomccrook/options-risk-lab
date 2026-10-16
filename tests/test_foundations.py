import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_risk_lab.contracts import Book, Market, Option, Position
from options_risk_lab.ledger import Fill, Ledger
from options_risk_lab.pricing import bsm
from options_risk_lab.reference import european


def test_exact_analytic_and_independent_reference():
    c, p = bsm(100, 100, 1, 0.2), bsm(100, 100, 1, 0.2, kind="put")
    assert c.price == pytest.approx(10.4505835722, abs=5e-11)
    assert p.price == pytest.approx(5.5735260223, abs=5e-11)
    assert c.delta == pytest.approx(0.6368306512, abs=5e-11)
    assert c.gamma == pytest.approx(0.01876201735, abs=5e-12)
    assert c.vega == pytest.approx(37.5240346917, abs=5e-11)
    for kind in ("call", "put"):
        ours, ref = bsm(100, 100, 1, 0.2, kind=kind), european(100, 100, 1, 0.2, kind=kind)
        for key in ("price", "delta", "gamma", "vega", "theta", "rho"):
            assert getattr(ours, key) == pytest.approx(getattr(ref, key), abs=1e-10)


@given(
    s=st.floats(30, 200),
    k=st.floats(30, 200),
    t=st.floats(0.01, 3),
    v=st.floats(0.03, 0.8),
    r=st.floats(-0.03, 0.15),
    q=st.floats(0, 0.08),
)
def test_parity_bounds_relationships(s, k, t, v, r, q):
    c, p = bsm(s, k, t, v, r, q), bsm(s, k, t, v, r, q, "put")
    forward_diff = s * math.exp(-q * t) - k * math.exp(-r * t)
    assert c.price - p.price == pytest.approx(forward_diff, abs=1e-10)
    assert c.gamma == p.gamma and c.vega == p.vega
    assert c.delta - p.delta == pytest.approx(math.exp(-q * t), abs=1e-12)
    assert -1e-12 <= c.price <= s * math.exp(-q * t) + 1e-12
    assert c.price >= max(forward_diff, 0) - 1e-12


def test_bumps_higher_derivatives_and_theta():
    g = bsm(103, 100, 0.7, 0.24, 0.03, 0.01)

    def f(s=103, t=0.7, v=0.24, r=0.03):
        return bsm(s, 100, t, v, r, 0.01).price

    h = 0.01
    assert (f(103 + h) - f(103 - h)) / (2 * h) == pytest.approx(g.delta, abs=2e-8)
    assert (f(103 + h) - 2 * f() + f(103 - h)) / h**2 == pytest.approx(g.gamma, abs=2e-8)
    e = 1e-4
    assert (f(v=0.24 + e) - f(v=0.24 - e)) / (2 * e) == pytest.approx(g.vega, abs=2e-6)
    assert (f(t=0.7 - e) - f(t=0.7 + e)) / (2 * e) == pytest.approx(g.theta, abs=1e-7)
    assert (f(v=0.24 + e) - 2 * f() + f(v=0.24 - e)) / e**2 == pytest.approx(g.volga, abs=1e-5)
    mixed = (
        f(103 + h, v=0.24 + e)
        - f(103 + h, v=0.24 - e)
        - f(103 - h, v=0.24 + e)
        + f(103 - h, v=0.24 - e)
    ) / (4 * h * e)
    assert mixed == pytest.approx(g.vanna, abs=2e-7)


def test_boundaries_and_contract_validation():
    assert bsm(100, 100, 0, 0.2).delta is None
    assert bsm(110, 100, 0, 0.2).price == 10
    assert bsm(100, 100, 1, 0).price == pytest.approx(100 - 100 * math.exp(-0.05))
    assert math.isfinite(bsm(100, 100, 1e-12, 0.2).gamma)
    for s in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            bsm(s, 100, 1, 0.2)
    with pytest.raises(ValueError):
        Market(spot=0)
    with pytest.raises(ValueError):
        Option(style="american")
    p = Position(instrument=Option(), quantity=-1)
    with pytest.raises(ValueError):
        Book(positions=(p, p))


def test_cash_fixture_a():
    ledger = Ledger(1000)
    ledger.trade(Fill("option", 1, 5.2, 10))
    assert ledger.cash == 948 and ledger.nav({"option": 5}) == 998
    assert ledger.nav({"option": 6}) == 1008
    ledger.trade(Fill("option", -1, 5.8, 10))
    assert ledger.cash == 1006


def test_cash_fixture_b_liability_not_profit():
    ledger = Ledger(10000)
    ledger.trade(Fill("call", -1, 6, 100))
    ledger.trade(Fill("shares", 30, 100))
    assert ledger.cash == 7600 and ledger.nav({"call": 6, "shares": 100}) == 10000
    ledger.trade(Fill("shares", -30, 110))
    ledger.settle("call", 10)
    assert ledger.cash == 9900


def test_fees_funding_dividends_roll_and_missing_marks():
    ledger = Ledger(1000)
    ledger.trade(Fill("shares", -2, 100, fee=1))
    assert ledger.cash == 1199
    flows = ledger.accrue(1, 0.05, 100, 0.02)
    assert flows["dividend"] == pytest.approx(-200 * math.expm1(0.02))
    assert flows["funding"] == pytest.approx(1199 * math.expm1(0.05))
    with pytest.raises(KeyError):
        ledger.nav({})
    ledger.trade(Fill("old", 1, 5, 10))
    ledger.trade(Fill("old", -1, 6, 10))
    ledger.trade(Fill("new", 1, 7, 10))
    assert ledger.inventory["old"] == 0 and ledger.inventory["new"] == 1


def test_quantlib_reference_grid_carry_and_signed_rates():
    for s in (70, 100, 140):
        for t in (90 / 365, 1, 2):
            for r in (-0.01, 0.05):
                for kind in ("call", "put"):
                    ours = bsm(s, 100, t, 0.3, r, 0.02, kind)
                    ref = european(s, 100, t, 0.3, r, 0.02, kind)
                    for k in ("price", "delta", "gamma", "vega", "theta", "rho"):
                        assert getattr(ours, k) == pytest.approx(getattr(ref, k), abs=1e-10)


def test_long_dividends_and_exact_scheduled_roll_with_fees():
    long = Ledger(1000)
    long.trade(Fill("shares", 2, 100))
    flows = long.accrue(1, 0.05, 100, 0.02)
    assert flows["dividend"] == pytest.approx(200 * math.expm1(0.02))
    assert long.cash == pytest.approx(800 * math.exp(0.05) + 200 * math.expm1(0.02))
    rolled = Ledger(1000)
    rolled.trade(Fill("old", 1, 5.2, 10, fee=1))
    rolled.trade(Fill("old", -1, 5.8, 10, fee=1))
    rolled.trade(Fill("new", 1, 7.2, 10, fee=1))
    assert rolled.cash == 931
    assert rolled.nav({"new": 7}) == 1001
    rolled.settle("new", 8)
    assert rolled.cash == 1011  # old +6, new +8, fees -3; spreads already in fills
