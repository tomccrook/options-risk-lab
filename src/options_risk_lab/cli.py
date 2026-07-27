"""One CLI for API-equivalent services and explicit recorded research jobs."""

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import typer

from .american import convergence
from .contracts import Market, Option
from .evaluation import evaluate as evaluate_study
from .experiments import Registry
from .pricing import price as price_option
from .services import WorkbenchRequest, hedge_view, portfolio_view
from .simulation import ReplayConfig
from .simulation import simulate as run_replay

app = typer.Typer(no_args_is_help=True)


def save(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False))


def wait(registry: Registry, id_: str, alias: Path) -> None:
    typer.echo(f"Run {id_}; immutable manifest in {registry.root}")
    while True:
        job = registry.get(id_)
        if job["status"] in ("complete", "failed", "cancelled"):
            save(alias, job)
            typer.echo(f"{job['status']}: {alias}")
            if job["status"] != "complete":
                typer.echo(job["error"])
                raise typer.Exit(1)
            return
        try:
            time.sleep(0.25)
        except KeyboardInterrupt:
            registry.cancel(id_)
            typer.echo("Cancellation requested; waiting for the next safe computation boundary")


@app.command()
def validate() -> None:
    typer.echo(json.dumps(convergence(), indent=2))


@app.command()
def price(spot: float = 100, strike: float = 100, vol: float = 0.2) -> None:
    typer.echo(
        price_option(Option(strike=strike), Market(spot=spot, vol=vol)).model_dump_json(indent=2)
    )


@app.command()
def shock(config: Path | None = None) -> None:
    req = WorkbenchRequest.model_validate_json(config.read_text()) if config else WorkbenchRequest()
    typer.echo(json.dumps(portfolio_view(req), indent=2))


@app.command()
def hedge(config: Path | None = None) -> None:
    req = WorkbenchRequest.model_validate_json(config.read_text()) if config else WorkbenchRequest()
    typer.echo(json.dumps(hedge_view(req), indent=2))


@app.command()
def simulate(seed: int = 11, policy: str = "band", regime: str = "matched") -> None:
    req = WorkbenchRequest()
    config = ReplayConfig.model_validate({"seed": seed, "policy": policy, "regime": regime})
    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "replay", config.model_dump(), lambda _: run_replay(req.resolved_book(), req.market, config)
    )
    wait(registry, id_, Path("artifacts/replay.json"))


@app.command()
def evaluate(phase: str = "locked", protocol: Path = Path("configs/evaluation.json")) -> None:
    if phase not in ("locked", "development"):
        raise typer.BadParameter("phase must be development or locked")
    config = json.loads(protocol.read_text())
    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "hedge-evaluation",
        {"protocol": config, "phase": phase},
        lambda event: evaluate_study(protocol, Path("artifacts/evaluation") / phase, event, phase),
    )
    wait(registry, id_, Path("artifacts") / f"evaluation-{phase}.json")


@app.command()
def train(protocol: Path = Path("configs/evaluation.json")) -> None:
    from .ml import study

    if (
        hashlib.sha256(protocol.read_bytes()).hexdigest()
        != protocol.with_suffix(".sha256").read_text().strip()
    ):
        raise typer.BadParameter("protected ML protocol changed; register a new protocol")
    config = json.loads(protocol.read_text())
    registry = Registry(Path("artifacts/jobs"))
    output = Path("artifacts/ml") / uuid.uuid4().hex
    id_ = registry.submit("surrogate-study", config, lambda event: study(config, output, event))
    wait(registry, id_, Path("artifacts/ml-study.json"))


@app.command()
def export(output: Path = Path("artifacts/report")) -> None:
    """Verify completed study payloads and export linked tables and scientific figures."""
    from .reporting import export_evidence

    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "evidence-export", {"output": str(output)}, lambda event: export_evidence(output, event)
    )
    wait(registry, id_, Path("artifacts/evidence-export.json"))


@app.command()
def demo() -> None:
    """Generate the locked synthetic evidence locally, then export; explicit expensive command."""
    evaluate(phase="locked", protocol=Path("configs/evaluation.json"))
    train(protocol=Path("configs/evaluation.json"))
    export(output=Path("artifacts/report"))


@app.command()
def models(config: Path | None = None) -> None:
    """Compare European prices/Greeks/scenarios under explicit asset models."""
    from .model_services import ModelComparisonRequest, compare_models

    req = (
        ModelComparisonRequest.model_validate_json(config.read_text())
        if config
        else ModelComparisonRequest()
    )
    typer.echo(json.dumps(compare_models(req), indent=2))


@app.command()
def model_mc(paths: int = 16384, steps: int = 128, seed: int = 811) -> None:
    from .model_services import MonteCarloRequest, compare_mc

    req = MonteCarloRequest(paths=paths, steps=steps, seed=seed)
    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "model-monte-carlo", req.model_dump(mode="json"), lambda event: compare_mc(req, event)
    )
    wait(registry, id_, Path("artifacts/model-mc.json"))


@app.command()
def model_replay(generator: str = "heston", paths: int = 128, seed: int = 137) -> None:
    from .model_replay import ModelReplayRequest, compare_replay

    req = ModelReplayRequest.model_validate({"generator": generator, "paths": paths, "seed": seed})
    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "model-hedge-replay", req.model_dump(mode="json"), lambda event: compare_replay(req, event)
    )
    wait(registry, id_, Path("artifacts/model-replay.json"))


@app.command()
def model_evaluate(phase: str = "locked", protocol: Path = Path("configs/model-risk.json")) -> None:
    from .model_evaluation import evaluate_models, read_protocol

    config, digest = read_protocol(protocol)
    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "model-risk-evaluation",
        {"protocol": config, "protocol_sha256": digest, "phase": phase},
        lambda event: evaluate_models(protocol, Path("artifacts/model-risk") / phase, event, phase),
    )
    wait(registry, id_, Path("artifacts") / f"model-risk-{phase}.json")


@app.command()
def model_export(output: Path = Path("artifacts/model-report")) -> None:
    from .model_reporting import export_models

    registry = Registry(Path("artifacts/jobs"))
    id_ = registry.submit(
        "model-evidence-export", {"output": str(output)}, lambda event: export_models(output, event)
    )
    wait(registry, id_, Path("artifacts/model-export.json"))
