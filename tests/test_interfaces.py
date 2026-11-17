import asyncio
import json
import subprocess
import sys
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from datagenome import __version__
from datagenome.api import create_app


def test_api() -> None:
    async def exercise() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app(30)), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/version")).json() == {"version": __version__}
            url = "/api/v1/datasets/profile"
            args = {"filename": "test.csv", "target": "label"}
            headers = {"content-type": "text/csv"}
            success = await client.post(
                url, params=args, headers=headers, content=b"x,label\n1,a\n2,b\n"
            )
            assert success.status_code == 200
            assert success.json()["target_distribution"] == {"a": 1, "b": 1}
            for params, body, media, status, code in [
                ({}, b"", headers, 422, "invalid_request"),
                ({"filename": "x.txt"}, b"", headers, 415, "unsupported_file"),
                (args, b"", {}, 415, "unsupported_media_type"),
                (args, b"x" * 31, headers, 413, "file_too_large"),
                (args, b"", headers, 422, "empty_dataset"),
                (args, b"x\n1\n", headers, 422, "unknown_target"),
            ]:
                rejected = await client.post(
                    url, params=params, content=body, headers=media
                )
                assert rejected.status_code == status
                assert rejected.json()["error"]["code"] == code

    asyncio.run(exercise())


def test_demo_cli(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "examples" / "generate_demo.py"
    csv = tmp_path / "demo.csv"
    report = tmp_path / "report.json"
    subprocess.run([sys.executable, str(script), str(csv)], check=True)
    command = [sys.executable, "-m", "datagenome"]
    subprocess.run([*command, "--help"], check=True, capture_output=True)
    version = subprocess.check_output([*command, "--version"], text=True)
    assert version.strip() == __version__
    run = [*command, "profile", str(csv)]
    assert (
        json.loads(subprocess.check_output(run, text=True))["target_distribution"]
        is None
    )
    subprocess.run([*run, "--target", "label", "--output", str(report)], check=True)
    result = json.loads(report.read_text(encoding="utf-8"))
    assert (result["row_count"], result["duplicate_row_count"]) == (21, 1)
    assert result["target_distribution"] == {"majority": 20, "minority": 1}
    assert {finding["category"] for finding in result["findings"]} == {
        "class_imbalance",
        "constant_column",
        "duplicate_rows",
        "missing_values",
    }
    assert result["columns"][1]["missing_count"] == 2
    original = csv.read_bytes()
    failed = subprocess.run([*run, "--output", str(csv)], capture_output=True)
    assert failed.returncode == 2
    assert json.loads(failed.stderr)["code"] == "invalid_output"
    assert csv.read_bytes() == original
