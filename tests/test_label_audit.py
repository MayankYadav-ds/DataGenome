import asyncio
import json
import subprocess
import sys

from httpx import ASGITransport, AsyncClient

from datagenome.api import create_app
from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.label_audit import audit_labels
from datagenome.splits import Manifest, SplitConfig, split


def fixture() -> Dataset:
    return Dataset(
        ("signal", "batch", "label"),
        tuple(
            (
                str((i % 3) * 100 + i % 7),
                f"batch-{i % 5}",
                str((i + 1) % 3 if i == 0 else i % 3),
            )
            for i in range(100)
        ),
    )


def test_label_audit_flags_injected_training_issue_and_is_holdout_invariant():
    data = fixture()
    parts = {
        "train": list(range(1, 91)),
        "validation": list(range(91, 96)),
        "test": list(range(96, 101)),
    }
    config = SplitConfig(seed=42)
    report = audit_labels(data, "label", Manifest(canonical(data), config, parts))
    assert report["status"] == "evaluated"
    assert report["evaluated_records"] == 90
    assert report["candidates"][0]["record_id"] == 1
    assert report["candidates"][0]["classification"] == "suspected_label_issue"
    changed = Dataset(data.columns, data.rows[:90] + (("inf", "new", "unseen"),) * 10)
    assert report == audit_labels(
        changed, "label", Manifest(canonical(changed), config, parts)
    )


def test_grouped_validation_rejects_insufficient_distinct_feature_vectors():
    data = Dataset(("signal", "label"), (("1", "a"), ("1", "b")) * 12)
    report = audit_labels(data, "label", split(data, SplitConfig(seed=42)))
    assert report["status"] == "insufficient_evidence"
    assert report["evaluated_records"] == 0
    assert report["candidates"] == []


def test_label_audit_cli_and_api(tmp_path):
    data = fixture()
    payload = (
        ",".join(data.columns) + "\n" + "\n".join(",".join(row) for row in data.rows)
    ).encode()
    path = tmp_path / "labels.csv"
    path.write_bytes(payload)
    result = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-m",
                "datagenome",
                "audit-labels",
                str(path),
                "--target",
                "label",
            ]
        )
    )
    assert result["label_audit"]["status"] == "evaluated"

    async def check():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/datasets/label-audit?filename=labels.csv&target=label",
                content=payload,
                headers={"content-type": "text/csv"},
            )
            assert response.status_code == 200
            assert response.json()["label_audit"] == result["label_audit"]

    asyncio.run(check())
