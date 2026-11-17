import json

import numpy as np
import pytest

from datagenome.anomalies import detect_anomalies
from datagenome.experiments import Intervention, compare
from datagenome.ingestion import Dataset, DatasetError
from datagenome.modeling import ModelConfig, fit_baseline, metrics
from datagenome.splits import SplitConfig, split


def fixture() -> tuple[Dataset, str]:
    return Dataset(
        ("x", "category", "constant", "label"),
        tuple((str(i), f"group{i}", "k", str(i % 3)) for i in range(72)),
    ), "label"


@pytest.mark.parametrize(
    "name", ["dummy", "logistic-regression", "decision-tree", "random-forest"]
)
def test_baselines_and_multiclass_metrics(name: str) -> None:
    data, target = fixture()
    manifest = split(data, SplitConfig("stratified"), target)
    result = fit_baseline(data, target, manifest, ModelConfig(name))
    assert set(result["metrics"]) == {"train", "validation"}
    validation = result["metrics"]["validation"]
    assert validation["roc_auc"] is not None
    assert validation["average_precision"] is None
    assert len(validation["per_class"]) == 3
    json.dumps(result, allow_nan=False)


def test_preprocessing_isolation_from_evaluation_cells() -> None:
    data, target = fixture()
    config = SplitConfig("stratified")
    manifest = split(data, config, target)
    before = fit_baseline(data, target, manifest)
    evaluation = set(manifest.partitions["validation"] + manifest.partitions["test"])
    changed = Dataset(
        data.columns,
        tuple(
            ("not numeric", "unseen", "k", row[-1]) if i in evaluation else row
            for i, row in enumerate(data.rows, 1)
        ),
    )
    after = fit_baseline(changed, target, split(changed, config, target))
    assert before["preprocessing"] == after["preprocessing"]
    assert before["metrics"]["train"] == after["metrics"]["train"]


def test_binary_and_undefined_metrics() -> None:
    good = metrics(
        ["a", "b"], ["a", "b"], np.array([[0.9, 0.1], [0.2, 0.8]]), ["a", "b"]
    )
    assert good["average_precision"] == good["roc_auc"] == 1
    sparse = metrics(["a"], ["a"], np.array([[0.9, 0.1]]), ["a", "b"])
    assert sparse["roc_auc"] is None
    assert "roc_auc" in sparse["undefined_metrics"]
    assert sparse["log_loss"] > 0
    unseen = metrics(["c"], ["a"], np.array([[0.9, 0.1]]), ["a", "b"])
    assert unseen["log_loss"] is None


def test_experiment_protects_test_and_detects_contamination() -> None:
    data, target = fixture()
    manifest = split(data, SplitConfig(), target)
    result = compare(
        data, target, manifest, Intervention(constant_features=("constant",))
    )
    assert result["status"] == "compared"
    assert result["affected_features"] == 1
    assert result["held_out_evaluated"] is False
    assert "test" not in result["modified"]["metrics"]
    with pytest.raises(DatasetError, match="training"):
        compare(
            data,
            target,
            manifest,
            Intervention(excluded_records=(manifest.partitions["test"][0],)),
        )
    src, dest = manifest.partitions["train"][0], manifest.partitions["test"][0]
    rows = list(data.rows)
    rows[dest - 1] = rows[src - 1]
    dirty = Dataset(data.columns, tuple(rows))
    compromised = compare(
        dirty,
        target,
        split(dirty, manifest.config, target),
        Intervention(remove_duplicates=True),
    )
    assert compromised["status"] == "compromised"
    assert "original" not in compromised


def test_anomaly_scores_repeat_and_handle_small_samples() -> None:
    data = Dataset(
        ("x", "flat", "category"),
        tuple((str(i % 7 if i < 40 else 1000), "1", "a") for i in range(41)),
    )
    report = detect_anomalies(data)
    assert report == detect_anomalies(data)
    assert report["ranked"][0]["record"] == 41
    assert all(
        result["status"] == "evaluated" for result in report["detectors"].values()
    )
    small = detect_anomalies(Dataset(data.columns, data.rows[:2]))
    assert all(
        result["status"] == "unsupported" for result in small["detectors"].values()
    )


def test_explicit_final_evaluation_replays_selected_intervention() -> None:
    from datagenome.analysis import execute

    dataset, target = fixture()
    payload = (
        "x,category,constant,label\n" + "\n".join(",".join(row) for row in dataset.rows)
    ).encode()
    result = execute(
        "evaluate",
        payload,
        target=target,
        limit=10000,
        intervention=Intervention(constant_features=("constant",)),
    )
    assert "test" in result["model"]["metrics"]
    assert "constant" not in result["model"]["preprocessing"]["categorical"]
    assert result["intervention"]["constant_features"] == ("constant",)
