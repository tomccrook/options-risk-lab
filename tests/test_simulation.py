import numpy as np
import pytest

from options_risk_lab.contracts import Book, Market, Option, Position
from options_risk_lab.ledger import Fill, Ledger
from options_risk_lab.pricing import bsm
from options_risk_lab.risk import preset
from options_risk_lab.simulation import ReplayConfig, simulate


def test_vector_replay_matches_independent_cash_fixture_b():
    m = Market(rate=0)
    b = Book(
        positions=(Position(instrument=Option(), quantity=-1),),
        shares=30,
        cash=10000 + 100 * bsm(100, 100, 1, 0.2, rate=0).price - 3000,
    )
    c = ReplayConfig(paths=1, steps=4, policy="none", share_half_spread=0, option_half_spread=0)
    result = simulate(b, m, c, (np.array([[100, 101, 105, 108, 110.0]]), np.full((1, 5), 0.2)))
    premium = bsm(100, 100, 1, 0.2, rate=0).price * 100
    assert result["raw_pnl"][0] == pytest.approx(premium + 300 - 1000)
    assert result["trace"][0]["nav"] == pytest.approx(10000)
    assert result["trace"][-1]["option_value"] == 0


def test_causal_prefix_and_paid_delayed_fills():
    m = Market(rate=0.03, yield_=0.02)
    b = preset("short-straddle", m, Option())
    c = ReplayConfig(
        paths=1,
        steps=4,
        policy="daily",
        delay_nodes=1,
        share_half_spread=0.1,
        option_half_spread=0,
        fee_per_trade=1,
    )
    a = np.array([[100.0, 102, 90, 85, 110]])
    d = a.copy()
    d[:, 3:] = 200
    r = simulate(b, m, c, (a, np.full_like(a, 0.2)))
    other = simulate(b, m, c, (d, np.full_like(d, 0.2)))
    assert r["trace"][:3] == other["trace"][:3]
    assert r["trace"][0]["fill"] == 0 and r["trace"][1]["fill"] != 0
    ledger = Ledger(b.cash)
    ledger.inventory["shares"] = b.shares
    ledger.multipliers["shares"] = 1
    for i, row in enumerate(r["trace"]):
        if i:
            ledger.accrue(0.25, m.rate, a[0, i - 1], m.yield_)
        if i == 4:
            payoff = sum(
                p.quantity
                * p.instrument.multiplier
                * max((1 if p.instrument.kind == "call" else -1) * (110 - p.instrument.strike), 0)
                for p in b.positions
            )
            ledger.cash += payoff
        if row["fill"]:
            quantity = row["fill"]
            execution = row["spot"] + np.sign(quantity) * 0.1
            ledger.trade(Fill("shares", quantity, execution, fee=1))
        assert ledger.cash == pytest.approx(row["cash"], abs=1e-8)
    assert r["financed_error"][0] == pytest.approx(r["raw_pnl"][0] - 10000 * np.expm1(0.03))


def test_zero_cost_frequency_convergence_paired_coarse_fine():
    m = Market(rate=0)
    b = preset("short-straddle", m, Option())
    rng = np.random.default_rng(912)
    z = rng.normal(size=(512, 256))
    path = 100 * np.exp(np.c_[np.zeros(512), np.cumsum(-(0.2**2) / 2 / 256 + 0.2 / 16 * z, axis=1)])
    fine = simulate(
        b,
        m,
        ReplayConfig(
            paths=512, steps=256, policy="daily", option_half_spread=0, share_half_spread=0
        ),
        (path, np.full_like(path, 0.2)),
    )
    coarse = simulate(
        b,
        m,
        ReplayConfig(
            paths=512, steps=16, policy="daily", option_half_spread=0, share_half_spread=0
        ),
        (path[:, ::16], np.full_like(path[:, ::16], 0.2)),
    )
    assert np.std(fine["financed_error"]) < np.std(coarse["financed_error"]) * 0.5


def test_surface_motion_and_inventory_constraints_are_explicit():
    from options_risk_lab.risk import Surface

    m = Market()
    b = preset("short-straddle", m, Option())
    c = ReplayConfig(paths=8, steps=12, policy="daily", max_shares=1, capital_limit=10000)
    constrained = simulate(b, m, c, surface=Surface(motion="sticky-log-moneyness"))
    assert sum(constrained["rejected_requests"]) > 0
    assert constrained["surface"]["motion"] == "sticky-log-moneyness"
    assert max(abs(r["shares"]) for r in constrained["trace"]) <= 1
