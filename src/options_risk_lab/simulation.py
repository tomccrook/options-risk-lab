"""Causal node decisions, self-financing arrays; replay exposes every cash movement."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from pydantic import Field

from .contracts import Book, Market, Record
from .pricing import batch_price_delta
from .risk import DEFAULT_SURFACE, Surface


class ReplayConfig(Record):
    seed: int = Field(default=11, ge=0, le=2**32 - 1)
    paths: int = Field(default=128, ge=1, le=10000)
    steps: int = Field(default=126, ge=4, le=1008)
    policy: Literal["none", "daily", "weekly", "monthly", "band"] = "band"
    band: float = Field(default=10, ge=0, le=100)
    share_half_spread: float = Field(default=0.01, ge=0, le=1)
    fee_per_trade: float = Field(default=0, ge=0, le=10)
    option_half_spread: float = Field(default=0.05, ge=0, le=1)
    delay_nodes: int = Field(default=0, ge=0, le=5)
    regime: Literal["matched", "physical", "misspecified", "jump-delay", "joint-vol"] = "matched"
    physical_drift: float = Field(default=0.08, ge=-0.2, le=0.5)
    realised_vol: float = Field(default=0.3, gt=0, le=1)
    jump: float = Field(default=-0.2, gt=-1, le=1)
    max_shares: int = Field(default=250, ge=1, le=1000)
    capital_limit: float = Field(default=25000, gt=0, le=1e6)


@dataclass(frozen=True)
class Observation:
    node: int
    delta: np.ndarray
    shares: np.ndarray
    pending: np.ndarray


def decision(observed: Observation, policy: str, band: float) -> tuple[np.ndarray, np.ndarray]:
    """Policy boundary has only present observations; no path or generator object."""
    target = np.rint(-observed.delta)
    if policy == "none":
        trade = np.zeros(len(target), dtype=bool)
    elif policy == "band":
        trade = np.abs(target - observed.shares) >= band
    else:
        frequency = {"daily": 1, "weekly": 5, "monthly": 21}[policy]
        trade = np.full(len(target), observed.node % frequency == 0)
    return target, trade & ~observed.pending & (target != observed.shares)


def paths(config: ReplayConfig, market: Market, horizon: float) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(config.seed)
    dt = horizon / config.steps
    realised = (
        market.vol
        if config.regime in ("matched", "physical", "jump-delay", "joint-vol")
        else config.realised_vol
    )
    drift = config.physical_drift if config.regime == "physical" else market.rate - market.yield_
    z = rng.standard_normal((config.paths, config.steps))
    increments = (drift - realised**2 / 2) * dt + realised * math.sqrt(dt) * z
    log_spot = np.c_[np.zeros(config.paths), np.cumsum(increments, axis=1)]
    if config.regime == "jump-delay":
        log_spot[:, config.steps // 2 :] += math.log1p(config.jump)
    spot = market.spot * np.exp(log_spot)
    iv = np.full_like(spot, market.vol)
    if config.regime == "joint-vol":
        iv = np.clip(market.vol * np.exp(-0.4 * log_spot), 0.01, 1.0)
    return spot, iv


def simulate(
    book: Book,
    market: Market,
    config: ReplayConfig,
    observed_paths: tuple[np.ndarray, np.ndarray] | None = None,
    surface: Surface = DEFAULT_SURFACE,
    valuation: Callable[[str, np.ndarray, float, float, np.ndarray], tuple[np.ndarray, np.ndarray]]
    | None = None,
    model_label: str = "BSM",
) -> dict[str, Any]:
    maturities = {p.instrument.tau(market) for p in book.positions if p.quantity != 0}
    if len(maturities) != 1 or min(maturities) <= 0:
        raise ValueError("dynamic replay requires a live single-expiry European book")
    horizon = maturities.pop()
    spot, iv = paths(config, market, horizon) if observed_paths is None else observed_paths
    if spot.shape != (config.paths, config.steps + 1) or iv.shape != spot.shape:
        raise ValueError("path dimensions do not match replay config")
    if (
        not np.isfinite(spot).all()
        or not np.isfinite(iv).all()
        or np.any(spot <= 0)
        or np.any(iv < 0 if valuation is not None else iv <= 0)
    ):
        raise ValueError("invalid observable path")
    if not np.allclose(spot[:, 0], market.spot) or not np.allclose(iv[:, 0], market.vol):
        raise ValueError("all paths must start from the declared observable market")

    def contract_vol(strike: float, node: int, tau: float) -> np.ndarray:
        if surface.motion == "flat":
            return iv[:, node]
        if surface.motion == "frozen-strike":
            forward = market.spot * math.exp((market.rate - market.yield_) * horizon)
        else:
            forward = spot[:, node] * np.exp((market.rate - market.yield_) * max(tau, 0))
        assigned = (
            iv[:, node] + surface.skew * np.log(strike / forward) + surface.term * (max(tau, 0) - 1)
        )
        if np.any(assigned < 0.005) or np.any(assigned > 2):
            raise ValueError("invalid synthetic surface during replay")
        return assigned

    def marks_delta(p: Any, node: int, tau: float) -> tuple[np.ndarray, np.ndarray]:
        if valuation is not None:
            mark, delta = valuation(
                p.instrument.kind, spot[:, node], p.instrument.strike, tau, iv[:, node]
            )
            if mark.shape != (config.paths,) or delta.shape != mark.shape:
                raise ValueError("custom valuation dimensions do not match paths")
            if not np.isfinite(mark).all() or not np.isfinite(delta).all():
                raise ArithmeticError("nonfinite custom valuation; replay rejected")
            return mark, delta
        return batch_price_delta(
            spot[:, node],
            p.instrument.strike,
            tau,
            contract_vol(p.instrument.strike, node, tau),
            market.rate,
            market.yield_,
            p.instrument.kind,
        )

    n = config.paths
    allocated = book.cash + book.shares * market.spot
    initial_option = 0.0
    for p in book.positions:
        mark, _ = marks_delta(p, 0, horizon)
        initial_option += float(mark[0]) * p.quantity * p.instrument.multiplier
    allocated += initial_option
    cash = np.full(n, allocated - initial_option - book.shares * market.spot, dtype=float)
    shares = np.full(n, book.shares, dtype=float)
    option_entry_cost = sum(
        abs(p.quantity) * p.instrument.multiplier * config.option_half_spread
        for p in book.positions
    )
    costs = np.full(n, option_entry_cost + abs(book.shares) * config.share_half_spread, dtype=float)
    cash -= costs
    turnover = np.full(n, abs(book.shares), dtype=float)
    trades = np.full(n, int(book.shares != 0))
    pending_target = np.zeros(n)
    due = np.full(n, -1, dtype=int)
    trace = []
    rejected = np.zeros(n, dtype=int)
    max_delta = np.zeros(n)
    dt = horizon / config.steps
    for node in range(config.steps + 1):
        funding = np.zeros(n)
        dividends = np.zeros(n)
        if node:
            funding = cash * np.expm1(market.rate * dt)
            dividends = shares * spot[:, node - 1] * np.expm1(market.yield_ * dt)
            cash += funding + dividends
        delta = np.zeros(n)
        option_value = np.zeros(n)
        for p in book.positions:
            mark, d = marks_delta(p, node, max(0, horizon - node * dt))
            option_value += mark * p.quantity * p.instrument.multiplier
            delta += d * p.quantity * p.instrument.multiplier
        risk_before = delta + shares
        max_delta = np.maximum(max_delta, np.abs(risk_before))
        request = np.zeros(n)
        filled = np.zeros(n)
        paid = np.zeros(n)
        # Outstanding target executes at eligible later quote, before new decisions.
        eligible = (due == node) & (node < config.steps)
        feasible_fill = (np.abs(pending_target) <= config.max_shares) & (
            np.abs(pending_target) * spot[:, node] + np.abs(option_value) <= config.capital_limit
        )
        rejected += eligible & ~feasible_fill
        due[eligible & ~feasible_fill] = -1
        eligible &= feasible_fill
        filled[eligible] = pending_target[eligible] - shares[eligible]
        due[eligible] = -1
        if node < config.steps:
            target, wants = decision(
                Observation(node, delta, shares + filled, due >= 0), config.policy, config.band
            )
            feasible = (np.abs(target) <= config.max_shares) & (
                np.abs(target) * spot[:, node] + np.abs(option_value) <= config.capital_limit
            )
            rejected += wants & ~feasible
            wants &= feasible
            request[wants] = target[wants] - (shares[wants] + filled[wants])
            delay = config.delay_nodes
            if delay == 0:
                filled[wants] += request[wants]
            else:
                pending_target[wants] = target[wants]
                due[wants] = node + delay
        else:
            # Cash settlement, then paid stock liquidation. Outstanding orders expire.
            cash += option_value
            option_value[:] = 0.0
            filled = -shares.copy()
            due[:] = -1
        paid = np.abs(filled) * config.share_half_spread + (filled != 0) * config.fee_per_trade
        cash -= filled * spot[:, node] + paid
        shares += filled
        costs += paid
        turnover += np.abs(filled)
        trades += filled != 0
        nav = cash + shares * spot[:, node] + option_value
        trace.append(
            {
                "node": node,
                "days": node * dt * 365,
                "spot": float(spot[0, node]),
                "iv": float(iv[0, node]),
                "request": float(request[0]),
                "fill": float(filled[0]),
                "execution_mid": float(spot[0, node]),
                "cost": float(paid[0]),
                "funding": float(funding[0]),
                "dividend": float(dividends[0]),
                "shares": float(shares[0]),
                "cash": float(cash[0]),
                "option_value": float(option_value[0]),
                "nav": float(nav[0]),
                "delta_before": float(risk_before[0]),
                "delta_after": float(delta[0] + shares[0]) if node < config.steps else None,
            }
        )
    error = cash - allocated * math.exp(market.rate * horizon)
    return {
        "financed_error": error.tolist(),
        "raw_pnl": (cash - allocated).tolist(),
        "rejected_requests": rejected.tolist(),
        "max_abs_delta": max_delta.tolist(),
        "surface": surface.model_dump(),
        "delta_basis": model_label + "; observable present inputs only",
        "initial_option_entry_cost": option_entry_cost,
        "costs": costs.tolist(),
        "turnover": turnover.tolist(),
        "trades": trades.tolist(),
        "trace": trace,
        "allocated": allocated,
        "funding_benchmark": allocated * math.exp(market.rate * horizon),
        "generator": config.regime,
        "config": config.model_dump(),
        "terminal_inventory": {"shares": 0, "options": 0},
        "quality": "synthetic-causal; single-expiry cash settlement",
    }
