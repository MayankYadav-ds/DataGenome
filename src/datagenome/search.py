from dataclasses import asdict
from typing import Any

from .identity import fingerprint
from .ingestion import DatasetError
from .store import Store
from .versions import Transform, derive, manifest_of, table


def generate_candidates(
    store: Store, project: str, version_id: str, *, maximum_candidates: int = 4
) -> dict[str, Any]:
    if not 1 <= maximum_candidates <= 4:
        raise DatasetError("search_budget", "Use 1–4 candidate plans.")
    version = store.get(project, version_id, "version")
    data = table(version)
    manifest = manifest_of(version)
    train = [i - 1 for i in manifest.partitions["train"]]
    protected = {version["target"], manifest.config.group, manifest.config.time}
    constants = tuple(
        name
        for j, name in enumerate(data.columns)
        if name not in protected
        and len({data.rows[i][j] for i in train if data.rows[i][j].strip()}) == 1
    )
    initial = []
    if constants:
        initial.append(("constant_features", Transform(constant_features=constants)))
    duplicates = Transform(remove_duplicates=True)
    if len({data.rows[i] for i in train}) < len(train):
        initial.append(("exact_training_duplicates", duplicates))
    # Candidate generation uses measured structural evidence. It does not infer replacement labels.
    pool = list(initial)
    if len(initial) == 2:
        pool.append(
            (
                "compatible_structural_combination",
                Transform(constant_features=constants, remove_duplicates=True),
            )
        )
    accepted, rejected = [], []
    for reason, plan in pool[:maximum_candidates]:
        identity = fingerprint(asdict(plan))
        try:
            preview = derive(version, plan)
            accepted.append(
                {
                    "id": identity,
                    "evidence": reason,
                    "plan": asdict(plan),
                    "anticipated_rows": len(preview["rows"]),
                    "requires_review": True,
                }
            )
        except DatasetError as error:
            rejected.append(
                {
                    "id": identity,
                    "evidence": reason,
                    "plan": asdict(plan),
                    "reason": error.code,
                }
            )
    result = {
        "mode": "review",
        "version_id": version_id,
        "candidates": accepted,
        "rejected": rejected,
        "limitations": [
            "Generation currently covers measured constants and exact duplicate training rows.",
            "Labels, minority exclusions and highly predictive feature removals require manual selection.",
            "Validation search provides exploratory comparisons.",
        ],
    }
    store.put(project, "search", result)
    return result


def compatible(left: Transform, right: Transform) -> dict[str, Any]:
    errors = []
    a, b = dict(left.corrections), dict(right.corrections)
    if any(a[i] != b[i] for i in a.keys() & b.keys()):
        errors.append("conflicting_label_replacements")
    removed = set(left.remove_records) | set(right.remove_records)
    if removed & (
        a.keys()
        | b.keys()
        | set(left.review_records)
        | set(right.review_records)
        | set(left.ambiguous_records)
        | set(right.ambiguous_records)
    ):
        errors.append("remove_and_relabel_or_review")
    return {"compatible": not errors, "reasons": errors}


def merge(left: Transform, right: Transform) -> Transform:
    result = compatible(left, right)
    if not result["compatible"]:
        raise DatasetError("plan_conflict", ", ".join(result["reasons"]))
    return Transform(
        remove_records=tuple(
            sorted(set(left.remove_records) | set(right.remove_records))
        ),
        corrections=tuple(
            sorted((dict(left.corrections) | dict(right.corrections)).items())
        ),
        remove_features=tuple(
            sorted(set(left.remove_features) | set(right.remove_features))
        ),
        constant_features=tuple(
            sorted(set(left.constant_features) | set(right.constant_features))
        ),
        review_records=tuple(
            sorted(set(left.review_records) | set(right.review_records))
        ),
        ambiguous_records=tuple(
            sorted(set(left.ambiguous_records) | set(right.ambiguous_records))
        ),
        remove_duplicates=left.remove_duplicates or right.remove_duplicates,
        max_fraction=min(left.max_fraction, right.max_fraction),
        minimum_class_support=max(
            left.minimum_class_support, right.minimum_class_support
        ),
        minimum_group_support=max(
            left.minimum_group_support, right.minimum_group_support
        ),
    )
