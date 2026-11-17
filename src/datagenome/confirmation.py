import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scipy.stats import fisher_exact

from .drift import holm
from .error_slices import analyze_errors
from .identity import fingerprint
from .independent import MAX_PROTOCOL_BYTES, claim_holdout, create_json
from .ingestion import Dataset, DatasetError
from .modeling import ModelConfig, classification_pipeline
from .numeric import number
from .splits import Manifest, column, restore, validate


def freeze_slices(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    model: ModelConfig,
    destination: Path,
    *,
    min_support: int = 10,
    min_gap: float = 0.10,
    iid: bool = False,
) -> dict[str, Any]:
    if not 0 < min_gap <= 1:
        raise DatasetError("invalid_slice_gap", "Use a positive minimum gap up to one.")
    discovery = analyze_errors(
        dataset, target, manifest, model, min_support=min_support
    )
    plan = {
        "kind": "error_slice_confirmation_v1",
        "target": target,
        "model": asdict(model),
        "split": {**asdict(manifest), "fingerprint": manifest.fingerprint},
        "min_support": min_support,
        "min_gap": min_gap,
        "iid": iid,
        "discovery_baseline_error": discovery["baseline_error_rate"],
        "slices": [
            s for s in discovery["slices"] if s["absolute_error_difference"] >= min_gap
        ],
    }
    artifact = {"plan": plan, "protocol_sha256": fingerprint(plan)}
    create_json(destination, artifact)
    return artifact


def membership(
    row: tuple[str, ...], dataset: Dataset, label: int, definition: dict[str, Any]
) -> bool:
    kind = definition["kind"]
    if kind == "intersection":
        return all(
            membership(row, dataset, label, item) for item in definition["conditions"]
        )
    if kind == "class":
        return bool(row[label] == definition["label"])
    value = row[column(dataset, definition["feature"])]
    if kind == "missing":
        return not value.strip()
    if kind == "category":
        return bool(value == definition["value"])
    numeric = number(value)
    return bool(
        numeric is not None
        and (numeric <= definition["threshold"]) == (definition["operator"] == "le")
    )


def confirm_slices(
    dataset: Dataset, protocol: Path, ledger: Path, *, summary_only: bool = True
) -> dict[str, Any]:
    try:
        with protocol.open("rb") as file:
            payload = file.read(MAX_PROTOCOL_BYTES + 1)
        if len(payload) > MAX_PROTOCOL_BYTES:
            raise ValueError
        artifact = json.loads(payload)
        plan = artifact["plan"]
        digest = fingerprint(plan)
        if (
            digest != artifact["protocol_sha256"]
            or plan["kind"] != "error_slice_confirmation_v1"
            or not isinstance(plan["slices"], list)
            or len(plan["slices"]) > 30
            or not 5 <= plan["min_support"] <= 500
            or not 0 < plan["min_gap"] <= 1
        ):
            raise ValueError
        manifest = restore(plan)
        validate(dataset, manifest)
        label = column(dataset, plan["target"])
        model = ModelConfig(**plan["model"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise DatasetError(
            "invalid_slice_protocol", "Invalid or mismatched slice protocol."
        ) from error
    if len(dataset.rows) > 2000 or len(dataset.columns) > 33:
        raise DatasetError(
            "slice_budget", "Confirmation supports 2,000 rows and 32 features."
        )
    if not plan["slices"]:
        return {"status": "no_frozen_candidates", "held_out_scored": False}
    train, test = manifest.partitions["train"], manifest.partitions["test"]
    selected = [
        i
        for i, name in enumerate(dataset.columns)
        if i != label and name not in {manifest.config.group, manifest.config.time}
    ]
    receipt = claim_holdout(manifest, ledger, digest)
    development = {
        tuple(dataset.rows[i - 1][j] for j in selected)
        for name in ("train", "validation")
        for i in manifest.partitions[name]
    }
    if any(
        tuple(dataset.rows[i - 1][j] for j in selected) in development for i in test
    ):
        raise DatasetError(
            "holdout_contamination",
            "Final rows share exact features with development rows.",
        )
    labels = [dataset.rows[i - 1][label] for i in train]
    truth = [dataset.rows[i - 1][label] for i in test]
    if set(truth) - set(labels):
        raise DatasetError(
            "slice_unknown_label", "Confirmation labels must be known during training."
        )

    from threadpoolctl import threadpool_limits

    pipeline, _, design, _, _ = classification_pipeline(dataset, selected, train, model)
    with threadpool_limits(limits=1):
        pipeline.fit(design(train), labels)
        predicted = pipeline.predict(design(test)).tolist()
    errors = [a != b for a, b in zip(truth, predicted, strict=True)]
    baseline = sum(errors) / len(errors)
    results = []
    iid = plan["iid"] and manifest.config.strategy not in {"group", "chronological"}
    for s in plan["slices"]:
        flags = [
            membership(dataset.rows[i - 1], dataset, label, s["definition"])
            for i in test
        ]
        total = sum(flags)
        row = {
            "definition": s["definition"],
            "discovery_support": s["records"],
            "discovery_error_rate": s["error_rate"],
            "confirmation_support": total,
        }
        if not total:
            row["outcome"] = "absent"
        elif min(total, len(test) - total) < plan["min_support"]:
            row["outcome"] = "insufficient_support"
        else:
            inside = sum(
                error and flag for error, flag in zip(errors, flags, strict=True)
            )
            outside = sum(errors) - inside
            effect = inside / total - baseline
            row.update(
                confirmation_error_rate=inside / total,
                baseline_error_rate=baseline,
                effect=effect,
                outcome="descriptive_replication"
                if effect >= plan["min_gap"]
                else "below_effect_threshold",
            )
            if iid:
                row["p_value"] = float(
                    fisher_exact(
                        [
                            [inside, total - inside],
                            [outside, len(test) - total - outside],
                        ],
                        alternative="greater",
                    ).pvalue
                )
        results.append(row)
    tested = [row for row in results if "p_value" in row]
    for row, p in zip(tested, holm([row["p_value"] for row in tested]), strict=True):
        row["adjusted_p_value"] = p
        if row["outcome"] == "descriptive_replication":
            row["outcome"] = "confirmed" if p <= 0.05 else "statistically_inconclusive"
    output: dict[str, Any] = {
        "status": "scored",
        "held_out_scored": True,
        "discovery_baseline_error": plan["discovery_baseline_error"],
        "confirmation_baseline_error": baseline,
        "outcomes": {
            outcome: sum(row["outcome"] == outcome for row in results)
            for outcome in sorted({row["outcome"] for row in results})
        },
        "limitations": [
            "Definitions were frozen on validation. Error associations are not causal.",
            "Inference uses Holm-adjusted one-sided Fisher tests only when IID is asserted.",
        ],
    }
    if not summary_only:
        output["slices"] = results
    create_json(ledger / (receipt + ".result.json"), output)
    return output


def main() -> None:
    import argparse

    from .ingestion import DEFAULT_MAX_BYTES, load_csv
    from .splits import SplitConfig, split

    parser = argparse.ArgumentParser(
        description="Freeze or confirm exploratory validation slices."
    )
    parser.add_argument("operation", choices=("freeze", "score"))
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=Path(".datagenome-ledger"))
    parser.add_argument("--target")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-support", type=int, default=10)
    parser.add_argument("--iid", action="store_true")
    parser.add_argument("--detailed", action="store_true")
    args = parser.parse_args()
    try:
        with args.dataset.open("rb") as source:
            data = load_csv(source, args.dataset.name, DEFAULT_MAX_BYTES)
        if args.operation == "freeze":
            if not args.target:
                parser.error("freeze requires --target")
            manifest = split(
                data, SplitConfig("stratified", seed=args.seed), args.target
            )
            frozen = freeze_slices(
                data,
                args.target,
                manifest,
                ModelConfig(seed=args.seed),
                args.protocol,
                min_support=args.min_support,
                iid=args.iid,
            )
            result = {
                "status": "frozen",
                "candidate_count": len(frozen["plan"]["slices"]),
            }
        else:
            result = confirm_slices(
                data, args.protocol, args.ledger, summary_only=not args.detailed
            )
    except DatasetError as error:
        parser.exit(2, json.dumps({"code": error.code, "message": str(error)}) + "\n")
    except OSError:
        parser.exit(2, '{"code":"slice_io_error"}\n')
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
