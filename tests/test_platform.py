import json
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from datagenome.api import create_app
from datagenome.ingestion import DatasetError, parse_csv
from datagenome.jobs import JobService
from datagenome.orchestration import DiagnosticConfig, orchestrate, report_view
from datagenome.planner import evaluate_plans
from datagenome.reporting import export_report
from datagenome.splits import SplitConfig, split
from datagenome.store import Store
from datagenome.uncertainty import ResamplingConfig, paired_interval
from datagenome.versions import (
    Transform,
    apply,
    compare_versions,
    preview,
    reconstruct,
    register,
    table,
)


def fixture(tmp_path):
    payload = b"x,constant,label\n" + b"".join(
        f"{i},secret-batch,{i % 2}\n".encode() for i in range(60)
    )
    data = parse_csv(payload)
    manifest = split(data, SplitConfig("stratified", seed=42), "label")
    store = Store(tmp_path / "data.sqlite3")
    project = store.project("local")["id"]
    version = register(store, project, payload, "label", manifest)
    return store, project, version, payload, data, manifest


def test_version_preview_reconstruction_and_training_label_protection(tmp_path):
    store, project, source, _, _, manifest = fixture(tmp_path)
    train = manifest.partitions["train"]
    chosen = train[0]
    replacement = str(1 - int(source["rows"][chosen - 1][-1]))
    plan = Transform(
        remove_records=(train[1],),
        corrections=((chosen, replacement),),
        constant_features=("constant",),
        review_records=(train[2],),
    )
    before = store.get(project, source["id"], "version")
    count = len(store.list(project, "version"))
    dry = preview(store, project, source["id"], plan)
    assert dry["dry_run"] and len(store.list(project, "version")) == count
    child = apply(store, project, source["id"], plan)
    assert reconstruct(store, project, child["id"]) == child
    assert table(child).rows[child["record_ids"].index(chosen)][-1] == replacement
    assert train[1] not in child["record_ids"]
    assert store.get(project, source["id"], "version") == before
    assert compare_versions(source, child)["removed_ids"] == [train[1]]
    assert child["provenance"]["label_changes"][0]["old_label"] != replacement
    for invalid in (
        Transform(corrections=((manifest.partitions["test"][0], "1"),)),
        Transform(remove_features=("label",)),
        Transform(remove_records=(True,)),
        Transform(corrections=((chosen, "new-label"),)),
        Transform(remove_records=(chosen, chosen)),
        Transform(remove_records=(chosen,), corrections=((chosen, replacement),)),
    ):
        with pytest.raises(DatasetError):
            preview(store, project, source["id"], invalid)
    other = store.project("unrelated")["id"]
    with pytest.raises(DatasetError, match="absent"):
        store.get(other, source["id"], "version")


def test_orchestration_partial_failures_cache_health_and_privacy(tmp_path):
    store, project, _, payload, data, manifest = fixture(tmp_path)
    config = DiagnosticConfig(("profile", "labels", "valuation", "unknown", "drift"))
    report = orchestrate(
        data, payload, "label", manifest, config, store=store, project=project
    )
    assert report["engines"]["unknown"]["status"] == "unsupported"
    assert report["engines"]["drift"]["status"] == "unsupported"
    assert (
        report["engines"]["valuation"]["status"] == "unsupported_or_failed"
    )  # categorical KNN input
    assert report["engines"]["profile"]["status"] == "completed"
    assert "distribution_stability" in report["health"]["unassessed"]
    assert 0 < report["health"]["coverage"] < 1
    assert report["recommendations"] and all(
        item["required_review"] for item in report["recommendations"]
    )
    cached = orchestrate(
        data, payload, "label", manifest, config, store=store, project=project
    )
    assert cached["engines"]["profile"]["cache_hit"]
    safe = report_view(report)
    assert "secret-batch" not in json.dumps(safe)
    assert "dataset_sha256" not in safe
    assert "DataGenome" in export_report(report, "markdown")
    assert export_report(report, "engine-csv").startswith("engine,status")
    with pytest.raises(DatasetError, match="Cancellation"):
        orchestrate(data, payload, "label", manifest, config, cancelled=lambda: True)


def test_experiment_review_and_execution_record_real_outcomes(tmp_path):
    store, project, source, _, _, _ = fixture(tmp_path)
    plans = [Transform(constant_features=("constant",))]
    result = evaluate_plans(store, project, source["id"], plans)
    assert result["mode"] == "review" and not store.list(project, "experiment")
    result = evaluate_plans(store, project, source["id"], plans, authorized=True)
    assert result["state"] == "completed"
    assert not result["held_out_evaluated"]
    assert result["nondominated_plan_indices"] == [0]
    assert result["arms"][0]["version_id"] != source["id"]


def test_job_states_cancel_recover_and_schema(tmp_path):
    store, project, version, _, _, _ = fixture(tmp_path)
    worker = JobService(store)
    config = DiagnosticConfig(("profile",))
    queued = worker.submit(project, version["id"], config)
    assert queued["state"] == "queued"
    assert worker.run_one()
    completed = worker.get(project, queued["id"])
    assert completed["state"] == "completed"
    assert completed["events"][-1]["completed_engines"] == 1
    job = worker.submit(project, version["id"], config)
    assert worker.cancel(project, job["id"])["state"] == "cancelled"
    interrupted = worker.submit(project, version["id"], config)
    with store.connection() as db:
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (interrupted["id"],))
    JobService(store, recover=True)
    assert worker.get(project, interrupted["id"])["state"] == "interrupted"
    for _ in range(8):
        worker.submit(project, version["id"], config)
    with pytest.raises(DatasetError, match="full"):
        worker.submit(project, version["id"], config)
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(DatasetError, match="schema"):
        Store(path)


def test_dependent_bootstrap_resamples_units_and_reports_support():
    before = [0.0, 1.0] * 40
    after = [1.0, 1.0] * 40
    groups = [f"unit-{i // 8}" for i in range(80)]
    cfg = ResamplingConfig(samples=99)
    result = paired_interval(before, after, groups, cfg)
    assert result == paired_interval(before, after, groups, cfg)
    assert result["paired_mean_change"] == 0.5
    assert result["percentile_95"] == [0.5, 0.5]
    assert (
        paired_interval(before, after, ["one"] * 80, cfg)["status"]
        == "insufficient_evidence"
    )
    temporal = paired_interval(
        before,
        after,
        [f"{i:03}" for i in range(80)],
        replace(cfg, mode="temporal", block_length=5),
    )
    assert temporal["effective_units"] == 16
    with pytest.raises(DatasetError):
        paired_interval(before, after, groups, replace(cfg, mode="temporal", samples=1))


def test_platform_routes_end_to_end_project_isolation_and_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAGENOME_STORE", str(tmp_path / "api.sqlite3"))
    with TestClient(create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "demo"}).json()["id"]
        payload = "x,constant,label\n" + "".join(
            f"{i},secret,{i % 2}\n" for i in range(60)
        )
        response = client.post(
            "/api/v1/datasets",
            json={"project_id": project, "csv": payload, "target": "label"},
        )
        assert response.status_code == 200, response.text
        identifier = response.json()["id"]
        spec = {
            "project_id": project,
            "version_id": identifier,
            "plan": {"constant_features": ["constant"]},
        }
        assert client.post("/api/v1/interventions/preview", json=spec).json()["dry_run"]
        assert client.post("/api/v1/interventions/apply", json=spec).status_code == 422
        changed = client.post(
            "/api/v1/interventions/apply", json={**spec, "reviewed": True}
        )
        assert changed.status_code == 200, changed.text
        assert (
            client.get(
                "/api/v1/datasets/" + identifier, params={"project_id": "unknown"}
            ).status_code
            == 404
        )
        result = client.post(
            "/api/v1/analyses",
            json={
                "project_id": project,
                "version_id": identifier,
                "engines": ["profile"],
            },
        )
        assert result.status_code == 200, result.text
        job = result.json()["id"]
        import time

        for _ in range(100):
            status = client.get(
                "/api/v1/jobs/" + job, params={"project_id": project}
            ).json()
            if status["state"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert status["state"] == "completed", status
        report = client.get(
            "/api/v1/reports/" + status["result_id"],
            params={"project_id": project, "format": "markdown"},
        )
        assert report.status_code == 200 and "secret" not in report.text
        assert (
            client.get(
                "/api/v1/datasets/" + identifier + "/export",
                params={"project_id": project},
            ).status_code
            == 422
        )
        export = client.get(
            "/api/v1/datasets/" + identifier + "/export",
            params={"project_id": project, "reviewed": True},
        )
        assert export.text == payload.replace("\n", "\r\n")
        assert client.get("/api/v1/capabilities").json()["jobs"]["workers"] == 1


def test_failed_experiment_and_failed_job_persist_without_raw_errors(
    tmp_path, monkeypatch
):
    import datagenome.jobs as jobs
    from datagenome.modeling import ModelConfig

    store, project, source, _, _, _ = fixture(tmp_path)
    with pytest.raises(DatasetError):
        evaluate_plans(
            store,
            project,
            source["id"],
            [Transform(constant_features=("constant",))],
            authorized=True,
            model=ModelConfig(model="unsupported"),
        )
    result = store.list(project, "experiment_result")
    assert result[0]["state"] == "failed"
    worker = JobService(store)
    item = worker.submit(project, source["id"], DiagnosticConfig(("profile",)))

    def fail(*args, **kwargs):
        raise RuntimeError("private-secret")

    monkeypatch.setattr(jobs, "orchestrate", fail)
    worker.run_one()
    status = worker.get(project, item["id"])
    assert status["state"] == "failed" and status["error"] == "RuntimeError"
    assert "private-secret" not in json.dumps(status)


def test_cancellation_during_engine_is_observed_before_completion(
    tmp_path, monkeypatch
):
    import datagenome.jobs as jobs

    store, project, source, _, _, _ = fixture(tmp_path)
    worker = JobService(store)
    item = worker.submit(project, source["id"], DiagnosticConfig(("profile",)))

    def run(*args, **kwargs):
        worker.cancel(project, item["id"])
        return {}

    monkeypatch.setattr(jobs, "orchestrate", run)
    worker.run_one()
    assert worker.get(project, item["id"])["state"] == "cancelled"


def test_request_limit_and_unknown_plan_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAGENOME_STORE", str(tmp_path / "api.sqlite3"))
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/projects",
            content=b"x" * 6_000_001,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"
        response = client.post(
            "/api/v1/interventions/preview",
            json={
                "project_id": "a" * 32,
                "version_id": "b" * 32,
                "plan": {"command": "execute"},
            },
        )
        assert response.status_code == 422


def test_health_formula_missing_evidence_and_critical_violation():
    from datagenome.orchestration import health

    assert health({})["score"] is None
    profile = {
        "row_count": 10,
        "column_count": 2,
        "duplicate_row_count": 2,
        "columns": [
            {"missing_count": 2, "constant": False},
            {"missing_count": 0, "constant": True},
        ],
    }
    result = health(
        {
            "profile": {"result": profile},
            "leakage": {
                "result": {
                    "leakage": [
                        {"id": "overlap", "classification": "confirmed_violation"}
                    ]
                }
            },
        }
    )
    assert result["critical_violations"] == ["overlap"]
    assert result["score"] == pytest.approx((90 + 80 + 50 + 0 * 2) / 5)
    assert "label_agreement" in result["unassessed"]
    adjusted = health({"profile": {"result": profile}}, {"completeness": 2})
    assert adjusted["score"] == pytest.approx((180 + 80 + 50) / 4)


def test_workspace_cli_review_reconstruction_and_report(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "local.sqlite3"
    csv = tmp_path / "data.csv"
    csv.write_text(
        "x,constant,label\n" + "".join(f"{i},batch,{i % 2}\n" for i in range(40))
    )
    cmd = [sys.executable, "-m", "datagenome.workspace", "--store", str(path)]
    project = json.loads(subprocess.check_output([*cmd, "project", "local"]))["id"]
    version = json.loads(
        subprocess.check_output(
            [*cmd, "register", str(csv), "--target", "label", "--project", project]
        )
    )["id"]
    plan = tmp_path / "plan.json"
    plan.write_text('{"constant_features":["constant"]}')
    common = [version, "--project", project, "--plan", str(plan)]
    dry = json.loads(subprocess.check_output([*cmd, "preview-intervention", *common]))
    assert dry["dry_run"]
    review = json.loads(subprocess.check_output([*cmd, "optimize-data", *common]))
    assert review["mode"] == "review"
    derived = json.loads(
        subprocess.check_output([*cmd, "apply-intervention", *common, "--reviewed"])
    )["id"]
    result = json.loads(
        subprocess.check_output(
            [*cmd, "compare-versions", version, derived, "--project", project]
        )
    )
    assert result["removed_features"] == ["constant"]
    output = tmp_path / "report.md"
    subprocess.check_output(
        [
            *cmd,
            "report",
            version,
            "--project",
            project,
            "--engines",
            "profile",
            "--output",
            str(output),
        ]
    )
    assert "DataGenome diagnostic report" in output.read_text()
