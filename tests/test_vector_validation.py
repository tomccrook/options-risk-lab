import numpy as np
import pytest

from options_risk_lab.pricing import bsm, vector_price, vector_price_greeks


def test_vector_control_rejects_unknown_option_kind():
    with pytest.raises(ValueError, match="option kind"):
        vector_price(np.array([[1.0, 1.0, 0.2, 0.05, 0.0]]), kind="calls")


@pytest.mark.parametrize("control", [vector_price, vector_price_greeks])
@pytest.mark.parametrize("column", range(5))
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_vector_controls_reject_nonfinite_rows(control, column, bad):
    values = np.array([[1.0, 1.0, 0.2, 0.05, 0.0]])
    values[0, column] = bad
    with pytest.raises(ValueError, match="finite"):
        control(values)


@pytest.mark.parametrize("control", [vector_price, vector_price_greeks])
def test_vector_controls_require_five_columns(control):
    with pytest.raises(ValueError, match="five columns"):
        control(np.ones((2, 4)))


def test_vector_control_prices_and_greeks_match_independent_scalar_path():
    rows = np.array([[0.8, 0.25, 0.4, -0.01, 0.02], [1.0, 1.0, 0.2, 0.05, 0.0]])
    for kind in ("call", "put"):
        expected = [bsm(m * 100, 100, t, v, r, q, kind).price for m, t, v, r, q in rows]
        np.testing.assert_allclose(vector_price(rows, kind) * 100, expected, atol=1e-12)
    expected_greeks = [bsm(m * 100, 100, t, v, r, q, "put") for m, t, v, r, q in rows]
    np.testing.assert_allclose(
        vector_price_greeks(rows),
        [[g.price, g.delta, g.gamma, g.vega] for g in expected_greeks],
        atol=1e-12,
    )
