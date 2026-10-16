from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .benchmark import ProbeRequest
from .contracts import Market, Option, Record
from .experiments import Registry, metrics
from .model_replay import ModelReplayRequest
from .model_services import ModelComparisonRequest, MonteCarloRequest
from .pricing import price
from .responses import AssetModelComparison, ComparisonResponse, CurveResponse, PortfolioResponse
from .services import CurveRequest, WorkbenchRequest, curves, hedge_view, portfolio_view, provenance
from .simulation import ReplayConfig, simulate

app = FastAPI(title="Options Risk and Hedging Laboratory", version="0.1.0")


@lru_cache(maxsize=1)
def registry() -> Registry:
    return Registry(Path("artifacts/jobs"))


def guarded(operation: Any, req: Any) -> dict[str, Any]:
    try:
        return operation(req)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "data": "synthetic"}


@app.post("/api/curves", response_model=CurveResponse)
def curve_endpoint(req: CurveRequest) -> dict[str, Any]:
    return guarded(curves, req)


class PriceRequest(Record):
    market: Market = Market()
    option: Option = Option()


@app.post("/api/price")
def price_endpoint(req: PriceRequest) -> dict[str, Any]:
    return {
        "value": price(req.option, req.market).model_dump(),
        "provenance": provenance(req.model_dump(mode="json")),
    }


@app.post("/api/portfolio", response_model=PortfolioResponse)
def portfolio_endpoint(req: WorkbenchRequest) -> dict[str, Any]:
    return guarded(portfolio_view, req)


@app.post("/api/hedges", response_model=ComparisonResponse, response_model_exclude_none=True)
def hedge_endpoint(req: WorkbenchRequest) -> dict[str, Any]:
    return guarded(hedge_view, req)


@app.post("/api/comparisons")
def save_comparison(req: WorkbenchRequest) -> dict[str, str]:
    # Snapshot before queueing, so later changes cannot alter saved assumptions.
    result = guarded(hedge_view, req)
    id_ = registry().submit("saved-comparison", req.model_dump(mode="json"), lambda _: result)
    return {"id": id_}


class ReplayRequest(Record):
    workbench: WorkbenchRequest = WorkbenchRequest()
    replay: ReplayConfig = ReplayConfig()


@app.post("/api/jobs/replay")
def replay_job(req: ReplayRequest) -> dict[str, str]:
    def operation(event: Any) -> dict[str, Any]:
        import numpy as np

        w = req.workbench
        result = simulate(w.resolved_book(), w.market, req.replay, surface=w.surface)
        counts, edges = np.histogram(result["financed_error"], bins=20)
        result["distribution"] = [
            {"error_usd": float((a + b) / 2), "count": int(count)}
            for a, b, count in zip(edges[:-1], edges[1:], counts, strict=True)
        ]
        result["metrics"] = metrics(
            np.array(result["financed_error"]),
            np.array(result["costs"]),
            np.array(result["turnover"]),
        )
        result["provenance"] = provenance(req.model_dump(mode="json"))
        return result

    id_ = registry().submit("replay", req.model_dump(mode="json"), operation)
    return {"id": id_}


@app.get("/api/jobs/{id_}")
def job_status(id_: str) -> dict[str, Any]:
    try:
        return registry().get(id_)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/jobs/{id_}/cancel")
def cancel_job(id_: str) -> dict[str, Any]:
    try:
        return registry().cancel(id_)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/evidence/{kind}")
def evidence_endpoint(kind: str) -> dict[str, Any]:
    from .benchmark import evidence

    if kind not in ("evaluation", "ml", "model-risk"):
        raise HTTPException(404, "unknown evidence kind")
    try:
        return evidence(kind)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/model-probe")
def probe_endpoint(req: ProbeRequest) -> dict[str, Any]:
    from .benchmark import probe

    return guarded(probe, req)


@app.post("/api/jobs/export")
def export_job() -> dict[str, str]:
    from .reporting import export_evidence

    id_ = registry().submit(
        "evidence-export",
        {"output": "artifacts/report"},
        lambda event: export_evidence(Path("artifacts/report"), event),
    )
    return {"id": id_}


@app.get("/api/reports/{name}")
def report_download(name: str) -> FileResponse:
    files = {
        "research": "research-report.md",
        "ml": "ml-report.md",
        "interview": "interview.md",
        "models": "model-risk-report.md",
    }
    if name not in files:
        raise HTTPException(404, "unknown report")
    path = Path("docs") / files[name]
    if not path.exists():
        raise HTTPException(404, "report not generated")
    return FileResponse(path, media_type="text/markdown", filename=files[name])


@app.post("/api/models/compare", response_model=AssetModelComparison)
def model_comparison_endpoint(req: ModelComparisonRequest) -> dict[str, Any]:
    from .model_services import compare_models

    return guarded(compare_models, req)


@app.post("/api/jobs/model-mc")
def model_mc_job(req: MonteCarloRequest) -> dict[str, str]:
    from .model_services import compare_mc

    id_ = registry().submit(
        "model-monte-carlo", req.model_dump(mode="json"), lambda event: compare_mc(req, event)
    )
    return {"id": id_}


@app.post("/api/jobs/model-replay")
def model_replay_job(req: ModelReplayRequest) -> dict[str, str]:
    from .model_replay import compare_replay

    id_ = registry().submit(
        "model-hedge-replay", req.model_dump(mode="json"), lambda event: compare_replay(req, event)
    )
    return {"id": id_}
