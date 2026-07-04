import numpy as np
import pytest
import torch
from torch import nn

from options_risk_lab.ml import Surrogate, domain_allowed, greeks, sample


class KnownHomogeneous(nn.Module):
    def forward(self, x):
        return x[:, 0] ** 2 + x[:, 2] ** 3


def test_dimensionless_greek_transforms_and_rejection():
    result = greeks(KnownHomogeneous(), np.array([[1.0, 1.0, 0.2, 0.05, 0.0]]))[0]
    assert result == pytest.approx([100.8, 2, 0.02, 12], abs=1e-12)
    assert not domain_allowed(np.array([[1.0, 0.001, 0.2, 0.05, 0.0]]), True)
    assert not domain_allowed(np.array([[1.0, 1.0, 0.2, 0.05, 0.0]]), False)


def test_initialization_and_frozen_train_region():
    torch.manual_seed(17)
    a = Surrogate()
    torch.manual_seed(17)
    b = Surrogate()
    assert all(torch.equal(x, y) for x, y in zip(a.parameters(), b.parameters(), strict=True))
    x = sample(2048, 101, "train")
    assert not np.any((x[:, 0] > 1.2) & (x[:, 1] < 0.3))


def test_vector_control_independently_matches_scalar():
    from options_risk_lab.ml import control_labels
    from options_risk_lab.pricing import vector_price_greeks

    x = sample(128, 29, "iid")
    assert np.max(np.abs(vector_price_greeks(x) - control_labels(x))) < 1e-10


def test_acceptance_metric_names_match_protocol():
    import json
    from pathlib import Path

    cfg = json.loads(Path("configs/evaluation.json").read_text())
    known = {"price", "delta", "gamma", "vega"}
    assert {key.removesuffix("_rmse") for key in cfg["ml_acceptance"]} == known


def test_discounted_european_bounds_are_distinct_from_american_intrinsic():
    from options_risk_lab.ml import control_labels, error_metrics

    x = np.array([[0.8, 1.0, 0.2, 0.08, 0.0]])
    actual = control_labels(x)
    assert actual[0, 0] < 20
    assert error_metrics(actual, actual, x, "european")["bounds_failures"] == 0
    assert error_metrics(actual, actual, x, "american")["bounds_failures"] == 1
