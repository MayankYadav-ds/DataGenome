import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datagenome.auth import Auth
from datagenome.benchmark_data import synthetic
from datagenome.configuration import Settings
from datagenome.holdouts import claim
from datagenome.ingestion import DatasetError
from datagenome.lease import Lease
from datagenome.operations import (
    backup,
    integrity,
    recover_restore,
    restore,
    verify_backup,
)
from datagenome.splits import SplitConfig, split
from datagenome.store import Store


def workspace(tmp_path):
    store = Store(tmp_path / "workspace.sqlite3")
    auth = Auth(store)
    with store.connection() as db:
        db.execute(
            "INSERT INTO users VALUES ('operator-fixture','fixture',?,0,NULL)",
            (auth.dummy_hash,),
        )
    auth.issue("operator-fixture", False)
    store.project("Original")
    return store, tmp_path / "ledger"


def test_backup_restore_preserves_data_revokes_sessions_and_unions_ledger(tmp_path):
    store, ledger = workspace(tmp_path)
    data = synthetic(11, 50)
    manifest = split(data, SplitConfig("stratified"), "label")
    claim(manifest, ledger, "first", data, "label")
    output = tmp_path / "snapshot"
    assert backup(store.path, ledger, output)["status"] == "backed_up"
    assert verify_backup(output)["status"] == "verified"
    with sqlite3.connect(output / "workspace.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    later = synthetic(23, 50)
    later_manifest = split(later, SplitConfig("stratified"), "label")
    claim(later_manifest, ledger, "second", later, "label")
    store.project("After snapshot")
    assert restore(store.path, ledger, output)["status"] == "dry_run"
    assert len(store.list("", "project")) == 2
    assert restore(store.path, ledger, output, apply=True)["status"] == "restored"
    assert len(store.list("", "project")) == 1
    assert integrity(store.path)["schema"] == 2
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    with pytest.raises(DatasetError, match="already claimed"):
        claim(later_manifest, ledger, "third", later, "label")


def test_backup_tamper_and_manifest_traversal_are_rejected(tmp_path):
    store, ledger = workspace(tmp_path)
    folder = tmp_path / "snapshot"
    backup(store.path, ledger, folder)
    manifest = folder / "manifest.json"
    value = json.loads(manifest.read_text())
    value["files"]["../../outside"] = "0" * 64
    manifest.write_text(json.dumps(value))
    with pytest.raises(DatasetError):
        verify_backup(folder)
    del value["files"]["../../outside"]
    manifest.write_text(json.dumps(value))
    with (folder / "workspace.sqlite3").open("ab") as file:
        file.write(b"tampered")
    with pytest.raises(DatasetError, match="identity failed"):
        restore(store.path, ledger, folder, apply=True)
    assert integrity(store.path)["status"] == "ok"


def test_restore_failed_swap_rolls_back_and_preserves_original(tmp_path, monkeypatch):
    store, ledger = workspace(tmp_path)
    ledger.mkdir()
    folder = tmp_path / "snapshot"
    backup(store.path, ledger, folder)
    store.project("Must survive")
    original = os.replace

    def fail_new_ledger(src, dst):
        if Path(src).name == "ledger" and Path(src).parent.name.startswith(
            ".dg-restore-"
        ):
            raise OSError("synthetic failure")
        return original(src, dst)

    with monkeypatch.context() as context:
        context.setattr(os, "replace", fail_new_ledger)
        with pytest.raises(OSError):
            restore(store.path, ledger, folder, apply=True)
    assert len(store.list("", "project")) == 2
    assert not store.path.with_suffix(".sqlite3.restore-pending.json").exists()


def test_failed_rollback_retains_recovery_journal_and_original(tmp_path, monkeypatch):
    store, ledger = workspace(tmp_path)
    ledger.mkdir()
    folder = tmp_path / "snapshot"
    backup(store.path, ledger, folder)
    store.project("Survive rollback failure")
    original = os.replace

    def unavailable(src, dst):
        if Path(src).name in {"ledger", "previous.sqlite3"}:
            raise OSError("synthetic storage failure")
        return original(src, dst)

    with monkeypatch.context() as context:
        context.setattr(os, "replace", unavailable)
        with pytest.raises(OSError):
            restore(store.path, ledger, folder, apply=True)
    with pytest.raises(DatasetError, match="interrupted restore"):
        Lease(store.path).acquire()
    assert recover_restore(store.path, ledger)["status"] == "recovery_dry_run"
    assert (
        recover_restore(store.path, ledger, apply=True)["status"]
        == "restore_rolled_back"
    )
    assert len(store.list("", "project")) == 2


def test_process_lease_prevents_duplicate_owners(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    with Lease(path):
        with pytest.raises(DatasetError, match="owning service"):
            Lease(path).acquire()
    with Lease(path):
        pass


@pytest.mark.parametrize(
    "key,value",
    [
        ("DATAGENOME_WORKERS", "2"),
        ("DATAGENOME_QUEUE_LIMIT", "999"),
        ("DATAGENOME_RETENTION_DAYS", "0"),
        ("DATAGENOME_HTTPS", "yes"),
    ],
)
def test_invalid_configuration_is_redacted(key, value, monkeypatch):
    monkeypatch.setenv(key, value)
    with pytest.raises(DatasetError, match="unsafe deployment"):
        Settings.load()


def test_production_requires_explicit_https_and_absolute_storage(monkeypatch):
    monkeypatch.setenv("DATAGENOME_ENV", "production")
    with pytest.raises(DatasetError):
        Settings.load()


def test_readiness_and_session_rotation_with_real_authentication():
    from datagenome.api import create_app

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        guest = client.post("/api/v1/auth/guest")
        prior = client.cookies.get("datagenome_session")
        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "phase10-fixture", "password": "synthetic-password-123"},
        )
        assert registered.status_code == 200
        assert client.cookies.get("datagenome_session") != prior
        assert app.state.auth.user(prior) is None
        assert guest.json()["guest"]
        assert (
            client.get(
                "/api/v1/projects", headers={"Host": "untrusted.invalid"}
            ).status_code
            == 400
        )


def test_owner_and_guest_cross_resource_matrix():
    from datagenome.api import create_app

    app = create_app()
    with TestClient(app) as owner:
        demo = owner.post("/api/v1/auth/guest").json()
        owner.headers["X-CSRF-Token"] = demo["csrf_token"]
        fixture = owner.post(
            "/api/v1/datasets/demo", json={"name": "Synthetic owned data"}
        ).json()
        p, v = fixture["project"]["id"], fixture["version"]["id"]
        for guest, username in (
            (True, ""),
            (True, ""),
            (False, "user-one"),
            (False, "user-two"),
        ):
            with closing(TestClient(app)) as outsider:
                session = outsider.post(
                    "/api/v1/auth/guest" if guest else "/api/v1/auth/register",
                    json={}
                    if guest
                    else {"username": username, "password": "synthetic-password-123"},
                ).json()
                outsider.headers["X-CSRF-Token"] = session["csrf_token"]
                for endpoint in (
                    f"/api/v1/projects/{p}/inventory",
                    f"/api/v1/datasets/{v}/configuration?project_id={p}",
                    f"/api/v1/projects/{p}",
                ):
                    assert outsider.get(endpoint).status_code == 404
                assert outsider.delete(f"/api/v1/projects/{p}").status_code == 404
                assert (
                    outsider.post(
                        "/api/v1/analyses",
                        json={"project_id": p, "version_id": v, "engines": ["profile"]},
                    ).status_code
                    == 404
                )


def test_every_protected_api_operation_rejects_missing_session():
    import re

    from datagenome.api import create_app

    app = create_app()
    public = {
        "/api/v1/capabilities",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/guest",
    }
    with TestClient(app) as client:
        checked = 0
        for path, methods in app.openapi()["paths"].items():
            if not path.startswith("/api/v1/") or path in public:
                continue
            for method in methods:
                if method not in {"get", "post", "delete", "patch", "put"}:
                    continue
                url = re.sub(r"\{[^}]+\}", "untrusted-id", path)
                assert (
                    client.request(
                        method, url, params={"project_id": "untrusted-id"}
                    ).status_code
                    == 401
                )
                checked += 1
        assert checked > 40


def test_derived_exports_escape_injection_without_changing_dataset_values():
    from datagenome.reporting import csv_cell, markdown_cell

    assert csv_cell(" =1+1").startswith("'")
    assert csv_cell("\t@SUM(1)").startswith("'")
    assert csv_cell("normal") == "normal"
    assert "<script>" not in markdown_cell("<script>alert(1)</script>")
    assert "[click]" not in markdown_cell("[click](javascript:alert(1))")


def test_rate_limits_recover_and_do_not_disable_unaffected_operations(
    tmp_path, monkeypatch
):
    import datagenome.auth as module

    store, _ = workspace(tmp_path)
    auth = Auth(store)
    clock = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    auth.rate("fixture-bucket", 2)
    auth.rate("fixture-bucket", 2)
    with pytest.raises(DatasetError) as error:
        auth.rate("fixture-bucket", 2)
    assert error.value.status == 429
    auth.rate("unaffected-bucket", 2)
    clock[0] += 61
    auth.rate("fixture-bucket", 2)


@pytest.mark.parametrize(
    "filename", ["../data.csv", "C:\\private\\data.csv", "data.csv\r\nInjected:yes.csv"]
)
def test_filename_traversal_and_header_controls_are_rejected(filename):
    from datagenome.ingestion import validate_filename

    with pytest.raises(DatasetError):
        validate_filename(filename)


def test_failed_startup_releases_workspace_lease(tmp_path, monkeypatch):
    from datagenome.api import create_app

    app = create_app()
    path = app.state.settings.store

    def fail_cleanup(self):
        raise sqlite3.OperationalError("synthetic storage failure")

    monkeypatch.setattr(Auth, "cleanup", fail_cleanup)
    with pytest.raises(sqlite3.OperationalError):
        with TestClient(app):
            pass
    with Lease(path):
        pass


def test_owner_job_capacity_is_scoped_and_recovers(tmp_path):
    from datagenome.jobs import JobService
    from datagenome.ownership import http_owner
    from datagenome.store import now

    store = Store(tmp_path / "queue.sqlite3")
    token = http_owner.set("first-owner")
    try:
        project = store.project("Bounded queue")["id"]
        service = JobService(store, recover=False)
        with store.connection() as db:
            for index in range(2):
                db.execute(
                    "INSERT INTO jobs VALUES (?,?,?,'{}',NULL,NULL,0,?,?)",
                    (str(index), project, "queued", now(), now()),
                )
            with pytest.raises(DatasetError) as error:
                service.owner_capacity(db)
            assert error.value.status == 429
            http_owner.set("second-owner")
            service.owner_capacity(db)
            http_owner.set("first-owner")
            db.execute("UPDATE jobs SET state='cancelled' WHERE id='0'")
            service.owner_capacity(db)
    finally:
        http_owner.reset(token)
