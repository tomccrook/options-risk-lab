"""Selected independent QuantLib checks; serial use because evaluation date is global."""

import QuantLib as ql

from .contracts import Greeks


def european(
    spot: float,
    strike: float,
    tau: float,
    vol: float,
    rate: float = 0.05,
    yield_: float = 0,
    kind: str = "call",
) -> Greeks:
    date = ql.Date(4, 10, 2026)
    ql.Settings.instance().evaluationDate = date
    dc = ql.Actual365Fixed()
    expiry = date + round(tau * 365)
    process = ql.BlackScholesMertonProcess(
        ql.QuoteHandle(ql.SimpleQuote(spot)),
        ql.YieldTermStructureHandle(ql.FlatForward(date, yield_, dc)),
        ql.YieldTermStructureHandle(ql.FlatForward(date, rate, dc)),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(date, ql.NullCalendar(), vol, dc)),
    )
    option = ql.VanillaOption(
        ql.PlainVanillaPayoff(ql.Option.Call if kind == "call" else ql.Option.Put, strike),
        ql.EuropeanExercise(expiry),
    )
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return Greeks(
        price=option.NPV(),
        delta=option.delta(),
        gamma=option.gamma(),
        vega=option.vega(),
        theta=option.theta(),
        rho=option.rho(),
        vanna=None,
        volga=None,
        quality="analytical",
    )
