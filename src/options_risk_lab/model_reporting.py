"""Export frozen model evidence, scientific plots and measured reference workloads."""

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from .experiments import Cancelled, export_table
from .model_mc import monte_carlo
from .models import ModelPoint, checked_heston_batch, matched_parameters, values
from .reporting import load_completed


def verified_model_job() -> dict[str, Any]:
    job = load_completed(Path("artifacts/model-risk-locked.json"))
    payload = Path("artifacts/jobs") / f"{job['id']}.result.json"
    expected = payload.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(payload.read_bytes()).hexdigest() != expected:
        raise ValueError("Model result payload hash changed")
    if json.loads(payload.read_text()) != job["result"]:
        raise ValueError("Model evidence alias differs from immutable result")
    return job


def export_models(output: Path, event: threading.Event | None = None) -> dict[str, Any]:
    job = verified_model_job()
    result = job["result"]
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.2,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    records = []

    def save(fig: Any, name: str) -> None:
        if event is not None and event.is_set():
            raise Cancelled("model export cancelled")
        fig.tight_layout()
        for extension in ("svg", "png", "pdf"):
            path = output / f"{name}.{extension}"
            fig.savefig(path, dpi=160, bbox_inches="tight")
            records.append(
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
        plt.close(fig)

    curves = result["comparison"]["curves"]
    colors = ("#334155", "#64748b", "#0f766e")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
    for ax, key, unit in zip(
        axes, ("price", "delta", "gamma"), ("USD/share", "share delta", "gamma /USD"), strict=True
    ):
        for model, color, style in zip(
            ("bsm", "merton", "heston"), colors, ("-", "--", "-."), strict=True
        ):
            ax.plot(
                [r["spot"] for r in curves],
                [r[f"{model}_{key}"] for r in curves],
                color=color,
                linestyle=style,
                label=model,
            )
        ax.set(xlabel="Spot USD; K=100", ylabel=unit, title="One-point premium match")
    fig.suptitle("European call · T=1year · r=5%, q=0 · synthetic RN models")
    axes[0].legend()
    save(fig, "model-curves")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
    for ax, model in zip(axes, ("bsm", "merton", "heston"), strict=True):
        budgets = result["protocol"]["mc_paths"]
        means = []
        se = []
        for count in budgets:
            observations = [
                r["greeks"]["price"]
                for r in result["monte_carlo"]
                if r["model"] == model and r["paths"] == count
            ]
            means.append(float(np.mean([r["error"] for r in observations])))
            se.append(1.96 * math_sqrt_sum([r["se"] for r in observations]) / len(observations))
        ax.errorbar(budgets, means, yerr=se, fmt="o-", color="#0f766e", capsize=4)
        ax.axhline(0, color="#334155", linewidth=0.8)
        ax.set(
            xscale="log",
            xlabel="MC paths; 3 independent batches",
            ylabel="Price error USD ± sampling CI",
            title=model,
        )
    fig.suptitle("S=K=100, T=1year · antithetic pairs · Heston128steps · step bias excluded")
    save(fig, "mc-convergence")
    hedgers = ("bsm-fixed", "bsm-state", "merton", "heston", "heston-minvariance", "bsm-weekly")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, generator in zip(axes, ("bsm", "merton", "heston"), strict=True):
        cell = [
            r
            for r in result["summary"]
            if r["generator"] == generator and r["spread"] == 0.01 and r["delay"] == 1
        ]
        records_by_hedger = {r["hedger"]: r for r in cell}
        ax.barh(
            hedgers,
            [records_by_hedger[h]["rmse"] for h in hedgers],
            color=["#0f766e" if h == "heston-minvariance" else "#64748b" for h in hedgers],
        )
        ax.set(xlabel="Financed error RMSE USD", title=f"{generator} generator")
        ax.invert_yaxis()
    fig.suptitle("Short straddle ×100 · 1c stock half-spread · 1-node delay · 3,072paths/cell")
    save(fig, "paid-model-hedges")
    fig, ax = plt.subplots(figsize=(8, 4))
    for model, color, style in zip(
        ("bsm", "merton", "heston"), colors, ("-", "--", "-."), strict=True
    ):
        rows = [r for r in result["comparison"]["scenarios"] if r["model"] == model]
        ax.plot(
            [100 * r["spot_return"] for r in rows],
            [r["full_change"] for r in rows],
            linestyle=style,
            color=color,
            label=model,
        )
    ax.axhline(0, color="#334155", linewidth=0.8)
    ax.set(
        xlabel="Spot shock %; parameters frozen, 30-day roll",
        ylabel="Unhedged short straddle mark change USD",
        title="Matched initial premium does not match stress exposure",
    )
    ax.legend()
    save(fig, "model-stress")
    point = ModelPoint.model_validate(result["protocol"]["point"])
    parameters = matched_parameters(point)
    timing = []
    # Same declared four reference outputs. Includes typed input and result conversion.
    for model, p in parameters.items():
        durations = []
        for _ in range(25):
            start = time.perf_counter()
            query = ModelPoint.model_validate(
                point.model_copy(update={"parameters": p}).model_dump()
            )
            if model == "heston":
                outputs, _ = checked_heston_batch(
                    np.array([float(query.spot)]),
                    query.strike,
                    query.tau,
                    p,
                    query.rate,
                    query.yield_,
                )
                evaluated = [float(x[0]) for x in outputs]
            else:
                evaluated = values(model, query).tolist()
            json.dumps(evaluated, allow_nan=False)
            durations.append((time.perf_counter() - start) * 1000)
        mc = []
        for seed in result["protocol"]["pricing_seeds"]:
            start = time.perf_counter()
            query = ModelPoint.model_validate(
                point.model_copy(update={"parameters": p}).model_dump()
            )
            sampled = monte_carlo(model, query, paths=131072, steps=128, seed=seed, event=event)
            json.dumps(sampled, allow_nan=False)
            mc.append((time.perf_counter() - start) * 1000)
        timing.append(
            {
                "model": model,
                "reference_first_query_ms": durations[0],
                "reference_warm_p50_ms": float(np.median(durations[1:])),
                "reference_warm_p95_ms": float(np.quantile(durations[1:], 0.95)),
                "mc_131072_p50_ms": float(np.median(mc)),
                "reference_repetitions": 24,
                "mc_repetitions": 3,
                "workload": (
                    "One price/delta/gamma/model-parameter-vega query; "
                    "typed normalization + outputs/serialization; "
                    "warm imported process. "
                    "MC adds mandatory CIs/CRN bumps and reference diagnostics; "
                    "simulation included; "
                    "no GPU/network/browser time."
                ),
            }
        )
    tables = {
        "summary": export_table(result["summary"], output / "summary.parquet"),
        "paired": export_table(result["paired"], output / "paired.parquet"),
        "scenarios": export_table(result["comparison"]["scenarios"], output / "scenarios.parquet"),
    }
    evidence = {
        "source_run_id": job["id"],
        "source_provenance": job["manifest"]["provenance"],
        "protocol_sha256": result["protocol_sha256"],
        "episodes": result["episodes"],
        "figures": records,
        "tables": tables,
        "timings": timing,
    }
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2, allow_nan=False))
    return evidence


def math_sqrt_sum(values: list[float]) -> float:
    return float(np.sqrt(np.sum(np.array(values) ** 2)))
