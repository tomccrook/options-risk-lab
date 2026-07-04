"""Model-derived stock hedges reuse the existing causal self-financing ledger.

A common generator sets every option mark/premium. Only share targets change.
Present variance is idealised observable data, available to every model.
"""

import math
import threading
from typing import Any, Literal

import numpy as np
from pydantic import Field

from .contracts import Book, Market, Option, Position, Record
from .experiments import Cancelled, metrics, paired_interval
from .model_mc import sample_paths
from .models import Model, ModelPoint, checked_heston_batch, matched_parameters, model_batch
from .pricing import batch_price_delta, bsm
from .simulation import ReplayConfig, simulate

HEDGERS = ("none", "bsm-fixed", "bsm-state", "merton", "heston", "heston-minvariance", "bsm-weekly")


class ModelReplayRequest(Record):
    point: ModelPoint = ModelPoint()
    generator: Model = "heston"
    paths: int = Field(default=128, ge=8, le=1024)
    steps: int = Field(default=126, ge=8, le=252)
    seed: int = Field(default=137, ge=0, le=2**32 - 1)
    substeps: int = Field(default=4, ge=1, le=8)
    half_spread: float = Field(default=0.01, ge=0, le=0.1)
    delay: int = Field(default=1, ge=0, le=2)
    selected_hedger: Literal[
        "none", "bsm-fixed", "bsm-state", "merton", "heston", "heston-minvariance", "bsm-weekly"
    ] = "heston-minvariance"


def precompute(
    req: ModelReplayRequest,
    event: threading.Event | None = None,
    observed: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict[str, Any]:
    parameters = matched_parameters(req.point)
    generator_point = req.point.model_copy(update={"parameters": parameters[req.generator]})
    spot, variance = (
        observed
        if observed is not None
        else sample_paths(
            req.generator,
            generator_point,
            req.paths,
            req.steps,
            req.seed,
            req.substeps,
            event=event,
        )
    )
    if spot.shape != (req.paths, req.steps + 1) or variance.shape != spot.shape:
        raise ValueError("observable path dimensions invalid")
    if not np.isfinite(variance).all() or np.any(variance < 0):
        raise ValueError("invalid observed variance")
    # Compute each present-node valuation once; cost/delay policies share this data.
    marks = np.empty_like(spot)
    deltas = {key: np.empty_like(spot) for key in HEDGERS if key != "none"}
    initial_variance = (
        parameters[req.generator].v0
        if req.generator == "heston"
        else parameters[req.generator].diffusion_vol ** 2
    )
    adaptive = 0
    for node in range(req.steps + 1):
        if event is not None and event.is_set():
            raise Cancelled("model valuation cancelled")
        tau = max(0, req.point.tau * (1 - node / req.steps))
        s, v = spot[:, node], variance[:, node]
        p = parameters["heston"]
        heston_variance = p.v0 * v / initial_variance
        heston, quality = checked_heston_batch(
            s, req.point.strike, tau, p, req.point.rate, req.point.yield_, heston_variance
        )
        adaptive += quality["adaptive_refinements"]
        merton = model_batch(
            "merton",
            s,
            req.point.strike,
            tau,
            parameters["merton"],
            req.point.rate,
            req.point.yield_,
        )
        fixed = model_batch(
            "bsm", s, req.point.strike, tau, parameters["bsm"], req.point.rate, req.point.yield_
        )
        # Same observed variance: one-point initial IV normalization for each generator.
        state_vol = req.point.parameters.diffusion_vol * np.sqrt(v / initial_variance)
        if tau > 0 and np.any(state_vol == 0):
            state_delta = np.array(
                [
                    bsm(
                        float(ss),
                        req.point.strike,
                        tau,
                        float(vv),
                        req.point.rate,
                        req.point.yield_,
                    ).delta
                    or 0.0
                    for ss, vv in zip(s, state_vol, strict=True)
                ]
            )
        else:
            _, state_delta = batch_price_delta(
                s, req.point.strike, tau, state_vol, req.point.rate, req.point.yield_, "call"
            )
        marks[:, node] = {"bsm": fixed, "merton": merton, "heston": heston}[req.generator][0]
        deltas["bsm-fixed"][:, node] = deltas["bsm-weekly"][:, node] = fixed[1]
        deltas["bsm-state"][:, node] = state_delta
        deltas["merton"][:, node] = merton[1]
        deltas["heston"][:, node] = heston[1]
        # dV/dv term; at zero variance use partial delta: instantaneous covariance is degenerate.
        dv = np.divide(
            heston[3], 2 * np.sqrt(heston_variance), out=np.zeros_like(v), where=heston_variance > 0
        )
        deltas["heston-minvariance"][:, node] = heston[1] + p.rho * p.vol_of_vol / s * dv
    return {
        "spot": spot,
        "variance": variance,
        "marks": marks,
        "deltas": deltas,
        "parameters": parameters,
        "adaptive_refinements": adaptive,
    }


def replay_one(req: ModelReplayRequest, data: dict[str, Any], hedger: str) -> dict[str, Any]:
    from datetime import timedelta

    point = req.point
    v_start = float(data["variance"][0, 0])
    market = Market(spot=point.spot, vol=math.sqrt(v_start), rate=point.rate, yield_=point.yield_)
    option = Option(
        strike=point.strike, expiry=market.valuation_time + timedelta(days=point.tau * 365)
    )
    dq = math.exp(-point.yield_ * point.tau)
    call = float(data["marks"][0, 0])
    put = call - point.spot * dq + point.strike * math.exp(-point.rate * point.tau)
    if min(call, put) < 0.05:
        raise ValueError(
            "Synthetic 5c option half-spread produces a negative entry bid; replay rejected"
        )
    book = Book(
        positions=(
            Position(instrument=option, quantity=-1),
            Position(
                instrument=option.model_copy(update={"id": "put", "kind": "put"}), quantity=-1
            ),
        ),
        cash=10000 + 100 * (call + put),
    )

    def valuation(
        kind: str, s: np.ndarray, strike: float, tau: float, observable_vol: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        node = int(round((1 - tau / point.tau) * req.steps))
        # Cache key includes node, the immutable run's model parameters, and present data.
        if not np.array_equal(s, data["spot"][:, node]) or not np.array_equal(
            observable_vol, np.sqrt(data["variance"][:, node])
        ):
            raise ValueError("valuation cache does not match present observation")
        mark = data["marks"][:, node].copy()
        delta = data["deltas"][hedger if hedger != "none" else "bsm-fixed"][:, node].copy()
        if kind == "put":
            mark -= s * math.exp(-point.yield_ * tau) - strike * math.exp(-point.rate * tau)
            delta -= math.exp(-point.yield_ * tau)
        return mark, delta

    config = ReplayConfig(
        seed=req.seed,
        paths=req.paths,
        steps=req.steps,
        policy="none" if hedger == "none" else ("weekly" if hedger == "bsm-weekly" else "daily"),
        share_half_spread=req.half_spread,
        option_half_spread=0.05,
        delay_nodes=req.delay,
        max_shares=250,
        capital_limit=25000,
    )
    result = simulate(
        book,
        market,
        config,
        (data["spot"], np.sqrt(data["variance"])),
        valuation=valuation,
        model_label=hedger,
    )
    for row in result["trace"]:
        row["variance"] = float(data["variance"][0, row["node"]])
    result["hedger"] = hedger
    result["generator"] = req.generator
    result["option_entry_premium"] = 100 * (call + put)
    return result


def compare_replay(req: ModelReplayRequest, event: threading.Event | None = None) -> dict[str, Any]:
    from .services import provenance

    data = precompute(req, event)
    summary = []
    results = {}
    for hedger in HEDGERS:
        if event is not None and event.is_set():
            raise Cancelled("model hedge comparison cancelled")
        result = replay_one(req, data, hedger)
        results[hedger] = result
        summary.append(
            {
                "hedger": hedger,
                **metrics(
                    np.array(result["financed_error"]),
                    np.array(result["costs"]),
                    np.array(result["turnover"]),
                ),
                "rejected_requests": sum(result["rejected_requests"]),
                "max_abs_delta": max(result["max_abs_delta"]),
            }
        )
    baseline = results["bsm-state"]
    paired = [
        {
            "hedger": key,
            "baseline": "bsm-state",
            **paired_interval(
                np.array(result["financed_error"]),
                np.array(baseline["financed_error"]),
                seed=919,
                samples=500,
            ),
        }
        for key, result in results.items()
        if key != "bsm-state"
    ]
    selected = results[req.selected_hedger]
    counts, edges = np.histogram(selected["financed_error"], bins=20)
    return {
        "config": req.model_dump(mode="json"),
        "parameters": {key: p.model_dump() for key, p in data["parameters"].items()},
        "summary": summary,
        "paired": paired,
        "trace": selected["trace"],
        "selected_hedger": req.selected_hedger,
        "distribution": [
            {"error_usd": float((a + b) / 2), "count": int(n)}
            for a, b, n in zip(edges[:-1], edges[1:], counts, strict=True)
        ],
        "allocated": selected["allocated"],
        "entry_premium_usd": selected["option_entry_premium"],
        "funding_benchmark": selected["funding_benchmark"],
        "terminal_inventory": selected["terminal_inventory"],
        "numerical_quality": {"adaptive_refinements": data["adaptive_refinements"]},
        "provenance": provenance(req.model_dump(mode="json")),
        "basis": (
            "Common generator option premiums/marks; stock-only integer hedges, "
            "same present variance information, paid entry/liquidation, "
            "250-share and $25,000 gross constraints"
        ),
        "warning": (
            "Exploratory synthetic control, not locked evidence or market profitability. "
            "Current variance is idealised observable; no future variance. Stock-only risk remains."
        ),
    }
