import json
import threading
import time

import pytest

from options_risk_lab.experiments import Registry


def await_terminal(registry, id_):
    for _ in range(100):
        job = registry.get(id_)
        if job["status"] in ("complete", "failed", "cancelled"):
            return job
        time.sleep(0.01)
    pytest.fail("worker did not complete")


def test_failed_jobs_preserved_and_manifest_immutable(tmp_path):
    registry = Registry(tmp_path)

    def fail(event):
        raise ValueError("numerical convergence failed")

    id_ = registry.submit("invalid-reference", {"seed": 7}, fail)
    job = await_terminal(registry, id_)
    assert job["status"] == "failed" and "convergence" in job["error"]
    manifest = json.loads((tmp_path / f"{id_}.manifest.json").read_text())
    assert manifest["config"] == {"seed": 7}
    assert "versions" in manifest["provenance"]
    registry.executor.shutdown()


def test_cancel_and_complete_result_digest(tmp_path):
    registry = Registry(tmp_path)
    ready = threading.Event()

    def run(event):
        ready.set()
        event.wait(2)
        return {"value": 1}

    id_ = registry.submit("cancellable", {}, run)
    assert ready.wait(1)
    registry.cancel(id_)
    assert await_terminal(registry, id_)["status"] == "cancelled"
    success = registry.submit("success", {}, lambda _: {"value": 2})
    assert await_terminal(registry, success)["result"] == {"value": 2}
    assert (tmp_path / f"{success}.result.sha256").exists()
    registry.executor.shutdown()


def test_seed_partitions_are_disjoint_and_protocol_locked():
    import hashlib
    from pathlib import Path

    p = Path("configs/evaluation.json")
    cfg = json.loads(p.read_text())
    groups = [set(cfg[k]) for k in ("development_seeds", "validation_seeds", "locked_seeds")]
    assert not (groups[0] & groups[1] or groups[1] & groups[2] or groups[0] & groups[2])
    assert (
        hashlib.sha256(p.read_bytes()).hexdigest() == p.with_suffix(".sha256").read_text().strip()
    )


def test_worker_existence_probe_does_not_signal_live_processes():
    import os

    from options_risk_lab.experiments import process_alive

    assert process_alive(os.getpid())
    assert not process_alive(-1)


def test_ml_cli_rejects_modified_protected_protocol_before_training(tmp_path):
    import hashlib

    from typer.testing import CliRunner

    from options_risk_lab.cli import app

    protocol = tmp_path / "frozen.json"
    protocol.write_text('{"ml_epochs": 300}')
    protocol.with_suffix(".sha256").write_text(hashlib.sha256(protocol.read_bytes()).hexdigest())
    protocol.write_text('{"ml_epochs": 600}')
    response = CliRunner().invoke(app, ["train", "--protocol", str(protocol)])
    assert response.exit_code != 0
    assert "protected ML protocol changed" in response.output
