"""Validated API output boundaries; unavailable sensitivities remain explicit nulls."""

from typing import Any, Literal

from .contracts import Book, Greeks, Record
from .risk import Shock


class Provenance(Record):
    config_hash: str
    engine: str
    code_revision: str
    assumptions: str
    data: str
    units: dict[str, str]
    pricing_basis: str
    quality: str
    valuation_clock: str
    versions: dict[str, str]
    source_sha256: str


class CurvePoint(Record):
    x: float
    call: Greeks
    put: Greeks


class CurveResponse(Record):
    rows: list[CurvePoint]
    selected: dict[str, Greeks]
    config: dict[str, Any]
    provenance: Provenance


class ScenarioResponse(Record):
    shock: Shock
    spot: float
    option_change: float
    share_change: float
    full_change: float
    approximation: float | None
    residual: float | None
    terms: dict[str, float]
    quality: str
    basis: str


class ExposureResponse(Record):
    net: dict[str, float | None]
    gross: dict[str, float]
    positions: list[dict[str, Any]]
    shares: float
    cash: float
    nav: float
    vega_per_vol_point: float
    return_scale_gamma: float
    total_surface_delta: float
    partial_basis: str
    quality: str


class PortfolioResponse(Record):
    book: Book
    risk: ExposureResponse
    selected: ScenarioResponse
    grid: list[ScenarioResponse]
    config: dict[str, Any]
    provenance: Provenance


class Trade(Record):
    id: str
    quantity: float
    mid: float
    multiplier: int
    instrument: dict[str, Any] | None = None


class HedgeResponse(Record):
    name: str
    status: Literal["evaluated", "infeasible", "ill-conditioned", "no-feasible-solution"]
    quantities: list[float] | None = None
    fractional_control: list[float] | None = None
    cost: float | None = None
    financed_cost: float | None = None
    capital: float | None = None
    cvar: float | None = None
    worst_loss: float | None = None
    pnl: list[float] | None = None
    residual: dict[str, float] | None = None
    trades: list[Trade] | None = None


class ComparisonResponse(Record):
    frontier: list[dict[str, Any]]
    surface_diagnostics: list[dict[str, Any]]
    hedges: list[HedgeResponse]
    candidates: list[dict[str, Any]]
    condition: float
    objective: str
    basis: str
    capital_basis: str
    limits: dict[str, Any]
    weights: list[float]
    config: dict[str, Any]
    provenance: Provenance


class AssetModelRow(Record):
    model: Literal["bsm", "merton", "heston"]
    label: str
    price: float
    delta: float
    gamma: float
    vega: float
    vega_basis: str
    parameters: dict[str, float]
    reference_ms: float


class AssetModelComparison(Record):
    config: dict[str, Any]
    rows: list[AssetModelRow]
    curves: list[dict[str, float]]
    scenarios: list[dict[str, Any]]
    numerical_checks: list[dict[str, Any]]
    total_ms: float
    units: dict[str, str]
    basis: str
    warning: str
    provenance: Provenance
