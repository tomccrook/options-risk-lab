"""Shared API/CLI comparison: model assumptions versus numerical engine error."""

import math
import threading
import time
from typing import Any

import numpy as np
from pydantic import Field

from .contracts import Record
from .model_mc import monte_carlo
from .models import (
    Model,
    ModelPoint,
    checked_heston_batch,
    fourier_batch,
    matched_parameters,
    model_batch,
    quantlib_heston,
)
from .services import provenance

MODELS: tuple[Model, ...] = ("bsm", "merton", "heston")
LABELS = {
    "bsm": "Black–Scholes–Merton",
    "merton": "Merton jump-diffusion",
    "heston": "Heston stochastic volatility",
}


class ModelComparisonRequest(Record):
    point: ModelPoint = ModelPoint()
    match_premium: bool = True


class MonteCarloRequest(ModelComparisonRequest):
    paths: int = Field(default=16384, ge=1024, le=262144, multiple_of=2)
    steps: int = Field(default=128, ge=16, le=512)
    seed: int = Field(default=811, ge=0, le=2**32 - 1)


def compare_models(req: ModelComparisonRequest) -> dict[str, Any]:
    begin = time.perf_counter()
    point = req.point
    params = (
        matched_parameters(point)
        if req.match_premium
        else {model: point.parameters for model in MODELS}
    )
    spot_grid = np.linspace(max(25, point.spot * 0.7), min(250, point.spot * 1.3), 41)
    curves = [{"spot": float(s)} for s in spot_grid]
    rows = []
    scenarios = []
    numerical = []
    for model in MODELS:
        p = params[model]
        start = time.perf_counter()
        if model == "heston":
            outputs, quality = checked_heston_batch(
                np.array([float(point.spot)]),
                point.strike,
                point.tau,
                p,
                point.rate,
                point.yield_,
                kind=point.kind,
            )
            curve, curve_quality = checked_heston_batch(
                spot_grid, point.strike, point.tau, p, point.rate, point.yield_
            )
            ql_point = point.model_copy(
                update={"parameters": p, "tau": round(point.tau * 365) / 365}
            )
            reference = quantlib_heston(ql_point)
            # QuantLib date rounding is disclosed; compare like maturity inputs.
            date_outputs, _ = checked_heston_batch(
                np.array([float(point.spot)]),
                point.strike,
                ql_point.tau,
                p,
                point.rate,
                point.yield_,
                kind=point.kind,
            )
            error = float(date_outputs[0][0] - reference)
            if abs(error) > 1e-5:
                raise ArithmeticError("Heston independent QuantLib price check failed")
            numerical.append(
                {
                    "model": model,
                    "reference": (
                        "QuantLib analytic Heston, order192 "
                        "(European deterministic limit when xi=0)"
                    ),
                    "price_error": error,
                    "date_tau": ql_point.tau,
                    "adaptive_refinements": quality["adaptive_refinements"]
                    + curve_quality["adaptive_refinements"],
                }
            )
        else:
            outputs = model_batch(
                model,
                np.array([float(point.spot)]),
                point.strike,
                point.tau,
                p,
                point.rate,
                point.yield_,
                point.kind,
            )
            curve = model_batch(
                model, spot_grid, point.strike, point.tau, p, point.rate, point.yield_
            )
            if model == "merton":
                independent = fourier_batch(
                    np.array([float(point.spot)]),
                    point.strike,
                    point.tau,
                    p,
                    point.rate,
                    point.yield_,
                    "merton",
                    kind=point.kind,
                    order=64,
                )
                error = float(outputs[0][0] - independent[0][0])
                if abs(error) > 1e-5:
                    raise ArithmeticError("Merton independent Fourier price check failed")
                numerical.append(
                    {
                        "model": model,
                        "reference": "Independent Fourier inversion",
                        "price_error": error,
                        "adaptive_refinements": 0,
                    }
                )
        rows.append(
            {
                "model": model,
                "label": LABELS[model],
                "price": float(outputs[0][0]),
                "delta": float(outputs[1][0]),
                "gamma": float(outputs[2][0]),
                "vega": float(outputs[3][0]),
                "vega_basis": "initial/current sqrt(variance), theta fixed"
                if model == "heston"
                else "diffusion sigma, jump parameters fixed",
                "parameters": p.model_dump(),
                "reference_ms": (time.perf_counter() - start) * 1000,
            }
        )
        for index, row in enumerate(curves):
            row[f"{model}_price"] = float(curve[0][index])
            row[f"{model}_delta"] = float(curve[1][index])
            row[f"{model}_gamma"] = float(curve[2][index])
        base_call = model_batch(
            model,
            np.array([float(point.spot)]),
            point.strike,
            point.tau,
            p,
            point.rate,
            point.yield_,
        )[0][0]
        base_put = (
            base_call
            - point.spot * math.exp(-point.yield_ * point.tau)
            + point.strike * math.exp(-point.rate * point.tau)
        )
        advance = min(30 / 365, point.tau / 4)
        for shock in (-0.2, -0.1, 0, 0.1, 0.2):
            s = point.spot * (1 + shock)
            tau = point.tau - advance
            if model == "heston":
                out, _ = checked_heston_batch(
                    np.array([s]), point.strike, tau, p, point.rate, point.yield_
                )
            else:
                out = model_batch(
                    model, np.array([s]), point.strike, tau, p, point.rate, point.yield_
                )
            put = (
                out[0][0]
                - s * math.exp(-point.yield_ * tau)
                + point.strike * math.exp(-point.rate * tau)
            )
            full = -100 * (out[0][0] + put - base_call - base_put)
            call_delta = outputs[1][0] + (
                math.exp(-point.yield_ * point.tau) if point.kind == "put" else 0
            )
            net_delta = -100 * (2 * call_delta - math.exp(-point.yield_ * point.tau))
            gamma = -200 * outputs[2][0]
            local = net_delta * (s - point.spot) + 0.5 * gamma * (s - point.spot) ** 2
            scenarios.append(
                {
                    "model": model,
                    "spot_return": shock,
                    "days": advance * 365,
                    "full_change": float(full),
                    "spot_taylor": float(local),
                    "residual": float(full - local),
                    "basis": (
                        "Unhedged short 1 call + 1 put ×100; spot Taylor omits time/cross "
                        "effects; current variance/diffusion parameters frozen"
                    ),
                }
            )
    evidence = provenance(req.model_dump(mode="json"))
    evidence.update(
        {
            "engine": "european-model-comparison-v1",
            "assumptions": "A01–A22/model-risk-v1",
            "pricing_basis": (
                "BSM / Merton Poisson mixture / independently checked Heston "
                "characteristic function"
            ),
            "quality": "Numerical integration checked; explicit parameter sensitivities",
        }
    )
    return {
        "config": req.model_dump(mode="json"),
        "rows": rows,
        "curves": curves,
        "scenarios": scenarios,
        "numerical_checks": numerical,
        "total_ms": (time.perf_counter() - begin) * 1000,
        "units": {
            "price": "USD/share",
            "delta": "shares per option share",
            "gamma": "1/USD",
            "vega": "USD per decimal parameter volatility; model-specific basis",
        },
        "basis": "One-point synthetic premium match"
        if req.match_premium
        else "Unmatched declared parameters",
        "warning": (
            "Monte Carlo is a numerical engine, not an asset model. One-point "
            "matching is not market calibration; richer models need not hedge "
            "better. Vega definitions differ."
        ),
        "provenance": evidence,
    }


def compare_mc(req: MonteCarloRequest, event: threading.Event | None = None) -> dict[str, Any]:
    params = (
        matched_parameters(req.point)
        if req.match_premium
        else {model: req.point.parameters for model in MODELS}
    )
    rows = []
    for model in MODELS:
        start = time.perf_counter()
        row = monte_carlo(
            model,
            req.point.model_copy(update={"parameters": params[model]}),
            req.paths,
            req.steps,
            req.seed,
            event=event,
        )
        row["elapsed_ms"] = (time.perf_counter() - start) * 1000
        rows.append(row)
    return {
        "config": req.model_dump(mode="json"),
        "rows": rows,
        "parameters": {key: p.model_dump() for key, p in params.items()},
        "basis": (
            "Antithetic price/pathwise delta; CRN spot gamma and parameter-"
            "volatility vega; includes simulation and Greek workloads"
        ),
        "warning": (
            "Heston confidence intervals exclude step bias; gamma/vega also "
            "have bump bias. No speed claim from unequal output/workload "
            "budgets."
        ),
        "provenance": provenance(req.model_dump(mode="json")),
    }
