"""Cash ledger: fills move cash once. Midpoint marks never deduct spreads again."""

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fill:
    instrument_id: str
    quantity: float
    price: float
    multiplier: int = 1
    fee: float = 0

    def __post_init__(self) -> None:
        if not all(math.isfinite(x) for x in (self.quantity, self.price, self.fee)):
            raise ValueError("nonfinite fill")
        if self.price < 0 or self.fee < 0 or self.multiplier < 1:
            raise ValueError("invalid fill")


@dataclass
class Ledger:
    cash: float
    inventory: dict[str, float] = field(default_factory=dict)
    multipliers: dict[str, int] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)

    def trade(self, fill: Fill) -> None:
        if fill.instrument_id in self.multipliers:
            if self.multipliers[fill.instrument_id] != fill.multiplier:
                raise ValueError("multiplier changed")
        self.cash -= fill.quantity * fill.multiplier * fill.price + fill.fee
        self.inventory[fill.instrument_id] = (
            self.inventory.get(fill.instrument_id, 0) + fill.quantity
        )
        self.multipliers[fill.instrument_id] = fill.multiplier
        self.fills.append(fill)

    def nav(self, marks: dict[str, float]) -> float:
        return self.cash + sum(
            q * self.multipliers[k] * marks[k] for k, q in self.inventory.items() if q != 0
        )

    def accrue(self, dt: float, rate: float, spot: float, yield_: float = 0) -> dict[str, float]:
        if dt < 0:
            raise ValueError("cannot fund backwards")
        funding = self.cash * math.expm1(rate * dt)
        dividend = self.inventory.get("shares", 0) * spot * math.expm1(yield_ * dt)
        self.cash += funding + dividend
        return {"funding": funding, "dividend": dividend}

    def settle(self, instrument_id: str, payoff: float) -> None:
        if payoff < 0 or not math.isfinite(payoff):
            raise ValueError("invalid payoff")
        self.cash += self.inventory[instrument_id] * self.multipliers[instrument_id] * payoff
        self.inventory[instrument_id] = 0
