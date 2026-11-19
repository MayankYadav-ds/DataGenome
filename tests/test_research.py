import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from datagenome.benchmark_data import corrupt, synthetic
from datagenome.benchmark_protocol import freeze
from datagenome.benchmark_studies import mathematical_reference
from datagenome.folds import historical_folds
from datagenome.holdouts import claim
from datagenome.identity import canonical
from datagenome.ingestion import Dataset, DatasetError
from datagenome.leakage import LeakageConfig, inspect_leakage
from datagenome.splits import SplitConfig, split
from datagenome.univariate import UnivariateConfig


def test_holdout_overlap_survives_changed_training_labels_and_partition(tmp_path):
    data = synthetic(3, 60)
    manifest = split(data, SplitConfig("stratified", seed=3), "label")
    claim(manifest, tmp_path, "first", data, "label")
    altered = corrupt(data, manifest.partitions["train"], "uniform_labels", 0.2, 4).data
    parts = {k: v.copy() for k, v in manifest.partitions.items()}
    parts["validation"][0], parts["test"][0] = parts["test"][0], parts["validation"][0]
    with pytest.raises(DatasetError, match="already claimed"):
        claim(
            replace(manifest, dataset_sha256=canonical(altered), partitions=parts),
            tmp_path,
            "second",
            altered,
            "label",
        )
    # Non-overlapping records can be scored, even with the same schema.
    other = synthetic(300, 60)
    claim(
        split(other, SplitConfig("stratified"), "label"),
        tmp_path,
        "third",
        other,
        "label",
    )


def test_legacy_ledger_and_concurrent_claims_fail_closed(tmp_path):
    data = synthetic(1, 40)
    manifest = split(data, SplitConfig("stratified"), "label")
    (tmp_path / "old.json").write_text(json.dumps({"status": "claimed"}))
    with pytest.raises(DatasetError, match="Legacy"):
        claim(manifest, tmp_path, "new", data, "label")
    assert not (tmp_path / ".claim-lock").exists()
    (tmp_path / ".claim-lock").mkdir()
    with pytest.raises(DatasetError, match="locked"):
        claim(manifest, tmp_path, "new", data, "label")


@pytest.mark.parametrize(
    "kind",
    [
        "uniform_labels",
        "class_labels",
        "feature_labels",
        "missing",
        "systematic_missing",
        "duplicates",
        "conflicting_duplicates",
        "anomalies",
        "redundant",
        "mean_shift",
        "variance_shift",
        "new_category",
        "dependence_shift",
        "outcome_change",
    ],
)
def test_corruptions_match_truth_and_preserve_outer_records(kind):
    original = synthetic(5, 100)
    ids = list(range(1, 61))
    changed = corrupt(original, ids, kind, 0.2, 11)
    assert changed == corrupt(original, ids, kind, 0.2, 11)
    assert changed.data.rows[60:] == original.rows[60:]
    actual = {
        i
        for i, (a, b) in enumerate(
            zip(original.rows, changed.data.rows, strict=True), 1
        )
        if a != b
    }
    assert actual == changed.changed
    assert changed.data is not original
    assert not corrupt(original, ids, kind, 0.0, 11).changed


def test_protocol_freeze_rejects_modified_configuration(tmp_path):
    path = tmp_path / "frozen.json"
    first = freeze(path, (11, 23, 37))
    assert freeze(path, (11, 23, 37)) == first
    with pytest.raises(DatasetError, match="differs"):
        freeze(path, (11,))


def test_independent_permutation_reference():
    out = mathematical_reference(11)
    assert out["shapley_max_error"] < 1e-12
    assert out["banzhaf_max_error"] < 1e-12
    assert out["efficiency_residual"] < 1e-12


def test_forward_univariate_isolated_from_outer_records():
    rows = tuple(
        (str(i % 7), f"2020-01-{1 + i // 4:02d}T00:00:00", str(i % 2))
        for i in range(80)
    )
    data = Dataset(("x", "time", "label"), rows)
    manifest = split(data, SplitConfig("chronological", time="time"), "label")
    folds = historical_folds(data, manifest.partitions["train"], "time", 3)
    train = manifest.partitions["train"]
    assert len(folds) == 3
    for fit, score in folds:
        assert max(data.rows[train[i] - 1][1] for i in fit) < min(
            data.rows[train[i] - 1][1] for i in score
        )
    config = LeakageConfig(univariate=UnivariateConfig(max_features=2))

    def scores(d, m):
        return [
            (s.columns, s.classification, s.evidence)
            for s in inspect_leakage(d, "label", m, config)
            if s.method == "univariate_predictive"
        ]

    before = scores(data, manifest)
    outer = set(manifest.partitions["validation"] + manifest.partitions["test"])
    altered = Dataset(
        data.columns,
        tuple(
            ("999", row[1], str(1 - int(row[-1]))) if i in outer else row
            for i, row in enumerate(data.rows, 1)
        ),
    )
    assert (
        scores(altered, replace(manifest, dataset_sha256=canonical(altered))) == before
    )
    assert before[0][2]["fold_strategy"] == "forward_only_expanding"


def test_published_artifact_identities_and_numerical_acceptance():
    root = Path(__file__).resolve().parents[1]
    folder = root / "benchmarks/results/phase9"
    index = json.loads((folder / "index.json").read_text())
    protocol = json.loads((root / "benchmarks/protocols/phase9-v1.json").read_text())
    total = 0
    for suite, meta in index.items():
        payload = (folder / suite / "results.json").read_bytes()
        assert hashlib.sha256(payload).hexdigest() == meta["sha256"]
        result = json.loads(payload)
        assert result["protocol_sha256"] == protocol["protocol_sha256"]
        assert len(result["trials"]) == meta["trials"]
        assert len({t["experiment_id"] for t in result["trials"]}) == meta["trials"]
        total += meta["trials"]
        if suite == "influence":
            for trial in result["trials"]:
                if trial["suite"] == "influence" and trial["status"] == "evaluated":
                    assert (
                        trial["result"]["gradient_max_error"]
                        < protocol["plan"]["influence"]["gradient_atol"]
                    )
                    assert (
                        trial["result"]["hessian_max_error"]
                        < protocol["plan"]["influence"]["hessian_atol"]
                    )
                    assert (
                        trial["result"]["solver_residual"]
                        <= protocol["plan"]["influence"]["solve_rtol"]
                    )
    summary = json.loads((root / "frontend/public/research-results.json").read_text())
    assert sum(s["trials"] for s in summary["suites"]) == total
    assert summary["protocol_sha256"] == protocol["protocol_sha256"]


def test_smoke_result_serialization_and_truth_isolation(tmp_path):
    from datagenome.benchmark import run

    result = run("smoke", tmp_path / "output", tmp_path / "protocol.json", (11,))
    assert len(result["trials"]) == 3
    assert result["status"] == "completed"
    published = json.loads((tmp_path / "output/results.json").read_text())
    assert published == result
    assert "rows" not in published["trials"][0]["result"]
    assert (tmp_path / "output/summary.csv").exists()
    assert (tmp_path / "output/report.md").exists()
