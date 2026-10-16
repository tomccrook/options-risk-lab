import math
import threading

import numpy as np
import pytest

from options_risk_lab.experiments import Cancelled
from options_risk_lab.ledger import Fill, Ledger
from options_risk_lab.model_replay import HEDGERS, ModelReplayRequest, precompute, replay_one
from options_risk_lab.model_services import ModelComparisonRequest, compare_models
from options_risk_lab.models import ModelPoint, checked_heston_batch, quantlib_heston


def test_checked_heston_refines_short_expiry_deep_tail_without_clipping():
    point = ModelPoint(spot=200, tau=1 / 365)
    out, quality = checked_heston_batch(
        np.array([200.0]), 100, point.tau, point.parameters, 0.05, 0
    )
    assert quality["adaptive_refinements"] == 1
    assert out[0][0] == pytest.approx(quantlib_heston(point), abs=1e-7)
    assert out[1][0] == pytest.approx(1, abs=1e-7)


def test_paid_model_hedges_have_common_premium_and_independently_reconcile_cash():
    req = ModelReplayRequest(paths=8, steps=16, half_spread=0.03, delay=1)
    data = precompute(req)
    premiums = []
    for hedger in HEDGERS:
        result = replay_one(req, data, hedger)
        premiums.append(result["option_entry_premium"])
        ledger = Ledger(10000)
        call = float(data["marks"][0, 0])
        put = call - req.point.spot + req.point.strike * math.exp(-req.point.rate * req.point.tau)
        ledger.trade(Fill("call", -1, call - 0.05, 100))
        ledger.trade(Fill("put", -1, put - 0.05, 100))
        for node, row in enumerate(result["trace"]):
            if node:
                ledger.accrue(
                    req.point.tau / req.steps,
                    req.point.rate,
                    result["trace"][node - 1]["spot"],
                    req.point.yield_,
                )
            if node == req.steps:
                ledger.settle("call", max(row["spot"] - req.point.strike, 0))
                ledger.settle("put", max(req.point.strike - row["spot"], 0))
            if row["fill"]:
                ledger.trade(
                    Fill(
                        "shares",
                        row["fill"],
                        row["spot"] + math.copysign(req.half_spread, row["fill"]),
                    )
                )
            assert row["cash"] == pytest.approx(ledger.cash, abs=1e-8)
            assert row["nav"] == pytest.approx(
                row["cash"] + row["shares"] * row["spot"] + row["option_value"], abs=1e-10
            )
        assert ledger.cash - result["funding_benchmark"] == pytest.approx(
            result["financed_error"][0], abs=1e-8
        )
        assert result["allocated"] == pytest.approx(10000, abs=1e-8)
        assert result["terminal_inventory"] == {"shares": 0, "options": 0}
        assert result["costs"][0] >= 10
    assert max(premiums) - min(premiums) < 1e-10


def test_model_hedge_prefix_causality_and_cancellation():
    req = ModelReplayRequest(paths=8, steps=16)
    original = precompute(req)
    spots = original["spot"].copy()
    variance = original["variance"].copy()
    spots[:, 9:] *= 0.8
    variance[:, 9:] *= 1.5
    changed = precompute(req, observed=(spots, variance))
    a = replay_one(req, original, "heston-minvariance")
    b = replay_one(req, changed, "heston-minvariance")
    assert a["trace"][:9] == b["trace"][:9]
    # Every delayed fill is a past request, executed at today's price.
    for node, row in enumerate(a["trace"][1:-1], start=1):
        if row["fill"]:
            assert row["fill"] == pytest.approx(a["trace"][node - 1]["request"])
    event = threading.Event()
    event.set()
    with pytest.raises(Cancelled):
        precompute(req, event)


def test_model_service_price_matching_curves_and_scenario_units():
    result = compare_models(ModelComparisonRequest())
    prices = [r["price"] for r in result["rows"]]
    assert max(prices) - min(prices) < 1e-8
    assert len(result["curves"]) == 41 and len(result["scenarios"]) == 15
    assert "model-specific" in result["units"]["vega"]
    assert result["provenance"]["engine"] == "european-model-comparison-v1"
    assert all(abs(r["price_error"]) < 1e-5 for r in result["numerical_checks"])


def test_model_api_typed_boundary_and_protected_protocol(tmp_path):
    from fastapi.testclient import TestClient

    from options_risk_lab.api import app
    from options_risk_lab.model_evaluation import read_protocol
    from options_risk_lab.models import ModelParameters

    client = TestClient(app)
    response = client.post("/api/models/compare", json={})
    assert response.status_code == 200 and len(response.json()["rows"]) == 3
    assert client.post("/api/models/compare", json={"point": {"spot": -1}}).status_code == 422
    assert client.post("/api/jobs/model-mc", json={"paths": 1025}).status_code == 422
    result = compare_models(
        ModelComparisonRequest(point=ModelPoint(parameters=ModelParameters(vol_of_vol=0)))
    )
    assert result["rows"][2]["price"] == pytest.approx(result["rows"][0]["price"], abs=1e-8)
    path = tmp_path / "protocol.json"
    path.write_text("{}")
    path.with_suffix(".sha256").write_text("bad")
    with pytest.raises(ValueError, match="Protected"):
        read_protocol(path)


def test_model_replay_rejects_negative_entry_bid():
    # Construct a present observable book with common marks below the declared half-spread.
    req = ModelReplayRequest(paths=8, steps=8)
    data = precompute(req)
    data["marks"][:, 0] = 0.01
    with pytest.raises(ValueError, match="negative entry bid"):
        replay_one(req, data, "bsm-fixed")
