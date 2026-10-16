"""Signed partial risk, explicit surface motion and full option-book repricing."""

import math
from datetime import timedelta
from typing import Any, Literal

from pydantic import Field

from .contracts import Book, Market, Option, Position, Record
from .pricing import price


class Surface(Record):
    motion: Literal["flat", "frozen-strike", "sticky-log-moneyness"] = "flat"
    skew: float = Field(default=-0.12, ge=-0.5, le=0.5)
    term: float = Field(default=0.015, ge=-0.1, le=0.1)

    def assigned(
        self,
        option: Option,
        current: Market,
        anchor: Market,
        level: float = 0,
        skew_shock: float = 0,
        term_shock: float = 0,
    ) -> float:
        if self.motion == "flat":
            result = anchor.vol + level
        else:
            # Frozen convention rolls tau but freezes k at the anchor forward.
            state = anchor if self.motion == "frozen-strike" else current
            forward = state.spot * math.exp((state.rate - state.yield_) * option.tau(state))
            k = math.log(option.strike / forward)
            result = anchor.vol + level + (self.skew + skew_shock) * k
            result += (self.term + term_shock) * (option.tau(current) - 1)
        if not 0.005 <= result <= 2:
            raise ValueError("invalid synthetic surface region: IV outside [0.005,2]")
        return result


class Shock(Record):
    spot_return: float = Field(default=0, gt=-1, le=2)
    vol_change: float = Field(default=0, ge=-1, le=1)
    days: float = Field(default=0, ge=0, le=730)
    skew_change: float = Field(default=0, ge=-0.5, le=0.5)
    term_change: float = Field(default=0, ge=-0.1, le=0.1)
    weight: float = Field(default=1, gt=0)


DEFAULT_SHOCK = Shock()
DEFAULT_SURFACE = Surface()


def assigned_market(
    option: Option, state: Market, anchor: Market, surface: Surface, shock: Shock = DEFAULT_SHOCK
) -> Market:
    vol = surface.assigned(
        option, state, anchor, shock.vol_change, shock.skew_change, shock.term_change
    )
    return Market(**(state.model_dump() | {"vol": vol}))


def exposures(book: Book, market: Market, surface: Surface = DEFAULT_SURFACE) -> dict[str, Any]:
    keys = ("price", "delta", "gamma", "vega", "theta", "vanna", "volga")
    net = {k: 0.0 for k in keys}
    gross = {k: 0.0 for k in keys}
    rows = []
    undefined = []
    for p in book.positions:
        g = price(p.instrument, assigned_market(p.instrument, market, market, surface))
        row: dict[str, Any] = {
            "id": p.instrument.id,
            "quantity": p.quantity,
            "multiplier": p.instrument.multiplier,
            "kind": p.instrument.kind,
            "strike": p.instrument.strike,
            "days": p.instrument.tau(market) * 365,
            "assigned_iv": surface.assigned(p.instrument, market, market),
            "quality": g.quality,
        }
        for k in keys:
            val = getattr(g, k)
            row[k] = None if val is None else p.quantity * p.instrument.multiplier * val
            if val is None:
                undefined.append(k)
            else:
                net[k] += row[k]
                gross[k] += abs(row[k])
        rows.append(row)
    net["delta"] += book.shares
    gross["delta"] += abs(book.shares)
    # Total spot derivative includes surface rule, anchored to today's surface.
    bump = market.spot * 1e-4
    up = book_option_value(
        book, market.model_copy(update={"spot": market.spot + bump}), market, surface
    )
    down = book_option_value(
        book, market.model_copy(update={"spot": market.spot - bump}), market, surface
    )
    total_delta = (up - down) / (2 * bump) + book.shares
    return {
        "net": {k: None if k in undefined else v for k, v in net.items()},
        "gross": gross,
        "positions": rows,
        "shares": book.shares,
        "cash": book.cash,
        "nav": book.cash + book.shares * market.spot + net["price"],
        "vega_per_vol_point": net["vega"] * 0.01,
        "return_scale_gamma": net["gamma"] * market.spot**2,
        "total_surface_delta": total_delta,
        "partial_basis": "assigned IV held fixed",
        "quality": "undefined-boundary" if undefined else "analytical",
    }


def book_option_value(
    book: Book, state: Market, anchor: Market, surface: Surface, shock: Shock = DEFAULT_SHOCK
) -> float:
    return sum(
        p.quantity
        * p.instrument.multiplier
        * price(p.instrument, assigned_market(p.instrument, state, anchor, surface, shock)).price
        for p in book.positions
    )


def scenario(book: Book, market: Market, shock: Shock, surface: Surface) -> dict[str, Any]:
    state = Market(
        **(
            market.model_dump()
            | {
                "spot": market.spot * (1 + shock.spot_return),
                "valuation_time": market.valuation_time + timedelta(days=shock.days),
            }
        )
    )
    if any(state.valuation_time > p.instrument.expiry for p in book.positions):
        raise ValueError(
            "Scenario crosses expiry: settlement spot/path is required; shorten the horizon"
        )
    full = book_option_value(book, state, market, surface, shock) - book_option_value(
        book, market, market, surface
    )
    ds = state.spot - market.spot
    approximation = 0.0
    terms = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "vanna": 0.0, "volga": 0.0}
    valid = True
    for p in book.positions:
        base = assigned_market(p.instrument, market, market, surface)
        target = assigned_market(p.instrument, state, market, surface, shock)
        dv = target.vol - base.vol
        g = price(p.instrument, base)
        if any(getattr(g, k) is None for k in terms):
            valid = False
            continue
        assert g.delta is not None and g.gamma is not None and g.vega is not None
        assert g.theta is not None and g.vanna is not None and g.volga is not None
        scale = p.quantity * p.instrument.multiplier
        components = {
            "delta": g.delta * ds,
            "gamma": 0.5 * g.gamma * ds**2,
            "vega": g.vega * dv,
            "theta": g.theta * shock.days / 365,
            "vanna": g.vanna * ds * dv,
            "volga": 0.5 * g.volga * dv**2,
        }
        for k, v in components.items():
            terms[k] += scale * v
        approximation += scale * sum(components.values())
    shares = book.shares * ds
    return {
        "shock": shock.model_dump(),
        "spot": state.spot,
        "option_change": full,
        "share_change": shares,
        "full_change": full + shares,
        "approximation": approximation + shares if valid else None,
        "residual": full - approximation if valid else None,
        "terms": terms,
        "quality": "analytical" if valid else "undefined-boundary",
        "basis": "unfinanced mark change; omitted rate/carry/time cross terms",
    }


def preset(name: str, market: Market, option: Option, surface: Surface = DEFAULT_SURFACE) -> Book:
    def position(
        id_: str, kind: str, quantity: float, strike: float | None = None, days: float | None = None
    ) -> Position:
        o = option.model_copy(update={"id": id_, "kind": kind, "strike": strike or option.strike})
        if days is not None:
            o = o.model_copy(update={"expiry": market.valuation_time + timedelta(days=days)})
        return Position(instrument=o, quantity=quantity)

    call = position("call", "call", 1)
    put = position("put", "put", 1)
    cases = {
        "long-call": (call,),
        "long-put": (put,),
        "long-straddle": (call, put),
        "short-straddle": (
            call.model_copy(update={"quantity": -1}),
            put.model_copy(update={"quantity": -1}),
        ),
        "delta-hedged-straddle": (
            call.model_copy(update={"quantity": -1}),
            put.model_copy(update={"quantity": -1}),
        ),
        "call-vertical": (call, position("call-upper", "call", -1, option.strike * 1.1)),
        "put-vertical": (put, position("put-lower", "put", -1, option.strike * 0.9)),
        "calendar": (position("near", "call", -1, days=90), position("far", "call", 1, days=365)),
    }
    if name == "locally-matched":
        import numpy as np

        from .hedging import candidates

        source = Book(positions=cases["short-straddle"])
        hedge_options = candidates(option, market)
        target = exposures(source, market, surface)["net"]
        g = np.array(
            [
                [
                    getattr(price(o, assigned_market(o, market, market, surface)), key)
                    * o.multiplier
                    for o in hedge_options
                ]
                for key in ("gamma", "vega")
            ]
        )
        if np.linalg.cond(g) > 1e8:
            raise ValueError("locally matched control is ill-conditioned")
        amounts = np.linalg.solve(g, -np.array([target["gamma"], target["vega"]]))
        book = Book(
            positions=source.positions
            + tuple(
                Position(instrument=o, quantity=float(q))
                for o, q in zip(hedge_options, amounts, strict=True)
            )
        )
        delta = exposures(book, market, surface)["net"]["delta"]
        shares = -delta
        value = book_option_value(book, market, market, surface)
        return book.model_copy(
            update={"shares": shares, "cash": 10000 - value - shares * market.spot}
        )
    if name not in cases:
        raise ValueError("unknown synthetic case")
    book = Book(positions=cases[name])
    shares = (
        round(-exposures(book, market, surface)["net"]["delta"])
        if name == "delta-hedged-straddle"
        else 0
    )
    value = book_option_value(book, market, market, surface)
    return book.model_copy(update={"shares": shares, "cash": 10000 - value - shares * market.spot})


def surface_diagnostics(
    option: Option, market: Market, anchor: Market, surface: Surface, shock: Shock = DEFAULT_SHOCK
) -> dict[str, Any]:
    """Necessary sampled European price checks; never advertised as arbitrage-free calibration."""
    import numpy as np

    strikes = np.linspace(0.65 * market.spot, 1.45 * market.spot, 81)
    prices = []
    for strike in strikes:
        o = option.model_copy(update={"strike": float(strike), "kind": "call"})
        prices.append(price(o, assigned_market(o, market, anchor, surface, shock)).price)
    values = np.array(prices)
    increasing = np.diff(values) > 1e-7
    nonconvex = np.diff(values, n=2) < -1e-6
    return {
        "passed": bool(not increasing.any() and not nonconvex.any()),
        "increasing_strike_cells": int(increasing.sum()),
        "nonconvex_strike_cells": int(nonconvex.sum()),
        "strikes": 81,
        "region": "0.65–1.45 × current spot, declared expiry",
        "basis": "Necessary sampled price conditions, not sufficient arbitrage proof",
    }
