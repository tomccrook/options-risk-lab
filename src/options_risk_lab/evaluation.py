import hashlib
import json
import threading
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import Market, Option
from .experiments import Cancelled, export_table, metrics, paired_interval, uncertainty
from .risk import preset
from .simulation import ReplayConfig, paths, simulate


def evaluate(
    protocol_path: Path, output: Path, cancel: threading.Event | None = None, phase: str = "locked"
) -> dict[str, Any]:
    output = output / uuid.uuid4().hex
    encoded = protocol_path.read_bytes()
    if (
        hashlib.sha256(encoded).hexdigest()
        != protocol_path.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("protected protocol changed; register a new protocol before evaluation")
    protocol = json.loads(encoded)
    seeds = protocol["locked_seeds"] if phase == "locked" else protocol["development_seeds"]
    count = protocol["paths_per_batch"] if phase == "locked" else protocol["pilot_paths"]
    market = Market()
    option = Option()
    book = preset("short-straddle", market, option)
    rows: list[dict[str, Any]] = []
    summary = []
    paired = []
    for regime in protocol["regimes"]:
        for spread in protocol["cost_per_share"]:
            combined: dict[str, list[dict[str, Any]]] = {p: [] for p in protocol["policies"]}
            for seed in seeds:
                config = ReplayConfig(
                    seed=seed,
                    paths=count,
                    steps=252,
                    regime=regime,
                    share_half_spread=spread,
                    delay_nodes=int(regime == "jump-delay"),
                    band=protocol["band_shares"],
                )
                common = paths(config, market, option.tau(market))
                for policy in protocol["policies"]:
                    if cancel and cancel.is_set():
                        raise Cancelled("evaluation cancelled between policies")
                    result = simulate(
                        book, market, config.model_copy(update={"policy": policy}), common
                    )
                    combined[policy].append(result)
                    rows.extend(
                        {
                            "regime": regime,
                            "spread": spread,
                            "seed": seed,
                            "path": i,
                            "policy": policy,
                            "financed_error": e,
                            "cost": result["costs"][i],
                            "turnover": result["turnover"][i],
                            "trades": result["trades"][i],
                        }
                        for i, e in enumerate(result["financed_error"])
                    )
            errors = {
                p: np.concatenate([r["financed_error"] for r in runs])
                for p, runs in combined.items()
            }
            for policy, runs in combined.items():
                stats = metrics(
                    errors[policy],
                    np.concatenate([r["costs"] for r in runs]),
                    np.concatenate([r["turnover"] for r in runs]),
                )
                stats.update(
                    uncertainty(
                        errors[policy], protocol["bootstrap_seed"], protocol["bootstrap_samples"]
                    )
                )
                batches = [
                    metrics(
                        np.array(r["financed_error"]), np.array(r["costs"]), np.array(r["turnover"])
                    )
                    for r in runs
                ]
                summary.append(
                    {
                        "regime": regime,
                        "spread": spread,
                        "policy": policy,
                        **stats,
                        "batch_metrics": batches,
                        "paths": len(errors[policy]),
                    }
                )
            for baseline in ("daily", "weekly", "monthly"):
                interval = paired_interval(
                    errors["band"],
                    errors[baseline],
                    protocol["bootstrap_seed"],
                    protocol["bootstrap_samples"],
                )
                paired.append(
                    {
                        "regime": regime,
                        "spread": spread,
                        "policy": "band",
                        "baseline": baseline,
                        **interval,
                    }
                )
    table = export_table(rows, output / "episodes.parquet")
    # Pilot establishes precision limitations; final batch count remains predeclared.
    return {
        "protocol": protocol,
        "protocol_sha256": hashlib.sha256(encoded).hexdigest(),
        "phase": phase,
        "summary": summary,
        "paired": paired,
        "episodes": table,
        "estimator": "exact worst 5% probability mass with fractional boundary",
        "warning": "Synthetic uncertainty conditional on generator; tail intervals limited.",
    }
