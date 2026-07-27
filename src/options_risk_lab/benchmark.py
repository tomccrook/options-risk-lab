"""Display/evaluation adapter; no approximate engine enters trading by default."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field

from .contracts import Record


class ProbeRequest(Record):
    target: Literal["european", "american"] = "american"
    method: Literal["price-only", "derivative-aware"] = "derivative-aware"
    m: float = Field(default=1, ge=0.1, le=3)
    tau: float = Field(default=1, ge=1 / 365, le=5)
    vol: float = Field(default=0.2, ge=0.02, le=1.4)
    rate: float = Field(default=0.05, ge=-0.1, le=0.5)
    yield_: float = Field(default=0, ge=0, le=0.2)


def evidence(kind: str) -> dict[str, Any]:
    path = {
        "evaluation": Path("artifacts/evaluation-locked.json"),
        "ml": Path("artifacts/ml-study.json"),
        "model-risk": Path("artifacts/model-risk-locked.json"),
    }[kind]
    if not path.exists():
        raise FileNotFoundError(f"{kind} study not run; use documented CLI command")
    job = json.loads(path.read_text())
    if job["status"] != "complete":
        raise ValueError(f"{kind} study {job['status']}: {job['error']}")
    return {
        **job["result"],
        "run_id": job["id"],
        "provenance": job["manifest"]["provenance"],
        "manifest": job["manifest"],
    }


def probe(req: ProbeRequest) -> dict[str, Any]:
    total_start = time.perf_counter()
    import torch

    from .american import labels, reference
    from .ml import Surrogate, control_labels, domain_allowed, error_metrics, greeks

    torch.set_num_threads(1)
    x = np.array([[req.m, req.tau, req.vol, req.rate, req.yield_]])
    labeler = control_labels if req.target == "european" else labels
    reference.cache_clear()
    start = time.perf_counter()
    actual = labeler(x)[0]
    reference_ms = (time.perf_counter() - start) * 1000
    raw = None
    accepted = False
    reason = "No completed study/model; reference engine used"
    model_ms = None
    try:
        result = evidence("ml")
        key = f"{req.target}/{req.method}"
        path = Path(result["model_directory"]) / f"{req.target}-{req.method}-17.pt"
        model_record = next(
            g
            for g in result["generation"]
            if g.get("target") == req.target
            and g.get("method") == req.method
            and g.get("seed") == 17
        )
        if hashlib.sha256(path.read_bytes()).hexdigest() != model_record.get("model_sha256"):
            raise ValueError("Model payload has no matching recorded hash; reference used")
        model = Surrogate(result["protocol"]["ml_width"], result["protocol"]["ml_depth"])
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        model.eval()
        start = time.perf_counter()
        raw = greeks(model, x)[0]
        model_ms = (time.perf_counter() - start) * 1000
        accepted = domain_allowed(x, result["accepted"][key])
        reason = (
            "Accepted in trained domain" if accepted else "Rejected global accuracy gate or OOD"
        )
        checks = error_metrics(raw[None, :], actual[None, :], x, req.target)
        if checks["bounds_failures"] or checks["shape_failures"]:
            accepted = False
            reason = "Shape/bound violation; reference used"
    except (FileNotFoundError, ValueError, KeyError) as exc:
        reason = str(exc)
    active = raw if accepted and raw is not None else actual
    return {
        "input": req.model_dump(),
        "reference": actual.tolist(),
        "raw_surrogate": raw.tolist() if raw is not None else None,
        "active": active.tolist(),
        "engine": "surrogate" if accepted else "reference",
        "reason": reason,
        "total_ms": (time.perf_counter() - total_start) * 1000,
        "quality": "Numerical FD; exercise/boundary Greeks may need a finer mesh"
        if req.target == "american"
        else "analytical",
        "reference_ms": reference_ms,
        "raw_inference_ms": model_ms,
        "K": 100,
        "units": ["USD/share", "share delta", "1/USD gamma", "USD/decimal IV vega"],
        "lifecycle": "American pricing/risk study only; no assignment simulation",
    }
