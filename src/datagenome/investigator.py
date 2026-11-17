from dataclasses import asdict
from typing import Any

import numpy as np
from scipy.special import expit

from .experiments import Intervention, active, prepare
from .influence import Array, LogisticObjective, estimate
from .ingestion import Dataset, DatasetError
from .label_audit import audit_labels
from .numeric import number
from .splits import Manifest, column, validate
from .valuation import ValuationConfig, value_data


def inspect_prediction(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    record_id: int,
    intervention: Intervention = Intervention(),
    *,
    summary_only: bool = False,
) -> dict[str, Any]:
    """Inspect one validation prediction using a fixed-objective binary model."""
    validate(dataset, manifest)
    if record_id not in manifest.partitions["validation"]:
        raise DatasetError("investigation_partition", "Select a validation record ID.")
    if len(dataset.rows) > 2000 or len(dataset.columns) > 33:
        raise DatasetError(
            "investigation_budget",
            "Investigation supports 2,000 rows and 32 features.",
            413,
        )
    index = column(dataset, target)
    train = sorted(manifest.partitions["train"])
    evaluation = manifest.partitions["validation"]
    classes = sorted({dataset.rows[i - 1][index] for i in train})
    if len(classes) != 2 or any(not label.strip() for label in classes):
        raise DatasetError(
            "investigation_binary", "Investigation needs two nonblank training labels."
        )
    if intervention.imputation is not None:
        raise DatasetError(
            "investigation_imputation",
            "This investigator uses fixed numeric median imputation.",
        )
    if any(dataset.rows[i - 1][index] not in classes for i in evaluation):
        raise DatasetError(
            "investigation_validation_labels",
            "Validation labels must be known binary labels.",
        )
    features = [
        i
        for i, name in enumerate(dataset.columns)
        if i != index and name not in {manifest.config.group, manifest.config.time}
    ]
    if not features:
        raise DatasetError(
            "investigation_features", "At least one numeric feature is required."
        )

    def fit(
        ids: list[int], excluded: list[str]
    ) -> tuple[LogisticObjective, Array, Array, list[int]]:
        selected = [i for i in features if dataset.columns[i] not in excluded]
        if not ids or not selected:
            raise DatasetError(
                "investigation_empty", "Retain training rows and numeric features."
            )
        if set(dataset.rows[i - 1][index] for i in ids) != set(classes):
            raise DatasetError(
                "investigation_class_guard", "Retain examples of both training classes."
            )

        def matrix(records: list[int]) -> Array:
            rows = []
            for i in records:
                values = []
                for j in selected:
                    cell = dataset.rows[i - 1][j]
                    value = number(cell)
                    if value is None and cell.strip():
                        raise DatasetError(
                            "investigation_numeric",
                            "Features must be finite numeric values or blanks.",
                        )
                    values.append(
                        np.nan if value is None else max(-1e12, min(1e12, value))
                    )
                rows.append(values)
            return np.asarray(rows, dtype=np.float64)

        training = matrix(ids)
        scoring = matrix(evaluation)
        if np.any(np.isnan(training).all(axis=0)):
            raise DatasetError(
                "investigation_empty_feature",
                "An investigated feature is missing in every training row.",
            )
        medians = np.nanmedian(training, axis=0)
        training = np.where(np.isnan(training), medians, training)
        scoring = np.where(np.isnan(scoring), medians, scoring)
        means = training.mean(axis=0)
        scale = training.std(axis=0)
        scale[scale == 0] = 1
        x = np.column_stack(
            (np.ones(len(ids)), np.clip((training - means) / scale, -1e4, 1e4))
        )
        v = np.column_stack(
            (np.ones(len(evaluation)), np.clip((scoring - means) / scale, -1e4, 1e4))
        )
        labels = np.asarray(
            [dataset.rows[i - 1][index] == classes[1] for i in ids], dtype=np.float64
        )
        objective = LogisticObjective(x, labels)
        return objective, objective.fit(), v, selected

    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=1):
        objective, beta, validation_x, selected = fit(train, [])
        loc = evaluation.index(record_id)
        row = validation_x[loc]
        logits = validation_x @ beta
        probabilities = expit(logits)
        actual = np.asarray(
            [dataset.rows[i - 1][index] == classes[1] for i in evaluation],
            dtype=np.float64,
        )
        predictions = (probabilities >= 0.5).astype(int)
        correct = bool(predictions[loc] == actual[loc])
        prediction = {
            "record_id": record_id,
            "correct": correct,
            "actual_class": classes[int(actual[loc])],
            "predicted_class": classes[predictions[loc]],
            "probabilities": {
                classes[0]: float(1 - probabilities[loc]),
                classes[1]: float(probabilities[loc]),
            },
            "margin": float(abs(2 * probabilities[loc] - 1)),
        }
        replacement = None
        if active(intervention):
            retained, excluded = prepare(dataset, target, manifest, intervention)
            modified, new_beta, new_validation, _ = fit(retained, excluded)
            updated = (expit(new_validation @ new_beta) >= 0.5).astype(int)
            new_correct = bool(updated[loc] == actual[loc])
            recalls = {}
            for k, label in enumerate(classes):
                mask = actual == k
                recalls[label] = (
                    float(np.mean(updated[mask] == k) - np.mean(predictions[mask] == k))
                    if mask.any()
                    else None
                )
            minority_count = min(np.bincount(objective.y.astype(int)))
            minority = [
                label
                for k, label in enumerate(classes)
                if int(np.sum(objective.y == k)) == minority_count
            ]
            replacement = {
                "status": "corrected"
                if new_correct and not correct
                else "worsened"
                if correct and not new_correct
                else "unchanged",
                "predicted_class": classes[updated[loc]],
                "validation_accuracy_delta": float(
                    np.mean(updated == actual) - np.mean(predictions == actual)
                ),
                "class_recall_delta": recalls,
                "minority_classes": minority,
                "minority_recall_degraded": any(
                    (delta := recalls[label]) is not None and delta < 0
                    for label in minority
                ),
                "retained_training_records": len(modified.y),
                "intervention": asdict(intervention),
            }
        influence = None
        if not correct and not summary_only:
            try:
                influence = estimate(
                    objective, beta, validation_x[loc : loc + 1], actual[loc : loc + 1]
                )
            except DatasetError as error:
                influence = {"unsupported": error.code}

    result: dict[str, Any] = {
        "model": {
            "family": "binary-logistic-fixed-objective",
            "regularization": 0.1,
            "intercept_regularized": True,
        },
        "validation_records": len(evaluation),
        "validation_accuracy": float(np.mean(predictions == actual)),
        "prediction_correct": correct,
        "validation_log_loss": float(
            np.mean(np.logaddexp(0, logits) - actual * logits)
        ),
        "limitations": [
            "Neighbor distance and influence estimates do not establish causation.",
            "The model accepts finite numeric features and blanks.",
            "Estimates use fixed preprocessing and an exploratory validation record.",
            "A corrected prediction does not establish generalization.",
        ],
    }
    if summary_only:
        if replacement is not None:
            result["intervention_summary"] = {
                key: replacement[key]
                for key in (
                    "status",
                    "validation_accuracy_delta",
                    "retained_training_records",
                )
            }
        return result

    values = beta[1:] * row[1:]
    contribution = {
        "intercept": float(beta[0]),
        "logit": float(logits[loc]),
        "reconstructed_logit": float(beta[0] + values.sum()),
        "features": [
            {
                "feature": dataset.columns[j],
                "transformed": float(row[k + 1]),
                "coefficient": float(beta[k + 1]),
                "logit_contribution": float(values[k]),
            }
            for k, j in enumerate(selected)
        ],
    }
    distances = np.linalg.norm(objective.x[:, 1:] - row[1:], axis=1)
    order = sorted(range(len(train)), key=lambda i: (distances[i], train[i]))[:10]
    audit = (
        audit_labels(dataset, target, manifest) if not correct else {"candidates": []}
    )
    flags = {item["record_id"]: item for item in audit["candidates"]}
    neighbors = [
        {
            "record_id": train[i],
            "distance": float(distances[i]),
            "label": dataset.rows[train[i] - 1][index],
            "exact_feature_match": all(
                dataset.rows[train[i] - 1][j] == dataset.rows[record_id - 1][j]
                for j in features
            ),
            "label_audit": flags.get(train[i]),
        }
        for i in order
    ]
    edges = [
        {
            "source": f"train:{item['record_id']}",
            "target": f"prediction:{record_id}",
            "type": "IS_NEAREST_NEIGHBOR_OF",
            "evidence": "measured",
        }
        for item in neighbors
    ]
    valuation_status = "not_requested_for_correct_prediction"
    if not correct:
        try:
            valuation = value_data(
                dataset,
                target,
                manifest,
                ValuationConfig(method="knn-shapley", k=min(3, len(train)), seconds=5),
            )
            valued = {item["record_id"]: item["score"] for item in valuation["records"]}
            valuation_status = "evaluated"
            for neighbor in neighbors:
                i = neighbor["record_id"]
                neighbor["global_knn_valuation"] = valued[i]
                if valued[i] < 0:
                    edges.append(
                        {
                            "source": f"train:{i}",
                            "target": f"global-valuation:{i}",
                            "type": "HAS_NEGATIVE_GLOBAL_VALUATION",
                            "evidence": "measured",
                        }
                    )
        except DatasetError as error:
            valuation_status = error.code
    for neighbor in neighbors:
        if neighbor["exact_feature_match"]:
            edges.append(
                {
                    "source": f"train:{neighbor['record_id']}",
                    "target": f"prediction:{record_id}",
                    "type": "IS_FEATURE_DUPLICATE_OF",
                    "evidence": "measured",
                }
            )
    flagged = [item["record_id"] for item in neighbors if item["label_audit"]]
    recommendations = []
    if flagged:
        edges.extend(
            {
                "source": f"train:{i}",
                "target": f"label-audit:{i}",
                "type": "HAS_SUSPECTED_LABEL_ISSUE",
                "evidence": "inferred",
            }
            for i in flagged
        )
        recommendations.append(
            {
                "id": "verify-neighbor-labels",
                "records": flagged,
                "supporting_findings": [f"label-audit:{i}" for i in flagged],
                "action": "Manually verify the observed labels.",
                "hypothesis": "A verified label problem could affect this prediction.",
                "validation": "Compare an explicit intervention on the same validation split.",
                "risk": "low",
                "contraindications": ["Ambiguous labels and difficult examples"],
                "limitations": [
                    "Detector agreement is not a probability of mislabeling."
                ],
            }
        )
    result.update(
        prediction=prediction,
        dataset_sha256=manifest.dataset_sha256,
        split_sha256=manifest.fingerprint,
        contribution=contribution,
        global_valuation_status=valuation_status,
        neighbors=neighbors,
        evidence_graph={
            "nodes": sorted(
                {edge[key] for edge in edges for key in ("source", "target")}
            ),
            "edges": edges,
        },
        neighbor_class_counts={
            label: sum(item["label"] == label for item in neighbors)
            for label in classes
        },
        neighbor_disagreement=sum(
            item["label"] != prediction["predicted_class"] for item in neighbors
        )
        / len(neighbors),
        recommendations=recommendations,
        intervention=replacement,
    )
    if influence is not None and "removal_loss_change" in influence:
        scores = influence.pop("removal_loss_change")
        derivatives = influence.pop("upweight_loss_derivative")
        ranked = sorted(range(len(train)), key=lambda i: (-abs(scores[i]), train[i]))[
            :10
        ]
        influence["records"] = [
            {
                "record_id": train[i],
                "estimated_removal_loss_change": float(scores[i]),
                "upweight_loss_derivative": float(derivatives[i]),
            }
            for i in ranked
        ]
        influence["status"] = "experimental"
        edges.extend(
            {
                "source": f"train:{train[i]}",
                "target": f"prediction:{record_id}",
                "type": "HAS_ESTIMATED_PREDICTION_INFLUENCE",
                "evidence": "inferred",
            }
            for i in ranked
        )
        result["evidence_graph"]["nodes"] = sorted(
            {edge[key] for edge in edges for key in ("source", "target")}
        )
    result["prediction_influence"] = influence
    return result
