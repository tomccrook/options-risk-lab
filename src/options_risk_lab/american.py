"""QuantLib FD American put: constant carry, ACT365 rounded dates, pricing study only."""

import threading
from functools import lru_cache
from typing import Any

import numpy as np
import QuantLib as ql

REFERENCE_LOCK = threading.RLock()


def _option(
    m: float, t: float, v: float, r: float, q: float, mesh: int, binomial: bool = False
) -> Any:
    if not 0.1 <= m <= 3 or not 1 / 365 <= t <= 5 or not 0.01 <= v <= 1.5:
        raise ValueError("American pricing domain exceeded")
    date = ql.Date(4, 10, 2026)
    ql.Settings.instance().evaluationDate = date
    dc = ql.Actual365Fixed()
    expiry = date + max(1, round(t * 365))
    process = ql.BlackScholesMertonProcess(
        ql.QuoteHandle(ql.SimpleQuote(m * 100)),
        ql.YieldTermStructureHandle(ql.FlatForward(date, q, dc)),
        ql.YieldTermStructureHandle(ql.FlatForward(date, r, dc)),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(date, ql.NullCalendar(), v, dc)),
    )
    option = ql.VanillaOption(
        ql.PlainVanillaPayoff(ql.Option.Put, 100), ql.AmericanExercise(date, expiry)
    )
    engine = (
        ql.BinomialVanillaEngine(process, "crr", mesh)
        if binomial
        else ql.FdBlackScholesVanillaEngine(process, mesh, mesh, 2)
    )
    option.setPricingEngine(engine)
    return option


@lru_cache(maxsize=16384)
def reference(
    m: float, t: float, v: float, r: float, q: float, mesh: int = 512, bump: float = 0.001
) -> tuple[float, float, float, float]:
    with REFERENCE_LOCK:
        option = _option(m, t, v, r, q, mesh)
        price, delta, gamma = option.NPV(), option.delta(), option.gamma()
        up = _option(m, t, v + bump, r, q, mesh).NPV()
        down = _option(m, t, v - bump, r, q, mesh).NPV()
        return float(price), float(delta), float(gamma), float((up - down) / (2 * bump))


def convergence() -> dict[str, Any]:
    # Controls include exercise, continuation and expiry proximity; no trading lifecycle.
    probes = [
        (0.5, 1.0, 0.2, 0.05, 0.0),
        (0.8, 0.25, 0.2, 0.05, 0.0),
        (1.0, 1.0, 0.2, 0.05, 0.0),
        (1.1, 0.05, 0.3, 0.03, 0.01),
        (1.3, 2.0, 0.5, 0.08, 0.04),
    ]
    rows = []
    for x in probes:
        values = {str(n): reference(*x, n) for n in (128, 256, 512, 1024)}
        diff = np.abs(np.array(values["1024"]) - values["512"])
        with REFERENCE_LOCK:
            tree = _option(*x, 4096, True).NPV()
        h = 0.002
        up = reference(x[0] + h, *x[1:], 1024)[0]
        down = reference(x[0] - h, *x[1:], 1024)[0]
        center = values["1024"][0]
        delta_bump = (up - down) / (200 * h)
        gamma_bump = (up - 2 * center + down) / (100 * h) ** 2
        vega_half = reference(*x, 1024, bump=0.0005)[3]
        stable = (
            diff[0] < 0.01
            and diff[1] < 0.002
            and diff[2] < 0.0005
            and diff[3] < 0.2
            and abs(delta_bump - values["1024"][1]) < 0.005
            and abs(gamma_bump - values["1024"][2]) < 0.001
            and abs(vega_half - values["1024"][3]) < 0.2
            and abs(tree - center) < 0.04
        )
        rows.append(
            {
                "x": list(x),
                "meshes": values,
                "difference_512_1024": diff.tolist(),
                "tree_4096": tree,
                "delta_bump": delta_bump,
                "gamma_bump": gamma_bump,
                "vega_half_bump": vega_half,
                "eligible": bool(stable),
            }
        )
    return {
        "rows": rows,
        "passed": all(r["eligible"] for r in rows),
        "basis": "American put / constant continuous carry / dates rounded ACT365",
        "mesh": 512,
        "reference_mesh": 1024,
        "vol_bump": 0.001,
        "spot_bump": 0.2,
        "limitations": "Selected probes, not a proof of convergence over all inputs",
    }


def labels(x: np.ndarray, mesh: int = 512) -> np.ndarray:
    return np.array([reference(*row, mesh) for row in x], dtype=float)
