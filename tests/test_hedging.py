import numpy as np
import pytest

from options_risk_lab.contracts import Market, Option
from options_risk_lab.hedging import HedgeConstraints, compare, cvar
from options_risk_lab.risk import Shock, Surface, preset


def test_exact_weighted_cvar_fractional_tail():
    assert cvar(np.array([0, 10, 20]), np.array([0.5, 0.4, 0.1]), 0.8) == pytest.approx(15)
    assert cvar(np.array([1, 2, 3, 4]), alpha=0.625) == pytest.approx(11 / 3)
    with pytest.raises(ValueError):
        cvar(np.array([float("nan")]))


def test_integer_budget_feasibility_and_strong_baselines():
    m, o = Market(), Option()
    shocks = tuple(
        Shock(spot_return=s, vol_change=v, days=30)
        for s in (-0.2, 0, 0.2)
        for v in (-0.05, 0, 0.05)
    )
    limits = HedgeConstraints(cost_budget=100, capital_budget=8000, max_shares=100, max_options=2)
    out = compare(preset("delta-hedged-straddle", m, o), m, Surface(), o, shocks, limits)
    assert len(out["hedges"]) == 5
    best = out["hedges"][-1]
    assert best["status"] == "evaluated"
    assert best["cost"] <= 100 and best["capital"] <= 8000
    assert all(q == round(q) for q in best["quantities"])
    assert (
        best["cvar"]
        <= min(h["cvar"] for h in out["hedges"][:-1] if h["status"] == "evaluated") + 1e-8
    )
    assert best["cost"] == pytest.approx(
        best["financed_cost"] / (2 + np.expm1(0.05 * 30 / 365)) * 2
    )
    zero = compare(
        preset("short-straddle", m, o),
        m,
        Surface(),
        o,
        shocks,
        limits.model_copy(update={"cost_budget": 0, "capital_budget": 0}),
    )
    assert zero["hedges"][-1]["quantities"] == [0, 0, 0]
    assert zero["hedges"][1]["status"] == "infeasible"


def test_paid_static_result_reconciles_to_cash_ledger():
    from datetime import timedelta

    from options_risk_lab.ledger import Fill, Ledger
    from options_risk_lab.pricing import price
    from options_risk_lab.risk import assigned_market

    m, o = Market(rate=0.03, yield_=0.01), Option()
    b = preset("short-straddle", m, o)
    limits = HedgeConstraints()
    shocks = tuple(
        Shock(spot_return=s, vol_change=v, days=30)
        for s in (-0.2, 0, 0.2)
        for v in (-0.05, 0, 0.05)
    )
    out = compare(b, m, Surface(), o, shocks, limits)
    chosen = out["hedges"][-1]
    ledger = Ledger(b.cash)
    for p in b.positions:
        ledger.inventory[p.instrument.id] = p.quantity
        ledger.multipliers[p.instrument.id] = p.instrument.multiplier
    ledger.inventory["shares"] = b.shares
    ledger.multipliers["shares"] = 1
    for trade in chosen["trades"]:
        q = trade["quantity"]
        if q:
            half = (
                limits.share_half_spread if trade["id"] == "shares" else limits.option_half_spread
            )
            fee = 0 if trade["id"] == "shares" else abs(q) * limits.fee_per_contract
            ledger.trade(
                Fill(trade["id"], q, trade["mid"] + np.sign(q) * half, trade["multiplier"], fee)
            )
    shock = shocks[8]
    new = m.model_copy(
        update={"spot": 120, "valuation_time": m.valuation_time + timedelta(days=30)}
    )
    ledger.accrue(30 / 365, m.rate, m.spot, m.yield_)
    for trade in chosen["trades"]:
        q = trade["quantity"]
        if q:
            if trade["id"] == "shares":
                mid = new.spot
                half = limits.share_half_spread
                fee = 0
            else:
                from options_risk_lab.contracts import Option as OptionRecord

                instrument = OptionRecord.model_validate(trade["instrument"])
                mid = price(instrument, assigned_market(instrument, new, m, Surface(), shock)).price
                half = limits.option_half_spread
                fee = abs(q) * limits.fee_per_contract
            ledger.trade(Fill(trade["id"], -q, mid - np.sign(q) * half, trade["multiplier"], fee))
    marks = {
        p.instrument.id: price(
            p.instrument, assigned_market(p.instrument, new, m, Surface(), shock)
        ).price
        for p in b.positions
    }
    marks["shares"] = 120
    assert ledger.nav(marks) - 10000 * np.exp(0.03 * 30 / 365) == pytest.approx(
        chosen["pnl"][8], abs=1e-8
    )
