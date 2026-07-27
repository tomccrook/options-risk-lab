"""Shared service provenance and bounded curve requests."""

import hashlib
import importlib.metadata
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field

from .contracts import Book, Market, Option, Record
from .hedging import HedgeConstraints
from .pricing import price
from .risk import Shock, Surface

ENGINE = "bsm-independent-v1"
UNITS = {
    "price": "USD/share",
    "delta": "shares/share option",
    "gamma": "1/USD",
    "vega": "USD/decimal IV",
    "theta": "USD/calendar year (advancing time)",
    "rho": "USD/decimal rate",
    "vanna": "1/decimal IV",
    "volga": "USD/decimal IV²",
}


@lru_cache(maxsize=1)
def revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def provenance(config: Any) -> dict[str, Any]:
    payload = json.dumps(config, sort_keys=True, default=str, allow_nan=False)
    versions = {
        name: importlib.metadata.version(name)
        for name in (
            "numpy",
            "scipy",
            "QuantLib",
            "torch",
            "pydantic",
            "fastapi",
            "pyarrow",
            "duckdb",
        )
    }
    source = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        source.update(path.name.encode())
        source.update(path.read_bytes())
    model_extension = isinstance(config, dict) and (
        "point" in config or config.get("protocol", {}).get("id") == "model-risk-v1"
    )
    return {
        "versions": versions,
        "source_sha256": source.hexdigest(),
        "config_hash": hashlib.sha256(payload.encode()).hexdigest(),
        "engine": "european-model-risk-v1" if model_extension else ENGINE,
        "code_revision": revision(),
        "assumptions": "A01–A22/model-risk-v1" if model_extension else "A01–A16/v1",
        "data": "synthetic-v1",
        "units": UNITS,
        "pricing_basis": (
            "Synthetic RN BSM/Merton/Heston; common premiums, model-specific sensitivities"
            if model_extension
            else "BSM constant continuous carry"
        ),
        "quality": "checked numerical model study" if model_extension else "validated-analytical",
        "valuation_clock": "UTC/ACT365",
    }


class CurveRequest(Record):
    market: Market = Market()
    option: Option = Option()
    quantity: float = Field(default=1, ge=-1000, le=1000)
    basis: Literal["per-share", "signed-contracts"] = "per-share"
    low: float = Field(default=50, gt=0)
    high: float = Field(default=150, gt=0)
    points: int = Field(default=101, ge=3, le=301)
    axis: Literal["spot", "vol", "days"] = "spot"
    surface: Surface = Field(default_factory=Surface)


def curves(req: CurveRequest) -> dict[str, Any]:
    if req.low >= req.high:
        raise ValueError("curve range must increase")

    def scaled(g: Any) -> dict[str, Any]:
        result = g.model_dump()
        if req.basis == "signed-contracts":
            for k, v in result.items():
                if isinstance(v, (int, float)):
                    result[k] = v * req.quantity * req.option.multiplier
        return result

    rows = []
    from datetime import timedelta

    for x in np.linspace(req.low, req.high, req.points):
        if req.axis == "spot":
            state, option = req.market.model_copy(update={"spot": float(x)}), req.option
        elif req.axis == "vol":
            state, option = Market(**(req.market.model_dump() | {"vol": float(x)})), req.option
        else:
            state = req.market
            option = req.option.model_copy(
                update={"expiry": state.valuation_time + timedelta(days=float(x))}
            )
        row: dict[str, Any] = {"x": float(x)}
        for kind in ("call", "put"):
            from .risk import assigned_market

            anchor = state if req.axis == "vol" else req.market
            g = price(
                option.model_copy(update={"kind": kind}),
                assigned_market(option, state, anchor, req.surface),
            )
            row[kind] = scaled(g)
        rows.append(row)
    selected = {
        k: scaled(
            price(
                req.option.model_copy(update={"kind": k}),
                assigned_market(req.option, req.market, req.market, req.surface),
            )
        )
        for k in ("call", "put")
    }
    evidence = provenance(req.model_dump(mode="json"))
    if req.basis == "signed-contracts":
        evidence["units"] = UNITS | {
            "price": "USD",
            "delta": "shares",
            "gamma": "shares/USD",
            "vanna": "shares/decimal IV",
        }
        evidence["pricing_basis"] += (
            f"; signed {req.quantity:g} contracts × {req.option.multiplier:g}"
        )
    return {
        "rows": rows,
        "selected": selected,
        "config": req.model_dump(mode="json"),
        "provenance": evidence,
    }


class WorkbenchRequest(Record):
    market: Market = Market()
    option: Option = Option()
    case: str = "delta-hedged-straddle"
    book: Book | None = None
    surface: Surface = Field(default_factory=lambda: Surface())
    selected_shock: Shock = Field(
        default_factory=lambda: Shock(spot_return=0.2, vol_change=0.05, days=30)
    )
    shocks: tuple[Shock, ...] = Field(
        min_length=1,
        max_length=100,
        default_factory=lambda: tuple(
            Shock(spot_return=s, vol_change=v, days=30)
            for s in (-0.2, -0.1, 0, 0.1, 0.2)
            for v in (-0.05, 0, 0.05)
        ),
    )
    limits: HedgeConstraints = Field(default_factory=lambda: HedgeConstraints())

    def resolved_book(self) -> Book:
        from .risk import preset

        return (
            self.book
            if self.book is not None
            else preset(self.case, self.market, self.option, self.surface)
        )


def portfolio_view(req: WorkbenchRequest) -> dict[str, Any]:
    from .risk import exposures, scenario

    book = req.resolved_book()
    if len(req.shocks) > 100:
        raise ValueError("scenario budget exceeds 100 states")
    return {
        "book": book.model_dump(mode="json"),
        "risk": exposures(book, req.market, req.surface),
        "selected": scenario(book, req.market, req.selected_shock, req.surface),
        "grid": [scenario(book, req.market, s, req.surface) for s in req.shocks],
        "config": req.model_dump(mode="json"),
        "provenance": provenance(req.model_dump(mode="json")),
    }


def hedge_view(req: WorkbenchRequest) -> dict[str, Any]:
    from .hedging import compare

    return {
        **compare(req.resolved_book(), req.market, req.surface, req.option, req.shocks, req.limits),
        "config": req.model_dump(mode="json"),
        "provenance": provenance(req.model_dump(mode="json")),
    }
