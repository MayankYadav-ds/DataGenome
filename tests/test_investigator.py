import asyncio
import json
import subprocess
import sys

import pytest
from auth_helpers import authenticate_async
from httpx import ASGITransport, AsyncClient

from datagenome.api import create_app
from datagenome.error_slices import analyze_errors
from datagenome.experiments import Intervention
from datagenome.identity import canonical
from datagenome.ingestion import Dataset, DatasetError
from datagenome.investigator import inspect_prediction
from datagenome.splits import Manifest, SplitConfig, split


def fixture():
    rows = []
    for i in range(75):
        label = i % 2
        flipped = 45 <= i < 55
        rows.append(
            (
                str(3 * (1 - label if flipped else label) + i * 0.001),
                str(i % 3),
                f"private-{label}",
            )
        )
    dataset = Dataset(("private-signal", "batch", "label"), tuple(rows))
    parts = {
        "train": list(range(1, 46)),
        "validation": list(range(46, 71)),
        "test": list(range(71, 76)),
    }
    return dataset, Manifest(canonical(dataset), SplitConfig(), parts)


def test_investigation_logit_evidence_and_holdout_guard():
    data, manifest = fixture()
    result = inspect_prediction(
        data, "label", manifest, 46, Intervention(excluded_records=(1,))
    )
    assert not result["prediction"]["correct"]
    contribution = result["contribution"]
    assert contribution["logit"] == pytest.approx(
        contribution["reconstructed_logit"], abs=1e-10
    )
    assert result["prediction_influence"]["status"] == "experimental"
    assert result["intervention"]["retained_training_records"] == 44
    nodes = set(result["evidence_graph"]["nodes"])
    assert all(
        edge["source"] in nodes and edge["target"] in nodes
        for edge in result["evidence_graph"]["edges"]
    )
    with pytest.raises(DatasetError, match="validation record"):
        inspect_prediction(data, "label", manifest, 71)


def test_slice_support_and_summary_privacy():
    data, manifest = fixture()
    detailed = analyze_errors(data, "label", manifest, min_support=6)
    assert detailed["slices"]
    assert all(item["records"] >= 6 for item in detailed["slices"])
    summary = inspect_prediction(data, "label", manifest, 46, summary_only=True)
    assert not any(
        secret in json.dumps(summary)
        for secret in ("private-0", "private-signal", "record_id", "sha256")
    )
    assert "slices" not in analyze_errors(data, "label", manifest, summary_only=True)


def test_investigation_cli_and_redacted_api(tmp_path):
    data, _ = fixture()
    record = split(data, SplitConfig(), "label").partitions["validation"][0]
    payload = (
        ",".join(data.columns) + "\n" + "\n".join(",".join(row) for row in data.rows)
    ).encode()
    path = tmp_path / "data.csv"
    path.write_bytes(payload)
    args = [
        sys.executable,
        "-m",
        "datagenome",
        "investigate",
        str(path),
        "--target",
        "label",
        "--record-id",
        str(record),
        "--privacy-mode",
        "summary",
    ]
    output = json.loads(subprocess.check_output(args))
    assert "identity" not in output and "split" not in output
    assert "prediction" not in output["investigation"]

    async def run():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://local"
        ) as client:
            await authenticate_async(client)
            response = await client.post(
                f"/api/v1/models/investigate?filename=data.csv&target=label&record_id={record}&privacy_mode=redacted",
                content=payload,
                headers={"content-type": "text/csv"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["investigation"] == output["investigation"]

    asyncio.run(run())
