from datetime import timedelta

import pytest

from options_risk_lab.contracts import Book, Market, Option, Position
from options_risk_lab.risk import Shock, Surface, exposures, preset, scenario


def test_signed_gross_units_and_delta_hedge():
    market = Market()
    p = Position(instrument=Option(), quantity=-2)
    risk = exposures(Book(positions=(p,)), market)
    assert risk["net"]["price"] == pytest.approx(-2090.11671444)
    assert risk["vega_per_vol_point"] == pytest.approx(-75.04806938)
    book = preset("delta-hedged-straddle", market, Option())
    e = exposures(book, market)
    assert abs(e["net"]["delta"]) <= 0.5
    assert e["net"]["gamma"] < 0 and e["gross"]["delta"] > 50
    assert e["nav"] == pytest.approx(10000)


def test_small_and_large_shock_residual_and_roll():
    market = Market()
    book = preset("delta-hedged-straddle", market, Option())
    small = scenario(book, market, Shock(spot_return=0.0001, vol_change=0.00001), Surface())
    assert abs(small["residual"]) < 1e-5
    large = scenario(book, market, Shock(spot_return=0.2, vol_change=0.05, days=30), Surface())
    assert abs(large["residual"]) > 10
    assert large["full_change"] == pytest.approx(large["option_change"] + large["share_change"])
    expired = scenario(book, market, Shock(spot_return=0.1, days=365), Surface())
    assert expired["option_change"] + exposures(book, market)["net"]["price"] == pytest.approx(
        -1000
    )


def test_surface_mappings_and_total_delta():
    m = Market()
    o = Option()
    target = m.model_copy(
        update={"spot": 120, "valuation_time": m.valuation_time + timedelta(days=30)}
    )
    frozen, sticky = Surface(motion="frozen-strike"), Surface(motion="sticky-log-moneyness")
    assert frozen.assigned(o, target, m) != sticky.assigned(o, target, m)
    book = Book(positions=(Position(instrument=o),))
    e = exposures(book, m, sticky)
    assert abs(e["total_surface_delta"] - e["net"]["delta"]) > 1
    with pytest.raises(ValueError):
        scenario(book, m, Shock(vol_change=-0.3), frozen)


def test_locally_matched_control_keeps_nonlocal_risk():
    m = Market()
    book = preset("locally-matched", m, Option())
    e = exposures(book, m)
    assert max(abs(e["net"][k]) for k in ("delta", "gamma", "vega")) < 1e-8
    shock = scenario(book, m, Shock(spot_return=0.3, vol_change=0.08, days=60), Surface())
    assert abs(shock["full_change"]) > 10


def test_static_horizon_after_expiry_requires_real_settlement_state():
    with pytest.raises(ValueError, match="crosses expiry"):
        scenario(preset("short-straddle", Market(), Option()), Market(), Shock(days=366), Surface())
