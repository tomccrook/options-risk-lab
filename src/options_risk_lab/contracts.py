"""Canonical units: years ACT/365, decimal annual rates/vol, per-share marks."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EPOCH = datetime(2026, 10, 4, tzinfo=UTC)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Market(Record):
    valuation_time: datetime = EPOCH
    spot: float = Field(default=100, gt=0, le=1e7)
    vol: float = Field(default=0.2, ge=0, le=3)
    rate: float = Field(default=0.05, ge=-0.2, le=1)
    yield_: float = Field(default=0, ge=-0.2, le=1)

    @model_validator(mode="after")
    def aware(self) -> Market:
        if self.valuation_time.tzinfo is None:
            raise ValueError("valuation_time must include timezone")
        return self


class Option(Record):
    id: str = "call-100"
    underlying: Literal["SYNTH"] = "SYNTH"
    currency: Literal["USD"] = "USD"
    strike: float = Field(default=100, gt=0, le=1e7)
    expiry: datetime = EPOCH + timedelta(days=365)
    kind: Literal["call", "put"] = "call"
    style: Literal["european"] = "european"
    settlement: Literal["cash"] = "cash"
    lifecycle: Literal["open"] = "open"
    multiplier: int = Field(default=100, ge=1, le=10000)

    @model_validator(mode="after")
    def aware(self) -> Option:
        if self.expiry.tzinfo is None:
            raise ValueError("expiry must include timezone")
        return self

    def tau(self, market: Market) -> float:
        return max(0, (self.expiry - market.valuation_time).total_seconds() / (365 * 86400))


class Position(Record):
    instrument: Option
    quantity: float = Field(default=1, ge=-1000, le=1000)


class Book(Record):
    positions: tuple[Position, ...] = ()
    shares: float = Field(default=0, ge=-1e6, le=1e6)
    cash: float = Field(default=0, ge=-1e9, le=1e9)

    @model_validator(mode="after")
    def unique(self) -> Book:
        ids = [p.instrument.id for p in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError("position instrument IDs must be unique")
        return self


class Greeks(Record):
    price: float
    delta: float | None
    gamma: float | None
    vega: float | None
    theta: float | None
    rho: float | None
    vanna: float | None
    volga: float | None
    quality: Literal["analytical", "deterministic-limit", "expiry", "undefined-kink"]
