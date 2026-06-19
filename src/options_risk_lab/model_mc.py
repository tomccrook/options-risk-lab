"""Independent MC controls: exact GBM/Merton; Andersen QE martingale Heston.

CI uses independent antithetic pairs (not individual legs or time nodes).
Heston sampling error does not cover time-discretisation bias.
"""

import math
import threading
from typing import Any

import numpy as np
from scipy.special import ndtr

from .experiments import Cancelled
from .models import Model, ModelParameters, ModelPoint, values


def qe_step(
    variance: np.ndarray,
    dt: float,
    p: ModelParameters,
    z_variance: np.ndarray,
    z_spot: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns next nonnegative variance and driftless log spot increment.

    QE's quadratic/exponential branches match conditional CIR moments. The
    conditional MGF correction makes exp(log increment) a unit-mean martingale.
    Reject parameter/step combinations without a finite correction.
    """
    decay = math.exp(-p.kappa * dt)
    if p.vol_of_vol == 0:
        integrated = p.theta * dt + (variance - p.theta) * (1 - decay) / p.kappa
        next_variance = p.theta + (variance - p.theta) * decay
        return next_variance, -0.5 * integrated + np.sqrt(integrated) * z_spot
    xi = p.vol_of_vol
    mean = p.theta + (variance - p.theta) * decay
    s2 = (
        variance * xi**2 * decay * (1 - decay) / p.kappa
        + p.theta * xi**2 / (2 * p.kappa) * (1 - decay) ** 2
    )
    psi = s2 / mean**2
    quadratic = psi <= 1.5
    next_variance = np.empty_like(variance)
    k1 = 0.5 * dt * (p.kappa * p.rho / xi - 0.5) - p.rho / xi
    k2 = 0.5 * dt * (p.kappa * p.rho / xi - 0.5) + p.rho / xi
    k3 = k4 = 0.5 * dt * (1 - p.rho**2)
    a_mgf = k2 + k4 / 2
    log_mgf = np.empty_like(variance)
    if quadratic.any():
        ps = psi[quadratic]
        b2 = 2 / ps - 1 + np.sqrt(2 / ps) * np.sqrt(2 / ps - 1)
        a = mean[quadratic] / (1 + b2)
        next_variance[quadratic] = a * (np.sqrt(b2) + z_variance[quadratic]) ** 2
        denominator = 1 - 2 * a_mgf * a
        if np.any(denominator <= 0):
            raise ArithmeticError("Heston QE quadratic MGF undefined; use smaller time steps")
        log_mgf[quadratic] = a_mgf * a * b2 / denominator - 0.5 * np.log(denominator)
    exponential = ~quadratic
    if exponential.any():
        prob = (psi[exponential] - 1) / (psi[exponential] + 1)
        beta = (1 - prob) / mean[exponential]
        if np.any(beta <= a_mgf):
            raise ArithmeticError("Heston QE exponential MGF undefined; use smaller time steps")
        uniform = np.minimum(ndtr(z_variance[exponential]), np.nextafter(1.0, 0.0))
        next_variance[exponential] = np.where(
            uniform <= prob, 0, np.log((1 - prob) / (1 - uniform)) / beta
        )
        log_mgf[exponential] = np.log(prob + (1 - prob) * beta / (beta - a_mgf))
    k0 = -log_mgf - (k1 + k3 / 2) * variance
    increment = (
        k0
        + k1 * variance
        + k2 * next_variance
        + np.sqrt(k3 * variance + k4 * next_variance) * z_spot
    )
    if not np.isfinite(increment).all() or np.any(next_variance < 0):
        raise ArithmeticError("invalid Heston QE state")
    return next_variance, increment


def sample_paths(
    model: Model,
    point: ModelPoint,
    paths: int,
    steps: int,
    seed: int,
    substeps: int = 1,
    antithetic: bool = False,
    event: threading.Event | None = None,
    terminal_only: bool = False,
    normal_increments: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    if antithetic and paths % 2:
        raise ValueError("antithetic paths must be even")
    dt = point.tau / (steps * substeps)
    p = point.parameters
    log_spot = np.full(paths, math.log(point.spot))
    variance = np.full(paths, p.v0 if model == "heston" else p.diffusion_vol**2)
    spots = np.empty((paths, 1 if terminal_only else steps + 1))
    variances = np.empty_like(spots)
    spots[:, 0], variances[:, 0] = point.spot, variance

    def normals() -> np.ndarray:
        z = rng.standard_normal(paths // 2 if antithetic else paths)
        return np.r_[z, -z] if antithetic else z

    for node in range(steps):
        if event is not None and event.is_set():
            raise Cancelled("model simulation cancelled")
        for subnode in range(substeps):
            index = node * substeps + subnode
            z = normals() if normal_increments is None else normal_increments[:, index, 0]
            if model == "heston":
                variance_z = (
                    normals() if normal_increments is None else normal_increments[:, index, 1]
                )
                variance, increment = qe_step(variance, dt, p, variance_z, z)
            else:
                increment = -0.5 * p.diffusion_vol**2 * dt + p.diffusion_vol * math.sqrt(dt) * z
                if model == "merton":
                    # Poisson legs independent; antithetic diffusion/jump normals only.
                    counts = rng.poisson(p.intensity * dt, paths)
                    increment += (
                        counts * p.jump_mean
                        + np.sqrt(counts) * p.jump_std * normals()
                        - p.intensity * p.compensator * dt
                    )
            log_spot += (point.rate - point.yield_) * dt + increment
        if not terminal_only:
            spots[:, node + 1], variances[:, node + 1] = np.exp(log_spot), variance
    if terminal_only:
        spots[:, 0], variances[:, 0] = np.exp(log_spot), variance
    if not np.isfinite(spots).all() or np.any(spots <= 0):
        raise ArithmeticError("invalid model spot paths")
    return spots, variances


def estimate(samples: np.ndarray, antithetic: bool) -> dict[str, Any]:
    observations = (
        (samples[: len(samples) // 2] + samples[len(samples) // 2 :]) / 2 if antithetic else samples
    )
    mean = float(observations.mean())
    se = float(observations.std(ddof=1) / math.sqrt(len(observations)))
    return {
        "value": mean,
        "se": se,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
        "independent_observations": len(observations),
    }


def monte_carlo(
    model: Model,
    point: ModelPoint,
    paths: int = 16384,
    steps: int = 128,
    seed: int = 811,
    bump_fraction: float = 0.0025,
    event: threading.Event | None = None,
) -> dict[str, Any]:
    # Exact terminal sampling for constant-vol models; Heston steps remain explicit.
    engine_steps = steps if model == "heston" else 1
    terminal, _ = sample_paths(
        model, point, paths, engine_steps, seed, antithetic=True, event=event, terminal_only=True
    )
    factor = terminal[:, 0] / point.spot
    sign = 1 if point.kind == "call" else -1
    discount = math.exp(-point.rate * point.tau)

    def payoff(spot: float, factors: np.ndarray = factor) -> np.ndarray:
        return discount * np.maximum(sign * (spot * factors - point.strike), 0)

    price = payoff(point.spot)
    delta = discount * sign * factor * (sign * (point.spot * factor - point.strike) > 0)
    bumps = []
    for fraction in (bump_fraction * 2, bump_fraction, bump_fraction / 2):
        h = point.spot * fraction
        gamma = (payoff(point.spot + h) - 2 * price + payoff(point.spot - h)) / h**2
        bumps.append({"spot_bump_usd": h, **estimate(gamma, True)})
    vol = math.sqrt(point.parameters.v0) if model == "heston" else point.parameters.diffusion_vol
    h = min(0.001, vol / 4)
    bumped_factors = []
    for shift in (-h, h):
        parameters = point.parameters.model_copy(
            update={"v0": (vol + shift) ** 2}
            if model == "heston"
            else {"diffusion_vol": vol + shift}
        )
        end, _ = sample_paths(
            model,
            point.model_copy(update={"parameters": parameters}),
            paths,
            engine_steps,
            seed,
            antithetic=True,
            event=event,
            terminal_only=True,
        )
        bumped_factors.append(end[:, 0] / point.spot)
    vega = (payoff(point.spot, bumped_factors[1]) - payoff(point.spot, bumped_factors[0])) / (2 * h)
    output = {
        "price": estimate(price, True),
        "delta": estimate(delta, True),
        "gamma": bumps[1],
        "vega": estimate(vega, True),
    }
    if model == "heston":
        from .models import checked_heston_batch

        checked, _ = checked_heston_batch(
            np.array([float(point.spot)]),
            point.strike,
            point.tau,
            point.parameters,
            point.rate,
            point.yield_,
            kind=point.kind,
        )
        reference = np.array([x[0] for x in checked])
    else:
        reference = values(model, point, 64)
    for i, key in enumerate(("price", "delta", "gamma", "vega")):
        output[key]["reference"] = float(reference[i])
        output[key]["error"] = output[key]["value"] - float(reference[i])
    return {
        "model": model,
        "seed": seed,
        "paths": paths,
        "steps": engine_steps,
        "greeks": output,
        "gamma_bumps": bumps,
        "vol_bump": h,
        "discounted_spot": estimate(discount * terminal[:, 0], True),
        "martingale_target": point.spot * math.exp(-point.yield_ * point.tau),
        "uncertainty": (
            "Independent antithetic-pair normal CI; "
            "excludes bump bias and Heston discretisation bias"
        ),
    }
