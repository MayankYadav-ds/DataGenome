from dataclasses import asdict, replace
from time import perf_counter
from typing import Any

from .anomalies import AnomalyConfig, detect_anomalies
from .error_slices import analyze_errors
from .experiments import Intervention, active, compare, prepare
from .identity import metadata
from .ingestion import DatasetError, parse_csv
from .intelligence import IntelligenceConfig, analyze
from .investigator import inspect_prediction
from .label_audit import audit_labels
from .leakage import LeakageConfig, inspect_leakage
from .modeling import ModelConfig, fit_baseline
from .profiling import profile
from .removal import compare_removal
from .splits import Manifest, SplitConfig, split, validate
from .valuation import ValuationConfig, value_data


def execute(
    operation: str,
    payload: bytes | bytearray,
    *,
    target: str | None,
    limit: int,
    rows: int = 20000,
    columns: int = 128,
    split_config: SplitConfig = SplitConfig(),
    model: ModelConfig = ModelConfig(),
    leakage: LeakageConfig = LeakageConfig(),
    intervention: Intervention = Intervention(),
    manifest: Manifest | None = None,
    intelligence: IntelligenceConfig = IntelligenceConfig(),
    anomaly: AnomalyConfig = AnomalyConfig(),
    valuation: ValuationConfig = ValuationConfig(),
    removal_fraction: float = 0.1,
    record_id: int | None = None,
    minimum_support: int = 10,
    privacy_mode: str = "detailed",
) -> dict[str, Any]:
    start = perf_counter()
    dataset = parse_csv(payload, limit, max_rows=rows, max_columns=columns)
    if target is not None and target not in dataset.columns:
        raise DatasetError("unknown_target", "Target must match a CSV header.")
    if (
        operation
        in {
            "train",
            "evaluate",
            "experiment",
            "detect-leakage",
            "audit-labels",
            "value-data",
            "compare-removal",
            "investigate",
            "analyze-errors",
            "investigate-intervention",
        }
        and target is None
    ):
        raise DatasetError("missing_target", "This operation requires a target column.")
    report: dict[str, Any] = {"schema_version": "1.0", "operation": operation}
    if operation not in {"diagnose", "detect-anomalies"} or manifest is not None:
        manifest = (
            manifest if manifest is not None else split(dataset, split_config, target)
        )
        validate(dataset, manifest)
        report["split"] = {**asdict(manifest), "fingerprint": manifest.fingerprint}
    report["identity"] = metadata(
        dataset, payload, target, asdict(manifest.config) if manifest else None
    )
    if operation == "diagnose":
        report.update(
            profile=asdict(profile(dataset, target)),
            intelligence=analyze(dataset, target, intelligence),
            anomalies=detect_anomalies(dataset, target, anomaly),
        )
        if manifest is not None and target is not None:
            report["leakage"] = [
                asdict(item)
                for item in inspect_leakage(dataset, target, manifest, leakage)
            ]
        else:
            report["unsupported"] = [
                "Pass a saved split manifest and target for split-aware diagnostics."
            ]
    elif operation == "detect-anomalies":
        report["anomalies"] = detect_anomalies(dataset, target, anomaly)
    elif (
        operation in {"investigate", "investigate-intervention"}
        and manifest
        and target is not None
    ):
        if model.model != "logistic-regression":
            raise DatasetError(
                "unsupported_investigator_model",
                "Investigation requires the binary logistic model.",
            )
        if record_id is None:
            raise DatasetError("missing_record_id", "Supply a validation record ID.")
        if operation == "investigate-intervention" and not active(intervention):
            raise DatasetError(
                "missing_intervention", "Select an explicit intervention."
            )
        result = inspect_prediction(
            dataset,
            target,
            manifest,
            record_id,
            intervention,
            summary_only=privacy_mode != "detailed",
        )
        report = {
            "schema_version": "1.0",
            "operation": operation,
            "investigation": result,
        }
    elif operation == "analyze-errors" and manifest and target is not None:
        result = analyze_errors(
            dataset,
            target,
            manifest,
            model,
            min_support=minimum_support,
            summary_only=privacy_mode != "detailed",
        )
        report = {
            "schema_version": "1.0",
            "operation": operation,
            "error_slices": result,
        }
    elif operation == "value-data" and manifest and target is not None:
        report["valuation"] = value_data(
            dataset, target, manifest, valuation, model=model
        )
    elif operation == "compare-removal" and manifest and target is not None:
        report["removal"] = compare_removal(
            dataset, target, manifest, valuation, model, removal_fraction
        )
    elif operation == "audit-labels" and manifest and target is not None:
        report["label_audit"] = audit_labels(dataset, target, manifest)
    elif operation == "detect-leakage" and manifest and target is not None:
        report["leakage"] = [
            asdict(signal)
            for signal in inspect_leakage(dataset, target, manifest, leakage)
        ]
        report["unsupported"] = [
            "Arbitrary retrospective preprocessing leakage.",
            "Unspecified event availability and time semantics.",
        ]
    elif operation in {"train", "evaluate"} and manifest and target is not None:
        apply_intervention = operation == "evaluate" and active(intervention)
        selected, features = (
            prepare(dataset, target, manifest, intervention)
            if apply_intervention
            else (None, [])
        )
        if apply_intervention:
            model = replace(
                model, imputation=intervention.imputation or model.imputation
            )
            report["intervention"] = asdict(intervention)
        violations = [
            asdict(signal)
            for signal in inspect_leakage(dataset, target, manifest, leakage)
            if signal.classification == "confirmed_violation"
            and not (
                signal.method == "unavailable_feature"
                and set(signal.columns) <= set(features)
            )
        ]
        report["evaluation_compromised"] = bool(violations)
        report["violations"] = violations
        if not violations or operation == "train":
            report["model"] = fit_baseline(
                dataset,
                target,
                manifest,
                model,
                include_test=operation == "evaluate",
                train_ids=selected,
                exclude=features,
            )
    elif operation == "experiment" and manifest and target is not None:
        result = compare(dataset, target, manifest, intervention, model, leakage)
        report["experiment"] = result
    elif operation != "split":
        raise DatasetError("missing_target", "This operation requires a target column.")
    report["execution"] = {"elapsed_seconds": perf_counter() - start}
    report["limitations"] = [
        "Record identifiers are one-based positions in the canonical dataset."
    ]
    return report
