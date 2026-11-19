from fastapi.testclient import TestClient

from datagenome.api import create_app
from datagenome.profiling import profile


def authenticate(client):
    result = client.post("/api/v1/auth/guest")
    assert result.status_code == 200
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]


def test_owned_inventory_and_configuration_privacy():
    app = create_app()
    with TestClient(app) as owner:
        outsider = TestClient(app)
        authenticate(owner)
        authenticate(outsider)
        demo = owner.post("/api/v1/datasets/demo", json={"name": "Synthetic"}).json()
        p, v = demo["project"]["id"], demo["version"]["id"]
        inventory = owner.get(f"/api/v1/projects/{p}/inventory").json()
        assert len(inventory["datasets"]) == 1 and not inventory["analyses"]
        assert "rows" not in inventory["datasets"][0]
        assert outsider.get(f"/api/v1/projects/{p}/inventory").status_code == 404
        config = owner.get(f"/api/v1/datasets/{v}/configuration?project_id={p}").json()
        assert config["partitions"] is None and config["record_ids"] is None
        assert (
            outsider.get(
                f"/api/v1/datasets/{v}/configuration?project_id={p}&reviewed=true"
            ).status_code
            == 404
        )
        reviewed = owner.get(
            f"/api/v1/datasets/{v}/configuration?project_id={p}&reviewed=true"
        ).json()
        assert len(reviewed["record_ids"]) == demo["version"]["row_count"]
        assert sum(reviewed["partition_counts"].values()) == 80
        outsider.close()


def test_synthetic_demo_contains_documented_training_only_problems():
    app = create_app()
    with TestClient(app) as client:
        authenticate(client)
        demo = client.post("/api/v1/datasets/demo", json={"name": "Fixture"}).json()
        p, v = demo["project"]["id"], demo["version"]["id"]
        stored = app.state.auth.store.get(p, v, "version")
        from datagenome.versions import manifest_of, table

        data = table(stored)
        manifest = manifest_of(stored)
        measured = profile(data, "label")
        assert measured.duplicate_row_count > 0
        assert any(c.missing_count > 0 for c in measured.columns)
        assert all(
            row[data.columns.index("review_code")] == row[-1] for row in data.rows
        )
        train = {tuple(data.rows[i - 1][:-1]) for i in manifest.partitions["train"]}
        assert not any(
            tuple(data.rows[i - 1][:-1]) in train
            for i in manifest.partitions["validation"]
        )


def test_analysis_accepts_explicit_bounded_valuation_method():
    app = create_app()
    with TestClient(app) as client:
        authenticate(client)
        demo = client.post("/api/v1/datasets/demo", json={"name": "Valuation"}).json()
        p, v = demo["project"]["id"], demo["version"]["id"]
        response = client.post(
            "/api/v1/analyses",
            json={
                "project_id": p,
                "version_id": v,
                "engines": ["valuation"],
                "valuation_method": "shapley",
            },
        )
        assert response.status_code == 200
        job = response.json()
        with app.state.auth.store.connection() as db:
            import json

            config = json.loads(
                db.execute(
                    "SELECT request FROM jobs WHERE id=?", (job["id"],)
                ).fetchone()[0]
            )["config"]
            assert config["valuation_method"] == "shapley"
        assert (
            client.post(
                "/api/v1/analyses",
                json={
                    "project_id": p,
                    "version_id": v,
                    "engines": ["valuation"],
                    "valuation_method": "invented",
                },
            ).status_code
            == 422
        )
