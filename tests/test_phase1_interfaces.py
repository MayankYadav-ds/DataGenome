import asyncio
import json
import subprocess
import sys

from httpx import ASGITransport, AsyncClient

from datagenome.api import create_app

CSV = b"x,kind,label\n" + b"".join(
    f"{i},category{i},class{i % 2}\n".encode() for i in range(36)
)


def test_phase1_api_routes() -> None:
    async def exercise() -> None:
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for path, result in (
                ("datasets/diagnose", "intelligence"),
                ("datasets/anomalies", "anomalies"),
                ("datasets/leakage", "leakage"),
                ("datasets/split", "split"),
                ("models/train", "model"),
                ("models/evaluate", "model"),
                ("experiments/compare", "experiment"),
            ):
                response = await client.post(
                    f"/api/v1/{path}?filename=test.csv&target=label&model=dummy&intervention=remove-duplicates",
                    content=CSV,
                    headers={"content-type": "text/csv"},
                )
                assert response.status_code == 200, response.text
                assert result in response.json()
                assert response.json()["schema_version"] == "1.0"
            invalid = await client.post(
                "/api/v1/datasets/split?filename=test.csv&seed=-1",
                content=CSV,
                headers={"content-type": "text/csv"},
            )
            assert invalid.status_code == 422
            assert invalid.json()["error"]["code"] == "invalid_request"
            assert (
                "text/csv"
                in app.openapi()["paths"]["/api/v1/datasets/diagnose"]["post"][
                    "requestBody"
                ]["content"]
            )
        capped = create_app(max_rows=2)
        async with AsyncClient(
            transport=ASGITransport(app=capped), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/datasets/profile?filename=test.csv",
                content=CSV,
                headers={"content-type": "text/csv"},
            )
            assert response.status_code == 413
            assert response.json()["error"]["code"] == "row_limit"

    asyncio.run(exercise())


def test_cli_manifest_roundtrip(tmp_path) -> None:
    dataset = tmp_path / "example.csv"
    dataset.write_bytes(CSV)
    manifest = tmp_path / "split.json"
    command = [sys.executable, "-m", "datagenome"]
    subprocess.run(
        [
            *command,
            "split",
            str(dataset),
            "--target",
            "label",
            "--output",
            str(manifest),
        ],
        check=True,
    )
    response = subprocess.check_output(
        [
            *command,
            "detect-leakage",
            str(dataset),
            "--target",
            "label",
            "--manifest",
            str(manifest),
        ]
    )
    assert json.loads(response)["split"] == json.loads(manifest.read_text())["split"]


def test_univariate_cli_and_api_opt_in(tmp_path):
    path = tmp_path / "input.csv"
    path.write_bytes(CSV)
    command = [
        sys.executable,
        "-m",
        "datagenome",
        "detect-leakage",
        str(path),
        "--target",
        "label",
        "--univariate",
        "--univariate-folds",
        "2",
    ]
    result = json.loads(subprocess.check_output(command))
    assert any(item["method"] == "univariate_predictive" for item in result["leakage"])

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            path = "/api/v1/datasets/leakage?filename=test.csv&target=label"
            for suffix, enabled in (
                ("", False),
                ("&univariate=true&univariate_folds=2", True),
            ):
                response = await client.post(
                    path + suffix, content=CSV, headers={"content-type": "text/csv"}
                )
                assert response.status_code == 200
                assert (
                    any(
                        item["method"] == "univariate_predictive"
                        for item in response.json()["leakage"]
                    )
                    == enabled
                )

    asyncio.run(exercise())
