"""Independent BSM implementation; QuantLib only appears in reference.py."""

import math

import numpy as np
from scipy.special import ndtr

from .contracts import Greeks, Market, Option


def bsm(
    spot: float,
    strike: float,
    tau: float,
    vol: float,
    rate: float = 0.05,
    yield_: float = 0,
    kind: str = "call",
) -> Greeks:
    if not all(math.isfinite(v) for v in (spot, strike, tau, vol, rate, yield_)):
        raise ValueError("nonfinite pricing input")
    if spot <= 0 or strike <= 0 or tau < 0 or vol < 0 or tau > 50:
        raise ValueError("invalid pricing domain")
    if kind not in ("call", "put"):
        raise ValueError("unsupported option kind")
    sign = 1 if kind == "call" else -1
    dq, dr = math.exp(-yield_ * tau), math.exp(-rate * tau)
    a, b = spot * dq, strike * dr
    if tau == 0 or vol == 0:
        x = a - b
        kink = abs(x) <= 1e-12 * max(a, b)
        itm = sign * x > 0
        return Greeks(
            price=max(sign * x, 0),
            delta=None if kink else sign * dq * itm,
            gamma=None if kink else 0,
            vega=None if kink else 0,
            theta=None if kink or tau == 0 else sign * (yield_ * a - rate * b) * itm,
            rho=None if kink else sign * tau * b * itm,
            vanna=None if kink else 0,
            volga=None if kink else 0,
            quality="undefined-kink" if kink else ("expiry" if tau == 0 else "deterministic-limit"),
        )
    root = math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - yield_ + vol * vol / 2) * tau) / (vol * root)
    d2 = d1 - vol * root
    n1, n2 = float(ndtr(sign * d1)), float(ndtr(sign * d2))
    phi = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    vega = a * phi * root
    return Greeks(
        price=sign * (a * n1 - b * n2),
        delta=sign * dq * n1,
        gamma=dq * phi / (spot * vol * root),
        vega=vega,
        theta=-a * phi * vol / (2 * root) + sign * (yield_ * a * n1 - rate * b * n2),
        rho=sign * tau * b * n2,
        vanna=-dq * phi * d2 / vol,
        volga=vega * d1 * d2 / vol,
        quality="analytical",
    )


def price(option: Option, market: Market) -> Greeks:
    return bsm(
        market.spot,
        option.strike,
        option.tau(market),
        market.vol,
        market.rate,
        market.yield_,
        option.kind,
    )


def _validate_vector_inputs(x: np.ndarray) -> None:
    if x.ndim != 2 or x.shape[1] != 5:
        raise ValueError("vector control requires a matrix with five columns: m, tau, sigma, r, q")
    if not np.isfinite(x).all():
        raise ValueError("vector control requires finite inputs")
    m, t, v = x[:, :3].T
    if np.any(m <= 0) or np.any(t <= 0) or np.any(v <= 0):
        raise ValueError("vector control requires positive m, tau and sigma")


def vector_price(x: np.ndarray, kind: str = "put") -> np.ndarray:
    """Vectorized analytical ML control: columns m, tau, sigma, r, q; returns P/K."""
    if kind not in ("call", "put"):
        raise ValueError("unsupported option kind")
    _validate_vector_inputs(x)
    m, t, v, r, q = x.T
    d1 = (np.log(m) + (r - q + v * v / 2) * t) / (v * np.sqrt(t))
    d2 = d1 - v * np.sqrt(t)
    sign = 1 if kind == "call" else -1
    return sign * (m * np.exp(-q * t) * ndtr(sign * d1) - np.exp(-r * t) * ndtr(sign * d2))


def batch_price_delta(
    spot: np.ndarray,
    strike: float,
    tau: float,
    vol: np.ndarray,
    rate: float,
    yield_: float,
    kind: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Same analytical BSM, vector path workload; expiry delta excluded from policies."""
    if tau <= 0:
        sign = 1 if kind == "call" else -1
        payoff = np.maximum(sign * (spot - strike), 0)
        return payoff, np.where(sign * (spot - strike) > 0, sign, 0.0)
    if np.any(vol <= 0) or np.any(spot <= 0):
        raise ValueError("batched simulation requires positive IV and spot")
    d1 = (np.log(spot / strike) + (rate - yield_ + vol * vol / 2) * tau) / (vol * np.sqrt(tau))
    d2 = d1 - vol * np.sqrt(tau)
    sign = 1 if kind == "call" else -1
    n1 = ndtr(sign * d1)
    mark = sign * (
        spot * np.exp(-yield_ * tau) * n1 - strike * np.exp(-rate * tau) * ndtr(sign * d2)
    )
    return mark, sign * np.exp(-yield_ * tau) * n1


def vector_price_greeks(x: np.ndarray) -> np.ndarray:
    """European put batch control: USD price/delta/gamma/decimal vega at K=100."""
    _validate_vector_inputs(x)
    m, t, v, r, q = x.T
    d1 = (np.log(m) + (r - q + v * v / 2) * t) / (v * np.sqrt(t))
    phi = np.exp(-d1 * d1 / 2) / np.sqrt(2 * np.pi)
    return np.c_[
        vector_price(x) * 100,
        -np.exp(-q * t) * ndtr(-d1),
        np.exp(-q * t) * phi / (100 * m * v * np.sqrt(t)),
        100 * m * np.exp(-q * t) * phi * np.sqrt(t),
    ]
