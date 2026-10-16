"""Small integer candidate set: exact enumeration plus normalized local baselines."""

import itertools
import math
from typing import Any

import numpy as np
from pydantic import Field

from .contracts import Book, Market, Option, Position, Record
from .pricing import price
from .risk import Shock, Surface, assigned_market, exposures, scenario, surface_diagnostics


class HedgeConstraints(Record):
    cost_budget: float = Field(default=100, ge=0, le=10000)
    capital_budget: float = Field(default=10000, ge=0, le=1e6)
    max_options: int = Field(default=3, ge=1, le=5)
    max_shares: int = Field(default=250, ge=1, le=500)
    share_half_spread: float = Field(default=0.01, ge=0, le=1)
    option_half_spread: float = Field(default=0.05, ge=0, le=2)
    fee_per_contract: float = Field(default=0.5, ge=0, le=10)
    alpha: float = Field(default=0.95, ge=0.5, lt=1)


def cvar(losses: np.ndarray, weights: np.ndarray | None = None, alpha: float = 0.95) -> float:
    """Integrate exact worst (1-alpha) probability mass, including fractional boundary."""
    losses = np.asarray(losses, dtype=float)
    w = np.ones(len(losses)) / len(losses) if weights is None else np.asarray(weights, dtype=float)
    if losses.ndim != 1 or len(w) != len(losses) or np.any(w <= 0):
        raise ValueError("invalid CVaR observations/weights")
    if not np.isfinite(losses).all() or not np.isfinite(w).all() or not 0 <= alpha < 1:
        raise ValueError("nonfinite CVaR or invalid alpha")
    w = w / w.sum()
    order = np.argsort(-losses)
    mass = 1 - alpha
    used = np.clip(mass - np.r_[0, np.cumsum(w[order])[:-1]], 0, w[order])
    return float(losses[order] @ used / mass)


def candidates(option: Option, market: Market) -> tuple[Option, Option]:
    from datetime import timedelta

    return (
        option.model_copy(
            update={
                "id": "hedge-near-put",
                "kind": "put",
                "strike": option.strike * 0.95,
                "expiry": market.valuation_time + timedelta(days=180),
            }
        ),
        option.model_copy(
            update={
                "id": "hedge-far-call",
                "kind": "call",
                "strike": option.strike * 1.05,
                "expiry": market.valuation_time + timedelta(days=730),
            }
        ),
    )


def compare(
    book: Book,
    market: Market,
    surface: Surface,
    option: Option,
    shocks: tuple[Shock, ...],
    limits: HedgeConstraints,
) -> dict[str, Any]:
    if not shocks:
        raise ValueError("hedge objective requires scenarios")
    if len({s.days for s in shocks}) != 1:
        raise ValueError("static hedge scenarios must share one horizon")
    from datetime import timedelta

    surface_checks = []
    for s in (Shock(), *shocks):
        state = Market(
            **(
                market.model_dump()
                | {
                    "spot": market.spot * (1 + s.spot_return),
                    "valuation_time": market.valuation_time + timedelta(days=s.days),
                }
            )
        )
        for p in book.positions:
            if p.instrument.tau(state) > 0:
                check = surface_diagnostics(p.instrument, state, market, surface, s)
                surface_checks.append(check)
                if not check["passed"]:
                    raise ValueError("sampled surface price diagnostics failed; hedge rejected")
    opts = candidates(option, market)
    if any(o.id in {p.instrument.id for p in book.positions} for o in opts):
        raise ValueError("hedge IDs collide with existing book")
    horizon = shocks[0].days / 365
    funding = math.expm1(market.rate * horizon)
    dividend = math.expm1(market.yield_ * horizon) * market.spot
    base_risk = exposures(book, market, surface)
    nav = base_risk["nav"]
    base = np.array([scenario(book, market, s, surface)["full_change"] for s in shocks])
    base += book.cash * funding + book.shares * dividend - nav * funding
    mids = np.array(
        [price(o, assigned_market(o, market, market, surface)).price * o.multiplier for o in opts]
    )
    changes = np.array(
        [
            [
                scenario(Book(positions=(Position(instrument=o),)), market, s, surface)[
                    "full_change"
                ]
                for o in opts
            ]
            for s in shocks
        ]
    )
    changes -= mids * funding
    share_change = np.array(
        [market.spot * s.spot_return + dividend - market.spot * funding for s in shocks]
    )
    weights = np.array([s.weight for s in shocks], dtype=float)
    weights /= weights.sum()
    g = np.array(
        [
            [
                getattr(price(o, assigned_market(o, market, market, surface)), k) * o.multiplier
                for o in opts
            ]
            for k in ("delta", "gamma", "vega")
        ]
    )
    target = np.array([base_risk["net"][k] for k in ("delta", "gamma", "vega")], dtype=float)
    if not np.isfinite(target).all():
        raise ValueError("undefined base Greeks cannot underpin hedge recommendation")
    scale = np.array([1.0, market.spot**2, 0.01])
    matrix = np.c_[np.array([1.0, 0.0, 0.0]), g] * scale[:, None]
    condition = float(np.linalg.cond(matrix))
    rows = []

    def evaluate(
        name: str, q: np.ndarray, ideal: list[float] | None = None, status: str = "evaluated"
    ) -> dict[str, Any]:
        stock = float(q[0])
        contracts = q[1:]
        # Spreads enter entry/exit fills, once each. Flat modeled quotes at both horizons.
        opening = abs(stock) * limits.share_half_spread + float(
            np.abs(contracts)
            @ (
                np.array([o.multiplier for o in opts]) * limits.option_half_spread
                + limits.fee_per_contract
            )
        )
        roundtrip = opening * (2 + funding)
        # Gross committed notional + gross marked option liability/acquisition;
        # transparent research limit, explicitly not an exchange margin model.
        capital = abs(stock) * market.spot + float(np.abs(contracts) @ mids) + opening
        pnl = base + stock * share_change + changes @ contracts - roundtrip
        feasible = (
            opening * 2 <= limits.cost_budget + 1e-8
            and capital <= limits.capital_budget + 1e-8
            and abs(stock) <= limits.max_shares
            and np.all(np.abs(contracts) <= limits.max_options)
            and np.all(q == np.round(q))
        )
        residual = target + np.c_[np.array([1.0, 0.0, 0.0]), g] @ q
        out = {
            "name": name,
            "status": status if feasible else "infeasible",
            "quantities": q.tolist(),
            "fractional_control": ideal,
            "cost": opening * 2,
            "financed_cost": roundtrip,
            "capital": capital,
            "cvar": cvar(-pnl, weights, limits.alpha),
            "worst_loss": float(-pnl.min()),
            "pnl": pnl.tolist(),
            "residual": dict(zip(("delta", "gamma", "vega"), residual.tolist(), strict=True)),
            "trades": [
                {"id": "shares", "quantity": stock, "mid": market.spot, "multiplier": 1},
                *[
                    {
                        "id": o.id,
                        "quantity": float(n),
                        "mid": float(mid / o.multiplier),
                        "multiplier": o.multiplier,
                        "instrument": o.model_dump(mode="json"),
                    }
                    for o, n, mid in zip(opts, contracts, mids, strict=True)
                ],
            ],
        }
        return out

    rows.append(evaluate("No additional hedge", np.zeros(3)))
    rows.append(evaluate("Underlying delta", np.array([round(-target[0]), 0, 0.0])))
    if abs(g[1, 0]) < 1e-8:
        rows.append({"name": "Local delta/gamma", "status": "ill-conditioned"})
    else:
        n = -target[1] / g[1, 0]
        ideal = [-target[0] - g[0, 0] * n, n, 0.0]
        rounded = round(n)
        rows.append(
            evaluate(
                "Local delta/gamma",
                np.array([round(-target[0] - g[0, 0] * rounded), rounded, 0.0]),
                ideal,
            )
        )
    if condition > 1e8 or np.linalg.matrix_rank(matrix) < 3:
        rows.append({"name": "Local delta/gamma/vega", "status": "ill-conditioned"})
    else:
        ideal = np.linalg.lstsq(matrix, -target * scale, rcond=None)[0]
        rounded = np.rint(ideal)
        rounded[0] = round(-target[0] - g[0] @ rounded[1:])
        rows.append(evaluate("Local delta/gamma/vega", rounded, ideal.tolist()))
    best = None
    frontier_candidates: list[dict[str, Any]] = []
    # For each integer option pair, evaluate every allowed integer stock inventory;
    # no relaxed/rounded optimality claim. Bound maximum search to 121*1001.
    stocks = np.arange(-limits.max_shares, limits.max_shares + 1)
    for pair in itertools.product(range(-limits.max_options, limits.max_options + 1), repeat=2):
        contracts = np.array(pair)
        option_cost = float(
            np.abs(contracts)
            @ (
                np.array([o.multiplier for o in opts]) * limits.option_half_spread
                + limits.fee_per_contract
            )
        )
        costs = 2 * (abs(stocks) * limits.share_half_spread + option_cost)
        capitals = abs(stocks) * market.spot + float(np.abs(contracts) @ mids) + costs / 2
        feasible = (costs <= limits.cost_budget + 1e-8) & (capitals <= limits.capital_budget + 1e-8)
        choices = stocks[feasible]
        if not len(choices):
            continue
        pnl = base[None, :] + choices[:, None] * share_change + changes @ contracts
        pnl -= (abs(choices) * limits.share_half_spread + option_cost)[:, None] * (2 + funding)
        # Weighted exact CVaR after sorting each outcome row.
        losses = -pnl
        order = np.argsort(-losses, axis=1)
        sorted_w = weights[order]
        used = np.clip(
            (1 - limits.alpha) - np.c_[np.zeros(len(choices)), np.cumsum(sorted_w, axis=1)[:, :-1]],
            0,
            sorted_w,
        )
        objective = (np.take_along_axis(losses, order, axis=1) * used).sum(axis=1) / (
            1 - limits.alpha
        )
        for stock, cost, capital, risk in zip(
            choices, costs[feasible], capitals[feasible], objective, strict=True
        ):
            frontier_candidates.append(
                {
                    "cost": float(cost),
                    "cvar": float(risk),
                    "capital": float(capital),
                    "quantities": [int(stock), *pair],
                }
            )
        index = int(np.argmin(objective))
        if best is None or objective[index] < best["cvar"] - 1e-9:
            best = evaluate("Scenario CVaR", np.r_[choices[index], contracts])
    rows.append(best or {"name": "Scenario CVaR", "status": "no-feasible-solution"})
    frontier: list[dict[str, Any]] = []
    minimum = float("inf")
    for candidate in sorted(frontier_candidates, key=lambda x: (x["cost"], x["cvar"])):
        if candidate["cvar"] < minimum - 1e-8:
            frontier.append(candidate)
            minimum = candidate["cvar"]
    return {
        "surface_diagnostics": surface_checks,
        "frontier": frontier,
        "hedges": rows,
        "candidates": [
            {
                "instrument": o.model_dump(mode="json"),
                "mid": float(mid / o.multiplier),
                "half_spread": limits.option_half_spread,
                "max_size": limits.max_options,
                "quality": "synthetic-theoretical",
            }
            for o, mid in zip(opts, mids, strict=True)
        ],
        "condition": condition,
        "objective": f"Weighted conditional stress CVaR {limits.alpha:.0%}",
        "basis": "Financed mark P&L; added hedges enter/close at modeled bid/ask; costs once",
        "capital_basis": "Gross share notional + gross option premium/liability + entry cost",
        "limits": limits.model_dump(),
        "weights": weights.tolist(),
    }
