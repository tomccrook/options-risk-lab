"""European model risk: exact Merton mixture and independently checked Heston CF.

Monte Carlo is an engine, not a competing asset model. Rates/carry are continuous,
parameters risk-neutral/synthetic. Heston vega0 bumps sqrt(initial variance),
not an implied surface or every model parameter simultaneously.
"""

import math
from functools import lru_cache
from typing import Literal

import numpy as np
import QuantLib as ql
from pydantic import Field
from scipy.optimize import brentq
from scipy.special import roots_legendre
from scipy.stats import poisson

from .contracts import Record
from .pricing import batch_price_delta, bsm

Model = Literal["bsm", "merton", "heston"]


class ModelParameters(Record):
    diffusion_vol: float = Field(default=0.2, gt=0, le=0.8)
    intensity: float = Field(default=0.4, ge=0, le=3)
    jump_mean: float = Field(default=-0.08, ge=-0.4, le=0.4)
    jump_std: float = Field(default=0.12, ge=0, le=0.5)
    v0: float = Field(default=0.04, gt=0, le=0.64)
    kappa: float = Field(default=2, ge=0.25, le=8)
    theta: float = Field(default=0.04, gt=0, le=0.64)
    vol_of_vol: float = Field(default=0.4, ge=0, le=1)
    rho: float = Field(default=-0.7, ge=-0.95, le=0.95)

    @property
    def compensator(self) -> float:
        return math.expm1(self.jump_mean + self.jump_std**2 / 2)


class ModelPoint(Record):
    spot: float = Field(default=100, ge=25, le=250)
    strike: float = Field(default=100, ge=25, le=250)
    tau: float = Field(default=1, ge=1 / 365, le=3)
    rate: float = Field(default=0.05, ge=-0.05, le=0.2)
    yield_: float = Field(default=0, ge=0, le=0.1)
    kind: Literal["call", "put"] = "call"
    parameters: ModelParameters = ModelParameters()


def merton_batch(
    spot: np.ndarray,
    strike: float,
    tau: float,
    p: ModelParameters,
    rate: float,
    yield_: float,
    kind: str = "call",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if tau <= 0:
        mark, delta = batch_price_delta(spot, strike, 0, np.ones_like(spot), rate, yield_, kind)
        return mark, delta, np.zeros_like(spot), np.zeros_like(spot)
    # Stock-numeraire Poisson weights; rate correction retains r-discounted mixture.
    mean = p.intensity * (1 + p.compensator) * tau
    count = max(1, int(poisson.ppf(1 - 1e-14, mean)) + 1) if mean else 1
    prices, deltas, gammas, vegas = (np.zeros_like(spot, dtype=float) for _ in range(4))
    for n in range(count):
        weight = float(poisson.pmf(n, mean)) if mean else 1.0
        vol = math.sqrt(p.diffusion_vol**2 + n * p.jump_std**2 / tau)
        adjusted_rate = (
            rate - p.intensity * p.compensator + n * (p.jump_mean + p.jump_std**2 / 2) / tau
        )
        mark, delta = batch_price_delta(
            spot, strike, tau, np.full_like(spot, vol), adjusted_rate, yield_, kind
        )
        d1 = (np.log(spot / strike) + (adjusted_rate - yield_ + vol**2 / 2) * tau) / (
            vol * math.sqrt(tau)
        )
        phi = np.exp(-(d1**2) / 2) / math.sqrt(2 * math.pi)
        prices += weight * mark
        deltas += weight * delta
        gammas += weight * math.exp(-yield_ * tau) * phi / (spot * vol * math.sqrt(tau))
        vegas += (
            weight * spot * math.exp(-yield_ * tau) * phi * math.sqrt(tau) * (p.diffusion_vol / vol)
        )
    return prices, deltas, gammas, vegas


@lru_cache(maxsize=8)
def quadrature(order: int) -> tuple[np.ndarray, np.ndarray]:
    # Composite Gaussian integration resolves low-frequency behaviour and long tails.
    x, w = roots_legendre(order)
    edges = (0, 1, 5, 20, 60, 150, 400, 1000, 2500)
    nodes = np.concatenate(
        [(x + 1) * (b - a) / 2 + a for a, b in zip(edges[:-1], edges[1:], strict=True)]
    )
    weights = np.concatenate([w * (b - a) / 2 for a, b in zip(edges[:-1], edges[1:], strict=True)])
    return nodes, weights


def heston_cf(
    u: np.ndarray, tau: float, variance: np.ndarray, p: ModelParameters
) -> tuple[np.ndarray, np.ndarray]:
    """Little-trap affine CF of log-return minus carry, and its variance coefficient."""
    if p.vol_of_vol == 0:
        integrated = p.theta * tau + (variance - p.theta) * (-math.expm1(-p.kappa * tau)) / p.kappa
        d = -0.5 * (u * u + 1j * u) * (-math.expm1(-p.kappa * tau)) / p.kappa
        return np.exp(-0.5 * (u * u + 1j * u) * integrated), d
    xi = p.vol_of_vol
    beta = p.kappa - p.rho * xi * 1j * u
    d = np.sqrt(beta * beta + xi * xi * (u * u + 1j * u))
    g = (beta - d) / (beta + d)
    decay = np.exp(-d * tau)
    c = p.kappa * p.theta / xi**2 * ((beta - d) * tau - 2 * np.log((1 - g * decay) / (1 - g)))
    coefficient = (beta - d) / xi**2 * (1 - decay) / (1 - g * decay)
    return np.exp(c + coefficient * variance), coefficient


def fourier_batch(
    spot: np.ndarray,
    strike: float,
    tau: float,
    p: ModelParameters,
    rate: float,
    yield_: float,
    model: Model,
    variance: np.ndarray | None = None,
    kind: str = "call",
    order: int = 32,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Lewis CF inversion with analytical BSM control; analytic spot derivatives.

    Heston fourth output is dV/d(current variance). Merton fourth output unavailable
    here (zero); mixture supplies diffusion vega. No clipping of prices/derivatives.
    """
    if tau <= 0:
        mark, delta = batch_price_delta(spot, strike, 0, np.ones_like(spot), rate, yield_, kind)
        return mark, delta, np.zeros_like(spot), np.zeros_like(spot)
    variance = np.full_like(spot, p.v0) if variance is None else variance
    u, weights = quadrature(order)
    shifted = u - 0.5j
    prices: list[float] = []
    deltas: list[float] = []
    gammas: list[float] = []
    sensitivity: list[float] = []
    for offset in range(0, len(spot), 128):
        s = spot[offset : offset + 128]
        v = variance[offset : offset + 128, None]
        if model == "heston":
            cf, coefficient = heston_cf(shifted, tau, v, p)
            integrated = p.theta * tau + (v - p.theta) * (-math.expm1(-p.kappa * tau)) / p.kappa
        elif model == "merton":
            integrated = np.full_like(v, p.diffusion_vol**2 * tau)
            cf = np.exp(
                -0.5 * (shifted * shifted + 1j * shifted) * integrated
                + p.intensity
                * tau
                * (
                    np.exp(1j * shifted * p.jump_mean - 0.5 * shifted**2 * p.jump_std**2)
                    - 1
                    - 1j * shifted * p.compensator
                )
            )
            coefficient = np.zeros_like(cf)
        else:
            raise ValueError("Fourier engine supports Merton/Heston only")
        sigma = np.sqrt(integrated[:, 0] / tau)
        base, base_delta = batch_price_delta(s, strike, tau, sigma, rate, yield_, "call")
        d1 = (np.log(s / strike) + (rate - yield_ + sigma**2 / 2) * tau) / (sigma * math.sqrt(tau))
        base_gamma = (
            math.exp(-yield_ * tau)
            * np.exp(-(d1**2) / 2)
            / (s * sigma * math.sqrt(2 * math.pi * tau))
        )
        control = np.exp(-0.5 * (shifted**2 + 1j * shifted) * integrated)
        phase = np.exp(1j * u * (np.log(s[:, None] / strike) + (rate - yield_) * tau))
        difference = (control - cf) * phase
        factor = np.sqrt(s * strike) * math.exp(-(rate + yield_) * tau / 2) / math.pi
        denominator = u * u + 0.25
        prices.extend(base + factor * np.sum(difference.real * weights / denominator, axis=1))
        deltas.extend(
            base_delta
            + factor
            / s
            * np.sum(((0.5 + 1j * u) * difference).real * weights / denominator, axis=1)
        )
        gammas.extend(base_gamma - factor / s**2 * np.sum(difference.real * weights, axis=1))
        sensitivity.extend(
            -factor * np.sum((cf * coefficient * phase).real * weights / denominator, axis=1)
        )
    c, d, g, dv = (np.array(x) for x in (prices, deltas, gammas, sensitivity))
    if kind == "put":
        c -= spot * math.exp(-yield_ * tau) - strike * math.exp(-rate * tau)
        d -= math.exp(-yield_ * tau)
    if not all(np.isfinite(x).all() for x in (c, d, g, dv)):
        raise ArithmeticError("nonfinite characteristic-function integration")
    return c, d, g, dv


def model_batch(
    model: Model,
    spot: np.ndarray,
    strike: float,
    tau: float,
    p: ModelParameters,
    rate: float,
    yield_: float,
    kind: str = "call",
    variance: np.ndarray | None = None,
    order: int = 32,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    spot = np.asarray(spot, dtype=float)
    if model == "merton":
        return merton_batch(spot, strike, tau, p, rate, yield_, kind)
    if model == "heston":
        c, d, g, dv = fourier_batch(
            spot, strike, tau, p, rate, yield_, model, variance, kind, order
        )
        v = np.full_like(spot, p.v0) if variance is None else variance
        return c, d, g, dv * 2 * np.sqrt(v)
    mark, delta = batch_price_delta(
        spot, strike, tau, np.full_like(spot, p.diffusion_vol), rate, yield_, kind
    )
    if tau <= 0:
        return mark, delta, np.zeros_like(spot), np.zeros_like(spot)
    d1 = (np.log(spot / strike) + (rate - yield_ + p.diffusion_vol**2 / 2) * tau) / (
        p.diffusion_vol * math.sqrt(tau)
    )
    phi = np.exp(-(d1**2) / 2) / math.sqrt(2 * math.pi)
    return (
        mark,
        delta,
        math.exp(-yield_ * tau) * phi / (spot * p.diffusion_vol * math.sqrt(tau)),
        spot * math.exp(-yield_ * tau) * phi * math.sqrt(tau),
    )


def values(model: Model, point: ModelPoint, order: int = 32) -> np.ndarray:
    return np.array(
        [
            x[0]
            for x in model_batch(
                model,
                np.array([point.spot], dtype=float),
                point.strike,
                point.tau,
                point.parameters,
                point.rate,
                point.yield_,
                point.kind,
                order=order,
            )
        ]
    )


def quantlib_heston(point: ModelPoint) -> float:
    # Explicit curves/date avoid mutating QuantLib's global evaluation clock.
    origin = ql.Date(4, 10, 2026)
    dc = ql.Actual365Fixed()
    days = int(round(point.tau * 365))
    rate = ql.YieldTermStructureHandle(ql.FlatForward(origin, point.rate, dc))
    dividend = ql.YieldTermStructureHandle(ql.FlatForward(origin, point.yield_, dc))
    p = point.parameters
    process = ql.HestonProcess(
        rate,
        dividend,
        ql.QuoteHandle(ql.SimpleQuote(point.spot)),
        p.v0,
        p.kappa,
        p.theta,
        p.vol_of_vol,
        p.rho,
    )
    if p.vol_of_vol == 0:
        tau = days / 365
        integrated = p.theta * tau + (p.v0 - p.theta) * (-math.expm1(-p.kappa * tau)) / p.kappa
        vol = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(origin, ql.NullCalendar(), math.sqrt(integrated / tau), dc)
        )
        engine = ql.AnalyticEuropeanEngine(
            ql.BlackScholesMertonProcess(
                ql.QuoteHandle(ql.SimpleQuote(point.spot)), dividend, rate, vol
            )
        )
    else:
        engine = ql.AnalyticHestonEngine(ql.HestonModel(process), 192)
    option = ql.VanillaOption(
        ql.PlainVanillaPayoff(
            ql.Option.Call if point.kind == "call" else ql.Option.Put, point.strike
        ),
        ql.EuropeanExercise(origin + days),
    )
    option.setPricingEngine(engine)
    return float(option.NPV())


def matched_parameters(point: ModelPoint) -> dict[Model, ModelParameters]:
    """Synthetic one-point price matching, not a calibrated market surface."""
    p = point.parameters
    target = bsm(
        point.spot, point.strike, point.tau, p.diffusion_vol, point.rate, point.yield_, point.kind
    ).price

    intrinsic_forward = max(
        (1 if point.kind == "call" else -1)
        * (
            point.spot * math.exp(-point.yield_ * point.tau)
            - point.strike * math.exp(-point.rate * point.tau)
        ),
        0.0,
    )
    if target - intrinsic_forward < 0.005:
        raise ValueError(
            "Initial premium match is poorly identified below $0.005 time value; "
            "use unmatched parameters or a contract with material time value"
        )

    def jump_error(vol: float) -> float:
        return (
            values(
                "merton",
                point.model_copy(
                    update={"parameters": p.model_copy(update={"diffusion_vol": vol})}
                ),
            )[0]
            - target
        )

    def heston_error(vol: float) -> float:
        hp = p.model_copy(update={"v0": vol**2, "theta": vol**2})
        return values("heston", point.model_copy(update={"parameters": hp}))[0] - target

    try:
        mv = brentq(jump_error, 0.005, 0.8, xtol=1e-11)
        hv = brentq(heston_error, 0.03, 0.8, xtol=1e-11)
    except ValueError as exc:
        raise ValueError(
            "One-point price match is infeasible under these fixed jump/vol parameters"
        ) from exc
    return {
        "bsm": p,
        "merton": p.model_copy(update={"diffusion_vol": mv}),
        "heston": p.model_copy(update={"v0": hv**2, "theta": hv**2}),
    }


def checked_heston_batch(
    spot: np.ndarray,
    strike: float,
    tau: float,
    p: ModelParameters,
    rate: float,
    yield_: float,
    variance: np.ndarray | None = None,
    kind: str = "call",
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], dict[str, int]]:
    """Refine difficult quadrature points; reject unresolved numerical errors.

    Both orders are evaluated before a hedge target is admitted. Adaptive Lewis
    inversion resolves low-variance/short-expiry points without clipping Greeks.
    """
    from scipy.integrate import quad_vec

    spot = np.asarray(spot, dtype=float)
    variance = np.full_like(spot, p.v0) if variance is None else variance
    coarse = model_batch("heston", spot, strike, tau, p, rate, yield_, kind, variance, 32)
    fine = model_batch("heston", spot, strike, tau, p, rate, yield_, kind, variance, 64)
    tolerances = (1e-5, 5e-5, 1e-5, 1e-3)
    bad = np.zeros(len(spot), dtype=bool)
    for a, b, tolerance in zip(coarse, fine, tolerances, strict=True):
        bad |= np.abs(a - b) > tolerance
    # Integral refinement alone can agree at the wrong value; also enforce bounds.
    dq, dr = math.exp(-yield_ * tau), math.exp(-rate * tau)
    if kind == "call":
        lower, upper, dmin, dmax = np.maximum(spot * dq - strike * dr, 0), spot * dq, 0.0, dq
    else:
        lower, upper, dmin, dmax = (
            np.maximum(strike * dr - spot * dq, 0),
            np.full_like(spot, strike * dr),
            -dq,
            0.0,
        )
    bad |= (
        (fine[0] < lower - 1e-6)
        | (fine[0] > upper + 1e-6)
        | (fine[1] < dmin - 1e-6)
        | (fine[1] > dmax + 1e-6)
        | (fine[2] < -1e-6)
    )
    for index in np.flatnonzero(bad):
        s, v = float(spot[index]), float(variance[index])
        integrated = p.theta * tau + (v - p.theta) * (-math.expm1(-p.kappa * tau)) / p.kappa
        sigma = math.sqrt(integrated / tau)
        base = bsm(s, strike, tau, sigma, rate, yield_, kind)
        factor = math.sqrt(s * strike) * math.exp(-(rate + yield_) * tau / 2) / math.pi
        log_m = math.log(s / strike) + (rate - yield_) * tau

        def integrand(
            u: float,
            v: float = v,
            integrated: float = integrated,
            log_m: float = log_m,
            s: float = s,
            factor: float = factor,
        ) -> np.ndarray:
            shifted = np.array([u - 0.5j])
            cf, coefficient = heston_cf(shifted, tau, np.array([v]), p)
            control = np.exp(-0.5 * (shifted**2 + 1j * shifted) * integrated)
            phase = np.exp(1j * u * log_m)
            diff = (control - cf)[0] * phase
            denom = u * u + 0.25
            return (
                np.array(
                    [
                        diff.real / denom,
                        ((0.5 + 1j * u) * diff).real / (denom * s),
                        -diff.real / s**2,
                        -((cf * coefficient)[0] * phase).real / denom * 2 * math.sqrt(v),
                    ]
                )
                * factor
            )

        correction, error = quad_vec(integrand, 0, np.inf, epsabs=1e-8, epsrel=1e-8, limit=1000)
        if error > 1e-6 or not np.isfinite(correction).all():
            raise ArithmeticError("Heston adaptive integration did not converge")
        result = np.array([base.price, base.delta, base.gamma, 0.0]) + correction
        for out, value in zip(fine, result, strict=True):
            out[index] = value
    if (
        np.any(fine[0] < lower - 1e-6)
        or np.any(fine[1] < dmin - 1e-6)
        or np.any(fine[1] > dmax + 1e-6)
        or np.any(fine[2] < -1e-6)
    ):
        raise ArithmeticError("Heston price/Greek bounds unresolved after refinement")
    return fine, {"points": len(spot), "adaptive_refinements": int(bad.sum())}
