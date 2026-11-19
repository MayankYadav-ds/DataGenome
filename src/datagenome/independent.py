import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

from .identity import fingerprint
from .ingestion import Dataset, DatasetError
from .modeling import ModelConfig, fit_baseline
from .removal import compare_removal
from .splits import Manifest, column, restore, validate
from .valuation import ValuationConfig

METRICS = (
    "accuracy",
    "balanced_accuracy",
    "macro_f1",
    "negative_log_loss",
    "per_class_recall",
)
MAX_PROTOCOL_BYTES = 2_000_000


def create_json(path: Path, value: object) -> None:
    payload = json.dumps(value, allow_nan=False, sort_keys=True)
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(payload + "\n")
    except FileExistsError as error:
        raise DatasetError(
            "protocol_exists", "An evaluation artifact already exists."
        ) from error


def freeze_removal(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    valuation: ValuationConfig,
    model: ModelConfig,
    fraction: float,
    path: Path,
) -> dict[str, Any]:
    """Persist the selection and its exploratory metrics before final scoring."""
    exploratory = compare_removal(
        dataset, target, manifest, valuation, model, fraction, include_duplicates=True
    )
    plan = {
        "schema_version": "1.0",
        "dependency_versions": {
            name: version(name) for name in ("datagenome", "scikit-learn", "numpy")
        },
        "target": target,
        "eligibility_policy": "matched-class-caps-v1",
        "split": {**asdict(manifest), "fingerprint": manifest.fingerprint},
        "valuation": asdict(valuation),
        "model": asdict(model),
        "fraction": fraction,
        "outcomes": METRICS,
        "matched_removal_count": exploratory["matched_removal_count"],
        "arms": {
            name: arm["removed_ids"]
            for name, arm in exploratory["arms"].items()
            if arm["status"] == "evaluated"
        },
        "unavailable_arms": {
            name: arm["status"]
            for name, arm in exploratory["arms"].items()
            if arm["status"] != "evaluated"
        },
    }
    frozen = {
        "plan": plan,
        "protocol_sha256": fingerprint(plan),
        "exploratory": exploratory,
    }
    create_json(path, frozen)
    return frozen


def final_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: metrics[key] for key in ("accuracy", "balanced_accuracy", "macro_f1")},
        "negative_log_loss": -metrics["log_loss"]
        if metrics["log_loss"] is not None
        else None,
        "per_class_recall": {
            label: row["recall"] for label, row in metrics["per_class"].items()
        },
    }


def claim_holdout(
    manifest: Manifest,
    ledger: Path,
    protocol_id: str,
    dataset: Dataset | None = None,
    target: str | None = None,
) -> str:
    from .holdouts import claim

    return claim(manifest, ledger, protocol_id, dataset, target)


def score_frozen(dataset: Dataset, protocol_path: Path, ledger: Path) -> dict[str, Any]:
    """Consume a final partition once within this ledger and score prespecified arms."""
    start = perf_counter()
    try:
        with protocol_path.open("rb") as file:
            payload = file.read(MAX_PROTOCOL_BYTES + 1)
        if len(payload) > MAX_PROTOCOL_BYTES:
            raise ValueError
        artifact = json.loads(payload)
        plan = artifact["plan"]
        protocol_id = fingerprint(plan)
        if (
            artifact["protocol_sha256"] != protocol_id
            or plan["schema_version"] != "1.0"
            or tuple(plan["outcomes"]) != METRICS
            or plan["eligibility_policy"] != "matched-class-caps-v1"
            or plan["dependency_versions"]
            != {name: version(name) for name in ("datagenome", "scikit-learn", "numpy")}
        ):
            raise ValueError
        manifest = restore(plan)
        validate(dataset, manifest)
        target = plan["target"]
        target_index = column(dataset, target)
        model = ModelConfig(**plan["model"])
        train = set(manifest.partitions["train"])
        arms = plan["arms"]
        if (
            not isinstance(arms, dict)
            or not 1 <= len(arms) <= 5
            or set(arms) - {"highest", "lowest", "random", "label_audit", "duplicates"}
        ):
            raise ValueError
        for ids in arms.values():
            if (
                not isinstance(ids, list)
                or any(type(i) is not int for i in ids)
                or len(ids) != plan["matched_removal_count"]
                or len(set(ids)) != len(ids)
                or not set(ids) <= train
            ):
                raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise DatasetError(
            "invalid_frozen_protocol",
            "The protocol is invalid or does not match this dataset.",
        ) from error

    from .holdouts import claim

    key = claim(manifest, ledger, protocol_id, dataset, target)

    def feature_key(i: int) -> tuple[str, ...]:
        row = dataset.rows[i - 1]
        return tuple(
            value
            for j, value in enumerate(row)
            if j != target_index
            and dataset.columns[j] not in {manifest.config.group, manifest.config.time}
        )

    development = {
        feature_key(i)
        for name in ("train", "validation")
        for i in manifest.partitions[name]
    }
    if any(feature_key(i) in development for i in manifest.partitions["test"]):
        raise DatasetError(
            "holdout_contamination",
            "Final rows share exact features with development rows.",
        )

    def score(removed: list[int]) -> dict[str, Any]:
        retained = sorted(train - set(removed))
        metrics = fit_baseline(
            dataset, target, manifest, model, train_ids=retained, include_test=True
        )["metrics"]["test"]
        return final_metrics(metrics)

    baseline = score([])
    results = {}
    for name, removed in arms.items():
        metrics = score(removed)
        delta = {
            key: metrics[key] - baseline[key]
            if metrics[key] is not None and baseline[key] is not None
            else None
            for key in METRICS
            if key != "per_class_recall"
        }
        delta["per_class_recall"] = {
            label: metrics["per_class_recall"][label] - value
            if value is not None and metrics["per_class_recall"][label] is not None
            else None
            for label, value in baseline["per_class_recall"].items()
        }
        results[name] = {
            "metrics": metrics,
            "delta": delta,
            "removed_count": len(removed),
        }
    result = {
        "status": "scored",
        "held_out_scored": True,
        "protocol_sha256": protocol_id,
        "baseline": baseline,
        "arms": results,
        "elapsed_seconds": perf_counter() - start,
    }
    # The exclusive claim remains after interrupted or failed scoring.
    create_json(ledger / (key + ".result.json"), result)
    return result


def main() -> None:
    import argparse

    from .ingestion import DEFAULT_MAX_BYTES, load_csv
    from .splits import SplitConfig, split

    parser = argparse.ArgumentParser(
        description="Freeze or score a local removal protocol."
    )
    parser.add_argument("operation", choices=("freeze", "score"))
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=Path(".datagenome-ledger"))
    parser.add_argument("--target")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fraction", type=float, default=0.1)
    args = parser.parse_args()
    try:
        with args.dataset.open("rb") as file:
            dataset = load_csv(file, args.dataset.name, DEFAULT_MAX_BYTES)
        if args.operation == "freeze":
            if not args.target:
                parser.error("freeze requires --target")
            manifest = split(
                dataset, SplitConfig("stratified", seed=args.seed), args.target
            )
            result = freeze_removal(
                dataset,
                args.target,
                manifest,
                ValuationConfig(method="knn-shapley", seed=args.seed),
                ModelConfig(seed=args.seed),
                args.fraction,
                args.protocol,
            )
            result = {"status": "frozen", "protocol_sha256": result["protocol_sha256"]}
        else:
            result = score_frozen(dataset, args.protocol, args.ledger)
    except DatasetError as error:
        parser.exit(2, json.dumps({"code": error.code, "message": str(error)}) + "\n")
    except OSError:
        parser.exit(2, '{"code":"evaluation_io_error"}\n')
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
