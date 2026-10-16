from fastapi.testclient import TestClient

from options_risk_lab.api import app

client = TestClient(app)


def test_curve_fixture_schema_and_invalid_inputs():
    response = client.post("/api/curves", json={})
    assert response.status_code == 200
    data = response.json()
    assert abs(data["selected"]["call"]["price"] - 10.4505835722) < 1e-9
    assert data["provenance"]["units"]["vega"] == "USD/decimal IV"
    assert len(data["rows"]) == 101
    assert client.post("/api/curves", json={"market": {"spot": -1}}).status_code == 422
    assert client.post("/api/curves", json={"low": 150, "high": 50}).status_code == 422
    assert client.post("/api/curves", json={"option": {"style": "american"}}).status_code == 422


def test_scenarios_and_hedges_have_same_assumptions_and_integer_trades():
    p = client.post("/api/portfolio", json={})
    h = client.post("/api/hedges", json={})
    assert p.status_code == 200 and h.status_code == 200
    assert p.json()["provenance"]["config_hash"] == h.json()["provenance"]["config_hash"]
    assert p.json()["selected"]["full_change"] < 0
    assert abs(p.json()["selected"]["residual"]) > 10
    assert h.json()["hedges"][-1]["status"] == "evaluated"
    assert (
        client.post("/api/portfolio", json={"surface": {"motion": "sticky-delta"}}).status_code
        == 422
    )


def test_signed_curve_basis_and_feasible_frontier():
    import pytest

    long = client.post("/api/curves", json={}).json()
    short = client.post("/api/curves", json={"basis": "signed-contracts", "quantity": -2}).json()
    assert short["selected"]["call"]["delta"] == pytest.approx(
        -200 * long["selected"]["call"]["delta"]
    )
    assert short["provenance"]["units"]["delta"] == "shares"
    frontier = client.post("/api/hedges", json={}).json()["frontier"]
    assert len(frontier) > 1
    assert all(
        a["cost"] <= b["cost"] and a["cvar"] > b["cvar"]
        for a, b in zip(frontier, frontier[1:], strict=False)
    )
    assert all(row["capital"] <= 10000 and row["cost"] <= 100 for row in frontier)


def test_report_routes_are_bounded_to_known_public_documents():
    assert client.get("/api/reports/credentials").status_code == 404
    assert client.get("/api/reports/research").status_code in (200, 404)
