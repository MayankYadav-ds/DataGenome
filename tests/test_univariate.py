from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.leakage import LeakageConfig, inspect_leakage
from datagenome.splits import Manifest, SplitConfig
from datagenome.univariate import UnivariateConfig


def audit(rows, *, config=UnivariateConfig()):
    data = Dataset(("numeric", "category", "unique", "target"), tuple(rows))
    manifest = Manifest(
        canonical(data),
        SplitConfig(seed=42),
        {
            "train": list(range(1, len(rows) - 1)),
            "validation": [len(rows) - 1],
            "test": [len(rows)],
        },
    )
    return [
        item
        for item in inspect_leakage(
            data, "target", manifest, LeakageConfig(univariate=config)
        )
        if item.method == "univariate_predictive"
    ]


def fixture(classes):
    return [
        (
            "" if i % 17 == 0 else str((i % classes) * 100 + i % 11),
            "" if i % 19 == 0 else f"category-{i % classes}",
            f"unique-{i}",
            str(i % classes),
        )
        for i in range(122)
    ]


def test_univariate_is_identical_after_outer_holdout_changes():
    rows = fixture(3)
    before = audit(rows)
    rows[-2:] = [
        ("1000000", "never-observed", "holdout", "renamed"),
        ("invalid numeric", "", "holdout", "another-class"),
    ]
    assert before == audit(rows)


def test_univariate_binary_and_multiclass_with_missing_and_unseen_values():
    for classes in (2, 3):
        results = {item.columns[0]: item for item in audit(fixture(classes))}
        assert results["numeric"].classification == "suspicious_heuristic"
        assert results["category"].classification == "suspicious_heuristic"
        assert results["unique"].classification == "no_signal"
        for item in results.values():
            evidence = item.evidence
            assert evidence["evaluated_records"] == 120
            assert evidence["metric"] == "balanced_accuracy"
            assert abs(evidence["baseline_score"] - 1 / classes) < 1e-12
            assert sum(f["evaluated_records"] for f in evidence["fold_scores"]) == 120


def test_univariate_insufficient_classes_and_feature_cap_are_explicit():
    too_few = audit(fixture(3)[:6])
    assert too_few[0].classification == "insufficient_evidence"
    assert too_few[0].evidence["score"] is None
    capped = audit(fixture(3), config=UnivariateConfig(max_features=1))
    assert len(capped) == 2
    assert capped[-1].evidence["omitted_features"] == ["category", "unique"]
