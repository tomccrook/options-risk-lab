"""Immutable manifest files plus SQLite job state; bounded local worker."""

import hashlib
import json
import os
import platform
import sqlite3
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .services import provenance


class Cancelled(Exception):
    pass


def process_alive(pid: int) -> bool:
    """Read-only process probe; Windows kill(pid, 0) is not a POSIX existence check."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        windows_api: Any = ctypes  # Platform-specific stdlib FFI, absent from POSIX stubs.
        kernel = windows_api.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return windows_api.get_last_error() == 5  # Access denied: do not declare worker dead.
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


class Registry:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db = root / "jobs.sqlite"
        with self.connect() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, "
                "manifest TEXT, result TEXT, error TEXT)"
            )
            for id_, payload in c.execute(
                "SELECT id,manifest FROM jobs WHERE status IN ('running','queued')"
            ):
                pid = json.loads(payload).get("worker_pid", -1)
                alive = process_alive(pid)
                if not alive:
                    c.execute(
                        "UPDATE jobs SET status='failed',error='worker interrupted by restart' "
                        "WHERE id=?",
                        (id_,),
                    )
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lab-worker")
        self.events: dict[str, threading.Event] = {}

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db, timeout=10)

    def submit(
        self,
        kind: str,
        config: dict[str, Any],
        operation: Callable[[threading.Event], dict[str, Any]],
    ) -> str:
        id_ = uuid.uuid4().hex
        manifest = {
            "id": id_,
            "worker_pid": os.getpid(),
            "kind": kind,
            "created_utc": datetime.now(UTC).isoformat(),
            "config": config,
            "provenance": provenance(config),
            "platform": platform.platform(),
        }
        payload = json.dumps(manifest, sort_keys=True, allow_nan=False)
        (self.root / f"{id_}.manifest.json").write_text(payload)
        with self.connect() as c:
            c.execute("INSERT INTO jobs VALUES (?,?,?,?,?)", (id_, "queued", payload, None, None))
        event = threading.Event()
        self.events[id_] = event
        self.executor.submit(self._run, id_, operation, event)
        return id_

    def _run(
        self,
        id_: str,
        operation: Callable[[threading.Event], dict[str, Any]],
        event: threading.Event,
    ) -> None:
        try:
            with self.connect() as c:
                c.execute("UPDATE jobs SET status='running' WHERE id=?", (id_,))
            if event.is_set():
                raise Cancelled("cancelled before execution")
            result = operation(event)
            if event.is_set():
                raise Cancelled("cancelled; result discarded")
            encoded = json.dumps(result, allow_nan=False)
            digest = hashlib.sha256(encoded.encode()).hexdigest()
            result_file = self.root / f"{id_}.result.json"
            result_file.write_text(encoded)
            (self.root / f"{id_}.result.sha256").write_text(digest)
            with self.connect() as c:
                c.execute("UPDATE jobs SET status='complete',result=? WHERE id=?", (encoded, id_))
        except Exception as exc:
            with self.connect() as c:
                status = "cancelled" if isinstance(exc, Cancelled) else "failed"
                c.execute("UPDATE jobs SET status=?,error=? WHERE id=?", (status, str(exc), id_))
        finally:
            self.events.pop(id_, None)

    def get(self, id_: str) -> dict[str, Any]:
        with self.connect() as c:
            row = c.execute(
                "SELECT status,manifest,result,error FROM jobs WHERE id=?", (id_,)
            ).fetchone()
        if row is None:
            raise KeyError("unknown run")
        return {
            "id": id_,
            "status": row[0],
            "manifest": json.loads(row[1]),
            "result": json.loads(row[2]) if row[2] else None,
            "error": row[3],
        }

    def cancel(self, id_: str) -> dict[str, Any]:
        self.get(id_)
        event = self.events.get(id_)
        if event:
            event.set()
        return self.get(id_)


def export_table(rows: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
    with duckdb.connect() as c:
        record = c.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()
        assert record is not None
        count = record[0]
    return {
        "path": str(path),
        "rows": count,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def metrics(errors: np.ndarray, costs: np.ndarray, turnover: np.ndarray) -> dict[str, float]:
    from .hedging import cvar

    return {
        "mean": float(errors.mean()),
        "bias": float(errors.mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "loss_q95": float(np.quantile(-errors, 0.95)),
        "cvar95": cvar(-errors, alpha=0.95),
        "mean_cost": float(costs.mean()),
        "mean_turnover": float(turnover.mean()),
        "tail_mass_count": len(errors) * 0.05,
    }


def paired_interval(
    a: np.ndarray, b: np.ndarray, seed: int = 919, samples: int = 2000
) -> dict[str, Any]:
    if a.shape != b.shape:
        raise ValueError("paired observations must align")
    rng = np.random.default_rng(seed)
    # Independent paths; preserve pairing and never resample nodes.
    boot = []
    for _ in range(samples):
        index = rng.integers(0, len(a), len(a))
        boot.append(float(np.sqrt(np.mean(a[index] ** 2)) - np.sqrt(np.mean(b[index] ** 2))))
    return {
        "rmse_difference": float(np.sqrt(np.mean(a * a)) - np.sqrt(np.mean(b * b))),
        "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
        "bootstrap_samples": samples,
        "unit": "independent paths; common random numbers",
        "mean_difference": float((a - b).mean()),
    }


def uncertainty(errors: np.ndarray, seed: int = 919, samples: int = 2000) -> dict[str, Any]:
    """Independent-path bootstrap, finite-tail-mass estimator shared with metrics."""
    rng = np.random.default_rng(seed)
    means = []
    tails = []
    mass = len(errors) * 0.05
    whole = int(mass)
    fraction = mass - whole
    for _ in range(samples):
        sampled = errors[rng.integers(0, len(errors), len(errors))]
        losses = -sampled
        # Include ceil(5% * n), with partial boundary mass.
        ordered = np.sort(losses)[::-1]
        tail = (ordered[:whole].sum() + fraction * ordered[whole]) / mass
        means.append(float(sampled.mean()))
        tails.append(float(tail))
    return {
        "mean_ci95": np.quantile(means, [0.025, 0.975]).tolist(),
        "cvar95_ci95": np.quantile(tails, [0.025, 0.975]).tolist(),
        "tail_observations": int(np.ceil(mass)),
        "bootstrap_samples": samples,
    }
