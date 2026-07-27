"""Representative workloads, not merely imports. Run on pinned runtime."""

import json
import platform
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import QuantLib as ql
import scipy
import torch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scipy.optimize import linprog

from options_risk_lab.contracts import Market
from options_risk_lab.reference import european

assert platform.python_version() == "3.14.8"
assert linprog([1.0, 2.0], bounds=[(1, 2), (0, 1)]).success
assert european(100, 100, 1, 0.2).price > 10
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "probe.parquet"
    pq.write_table(pa.table({"price": np.array([10.45, 5.57])}), p)
    with duckdb.connect() as c:
        assert c.execute("SELECT count(*) FROM read_parquet(?)", [str(p)]).fetchone()[0] == 2
x = torch.tensor([1.0], dtype=torch.float64, requires_grad=True)
y = torch.tanh(x) ** 2
g = torch.autograd.grad(y.sum(), x, create_graph=True)[0]
assert torch.isfinite(torch.autograd.grad(g.sum(), x)[0]).all()
api = FastAPI()


@api.get("/probe")
def probe() -> Market:
    return Market()


assert TestClient(api).get("/probe").status_code == 200
print(
    json.dumps(
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "quantlib": ql.__version__,
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "mps_available": torch.backends.mps.is_available(),
            "training_device": "cpu",
        }
    )
)
