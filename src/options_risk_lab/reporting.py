"""Reproducible evidence exports; never train or tune when rendering a report."""

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from .experiments import Cancelled, export_table
from .risk import Shock, Surface, preset, scenario
from .services import WorkbenchRequest, hedge_view, portfolio_view


def load_completed(path: Path) -> dict[str, Any]:
    job = json.loads(path.read_text())
    if job["status"] != "complete":
        raise ValueError(f"cannot export {path}: run {job['id']} is {job['status']}")
    for key in ("episodes", "errors"):
        record = job["result"].get(key)
        if (
            record
            and hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest() != record["sha256"]
        ):
            raise ValueError(f"evidence payload changed: {record['path']}")
    return job


def export_evidence(output: Path, cancel: threading.Event | None = None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    evaluation = load_completed(Path("artifacts/evaluation-locked.json"))
    ml = load_completed(Path("artifacts/ml-study.json"))
    output.mkdir(parents=True, exist_ok=True)
    req = WorkbenchRequest()
    portfolio = portfolio_view(req)
    comparison = hedge_view(req)
    # Independent changes to stress support expose conditional optimizer dependence.
    trials = []
    for support, values in (
        ("wide", (-0.2, -0.1, 0, 0.1, 0.2)),
        ("narrow", (-0.1, -0.05, 0, 0.05, 0.1)),
    ):
        shocks = tuple(
            Shock(spot_return=s, vol_change=v, days=30) for s in values for v in (-0.05, 0, 0.05)
        )
        for budget in (0, 25, 100):
            if cancel and cancel.is_set():
                raise Cancelled("export cancelled between stress trials")
            study = hedge_view(
                req.model_copy(
                    update={
                        "shocks": shocks,
                        "limits": req.limits.model_copy(update={"cost_budget": budget}),
                    }
                )
            )
            for row in study["hedges"]:
                trials.append(
                    {
                        "support": support,
                        "budget": budget,
                        "method": row["name"],
                        "status": row["status"],
                        "cvar": row.get("cvar"),
                        "cost": row.get("cost"),
                        "capital": row.get("capital"),
                        "quantities": row.get("quantities"),
                    }
                )
    surfaces = []
    book = preset("delta-hedged-straddle", req.market, req.option, Surface(motion="frozen-strike"))
    for motion in ("flat", "frozen-strike", "sticky-log-moneyness"):
        for shock in req.shocks:
            result = scenario(book, req.market, shock, Surface(motion=motion))
            surfaces.append(
                {
                    "motion": motion,
                    **shock.model_dump(),
                    "full_change": result["full_change"],
                    "residual": result["residual"],
                }
            )
    local = []
    for case in ("delta-hedged-straddle", "locally-matched"):
        for size in (0.001, 0.01, 0.05, 0.1, 0.2):
            request = req.model_copy(
                update={
                    "case": case,
                    "selected_shock": Shock(
                        spot_return=size, vol_change=size / 4, days=30 * size / 0.2
                    ),
                }
            )
            view = portfolio_view(request)
            local.append(
                {
                    "case": case,
                    "spot_return": size,
                    "full_change": view["selected"]["full_change"],
                    "taylor": view["selected"]["approximation"],
                    "residual": view["selected"]["residual"],
                    "net": view["risk"]["net"],
                }
            )
    tables = {
        "hedge_stress_sensitivity": export_table(trials, output / "stress-hedges.parquet"),
        "surface_motion": export_table(surfaces, output / "surface-motion.parquet"),
        "locked_summary": export_table(
            evaluation["result"]["summary"], output / "locked-summary.parquet"
        ),
        "surrogate_summary": export_table(
            ml["result"]["metrics"], output / "surrogate-summary.parquet"
        ),
    }
    figures = []

    def figure(name: str, fig: Any) -> None:
        for extension in ("png", "svg", "pdf"):
            path = output / f"{name}.{extension}"
            fig.savefig(path, dpi=180, bbox_inches="tight")
            figures.append(
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
        plt.close(fig)

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(7, 4))
    for case in ("delta-hedged-straddle", "locally-matched"):
        data = [r for r in local if r["case"] == case]
        ax.plot(
            [100 * r["spot_return"] for r in data],
            [r["residual"] for r in data],
            marker="o",
            label=case,
        )
    ax.set(
        xlabel="Positive spot stress (%) with IV/time scaled",
        ylabel="Full minus Taylor mark change (USD)",
        title="Local matching does not control finite stresses",
    )
    ax.axhline(0, color="grey", linewidth=0.7)
    ax.legend()
    figure("approximation-residuals", fig)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, regime in zip(axes, ("matched", "misspecified", "jump-delay"), strict=True):
        for policy in evaluation["result"]["protocol"]["policies"]:
            data = [
                r
                for r in evaluation["result"]["summary"]
                if r["regime"] == regime and r["policy"] == policy
            ]
            ax.plot(
                [r["mean_cost"] for r in data], [r["rmse"] for r in data], marker="o", label=policy
            )
        ax.set(xlabel="Mean execution costs (USD)", title=regime)
    axes[0].set_ylabel("Financed terminal error RMSE (USD)")
    axes[-1].legend()
    figure("locked-cost-risk", fig)
    fig, ax = plt.subplots(figsize=(7, 4))
    frontier = comparison["frontier"]
    ax.step(
        [r["cost"] for r in frontier],
        [r["cvar"] for r in frontier],
        color="#0f766e",
        where="post",
        label="Feasible integer budget frontier",
    )
    for row in comparison["hedges"]:
        if row["status"] == "evaluated":
            ax.scatter(row["cost"], row["cvar"], label=row["name"], marker="x")
    ax.set(
        xlabel="Round trip execution cost (USD)",
        ylabel="Conditional stress CVaR95 (USD)",
        title="15 uniform stress states; gross capital limit $10,000",
    )
    ax.legend(fontsize=8)
    figure("static-cost-risk", fig)
    fig, axes = plt.subplots(1, 4, figsize=(12, 4))
    for ax, greek in zip(axes, ("price", "delta", "gamma", "vega"), strict=True):
        for method in ("price-only", "derivative-aware"):
            data = [
                r
                for r in ml["result"]["metrics"]
                if r["target"] == "american" and r["split"] == "iid" and r["method"] == method
            ]
            ax.plot(
                [r["seed"] for r in data],
                [r["rmse"][greek] for r in data],
                marker="o" if method == "price-only" else "s",
                linestyle="-" if method == "price-only" else "--",
                label=method,
            )
        ax.set(xlabel="Matched training seed", title=f"{greek.capitalize()} RMSE")
    fig.suptitle("Synthetic American put · per-share units · decimal IV vega", fontsize=12)
    fig.tight_layout()
    axes[0].set_ylabel("Error in declared Greek units")
    axes[-1].legend(fontsize=8)
    figure("surrogate-risk-errors", fig)
    result = {
        "upstream_runs": {"evaluation": evaluation["id"], "ml": ml["id"]},
        "default_portfolio": portfolio,
        "default_comparison": comparison,
        "local_stresses": local,
        "stress_trials": trials,
        "surface_trials": surfaces,
        "tables": tables,
        "figures": figures,
        "scope": (
            "Synthetic scientific evidence; mark change separate from "
            "financed terminal error; no tuning"
        ),
    }
    (output / "evidence.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    return result
