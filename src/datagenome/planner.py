from collections.abc import Callable
from dataclasses import asdict, replace
from random import Random
from time import perf_counter
from typing import Any

from .identity import fingerprint
from .ingestion import DatasetError
from .modeling import ModelConfig, fit_baseline
from .store import Store
from .versions import Transform, apply, derive, manifest_of, table


def evaluate_plans(
    store: Store,
    project: str,
    version_id: str,
    plans: list[Transform],
    *,
    authorized: bool = False,
    model: ModelConfig = ModelConfig(),
    max_fits: int = 6,
    cancelled: Callable[[], bool] | None = None,
    event: Callable[[dict[str, Any]], None] | None = None,
    seconds: float = 120,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    deadline_start = perf_counter()
    if not 0 < seconds <= 120:
        raise DatasetError(
            "experiment_budget", "Use a cooperative deadline in (0,120]."
        )

    def boundary(completed: int) -> None:
        if event:
            event({"stage": "fit_complete", "completed_fits": completed})
        if cancelled and cancelled():
            raise DatasetError("job_cancelled", "Experiment stopped at a fit boundary.")
        if perf_counter() - deadline_start > seconds:
            raise DatasetError(
                "experiment_timeout", "Experiment reached its cooperative deadline."
            )

    if not 1 <= len(plans) <= 4 or not 2 <= max_fits <= 6:
        raise DatasetError(
            "planner_budget", "Use 1–4 explicit plans and at most six fits."
        )
    if len({fingerprint(asdict(plan)) for plan in plans}) != len(plans):
        raise DatasetError(
            "duplicate_plan", "Intervention candidates must be distinct."
        )
    version = store.get(project, version_id, "version")
    derived = [derive(version, plan) for plan in plans]
    review = [
        {
            "plan": asdict(plan),
            "anticipated_rows": len(candidate["rows"]),
            "affected_records": candidate["affected_records"],
            "affected_features": candidate["affected_features"],
        }
        for plan, candidate in zip(plans, derived, strict=True)
    ]
    if not authorized:
        return {
            "mode": "review",
            "plans": review,
            "datasets_modified": False,
            "required_review": True,
        }
    plan_roles = ["requested"] * len(plans)
    for number, (plan, candidate) in enumerate(
        zip(list(plans), list(derived), strict=True)
    ):
        count = len(version["rows"]) - len(candidate["rows"])
        if not count:
            continue
        if plan.corrections or plan.remove_features or plan.constant_features:
            continue
        ids = manifest_of(version).partitions["train"]
        shuffled = [version["record_ids"][i - 1] for i in ids]
        Random(model.seed + number).shuffle(shuffled)
        random_plan = replace(
            plan, remove_records=tuple(shuffled[:count]), remove_duplicates=False
        )
        try:
            control = derive(version, random_plan)
        except DatasetError:
            review[number]["random_control_status"] = "ineligible_under_guards"
            continue
        plans = [*plans, random_plan]
        derived = [*derived, control]
        plan_roles.append("matched_random_removal")
    if len(plans) + 1 > max_fits:
        raise DatasetError("planner_budget", "The fit budget is too small.")
    for candidate in derived:
        # Scientific comparison rejects metadata or validation changes before fitting.
        before, after = table(version), table(candidate)
        a, b = manifest_of(version), manifest_of(candidate)
        target_index = before.columns.index(version["target"])
        selected = [
            j
            for j, name in enumerate(before.columns)
            if j != target_index and name not in {a.config.group, a.config.time}
        ]
        train_features = {
            tuple(before.rows[i - 1][j] for j in selected)
            for i in a.partitions["train"]
        }
        if any(
            tuple(before.rows[i - 1][j] for j in selected) in train_features
            for i in a.partitions["validation"]
        ):
            raise DatasetError(
                "experiment_contamination",
                "Training and validation feature vectors overlap.",
            )
        if [version["record_ids"][i - 1] for i in a.partitions["validation"]] != [
            candidate["record_ids"][i - 1] for i in b.partitions["validation"]
        ]:
            raise DatasetError(
                "experiment_validation", "Validation record identities changed."
            )
        if [before.rows[i - 1][target_index] for i in a.partitions["validation"]] != [
            after.rows[i - 1][after.columns.index(version["target"])]
            for i in b.partitions["validation"]
        ]:
            raise DatasetError("experiment_validation", "Validation labels changed.")
    if experiment_id is not None:
        experiment = store.get(project, experiment_id, "experiment")
    else:
        experiment = store.put(
            project,
            "experiment",
            {
                "state": "running",
                "version_id": version_id,
                "plans": [asdict(p) for p in plans],
                "model": asdict(model),
                "split_sha256": manifest_of(version).fingerprint,
                "warnings": [],
                "limitations": [
                    "Validation is exploratory. Independent scoring requires a frozen protocol."
                ],
            },
        )
    started = perf_counter()
    try:
        boundary(0)
        baseline = fit_baseline(
            table(version),
            version["target"],
            manifest_of(version),
            model,
            include_predictions=True,
        )
        boundary(1)
        arms = []
        for arm_index, (candidate, plan) in enumerate(zip(derived, plans, strict=True)):
            result = fit_baseline(
                table(candidate),
                candidate["target"],
                manifest_of(candidate),
                model,
                include_predictions=True,
            )
            boundary(arm_index + 2)
            persisted = apply(store, project, version_id, plan)
            left, right = (
                baseline["metrics"]["validation"],
                result["metrics"]["validation"],
            )
            delta = {
                key: right[key] - left[key]
                if right[key] is not None and left[key] is not None
                else None
                for key in ("accuracy", "balanced_accuracy", "macro_f1", "log_loss")
            }
            recalls = {
                label: right["per_class"][label]["recall"] - row["recall"]
                if row["recall"] is not None
                and right["per_class"][label]["recall"] is not None
                else None
                for label, row in left["per_class"].items()
            }
            from .uncertainty import ResamplingConfig, metric_intervals

            manifest = manifest_of(version)
            data = table(version)
            unit_column = manifest.config.group or manifest.config.time
            units = [
                data.rows[i - 1][data.columns.index(unit_column)]
                if unit_column
                else str(i)
                for i in manifest.partitions["validation"]
            ]
            uncertainty = metric_intervals(
                baseline["validation_predictions"]["actual"],
                baseline["validation_predictions"]["predicted"],
                result["validation_predictions"]["predicted"],
                units,
                ResamplingConfig(
                    mode="group"
                    if manifest.config.group
                    else "temporal"
                    if manifest.config.time
                    else "independent",
                    samples=99,
                ),
            )
            if manifest.config.group and manifest.config.time:
                uncertainty = {
                    name: {
                        "status": "unsupported_combined_dependence",
                        "percentile_95": None,
                    }
                    for name in ("accuracy", "balanced_accuracy", "macro_f1")
                }
            arms.append(
                {
                    "version_id": persisted["id"],
                    "role": plan_roles[arm_index],
                    "metrics": right,
                    "uncertainty": uncertainty,
                    "delta": delta,
                    "class_recall_change": recalls,
                    "training_seconds": result["train_seconds"],
                    "evaluation_seconds": result["evaluate_seconds"],
                    "removed_records": len(version["rows"]) - len(candidate["rows"]),
                    "corrected_labels": len(plan.corrections),
                    "removed_features": len(plan.remove_features)
                    + len(plan.constant_features),
                }
            )
        objectives = ("balanced_accuracy", "macro_f1")
        nondominated = []
        for i, arm in enumerate(arms):
            if not any(
                all(other["metrics"][key] >= arm["metrics"][key] for key in objectives)
                and any(
                    other["metrics"][key] > arm["metrics"][key] for key in objectives
                )
                for j, other in enumerate(arms)
                if j != i
            ):
                nondominated.append(i)
        result = {
            "state": "completed",
            "baseline": baseline["metrics"]["validation"],
            "arms": arms,
            "pareto_objectives": objectives,
            "nondominated_plan_indices": nondominated,
            "held_out_evaluated": False,
            "elapsed_seconds": perf_counter() - started,
            "limitations": [
                "Nondominance does not imply superiority or material improvement.",
                "Per-class recall can degrade despite aggregate gains.",
            ],
        }
    except Exception as error:
        terminal = (
            "cancelled"
            if isinstance(error, DatasetError) and error.code == "job_cancelled"
            else "failed"
        )
        store.put(
            project,
            "experiment_result",
            {
                "experiment_id": experiment["id"],
                "state": terminal,
                "error_type": type(error).__name__,
            },
            experiment["id"] + ".result",
        )
        raise
    stored = store.put(
        project,
        "experiment_result",
        {**result, "experiment_id": experiment["id"]},
        experiment["id"] + ".result",
    )
    return stored
