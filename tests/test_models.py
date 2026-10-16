import math

import numpy as np
import pytest

from options_risk_lab.model_mc import monte_carlo, sample_paths
from options_risk_lab.models import (
    ModelParameters,
    ModelPoint,
    fourier_batch,
    matched_parameters,
    quantlib_heston,
    values,
)
from options_risk_lab.pricing import bsm


def test_merton_mixture_independent_fourier_and_zero_jump_control():
    for spot, days, kind in [(70.0, 30, "put"), (100.0, 365, "call"), (130.0, 730, "put")]:
        point = ModelPoint(spot=spot, tau=days / 365, kind=kind)
        result = values("merton", point)
        reference = fourier_batch(
            np.array([spot]),
            100,
            point.tau,
            point.parameters,
            0.05,
            0,
            "merton",
            kind=kind,
            order=64,
        )
        assert result[:3] == pytest.approx([x[0] for x in reference[:3]], abs=1e-8)
    point = ModelPoint(parameters=ModelParameters(intensity=0))
    assert values("merton", point) == pytest.approx(values("bsm", point), abs=1e-12)


def test_heston_independent_quantlib_convergence_parity_and_bumps():
    for spot, days in [(70, 7), (85, 30), (100, 365), (130, 730)]:
        point = ModelPoint(spot=spot, tau=days / 365)
        coarse, fine = values("heston", point, 32), values("heston", point, 64)
        assert coarse == pytest.approx(fine, abs=1e-5)
        assert fine[0] == pytest.approx(quantlib_heston(point), abs=1e-7)
        h = 0.01
        up = values("heston", point.model_copy(update={"spot": spot + h}), 64)[0]
        dn = values("heston", point.model_copy(update={"spot": spot - h}), 64)[0]
        assert fine[1] == pytest.approx((up - dn) / (2 * h), abs=1e-7)
        assert fine[2] == pytest.approx((up - 2 * fine[0] + dn) / h**2, abs=1e-7)
        v = math.sqrt(point.parameters.v0)
        upv = values(
            "heston",
            point.model_copy(
                update={"parameters": point.parameters.model_copy(update={"v0": (v + 1e-4) ** 2})}
            ),
            64,
        )[0]
        dnv = values(
            "heston",
            point.model_copy(
                update={"parameters": point.parameters.model_copy(update={"v0": (v - 1e-4) ** 2})}
            ),
            64,
        )[0]
        assert fine[3] == pytest.approx((upv - dnv) / 2e-4, abs=1e-5)
        put = values("heston", point.model_copy(update={"kind": "put"}), 64)
        assert fine[0] - put[0] == pytest.approx(
            spot - 100 * math.exp(-0.05 * point.tau), abs=1e-12
        )
        assert fine[1] - put[1] == pytest.approx(1, abs=1e-12)
        assert fine[2:] == pytest.approx(put[2:], abs=1e-12)


def test_heston_deterministic_variance_limit_and_one_point_price_match():
    point = ModelPoint(parameters=ModelParameters(vol_of_vol=0))
    assert values("heston", point)[:3] == pytest.approx(values("bsm", point)[:3], abs=1e-10)
    params = matched_parameters(ModelPoint())
    for model, p in params.items():
        assert values(model, ModelPoint(parameters=p))[0] == pytest.approx(
            bsm(100, 100, 1, 0.2).price, abs=1e-8
        )
    with pytest.raises(ValueError, match="infeasible"):
        matched_parameters(ModelPoint(parameters=ModelParameters(diffusion_vol=0.05, intensity=3)))


@pytest.mark.parametrize("model", ["bsm", "merton", "heston"])
def test_mc_price_greeks_martingale_with_sampling_uncertainty(model):
    result = monte_carlo(model, ModelPoint(), paths=32768, steps=128, seed=137)
    for key in ["price", "delta", "gamma", "vega"]:
        x = result["greeks"][key]
        assert abs(x["error"]) < 5 * x["se"] + (0.03 if model == "heston" else 0.002)
    martingale = result["discounted_spot"]
    assert abs(martingale["value"] - result["martingale_target"]) < 5 * martingale["se"]
    assert martingale["independent_observations"] == 16384


def test_heston_variance_nonnegative_zero_branch_and_deterministic_sampling():
    point = ModelPoint(parameters=ModelParameters(kappa=1, theta=0.02, vol_of_vol=0.8))
    s, v = sample_paths("heston", point, 128, 64, 137)
    assert np.isfinite(s).all() and np.all(v >= 0) and np.any(v == 0)
    again = sample_paths("heston", point, 128, 64, 137)
    assert np.array_equal(s, again[0]) and np.array_equal(v, again[1])
    point = ModelPoint(parameters=ModelParameters(vol_of_vol=0))
    s, v = sample_paths("heston", point, 128, 64, 137)
    assert v == pytest.approx(0.04, abs=1e-15)


def test_premium_matching_rejects_weakly_identified_thin_time_value():
    with pytest.raises(ValueError, match="poorly identified"):
        matched_parameters(ModelPoint(spot=200, tau=1 / 365))
