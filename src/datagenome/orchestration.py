from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from time import perf_counter
from typing import Any

from .analysis import execute
from .drift import DriftConfig, detect_drift
from .identity import canonical, fingerprint
from .ingestion import Dataset, DatasetError, parse_csv
from .profiling import profile
from .splits import Manifest, column, validate
from .store import Store
from .valuation import ValuationConfig

ENGINES = (
    "profile",
    "intelligence",
    "leakage",
    "labels",
    "anomalies",
    "valuation",
    "investigation",
    "errors",
    "fairness",
    "proxies",
    "drift",
)
OPERATIONS = {
    "leakage": "detect-leakage",
    "labels": "audit-labels",
    "anomalies": "detect-anomalies",
    "valuation": "value-data",
    "investigation": "investigate",
    "errors": "analyze-errors",
    "fairness": "audit-fairness",
    "proxies": "detect-proxies",
}


@dataclass(frozen=True)
class DiagnosticConfig:
    engines: tuple[str, ...] = (
        "profile",
        "intelligence",
        "leakage",
        "labels",
        "anomalies",
    )
    seconds: float = 60
    attributes: tuple[str, ...] = ()
    record_id: int | None = None
    valuation_method: str = "knn-shapley"
    privacy: str = "summary"


def health(
    results: dict[str, Any], weights: dict[str, float] | None = None
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    critical = []
    prof = results.get("profile", {}).get("result")
    if prof:
        total = prof["row_count"] * prof["column_count"]
        missing = sum(item["missing_count"] for item in prof["columns"])
        components["completeness"] = {
            "score": 100 * (1 - missing / total),
            "weight": 1,
            "evidence": {"missing_cells": missing, "cells": total},
        }
        components["duplicate_burden"] = {
            "score": 100 * (1 - prof["duplicate_row_count"] / prof["row_count"]),
            "weight": 1,
            "evidence": {"duplicate_rows": prof["duplicate_row_count"]},
        }
        constants = sum(item["constant"] for item in prof["columns"])
        components["feature_variation"] = {
            "score": 100 * (1 - constants / prof["column_count"]),
            "weight": 1,
            "evidence": {"constant_columns": constants},
        }
    labels = results.get("labels", {}).get("result", {}).get("label_audit")
    if labels and labels["status"] == "evaluated" and labels["evaluated_records"]:
        components["label_agreement"] = {
            "score": 100
            * (1 - labels["candidate_count"] / labels["evaluated_records"]),
            "weight": 1,
            "evidence": {
                "candidates": labels["candidate_count"],
                "evaluated": labels["evaluated_records"],
            },
        }
    leakage = results.get("leakage", {}).get("result", {}).get("leakage")
    if leakage is not None:
        critical = [
            item["id"]
            for item in leakage
            if item["classification"] == "confirmed_violation"
        ]
        components["evaluation_integrity"] = {
            "score": 0 if critical else 100,
            "weight": 2,
            "evidence": {"confirmed_violations": len(critical)},
        }
    potential = (
        "completeness",
        "duplicate_burden",
        "feature_variation",
        "label_agreement",
        "evaluation_integrity",
        "representation",
        "distribution_stability",
    )
    if weights is not None:
        from math import isfinite

        allowed = {
            "completeness",
            "duplicate_burden",
            "feature_variation",
            "label_agreement",
            "evaluation_integrity",
        }
        if set(weights) - allowed or any(
            not isfinite(value) or not 0 < value <= 10 for value in weights.values()
        ):
            raise DatasetError(
                "health_weights", "Use positive finite component weights up to ten."
            )
        for name, value in weights.items():
            if name in components:
                components[name]["weight"] = value
    weight = sum(item["weight"] for item in components.values())
    return {
        "score": sum(item["score"] * item["weight"] for item in components.values())
        / weight
        if weight
        else None,
        "components": components,
        "coverage": len(components) / len(potential),
        "unassessed": sorted(set(potential) - components.keys()),
        "critical_violations": critical,
        "formula": "sum(available score * weight) / sum(available weight); no imputation",
        "limitations": [
            "Scores summarize measured burden and agreement. They do not predict generalization.",
            "Fairness remains separate. Integrity violations require review regardless of aggregate score.",
        ],
    }


def recommendations(
    results: dict[str, Any], training_ids: set[int]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(
        category: str,
        engine: str,
        evidence: str,
        classification: str,
        severity: str,
        records: list[int],
        features: list[str],
        action: str,
        conflict: str | None = None,
    ) -> None:
        priority = {"critical": 100, "high": 70, "warning": 40, "info": 10}[severity]
        priority += min(10, len(records) // 10)
        items.append(
            {
                "id": fingerprint([category, engine, evidence]),
                "category": category,
                "support": [{"engine": engine, "finding": evidence}],
                "evidence_classification": classification,
                "severity": severity,
                "records": records[:100],
                "features": features,
                "action": action,
                "priority": priority,
                "priority_formula": "severity base + min(10, affected records // 10)",
                "effort": "review_and_one_controlled_experiment",
                "required_review": True,
                "benefit_hypothesis": "A verified issue may explain unreliable evaluation or prediction.",
                "risks": [
                    "A legitimate observation or useful predictor could be removed."
                ],
                "conflicts": [conflict] if conflict else [],
                "validation": "Freeze a supported training-only plan and compare fixed validation records.",
                "compatibility": [
                    "Preserve classes, groups, evaluation labels and chronology."
                ],
                "limitations": [
                    "Detector agreement is not a calibrated probability of an error."
                ],
            }
        )

    profile_result = results.get("profile", {}).get("result")
    if profile_result:
        for item in profile_result["findings"]:
            add(
                item["category"],
                "profile",
                item["id"],
                "measured_structural",
                "warning",
                [i for i in item["affected_records"] if i in training_ids],
                list(item["affected_columns"]),
                item["suggested_remediation"],
            )
    intel = results.get("intelligence", {}).get("result", {})
    conflicts = intel.get("duplicates", {}).get("conflicting_labels", [])
    if conflicts:
        add(
            "conflicting_duplicates",
            "intelligence",
            "conflicting_labels",
            "measured_structural",
            "high",
            sorted({i for group in conflicts for i in group if i in training_ids}),
            [],
            "Review conflicting labels against source evidence.",
            "Duplicate features can have legitimately ambiguous labels.",
        )
    for finding in intel.get("findings", []):
        if finding["method"] in {
            "correlated_features",
            "redundant_features",
            "near_constant",
        }:
            add(
                "redundant_feature_review",
                "intelligence",
                finding["id"],
                "descriptive_association",
                "info",
                [],
                list(finding["columns"]),
                "Compare explicitly selected feature exclusions.",
                "Association and redundancy do not measure incremental model utility.",
            )
    for item in results.get("leakage", {}).get("result", {}).get("leakage", []):
        if item["classification"] in {
            "no_signal",
            "insufficient_evidence",
            "unsupported_analysis",
        }:
            continue
        add(
            "leakage_review",
            "leakage",
            item["id"],
            item["classification"],
            "critical"
            if item["classification"] == "confirmed_violation"
            else "warning",
            [i for i in item["records"] if i in training_ids],
            list(item["columns"]),
            "Review feature provenance and split construction.",
            "Predictive strength can be legitimate; exclude only after review.",
        )
    labels = results.get("labels", {}).get("result", {}).get("label_audit", {})
    flagged = [
        item["record_id"]
        for item in labels.get("candidates", [])
        if item["record_id"] in training_ids
    ]
    if flagged:
        add(
            "label_review",
            "labels",
            "out_of_fold_candidates",
            "heuristic",
            "warning",
            flagged,
            [],
            "Manually verify labels before proposing explicit corrections.",
            "Model disagreement alone does not authorize a replacement label.",
        )
    anomalies = results.get("anomalies", {}).get("result", {}).get("anomalies", {})
    flagged = [
        item["record"]
        for item in anomalies.get("ranked", [])
        if item["record"] in training_ids
    ]
    if flagged:
        add(
            "outlier_review",
            "anomalies",
            "ranked_agreement",
            "heuristic",
            "warning",
            flagged,
            [],
            "Check source context for unusual observations.",
            "Rare valid observations may support a minority class.",
        )
    values = results.get("valuation", {}).get("result", {}).get("valuation", {})
    negative = [
        item["record_id"] for item in values.get("records", []) if item["score"] < 0
    ]
    if negative:
        add(
            "low_value_review",
            "valuation",
            "negative_validation_marginals",
            "model_conditional",
            "warning",
            negative,
            [],
            "Evaluate explicitly selected exclusions with class and group guards.",
            "Low global utility can coexist with useful minority-class contributions.",
        )
    for engine in ("fairness", "proxies", "drift"):
        data = results.get(engine, {}).get("result", {})
        root = data.get(engine, data)
        active = (
            root.get("recommendations")
            or root.get("potential_proxy_count", 0)
            or root.get("review_count", 0)
        )
        if active:
            add(
                engine + "_review",
                engine,
                "aggregate_review",
                "descriptive_association",
                "warning",
                [],
                [],
                "Review the measured group or distribution evidence and prespecify an independent check.",
            )
    return sorted(items, key=lambda item: (-item["priority"], item["id"]))


def orchestrate(
    data: Dataset,
    payload: bytes,
    target: str | None,
    manifest: Manifest,
    config: DiagnosticConfig = DiagnosticConfig(),
    *,
    comparison: Dataset | None = None,
    store: Store | None = None,
    project: str | None = None,
    event: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    validate(data, manifest)
    if canonical(parse_csv(payload, max_rows=5000, max_columns=64)) != canonical(data):
        raise DatasetError(
            "diagnostic_identity", "Payload and supplied dataset differ."
        )
    if (
        not 1 <= len(config.engines) <= len(ENGINES)
        or len(set(config.engines)) != len(config.engines)
        or not 0 < config.seconds <= 120
        or config.privacy not in {"summary", "detailed", "redacted"}
        or any(
            not isinstance(name, str) or not 1 <= len(name) <= 64
            for name in config.engines
        )
        or len(config.attributes) > 3
        or any(
            not isinstance(name, str) or len(name) > 255 for name in config.attributes
        )
        or len(data.rows) > 5000
        or len(data.columns) > 64
    ):
        raise DatasetError(
            "diagnostic_config", "Invalid engine selection, privacy or resource budget."
        )
    if target is not None:
        column(data, target)
    started = perf_counter()
    results: dict[str, Any] = {}
    events = []
    dependencies = {
        name: version(name) for name in ("datagenome", "numpy", "scipy", "scikit-learn")
    }
    from .intelligence import analyze

    ordered = [engine for engine in ENGINES if engine in config.engines] + [
        engine for engine in config.engines if engine not in ENGINES
    ]
    for engine in ordered:
        if cancelled is not None and cancelled():
            raise DatasetError(
                "job_cancelled", "Cancellation observed between engines."
            )
        if perf_counter() - started > config.seconds:
            results[engine] = {"status": "budget_exhausted"}
            continue
        current = {
            "engine": engine,
            "state": "started",
            "completed_engines": len(results),
        }
        events.append(current)
        if event:
            event(current)
        key = fingerprint(
            [
                canonical(data),
                manifest.fingerprint,
                target,
                asdict(config),
                engine,
                project,
                canonical(comparison) if comparison else None,
                dependencies,
            ]
        )
        cached = []
        if store is not None and project is not None:
            # Content key lookup avoids a directory or path supplied by a request.
            try:
                cached = [store.get(project, key, "cache")]
            except DatasetError as error:
                if error.code != "artifact_not_found":
                    raise
        try:
            if cached:
                outcome = cached[0]["outcome"]
            elif engine == "profile":
                outcome = {
                    "status": "completed",
                    "result": asdict(profile(data, target)),
                }
            elif engine == "intelligence":
                outcome = {"status": "completed", "result": analyze(data, target)}
            elif engine == "drift":
                outcome = (
                    {
                        "status": "completed",
                        "result": detect_drift(
                            data,
                            comparison,
                            DriftConfig(summary_only=False),
                            target=target,
                        ),
                    }
                    if comparison
                    else {
                        "status": "unsupported",
                        "reason": "A comparison dataset is required.",
                    }
                )
            elif engine in OPERATIONS:
                if target is None and engine not in {"anomalies", "proxies"}:
                    outcome = {
                        "status": "unsupported",
                        "reason": "This engine requires a target.",
                    }
                else:
                    result = execute(
                        OPERATIONS[engine],
                        payload,
                        target=target,
                        limit=5 * 1024 * 1024,
                        manifest=manifest,
                        record_id=config.record_id,
                        audit_attributes=config.attributes,
                        privacy_mode="detailed",
                        valuation=ValuationConfig(
                            method=config.valuation_method,
                            seconds=min(config.seconds, 30),
                        ),
                    )
                    outcome = {"status": "completed", "result": result}
            else:
                outcome = {"status": "unsupported", "reason": "Unknown engine."}
        except DatasetError as error:
            outcome = {"status": "unsupported_or_failed", "code": error.code}
        except Exception as error:
            # Preserve unrelated engines and avoid leaking dataset fragments in exceptions.
            outcome = {"status": "failed", "error_type": type(error).__name__}
        if (
            not cached
            and outcome["status"] == "completed"
            and store is not None
            and project is not None
        ):
            try:
                store.put(project, "cache", {"outcome": outcome}, key)
            except DatasetError as error:
                if error.code != "immutable_artifact":
                    raise
        results[engine] = {**outcome, "cache_hit": bool(cached)}
        current = {
            "engine": engine,
            "state": outcome["status"],
            "completed_engines": len(results),
        }
        events.append(current)
        if event:
            event(current)
    report = {
        "schema_version": "2.0",
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "configuration": asdict(config),
        "dependencies": dependencies,
        "engines": results,
        "health": health(results),
        "recommendations": recommendations(results, set(manifest.partitions["train"])),
        "events": events,
        "warnings": [
            {"engine": name, "status": value["status"], "code": value.get("code")}
            for name, value in results.items()
            if value["status"] != "completed"
        ],
        "elapsed_seconds": perf_counter() - started,
        "limitations": [
            "Optional engines can fail independently. Budgets are checked between engines.",
            "Recommendations require review and authorize no mutation.",
        ],
    }
    return report


def report_view(report: dict[str, Any], privacy: str = "summary") -> dict[str, Any]:
    if privacy == "detailed":
        return report
    if privacy not in {"summary", "redacted"}:
        raise DatasetError("report_privacy", "Use summary, redacted or detailed.")
    measured = report["health"]
    # No raw evidence, labels, names, hashes or record IDs in this conservative view.
    return {
        "schema_version": report["schema_version"],
        "engines": {
            key: {"status": value["status"]} for key, value in report["engines"].items()
        },
        "health": {
            "score": measured["score"],
            "coverage": measured["coverage"],
            "unassessed": measured["unassessed"],
            "critical_violation_count": len(measured["critical_violations"]),
        },
        "recommendation_counts": dict(
            Counter(item["category"] for item in report["recommendations"])
        ),
        "limitations": report["limitations"],
    }
