import hashlib
import json

import pytest

from options_risk_lab.reporting import load_completed


def test_export_rejects_failed_jobs_and_changed_payloads(tmp_path):
    payload = tmp_path / "episodes.parquet"
    payload.write_bytes(b"fixture-payload")
    job = tmp_path / "job.json"
    record = {
        "id": "fixture",
        "status": "complete",
        "result": {
            "episodes": {
                "path": str(payload),
                "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
            }
        },
    }
    job.write_text(json.dumps(record))
    assert load_completed(job)["id"] == "fixture"
    payload.write_bytes(b"changed")
    with pytest.raises(ValueError, match="evidence payload changed"):
        load_completed(job)
    record["status"] = "failed"
    job.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="is failed"):
        load_completed(job)
