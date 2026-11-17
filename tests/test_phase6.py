import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from random import Random

import pytest
from httpx import ASGITransport, AsyncClient

from datagenome.api import create_app
from datagenome.confirmation import confirm_slices, freeze_slices
from datagenome.drift import DriftConfig, detect_drift, holm
from datagenome.fairness import (
    FairnessConfig,
    audit_fairness,
    binary_metrics,
    compare_fairness,
)
from datagenome.folds import connected_groups, historical_folds
from datagenome.identity import canonical
from datagenome.ingestion import Dataset, DatasetError
from datagenome.label_audit import LabelAuditConfig, audit_labels
from datagenome.modeling import ModelConfig, fit_baseline
from datagenome.performance_drift import performance_drift
from datagenome.proxies import detect_proxies
from datagenome.splits import Manifest, SplitConfig, split


def fixture():
    rows = []
    for i in range(150):
        group = (i // 2) % 3
        y = i % 2
        score = 1 - y if i >= 90 and group == 1 else y
        rows.append(
            (
                str(score * 10 + i * 0.001),
                f"private-{group}",
                f"entity-{i // 6}",
                (datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i // 2)).isoformat(),
                str(y),
            )
        )
    data = Dataset(("x", "sensitive", "entity", "time", "label"), tuple(rows))
    parts = {
        "train": list(range(1, 91)),
        "validation": list(range(91, 121)),
        "test": list(range(121, 151)),
    }
    return data, Manifest(canonical(data), SplitConfig(), parts)


def test_groups_and_history_are_isolated():
    data, _ = fixture()
    grouped = split(data, SplitConfig("group", group="entity"), "label")
    groups = [{data.rows[i - 1][2] for i in ids} for ids in grouped.partitions.values()]
    assert sum(map(len, groups)) == len(set.union(*groups))
    base = fit_baseline(data, "label", grouped)
    assert "entity" not in base["preprocessing"]["categorical"]
    assert audit_labels(data, "label", grouped)["evaluated_records"] == len(
        grouped.partitions["train"]
    )
    assert connected_groups([("x", "a"), ("x", "b"), ("y", "b")]) == [0, 0, 0]
    chrono = split(data, SplitConfig("chronological", time="time"), "label")
    ids = chrono.partitions["train"]
    folds = historical_folds(data, ids, "time", 3, 86400)
    for fit, score in folds:
        latest = max(datetime.fromisoformat(data.rows[ids[i] - 1][3]) for i in fit)
        earliest = min(datetime.fromisoformat(data.rows[ids[i] - 1][3]) for i in score)
        assert earliest - latest > timedelta(days=1)
    result = audit_labels(
        data, "label", chrono, LabelAuditConfig(folds=3, temporal_gap_seconds=86400)
    )
    assert 0 < result["evaluated_records"] < len(ids)
    assert result["unscored_labeled_records"] + result["evaluated_records"] == len(ids)


def test_fairness_metrics_privacy_and_exclusion():
    simple = binary_metrics([True, False], [False, False], [0.1, 0.2], True)
    assert simple["confusion_matrix"] == [[1, 0], [1, 0]]
    assert simple["precision"]["value"] is None
    assert simple["false_negative_rate"]["value"] == 1
    data, manifest = fixture()
    config = FairnessConfig(
        ("sensitive",), min_support=6, min_class_count=2, summary_only=False
    )
    detailed = audit_fairness(data, "label", manifest, config)
    group = detailed["comparisons"][0]
    assert group["disparities"]["equal_opportunity_difference"] == 1
    assert "sensitive" in detailed["audit_features_excluded"]
    summary = audit_fairness(
        data, "label", manifest, FairnessConfig(("sensitive",), min_support=11)
    )
    assert "private-" not in json.dumps(summary)
    assert (
        summary["comparisons"][0]["disparities"]["equal_opportunity_difference"] is None
    )
    assert (
        compare_fairness(data, "label", manifest, config, ModelConfig(), (1, 2))[
            "held_out_evaluated"
        ]
        is False
    )
    with pytest.raises(DatasetError, match="training records"):
        compare_fairness(data, "label", manifest, config, ModelConfig(), (121,))


def test_proxy_and_drift_detect_injections_and_control():
    rng = Random(42)
    base = Dataset(
        ("x", "y", "cat", "group", "proxy"),
        tuple(
            (
                str(rng.gauss(0, 1)),
                str(rng.gauss(0, 1)),
                "a" if i % 2 else "b",
                str(i % 2),
                "proxy-" + str(i % 2),
            )
            for i in range(200)
        ),
    )
    shifted = Dataset(
        base.columns,
        tuple(
            ("" if i < 40 else str(float(row[0]) + 3), row[1], "new", row[3], row[4])
            for i, row in enumerate(base.rows)
        ),
    )
    cfg = DriftConfig(iid=True, summary_only=False)
    flags = detect_drift(base, shifted, cfg)
    assert flags["review_count"] >= 3
    assert flags["multivariate"]["status"] == "evaluated"
    assert detect_drift(base, base, cfg)["review_count"] == 0
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    found = detect_proxies(
        base, split(base, SplitConfig()), "group", summary_only=False
    )
    assert any(
        row["feature"] == "proxy" and row["potential_proxy"]
        for row in found["findings"]
    )


def test_slice_confirmation_freeze_and_shared_ledger(tmp_path):
    data, manifest = fixture()
    path = tmp_path / "local.protocol.json"
    frozen = freeze_slices(data, "label", manifest, ModelConfig(), path, min_support=6)
    assert frozen["plan"]["slices"]
    result = confirm_slices(data, path, tmp_path / "ledger", summary_only=False)
    assert result["held_out_scored"]
    assert any(row["outcome"] == "descriptive_replication" for row in result["slices"])
    with pytest.raises(DatasetError, match="already claimed"):
        confirm_slices(data, path, tmp_path / "ledger")


def test_performance_drift_uses_same_fit():
    data, manifest = fixture()
    aligned = Dataset(("x", "label"), tuple((row[0], row[-1]) for row in data.rows))
    later = Dataset(
        aligned.columns, tuple((str(20 + i * 0.001), str(i % 2)) for i in range(40))
    )
    result = performance_drift(
        aligned,
        later,
        "label",
        Manifest(canonical(aligned), manifest.config, manifest.partitions),
    )
    assert result["same_fitted_model"]
    assert set(result["changes"]) == {
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "calibration_ece",
    }


def test_phase6_cli_and_rest(tmp_path):
    data, _ = fixture()
    body = ",".join(data.columns) + "\n" + "\n".join(",".join(row) for row in data.rows)
    path = tmp_path / "fixture.csv"
    path.write_text(body, encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "datagenome",
        "audit-fairness",
        str(path),
        "--target",
        "label",
        "--sensitive-column",
        "sensitive",
        "--minimum-support",
        "5",
    ]
    assert json.loads(subprocess.check_output(command))["fairness"]

    async def run():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://local"
        ) as client:
            for endpoint in ("fairness", "proxies"):
                response = await client.post(
                    "/api/v1/datasets/" + endpoint,
                    params={
                        "filename": "data.csv",
                        "target": "label",
                        "sensitive_column": "sensitive",
                        "minimum_support": 5,
                    },
                    content=body,
                    headers={"Content-Type": "text/csv"},
                )
                assert response.status_code == 200, response.text
                assert "private-" not in response.text
            response = await client.post(
                "/api/v1/datasets/drift",
                json={"reference_csv": body, "comparison_csv": body, "target": "label"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["drift"]["review_count"] == 0

    asyncio.run(run())


def test_explicit_availability_violation_and_metadata_duplicate_check():
    from datagenome.leakage import LeakageConfig, inspect_leakage

    data = Dataset(
        ("x", "entity", "when", "available", "label"),
        (
            ("1", "a", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "a"),
            ("5", "a", "2024-01-01T01:00:00Z", "2024-01-01T00:00:00Z", "b"),
            ("1", "b", "2024-01-02T00:00:00Z", "2024-01-01T01:00:00Z", "a"),
            ("8", "c", "2024-01-03T00:00:00Z", "2024-01-03T00:00:00Z", "b"),
        ),
    )
    manifest = Manifest(
        canonical(data),
        SplitConfig(),
        {"train": [1, 2], "validation": [3], "test": [4]},
    )
    signals = inspect_leakage(
        data,
        "label",
        manifest,
        LeakageConfig(group="entity", time="when", availability=(("x", "available"),)),
    )
    found = {
        signal.method
        for signal in signals
        if signal.classification == "confirmed_violation"
    }
    assert {"feature_available_after_prediction", "cross_split_features"} <= found
