import json
import platform
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from options_risk_lab.api import app
from options_risk_lab.services import provenance

client = TestClient(app)
rows = []
for route, payload, repeats in [
    ("/api/curves", {}, 50),
    ("/api/portfolio", {}, 30),
    ("/api/hedges", {}, 20),
    ("/api/model-probe", {}, 5),
]:
    start = time.perf_counter()
    first = client.post(route, json=payload)
    cold = (time.perf_counter() - start) * 1000
    assert first.status_code == 200, first.text
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        response = client.post(route, json=payload)
        assert response.status_code == 200, response.text
        timings.append((time.perf_counter() - start) * 1000)
    rows.append(
        {
            "route": route,
            "cold_first_ms": cold,
            "p50_ms": float(np.median(timings)),
            "p95_ms": float(np.quantile(timings, 0.95)),
            "repeats": repeats,
            "cache": "No curve/result cache; hot imports and OS page cache",
            "workload": "101 points / 15 scenarios / 49 option pairs × 501 integer shares",
        }
    )
try:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
except ImportError:
    rss = None  # Native Windows: latency supported, no stdlib RSS counter.
result = {
    "platform": platform.platform(),
    "latency": rows,
    "rss_max": rss,
    "rss_units": "bytes on macOS; KiB on Linux",
    "provenance": provenance({"workload": "ordinary European service and rejected-model fallback"}),
    "limitation": "In-process HTTP adapter; excludes Vite proxy/network/browser debounce",
}
Path("artifacts/performance.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
