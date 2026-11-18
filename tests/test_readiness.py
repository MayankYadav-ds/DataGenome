import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from test_platform import fixture

from datagenome.api import create_app
from datagenome.ingestion import DatasetError, parse_csv
from datagenome.jobs import JobService
from datagenome.preprocessing import (
    LearnedConfig,
    fit_parameters,
    persist_parameters,
    transform_parameters,
)
from datagenome.search import compatible, generate_candidates, merge
from datagenome.store import Store
from datagenome.versions import Transform, table


def enter(client, mode="guest", username="alice"):
    body = (
        {}
        if mode == "guest"
        else {"username": username, "password": "synthetic-password-123"}
    )
    response = client.post("/api/v1/auth/" + mode, json=body)
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


def test_sessions_passwords_and_revocation(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/projects").status_code == 401
        response = enter(client, "register")
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        with app.state.auth.store.connection() as db:
            row = db.execute("SELECT password_hash FROM users").fetchone()
            assert (
                row[0].startswith("$argon2id$") and "synthetic-password" not in row[0]
            )
            token = client.cookies.get("datagenome_session")
            assert db.execute("SELECT token_hash FROM sessions").fetchone()[0] != token
        assert client.get("/api/v1/auth/session").json()["username"] == "alice"
        saved = dict(client.cookies)
        assert client.post("/api/v1/auth/logout").status_code == 200
        client.cookies.update(saved)
        assert client.get("/api/v1/projects").status_code == 401
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": "wrong-password-123"},
            ).status_code
            == 401
        )
        enter(client, "login")
        with app.state.auth.store.connection() as db:
            db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
        assert client.get("/api/v1/projects").status_code == 401


@pytest.mark.parametrize("mode", ["guest", "register"])
def test_adversarial_http_ownership_csrf_and_deletion(mode):
    app = create_app()
    # One application lifespan, two independent clients/cookie jars.
    with TestClient(app) as first:
        second = TestClient(app)
        enter(first, mode, "alice")
        enter(second, mode, "bob")
        created = first.post(
            "/api/v1/datasets/demo", json={"name": "private fixture"}
        ).json()
        project, version = created["project"]["id"], created["version"]["id"]
        assert second.get("/api/v1/projects").json() == []
        endpoints = [
            f"/projects/{project}",
            f"/datasets/{version}?project_id={project}",
            f"/datasets/{version}/preview?project_id={project}&reviewed=true",
            f"/reports?project_id={project}",
        ]
        for endpoint in endpoints:
            assert second.get("/api/v1" + endpoint).status_code == 404
        assert (
            second.post(
                "/api/v1/analyses",
                json={
                    "project_id": project,
                    "version_id": version,
                    "engines": ["profile"],
                },
            ).status_code
            == 404
        )
        # Indirect result and job paths must reject the owning project before lookup.
        for kind in ["jobs", "reports", "experiments", "analyses"]:
            assert (
                second.get(f"/api/v1/{kind}/invented?project_id={project}").status_code
                == 404
            )
        assert second.delete(f"/api/v1/projects/{project}").status_code == 404
        csrf = first.headers.pop("X-CSRF-Token")
        assert first.delete(f"/api/v1/projects/{project}").status_code == 403
        first.headers["X-CSRF-Token"] = csrf
        assert (
            first.post(
                "/api/v1/projects",
                json={"name": "bad origin"},
                headers={"Origin": "https://attacker.invalid"},
            ).status_code
            == 403
        )
        assert (
            first.get(
                f"/api/v1/datasets/{version}/preview?project_id={project}"
            ).status_code
            == 422
        )
        response = first.delete(f"/api/v1/datasets/{version}?project_id={project}")
        assert response.status_code == 200
        assert (
            first.get(f"/api/v1/datasets/{version}?project_id={project}").status_code
            == 404
        )
        assert first.delete("/api/v1/auth/account").status_code == 200
        assert first.get("/api/v1/projects").status_code == 401
        assert second.get("/api/v1/auth/session").status_code == 200
        second.close()


def test_guest_expiry_legacy_ownership_and_upload_bounds(tmp_path):
    app = create_app()
    auth = app.state.auth
    legacy = auth.store.project("trusted legacy")
    with TestClient(app) as client:
        enter(client)
        assert client.get(f"/api/v1/projects/{legacy['id']}").status_code == 404
        response = client.post("/api/v1/datasets/demo", json={"name": "guest"})
        project = response.json()["project"]["id"]
        assert (
            client.post("/api/v1/projects", json={"name": "../outside"}).status_code
            == 200
        )
        # Names are labels, never filesystem paths.
        assert (
            client.post("/api/v1/projects", json={"name": "third"}).status_code == 200
        )
        assert (
            client.post("/api/v1/projects", json={"name": "fourth"}).status_code == 429
        )
        assert (
            client.post("/api/v1/datasets", content=b"x" * 6_000_001).status_code == 413
        )
        with auth.store.connection() as db:
            db.execute("UPDATE users SET expires=? WHERE guest=1", (time.time() - 1,))
        assert client.get("/api/v1/projects").status_code == 401
        assert auth.cleanup() == 1
        with auth.store.connection() as db:
            assert (
                db.execute("SELECT 1 FROM artifacts WHERE id=?", (project,)).fetchone()
                is None
            )
        assert auth.store.get("", legacy["id"], "project")["name"] == "trusted legacy"


def test_preprocessing_roundtrip_isolation_and_corruption(tmp_path):
    store, project, version, _, _, manifest = fixture(tmp_path)
    config = LearnedConfig(features=("constant", "x"), scaling="robust")
    artifact = persist_parameters(store, project, version["id"], config)
    restored = store.get(project, artifact["id"], "preprocessing")
    records = list(range(1, 61))
    assert transform_parameters(
        artifact, table(version), records
    ) == transform_parameters(restored, table(version), records)
    changed = copy.deepcopy(version)
    for i in manifest.partitions["validation"] + manifest.partitions["test"]:
        changed["rows"][i - 1][0] = "1000000"
        changed["rows"][i - 1][1] = "unseen"
    # Split validation binds dataset content; construct an equivalent fresh manifest for the altered data.
    from datagenome.identity import canonical
    from datagenome.ingestion import Dataset
    from datagenome.splits import split

    modified_data = Dataset(
        tuple(changed["columns"]), tuple(tuple(row) for row in changed["rows"])
    )
    changed["canonical_sha256"] = canonical(modified_data)
    new_manifest = split(modified_data, manifest.config, "label")
    assert new_manifest.partitions == manifest.partitions
    changed["split"] = json.loads(
        json.dumps({**asdict(new_manifest), "fingerprint": new_manifest.fingerprint})
    )
    fitted = fit_parameters(changed, config)
    original = fit_parameters(version, config)
    assert fitted["parameters"]["features"] == original["parameters"]["features"]
    assert (
        transform_parameters(fitted, modified_data, [manifest.partitions["test"][0]])[
            0
        ][0]
        == 0.0
    )
    corrupt = copy.deepcopy(artifact)
    corrupt["parameters"]["features"][1]["scale"] = 0
    with pytest.raises(DatasetError, match="Corrupt"):
        transform_parameters(corrupt, table(version), [1])
    with pytest.raises(DatasetError):
        transform_parameters(artifact, parse_csv(b"other,label\n1,0\n"), [1])


def test_experiment_queue_dedup_restart_and_events(tmp_path):
    store, project, version, *_ = fixture(tmp_path)
    worker = JobService(store)
    plans = [asdict(Transform(constant_features=("constant",)))]
    queued = worker.submit_experiment(project, version["id"], plans)
    assert worker.submit_experiment(project, version["id"], plans)["id"] == queued["id"]
    worker = JobService(store, recover=True)
    assert worker.get(project, queued["id"])["state"] == "queued"
    assert worker.run_one()
    done = worker.get(project, queued["id"])
    assert done["state"] == "completed", done
    assert done["events"][-1]["completed_fits"] >= 2
    result = store.get(project, done["result_id"], "experiment_result")
    assert result["state"] == "completed" and not result["held_out_evaluated"]
    next_job = worker.submit_experiment(project, version["id"], plans)
    assert worker.cancel(project, next_job["id"])["state"] == "cancelled"
    interrupted = worker.submit_experiment(project, version["id"], plans)
    with store.connection() as db:
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (interrupted["id"],))
    recovered = JobService(store, recover=True)
    assert recovered.get(project, interrupted["id"])["state"] == "interrupted"
    assert (
        store.get(
            project, interrupted["experiment_id"] + ".result", "experiment_result"
        )["state"]
        == "interrupted"
    )


def test_search_conflicts_and_concurrent_atomic_writes(tmp_path):
    store, project, version, *_ = fixture(tmp_path)
    first = generate_candidates(store, project, version["id"])
    second = generate_candidates(store, project, version["id"])
    assert first == second and first["mode"] == "review"
    assert first["candidates"][0]["evidence"] == "constant_features"
    assert not compatible(
        Transform(remove_records=(1,)), Transform(corrections=((1, "1"),))
    )["compatible"]
    with pytest.raises(DatasetError, match="remove_and"):
        merge(Transform(remove_records=(1,)), Transform(review_records=(1,)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(
            pool.map(lambda i: store.put(project, "test", {"number": i}), range(24))
        )
    assert len({v["id"] for v in values}) == 24
    assert len(store.list(project, "test")) == 24


def test_metric_bootstrap_dependence_and_determinism():
    from datagenome.uncertainty import ResamplingConfig, metric_intervals

    actual = [str(i % 2) for i in range(120)]
    before = ["0"] * 120
    after = actual.copy()
    for mode, units in [
        ("independent", [str(i) for i in range(120)]),
        ("group", [str(i // 10) for i in range(120)]),
        ("temporal", [str(i) for i in range(120)]),
    ]:
        config = ResamplingConfig(mode=mode, samples=39)
        result = metric_intervals(actual, before, after, units, config)
        assert result == metric_intervals(actual, before, after, units, config)
        assert all(item["status"] == "estimated" for item in result.values())
        assert result["accuracy"]["observed_change"] == 0.5
    unsupported = metric_intervals(
        actual, before, after, ["one"] * 120, ResamplingConfig(samples=39)
    )
    assert unsupported["accuracy"]["status"] == "insufficient_evidence"


def test_real_guest_analysis_experiment_reports_and_cross_access():
    app = create_app()
    with TestClient(app) as client:
        other = TestClient(app)
        enter(client)
        enter(other, "register", "bob")
        demo = client.post("/api/v1/datasets/demo", json={"name": "workflow"}).json()
        project, version = demo["project"]["id"], demo["version"]["id"]
        submitted = client.post(
            "/api/v1/analyses",
            json={
                "project_id": project,
                "version_id": version,
                "engines": ["profile", "intelligence"],
            },
        )
        assert submitted.status_code == 200
        job = submitted.json()["id"]

        def finish(identifier):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                status = client.get(
                    f"/api/v1/jobs/{identifier}?project_id={project}"
                ).json()
                if status["state"] not in {"queued", "running"}:
                    assert status["state"] == "completed", status
                    return status
                time.sleep(0.05)
            pytest.fail("Local job exceeded test deadline")

        status = finish(job)
        analysis = status["result_id"]
        assert (
            client.get(f"/api/v1/reports/{analysis}?project_id={project}").status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/analyses/{analysis}/health?project_id={project}"
            ).status_code
            == 200
        )
        for path in [f"/jobs/{job}", f"/reports/{analysis}", f"/analyses/{analysis}"]:
            assert (
                other.get("/api/v1" + path + f"?project_id={project}").status_code
                == 404
            )
        submitted = client.post(
            "/api/v1/experiments",
            json={
                "project_id": project,
                "version_id": version,
                "plans": [{"remove_features": ["z"]}],
                "authorized": True,
            },
        )
        assert submitted.status_code == 200, submitted.text
        experiment = submitted.json()["experiment_id"]
        finish(submitted.json()["id"])
        result = client.get(
            f"/api/v1/experiments/{experiment}?project_id={project}"
        ).json()
        assert result["state"] == "completed" and not result["held_out_evaluated"]
        assert (
            other.get(
                f"/api/v1/experiments/{experiment}?project_id={project}"
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/v1/reports/{analysis}?project_id={project}"
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/v1/reports/{analysis}?project_id={project}").status_code
            == 404
        )
        assert client.delete(f"/api/v1/projects/{project}").status_code == 200
        other.close()


def test_running_experiment_cancels_at_actual_fit_boundary(tmp_path):
    from datagenome.planner import evaluate_plans

    store, project, version, *_ = fixture(tmp_path)
    events = []
    with pytest.raises(DatasetError, match="fit boundary"):
        evaluate_plans(
            store,
            project,
            version["id"],
            [Transform(constant_features=("constant",))],
            authorized=True,
            event=events.append,
            cancelled=lambda: bool(events and events[-1]["completed_fits"] >= 1),
        )
    assert events[-1]["completed_fits"] == 1
    assert store.list(project, "experiment_result")[0]["state"] == "cancelled"
    assert len(store.list(project, "version")) == 1


def test_contract_security_schemes_and_measured_report_series(tmp_path):
    app = create_app()
    schema = app.openapi()
    from pathlib import Path

    expected = json.loads(
        (Path(__file__).parents[1] / "docs" / "openapi.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema == expected
    assert schema["components"]["securitySchemes"]["LocalSession"]["in"] == "cookie"
    assert schema["paths"]["/api/v1/projects"]["post"]["security"] == [
        {"LocalSession": []}
    ]
    assert any(
        item["name"] == "X-CSRF-Token"
        for item in schema["paths"]["/api/v1/projects"]["post"]["parameters"]
    )
    from datagenome.orchestration import DiagnosticConfig, orchestrate, report_view

    store, project, _, payload, data, manifest = fixture(tmp_path)
    report = orchestrate(
        data, payload, "label", manifest, DiagnosticConfig(("profile",))
    )
    view = report_view(report)
    assert view["series"]["health_coverage"][0]["value"] == report["health"]["coverage"]
    assert sum(item["value"] for item in view["series"]["health_coverage"]) == 1
    assert view["tables"]["engine_status"]["rows"] == [["profile", "completed"]]


def test_schema_one_migrates_without_adopting_legacy_projects(tmp_path):
    store = Store(tmp_path / "old.sqlite3")
    project = store.project("legacy")
    with store.connection() as db:
        db.execute("DROP TABLE project_owners")
        db.execute("PRAGMA user_version=1")
    upgraded = Store(store.path)
    assert upgraded.get("", project["id"], "project") == project
    with upgraded.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM project_owners").fetchone()[0] == 0


def test_retention_and_delete_are_scoped_and_atomic(tmp_path):
    from datagenome.lifecycle import delete_project, retention

    store, project, version, *_ = fixture(tmp_path)
    other = store.project("other")["id"]
    old = store.put(project, "analysis", {"report": {"private": "data"}})
    with store.connection() as db:
        db.execute("UPDATE artifacts SET created='2000-01-01' WHERE id=?", (old["id"],))
    assert retention(store, 1) == 1
    assert store.get(project, version["id"], "version")
    queued = JobService(store).submit_experiment(
        project, version["id"], [asdict(Transform(constant_features=("constant",)))]
    )
    with store.connection() as db:
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (queued["id"],))
    with pytest.raises(DatasetError, match="Cancel running"):
        delete_project(store, project)
    assert store.get(project, version["id"], "version")
    with store.connection() as db:
        db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (queued["id"],))
    delete_project(store, project)
    with pytest.raises(DatasetError):
        store.get(project, version["id"], "version")
    assert store.get("", other, "project")["name"] == "other"


def test_replication_freeze_identity_and_one_use_ledger(tmp_path, monkeypatch):
    import importlib
    from datetime import datetime, timedelta
    from pathlib import Path

    from datagenome.ingestion import Dataset

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "benchmarks"))
    replication = importlib.import_module("dependent_replication")
    data = Dataset(
        tuple([f"x{j}" for j in range(5)] + ["date", "activity"]),
        tuple(
            tuple(
                [str(i + j) for j in range(5)]
                + [
                    (datetime(2020, 1, 1) + timedelta(minutes=i)).isoformat(),
                    str(i % 2),
                ]
            )
            for i in range(300)
        ),
    )
    monkeypatch.setattr(replication, "load", lambda kind, archive: data)
    archive = tmp_path / "synthetic.zip"
    archive.write_bytes(b"synthetic-only")
    folder = tmp_path / "ledger"
    replication.freeze("occupancy", archive, folder)
    protocol = json.loads((folder / "occupancy.protocol.json").read_text())
    assert protocol["protocol"]["previously_scored_validation_overlap_records"] == 0
    replication.score("occupancy", archive, folder)
    assert (folder / "occupancy.results.json").exists()
    with pytest.raises(FileExistsError):
        replication.score("occupancy", archive, folder)
    archive.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        replication.score("occupancy", archive, folder)


def test_replication_rejects_cross_seed_validation_reuse(tmp_path, monkeypatch):
    import importlib
    from pathlib import Path

    from datagenome.ingestion import Dataset

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "benchmarks"))
    replication = importlib.import_module("dependent_replication")
    data = Dataset(
        tuple([f"x{j}" for j in range(6)] + ["subject", "activity"]),
        tuple(
            tuple([str(i + j) for j in range(6)] + [str(i // 10), str(i % 2)])
            for i in range(300)
        ),
    )
    monkeypatch.setattr(replication, "load", lambda kind, archive: data)
    archive = tmp_path / "synthetic.zip"
    archive.write_bytes(b"synthetic-only")
    folder = tmp_path / "ledger"
    replication.freeze("har", archive, folder)
    protocol = json.loads((folder / "har.protocol.json").read_text())
    assert protocol["protocol"]["previously_scored_validation_overlap_records"] > 0
    with pytest.raises(ValueError, match="prior validation overlap"):
        replication.score("har", archive, folder)
    assert not (folder / "har.results.json").exists()
