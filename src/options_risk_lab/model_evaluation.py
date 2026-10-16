"""Separately protected synthetic model-risk evidence; old locked study untouched."""

import hashlib
import json
import math
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from .experiments import Cancelled, export_table, metrics, paired_interval, uncertainty
from .model_mc import estimate, monte_carlo, sample_paths
from .model_replay import ModelReplayRequest, precompute, replay_one
from .model_services import ModelComparisonRequest, compare_models
from .models import ModelPoint, matched_parameters, values


def read_protocol(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Protected model-risk protocol changed; register a new study")
    protocol = json.loads(raw)
    ModelPoint.model_validate(protocol["point"])
    return protocol, digest


def heston_step_control(
    point: ModelPoint, config: dict[str, Any], event: threading.Event | None
) -> list[dict[str, Any]]:
    count = config["convergence_paths"]
    largest = max(config["convergence_steps"])
    rng = np.random.default_rng(867)
    base = rng.standard_normal((count // 2, largest, 2))
    fine = np.concatenate([base, -base])
    samples = {}
    rows = []
    for steps in config["convergence_steps"]:
        ratio = largest // steps
        shocks = fine.reshape(count, steps, ratio, 2).sum(axis=2) / math.sqrt(ratio)
        spots, variance = sample_paths(
            "heston",
            point,
            count,
            steps,
            867,
            antithetic=True,
            event=event,
            terminal_only=True,
            normal_increments=shocks,
        )
        payoff = np.exp(-point.rate * point.tau) * np.maximum(spots[:, 0] - point.strike, 0)
        samples[steps] = payoff
        rows.append(
            {
                "steps": steps,
                "price": estimate(payoff, True),
                "discounted_spot": estimate(spots[:, 0] * math.exp(-point.rate * point.tau), True),
                "reference": float(values("heston", point, 64)[0]),
                "min_terminal_variance": float(variance.min()),
            }
        )
    for row in rows:
        row["paired_difference_to_finest"] = estimate(
            samples[row["steps"]] - samples[largest], True
        )
    return rows


def evaluate_models(
    protocol_path: Path, output: Path, event: threading.Event | None = None, phase: str = "locked"
) -> dict[str, Any]:
    protocol, digest = read_protocol(protocol_path)
    if phase not in ("locked", "development"):
        raise ValueError("phase must be locked or development")
    output = output / uuid.uuid4().hex
    point = ModelPoint.model_validate(protocol["point"])
    params = matched_parameters(point)
    seeds = protocol["locked_seeds"] if phase == "locked" else protocol["development_seeds"]
    count = protocol["paths_per_batch"] if phase == "locked" else protocol["pilot_paths"]
    rows: list[dict[str, Any]] = []
    combined: dict[tuple[str, float, int, str], list[dict[str, Any]]] = {}
    traces = []
    quality = []
    started = time.perf_counter()
    for generator in protocol["generators"]:
        for seed in seeds:
            req = ModelReplayRequest(
                point=point,
                generator=generator,
                seed=seed,
                paths=count,
                steps=protocol["steps"],
                substeps=protocol["substeps"],
            )
            data = precompute(req, event)
            quality.append(
                {
                    "generator": generator,
                    "seed": seed,
                    "adaptive_refinements": data["adaptive_refinements"],
                }
            )
            for spread in protocol["costs"]:
                for delay in protocol["delays"]:
                    config = req.model_copy(update={"half_spread": spread, "delay": delay})
                    for hedger in protocol["hedgers"]:
                        if event is not None and event.is_set():
                            raise Cancelled("model evaluation cancelled")
                        result = replay_one(config, data, hedger)
                        key = (generator, spread, delay, hedger)
                        combined.setdefault(key, []).append(result)
                        rows.extend(
                            {
                                "generator": generator,
                                "spread": spread,
                                "delay": delay,
                                "seed": seed,
                                "path": i,
                                "hedger": hedger,
                                "financed_error": e,
                                "cost": result["costs"][i],
                                "turnover": result["turnover"][i],
                                "trades": result["trades"][i],
                                "rejected_requests": result["rejected_requests"][i],
                            }
                            for i, e in enumerate(result["financed_error"])
                        )
                        if seed == seeds[0] and spread == 0.01 and delay == 1:
                            traces.append(
                                {
                                    "generator": generator,
                                    "hedger": hedger,
                                    "seed": seed,
                                    "path": 0,
                                    "trace": result["trace"],
                                    "entry_premium": result["option_entry_premium"],
                                }
                            )
    summary = []
    paired = []
    errors = {
        key: np.concatenate([r["financed_error"] for r in results])
        for key, results in combined.items()
    }
    for (generator, spread, delay, hedger), results in combined.items():
        e = errors[generator, spread, delay, hedger]
        stats = metrics(
            e,
            np.concatenate([r["costs"] for r in results]),
            np.concatenate([r["turnover"] for r in results]),
        )
        stats.update(uncertainty(e, protocol["bootstrap_seed"], protocol["bootstrap_samples"]))
        summary.append(
            {
                "generator": generator,
                "spread": spread,
                "delay": delay,
                "hedger": hedger,
                **stats,
                "rejected_requests": sum(sum(r["rejected_requests"]) for r in results),
                "max_abs_delta": max(max(r["max_abs_delta"]) for r in results),
                "batch_metrics": [
                    metrics(
                        np.array(r["financed_error"]), np.array(r["costs"]), np.array(r["turnover"])
                    )
                    for r in results
                ],
            }
        )
        if hedger in ("merton", "heston", "heston-minvariance"):
            for baseline in protocol["baselines"]:
                b = errors[generator, spread, delay, baseline]
                interval = paired_interval(
                    e, b, protocol["bootstrap_seed"], protocol["bootstrap_samples"]
                )
                reduction = 1 - float(np.sqrt(np.mean(e**2)) / np.sqrt(np.mean(b**2)))
                paired.append(
                    {
                        "generator": generator,
                        "spread": spread,
                        "delay": delay,
                        "hedger": hedger,
                        "baseline": baseline,
                        **interval,
                        "rmse_reduction_fraction": reduction,
                        "supports_threshold": bool(reduction >= 0.05 and interval["ci95"][1] < 0),
                    }
                )
    episodes = export_table(rows, output / "episodes.parquet")
    numerical = []
    if phase == "locked":
        for model, p in params.items():
            for seed in protocol["pricing_seeds"]:
                for paths in protocol["mc_paths"]:
                    start = time.perf_counter()
                    row = monte_carlo(
                        model,
                        point.model_copy(update={"parameters": p}),
                        paths=paths,
                        steps=protocol["mc_steps"],
                        seed=seed,
                        event=event,
                    )
                    row["elapsed_ms"] = (time.perf_counter() - start) * 1000
                    row["price_gate"] = (
                        abs(row["greeks"]["price"]["error"])
                        <= 4 * row["greeks"]["price"]["se"] + protocol["numerical_price_allowance"]
                    )
                    numerical.append(row)
        convergence = heston_step_control(
            point.model_copy(update={"parameters": params["heston"]}), protocol, event
        )
    else:
        convergence = []
    comparison = compare_models(ModelComparisonRequest(point=point))
    return {
        "protocol": protocol,
        "protocol_sha256": digest,
        "phase": phase,
        "parameters": {key: p.model_dump() for key, p in params.items()},
        "summary": summary,
        "paired": paired,
        "episodes": episodes,
        "representative_traces": traces,
        "numerical_quality": quality,
        "monte_carlo": numerical,
        "heston_convergence": convergence,
        "comparison": comparison,
        "elapsed_seconds": time.perf_counter() - started,
        "basis": (
            "Common one-point premium, shared observable variance mapping "
            "normalized to each model initial variance, present-node pricing "
            "only; all stock costs/capital constraints paid through existing "
            "ledger"
        ),
        "warning": (
            "Independent-path bootstrap conditional on synthetic RN generator."
            " No real-data calibration, traded American assignment, or "
            "profitability claim; stock hedging cannot span jumps or "
            "independent volatility."
        ),
    }
