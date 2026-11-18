"""Synthetic local HTTP workflow measurement; no private input or persistent export."""

import argparse
import json
import os
import tempfile
import time
import tracemalloc
from pathlib import Path

from fastapi.testclient import TestClient
from improvement_workflow import windows_memory

from datagenome.api import create_app


def run():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "bench.sqlite3"
        previous = os.environ.get("DATAGENOME_STORE")
        os.environ["DATAGENOME_STORE"] = str(path)
        tracemalloc.start()
        started = time.perf_counter()
        try:
            app = create_app()
            with TestClient(app) as client:
                startup = time.perf_counter() - started
                response = client.post("/api/v1/auth/guest")
                response.raise_for_status()
                client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
                demo = client.post(
                    "/api/v1/datasets/demo", json={"name": "synthetic benchmark"}
                ).json()
                project, version = demo["project"]["id"], demo["version"]["id"]
                latency = []
                for _ in range(20):
                    at = time.perf_counter()
                    client.get("/api/v1/projects").raise_for_status()
                    latency.append(time.perf_counter() - at)

                def job(endpoint, body):
                    at = time.perf_counter()
                    response = client.post("/api/v1/" + endpoint, json=body)
                    response.raise_for_status()
                    identifier = response.json()["id"]
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        status = client.get(
                            f"/api/v1/jobs/{identifier}?project_id={project}"
                        ).json()
                        if status["state"] not in {"queued", "running"}:
                            if status["state"] != "completed":
                                raise RuntimeError(status["state"])
                            return time.perf_counter() - at
                        time.sleep(0.05)
                    raise RuntimeError("Benchmark deadline")

                analysis = job(
                    "analyses",
                    {
                        "project_id": project,
                        "version_id": version,
                        "engines": ["profile", "intelligence", "leakage"],
                    },
                )
                experiment = job(
                    "experiments",
                    {
                        "project_id": project,
                        "version_id": version,
                        "plans": [{"remove_features": ["z"]}],
                        "authorized": True,
                    },
                )
                result = {
                    "startup_seconds": startup,
                    "analysis_job_seconds": analysis,
                    "experiment_job_seconds": experiment,
                    "project_get_seconds": {
                        "minimum": min(latency),
                        "median": sorted(latency)[10],
                        "maximum": max(latency),
                        "requests": 20,
                    },
                    "sqlite_bytes": path.stat().st_size,
                    "peak_traced_python_bytes": tracemalloc.get_traced_memory()[1],
                    "windows_process_memory": windows_memory(),
                    "method": "Single local synthetic 60-row run, TestClient HTTP stack, one worker; startup includes Argon2 dummy hash; peak tracing excludes native allocations; process peak includes earlier imports.",
                }
                return result
        finally:
            tracemalloc.stop()
            if previous is None:
                os.environ.pop("DATAGENOME_STORE", None)
            else:
                os.environ["DATAGENOME_STORE"] = previous


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(run(), indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
