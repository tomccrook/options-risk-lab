"""Bounded matched-budget differential surrogate study; reference fallback is default."""

import hashlib
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.interpolate import RegularGridInterpolator
from torch import nn

from .american import convergence, labels
from .experiments import Cancelled, export_table
from .pricing import bsm, vector_price, vector_price_greeks

LOW = np.array([0.7, 0.1, 0.1, 0.01, 0.0])
HIGH = np.array([1.3, 2.0, 0.5, 0.08, 0.04])


class Surrogate(nn.Module):
    center: torch.Tensor
    scale: torch.Tensor

    def __init__(self, width: int = 48, depth: int = 3) -> None:
        super().__init__()
        self.register_buffer("center", torch.tensor((HIGH + LOW) / 2, dtype=torch.float64))
        self.register_buffer("scale", torch.tensor((HIGH - LOW) / 2, dtype=torch.float64))
        layers: list[nn.Module] = [nn.Linear(5, width), nn.Tanh()]
        for _ in range(depth - 1):
            layers.extend([nn.Linear(width, width), nn.Tanh()])
        layers.append(nn.Linear(width, 1))
        self.network = nn.Sequential(*layers).double()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network((x - self.center) / self.scale).squeeze(-1)


def greeks(model: nn.Module, x: np.ndarray) -> np.ndarray:
    t = torch.tensor(x, dtype=torch.float64, requires_grad=True)
    y = model(t)
    grad = torch.autograd.grad(y.sum(), t, create_graph=True)[0]
    gamma = torch.autograd.grad(grad[:, 0].sum(), t)[0][:, 0]
    return np.c_[
        y.detach().numpy() * 100,
        grad[:, 0].detach().numpy(),
        gamma.detach().numpy() / 100,
        grad[:, 2].detach().numpy() * 100,
    ]


def control_labels(x: np.ndarray) -> np.ndarray:
    return np.array(
        [
            [g.price, g.delta, g.gamma, g.vega]
            for row in x
            for g in [bsm(row[0] * 100, 100, row[1], row[2], row[3], row[4], "put")]
        ]
    )


def sample(count: int, seed: int, region: str) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.uniform(LOW, HIGH, size=(count, 5))
    x[:, 1] = np.clip(np.rint(x[:, 1] * 365), 37, 730) / 365
    if region == "train":
        # Held-out joint m/t region never appears in training.
        bad = (x[:, 0] > 1.2) & (x[:, 1] < 0.3)
        while bad.any():
            x[bad] = rng.uniform(LOW, HIGH, size=(int(bad.sum()), 5))
            x[:, 1] = np.clip(np.rint(x[:, 1] * 365), 37, 730) / 365
            bad = (x[:, 0] > 1.2) & (x[:, 1] < 0.3)
    elif region == "held-region":
        x[:, 0] = rng.uniform(1.2, 1.3, count)
        x[:, 1] = rng.uniform(0.1, 0.3, count)
    elif region == "boundary":
        x[:, 0] = rng.uniform(0.75, 1.03, count)
        x[:, 1] = rng.uniform(1 / 365, 0.08, count)
    elif region == "ood":
        x[:, 1] = rng.uniform(0.02, 0.08, count)
        x[:, 2] = rng.uniform(0.55, 0.7, count)
    elif region != "iid":
        raise ValueError("unknown split")
    x[:, 1] = np.maximum(1, np.rint(x[:, 1] * 365)) / 365
    return x


def error_metrics(
    predicted: np.ndarray, actual: np.ndarray, x: np.ndarray, target: str = "american"
) -> dict[str, Any]:
    errors = predicted - actual
    rmse = np.sqrt(np.mean(errors**2, axis=0))
    if target == "european":
        lower = np.maximum(
            100 * np.exp(-x[:, 3] * x[:, 1]) - 100 * x[:, 0] * np.exp(-x[:, 4] * x[:, 1]), 0
        )
        upper = 100 * np.exp(-x[:, 3] * x[:, 1])
    else:
        lower = np.maximum(100 - 100 * x[:, 0], 0)
        upper = 100 * np.maximum(1, np.exp(-x[:, 3] * x[:, 1]))
    bound = (predicted[:, 0] < lower - 0.01) | (predicted[:, 0] > upper + 0.01)
    invalid = (predicted[:, 1] > 0) | (predicted[:, 1] < -1.01) | (predicted[:, 2] < -0.0001)
    return {
        "rmse": dict(zip(("price", "delta", "gamma", "vega"), rmse.tolist(), strict=True)),
        "max_abs": dict(
            zip(
                ("price", "delta", "gamma", "vega"),
                np.abs(errors).max(axis=0).tolist(),
                strict=True,
            )
        ),
        "bounds_failures": int(bound.sum()),
        "shape_failures": int(invalid.sum()),
        "share_hedge_rmse_1_contract": float(rmse[1] * 100),
        "gamma_exposure_rmse_1_contract": float(rmse[2] * 100),
        "samples": len(x),
    }


def train(
    x: np.ndarray,
    reference: np.ndarray,
    seed: int,
    epochs: int,
    differential: bool,
    width: int,
    depth: int,
    cancel: threading.Event | None = None,
) -> tuple[Surrogate, float, list[dict[str, float]]]:
    torch.manual_seed(seed)
    model = Surrogate(width, depth)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    inputs = torch.tensor(x, dtype=torch.float64, requires_grad=True)
    target = torch.tensor(reference[:, 0] / 100, dtype=torch.float64)
    delta = torch.tensor(reference[:, 1], dtype=torch.float64)
    trace = []
    started = time.perf_counter()
    for epoch in range(epochs):
        if cancel and cancel.is_set():
            raise Cancelled("training cancelled between epochs")
        optimizer.zero_grad(set_to_none=True)
        inputs.grad = None
        y = model(inputs)
        d = torch.autograd.grad(y.sum(), inputs, create_graph=True)[0][:, 0]
        price_loss = torch.mean(((y - target) / 0.1) ** 2)
        delta_loss = torch.mean(((d - delta) / 0.5) ** 2)
        # Same derivative graph/batches/updates for both arms; delta loss weight differs.
        loss = price_loss + (0.25 if differential else 0) * delta_loss
        loss.backward()
        optimizer.step()
        if epoch % 50 == 0 or epoch == epochs - 1:
            trace.append(
                {
                    "epoch": float(epoch),
                    "price_loss": float(price_loss.detach()),
                    "delta_loss": float(delta_loss.detach()),
                }
            )
    return model, time.perf_counter() - started, trace


def timed(operation: Any, repeats: int = 5) -> tuple[Any, dict[str, float]]:
    operation()  # identical warmup excluded and disclosed
    durations = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = operation()
        durations.append(time.perf_counter() - start)
    return result, {
        "p50_ms": float(np.median(durations) * 1000),
        "p95_ms": float(np.quantile(durations, 0.95) * 1000),
        "repeats": repeats,
    }


def study(
    protocol: dict[str, Any], output: Path, cancel: threading.Event | None = None
) -> dict[str, Any]:
    torch.set_num_threads(1)
    output.mkdir(parents=True, exist_ok=True)
    gate = convergence()
    if not gate["passed"]:
        raise ValueError("American reference convergence gate failed; see convergence command")
    training_x = sample(protocol["ml_labels"], 101, "train")
    splits = {
        name: sample(256, seed, name)
        for name, seed in [("iid", 701), ("held-region", 709), ("boundary", 719), ("ood", 727)]
    }
    entries = []
    rows: list[dict[str, Any]] = []
    timings = []
    generation: list[dict[str, Any]] = []
    for target in ("european", "american"):
        labeler = control_labels if target == "european" else labels
        start = time.perf_counter()
        training_y = labeler(training_x)
        references = {name: labeler(x) for name, x in splits.items()}
        shocked = {name: x.copy() for name, x in splits.items()}
        for sx in shocked.values():
            sx[:, 0] *= 1.1
            sx[:, 2] += 0.03
        shocked_references = {name: labeler(x) for name, x in shocked.items()}
        label_seconds = time.perf_counter() - start
        uncertainty = None
        if target == "american":
            check = labels(training_x[:32], 1024)
            diff = np.abs(check - training_y[:32])
            uncertainty = {
                "samples": 32,
                "max_512_1024": diff.max(axis=0).tolist(),
                "delta_label_eligible": bool(diff[:, 1].max() < 0.005),
            }
            if not uncertainty["delta_label_eligible"]:
                raise ValueError("differential label convergence failure in training subset")
        generation.append(
            {"target": target, "label_seconds": label_seconds, "reference_uncertainty": uncertainty}
        )
        # Same-domain grid subspace, <=2048 labels and no larger model storage than MLP.
        axes = [np.linspace(LOW[i], HIGH[i], n) for i, n in enumerate((8, 5, 5, 3, 3))]
        grid_x = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 5)
        grid_start = time.perf_counter()
        grid_eligible = ~((grid_x[:, 0] > 1.2) & (grid_x[:, 1] < 0.3))
        grid_y = np.full(len(grid_x), np.nan)
        grid_y[grid_eligible] = labeler(grid_x[grid_eligible])[:, 0] / 100
        interpolator = RegularGridInterpolator(
            axes, grid_y.reshape(8, 5, 5, 3, 3), bounds_error=False, fill_value=None
        )

        def grid_predict(
            x: np.ndarray, interpolator: Any = interpolator, labeler: Any = labeler
        ) -> np.ndarray:
            y = interpolator(x) * 100
            derivatives = []
            for index, h in ((0, 0.002), (2, 0.001)):
                u = x.copy()
                d = x.copy()
                u[:, index] += h
                d[:, index] -= h
                derivatives.append((interpolator(u) - interpolator(d)) / (2 * h))
            u = x.copy()
            d = x.copy()
            u[:, 0] += 0.002
            d[:, 0] -= 0.002
            gamma = (interpolator(u) - 2 * interpolator(x) + interpolator(d)) / 0.002**2 / 100
            prediction = np.c_[y, derivatives[0], gamma, derivatives[1] * 100]
            missing = (
                ~np.isfinite(prediction).all(axis=1)
                | np.any(x < LOW, axis=1)
                | np.any(x > HIGH, axis=1)
            )
            if missing.any():
                prediction[missing] = labeler(x[missing])
            return prediction

        for name, x in splits.items():

            def benchmark_grid(
                x: np.ndarray = x, grid_predict: Any = grid_predict, target: str = target
            ) -> np.ndarray:
                if target == "american":
                    from .american import reference

                    reference.cache_clear()
                return grid_predict(x)

            predicted, latency = timed(benchmark_grid, 3)
            entries.append(
                {
                    "target": target,
                    "method": "grid",
                    "seed": None,
                    "split": name,
                    "fallback_points": int(
                        (
                            ~np.isfinite(interpolator(x))
                            | np.any(x < LOW, axis=1)
                            | np.any(x > HIGH, axis=1)
                        ).sum()
                    ),
                    **error_metrics(predicted, references[name], x, target),
                }
            )
            timings.append(
                {"target": target, "method": "grid", "split": name, "batch": len(x), **latency}
            )
        generation.append(
            {
                "target": target,
                "method": "grid",
                "labels": int(grid_eligible.sum()),
                "fallback": "Missing held-region cells and OOD use reference with overhead",
                "build_seconds": time.perf_counter() - grid_start,
                "bytes": grid_y.nbytes,
                "domain": {"low": LOW.tolist(), "high": HIGH.tolist()},
                "warning": "Multilinear price interpolation has unreliable gamma at knots",
            }
        )
        for seed in protocol["ml_seeds"]:
            for differential in (False, True):
                method = "derivative-aware" if differential else "price-only"
                model, seconds, loss_trace = train(
                    training_x,
                    training_y,
                    seed,
                    protocol["ml_epochs"],
                    differential,
                    protocol["ml_width"],
                    protocol["ml_depth"],
                    cancel,
                )
                torch.save(model.state_dict(), output / f"{target}-{method}-{seed}.pt")
                generation.append(
                    {
                        "target": target,
                        "method": method,
                        "seed": seed,
                        "train_seconds": seconds,
                        "loss_trace": loss_trace,
                        "model_sha256": hashlib.sha256(
                            (output / f"{target}-{method}-{seed}.pt").read_bytes()
                        ).hexdigest(),
                        "parameters": sum(p.numel() for p in model.parameters()),
                        "model_bytes": sum(
                            p.numel() * p.element_size() for p in model.parameters()
                        ),
                    }
                )
                for name, x in splits.items():
                    predicted, latency = timed(lambda model=model, x=x: greeks(model, x))
                    measured = error_metrics(predicted, references[name], x, target)
                    shock_prediction = greeks(model, shocked[name])
                    scenario_error = (
                        (shock_prediction[:, 0] - predicted[:, 0])
                        - (shocked_references[name][:, 0] - references[name][:, 0])
                    ) * 100
                    ds = x[:, 0] * 100 * 0.1
                    share_error = (
                        np.rint(predicted[:, 1] * 100) - np.rint(references[name][:, 1] * 100)
                    ) * ds
                    measured["scenario_change_rmse_1_contract_usd"] = float(
                        np.sqrt(np.mean(scenario_error**2))
                    )
                    measured["actual_share_hedge_pnl_discrepancy_rmse_usd"] = float(
                        np.sqrt(np.mean(share_error**2))
                    )
                    measured["shock_basis"] = "10% spot +3 vol points; no time advance, marks only"
                    entries.append(
                        {
                            "target": target,
                            "method": method,
                            "seed": seed,
                            "split": name,
                            **measured,
                        }
                    )
                    timings.append(
                        {
                            "target": target,
                            "method": method,
                            "seed": seed,
                            "split": name,
                            "batch": len(x),
                            "device": "cpu",
                            "dtype": "float64",
                            **latency,
                        }
                    )
                    rows.extend(
                        {
                            "target": target,
                            "method": method,
                            "seed": seed,
                            "split": name,
                            "m": float(x[i, 0]),
                            "tau": float(x[i, 1]),
                            "iv": float(x[i, 2]),
                            "price_error": float(e[0]),
                            "delta_error": float(e[1]),
                            "gamma_error": float(e[2]),
                            "vega_error": float(e[3]),
                        }
                        for i, e in enumerate(predicted - references[name])
                    )
        # Vectorized analytical reference timing includes full input batch, not a scalar loop.
        x = splits["iid"]
        if target == "european":
            _, latency = timed(lambda x=x: vector_price_greeks(x))
            timings.append(
                {
                    "target": target,
                    "method": "vector-reference-price-greeks",
                    "batch": len(x),
                    **latency,
                }
            )
            _, latency = timed(lambda x=x: vector_price(x))
            timings.append(
                {"target": target, "method": "vector-reference-price", "batch": len(x), **latency}
            )
        else:
            from .american import reference

            def uncached_reference(x: np.ndarray = x) -> np.ndarray:
                reference.cache_clear()
                return labels(x)

            _, latency = timed(uncached_reference, 3)
            timings.append(
                {
                    "target": target,
                    "method": "fd-reference-price-greeks",
                    "batch": len(x),
                    **latency,
                }
            )
    acceptance = {k.removesuffix("_rmse"): v for k, v in protocol["ml_acceptance"].items()}
    # Global risk acceptance: all seeds & in-domain/held-region scores; boundaries rejected.
    accepted = {}
    for target in ("european", "american"):
        for method in ("price-only", "derivative-aware"):
            subset = [
                e
                for e in entries
                if e["target"] == target
                and e["method"] == method
                and e["split"] in ("iid", "held-region")
            ]
            passed = all(
                all(e["rmse"][k] <= limit for k, limit in acceptance.items())
                and e["bounds_failures"] == 0
                and e["shape_failures"] == 0
                for e in subset
            )
            accepted[f"{target}/{method}"] = passed
    return {
        "protocol": protocol,
        "reference_gate": gate,
        "metrics": entries,
        "timings": timings,
        "generation": generation,
        "accepted": accepted,
        "device": "cpu",
        "model_directory": str(output),
        "dtype": "float64",
        "dataset": {
            "train_seed": 101,
            "train_labels": len(training_x),
            "split_labels": 256,
            "low": LOW.tolist(),
            "high": HIGH.tolist(),
        },
        "fallback": "Reference used for any unaccepted model or outside trained domain",
        "errors": export_table(rows, output / "surrogate-errors.parquet"),
        "budget": "Same data, initialization seeds, parameters, full-batch updates, "
        "epochs and derivative graph; measured wall times reported separately",
        "timing_basis": "Warm batch including normalization/autograd/output; no transfers on CPU; "
        "FD cache cleared per measured repeat; analytical price-only timing labelled",
        "limitation": "No American trading lifecycle; static share hedge errors only",
    }


def domain_allowed(x: np.ndarray, accepted: bool) -> bool:
    return bool(accepted and np.all(x >= LOW) and np.all(x <= HIGH))
