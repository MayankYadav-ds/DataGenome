"""Regenerate the public preview using the actual isolated synthetic backend workflow."""

import json
import os
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from datagenome.api import create_app


def main():
    with tempfile.TemporaryDirectory() as folder:
        os.environ["DATAGENOME_STORE"] = str(Path(folder) / "preview.sqlite3")
        with TestClient(create_app()) as client:
            session = client.post("/api/v1/auth/guest").json()
            client.headers["X-CSRF-Token"] = session["csrf_token"]
            demo = client.post(
                "/api/v1/datasets/demo", json={"name": "Synthetic public preview"}
            ).json()
            project, version = demo["project"]["id"], demo["version"]["id"]
            job = client.post(
                "/api/v1/analyses",
                json={
                    "project_id": project,
                    "version_id": version,
                    "engines": ["profile", "intelligence", "leakage", "labels"],
                },
            ).json()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                state = client.get(
                    f"/api/v1/jobs/{job['id']}?project_id={project}"
                ).json()
                if state["state"] not in {"queued", "running"}:
                    if state["state"] != "completed":
                        raise RuntimeError(
                            "Synthetic preview analysis did not complete"
                        )
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("Synthetic preview deadline")
            report = client.get(
                f"/api/v1/analyses/{state['result_id']}?project_id={project}"
            ).json()
            output = {
                "source": "Built-in synthetic demo; computed by the actual backend. Not customer results.",
                "rows": demo["version"]["row_count"],
                "columns": demo["version"]["column_count"],
                "health": report["health"],
                "recommendation_counts": report["recommendation_counts"],
                "engines": report["engines"],
            }
            Path("frontend/public/demo-preview.json").write_text(
                json.dumps(output, indent=2) + "\n", encoding="utf-8"
            )
            client.delete("/api/v1/auth/account")


if __name__ == "__main__":
    main()
