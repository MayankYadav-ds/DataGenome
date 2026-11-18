from dataclasses import asdict, dataclass
from typing import Any

from .identity import canonical, fingerprint
from .ingestion import Dataset, DatasetError, parse_csv
from .splits import Manifest, column, restore, validate
from .store import Store


@dataclass(frozen=True)
class Transform:
    remove_records: tuple[int, ...] = ()
    corrections: tuple[tuple[int, str], ...] = ()
    remove_features: tuple[str, ...] = ()
    constant_features: tuple[str, ...] = ()
    review_records: tuple[int, ...] = ()
    ambiguous_records: tuple[int, ...] = ()
    remove_duplicates: bool = False
    max_fraction: float = 0.20
    minimum_class_support: int = 2
    minimum_group_support: int = 2


def table(version: dict[str, Any]) -> Dataset:
    data = Dataset(
        tuple(version["columns"]), tuple(tuple(row) for row in version["rows"])
    )
    if canonical(data) != version["canonical_sha256"]:
        raise DatasetError(
            "version_integrity", "Stored version content failed its fingerprint."
        )
    return data


def manifest_of(version: dict[str, Any]) -> Manifest:
    return restore(version)


def register(
    store: Store,
    project: str,
    payload: bytes,
    target: str,
    manifest: Manifest,
    filename: str = "upload.csv",
) -> dict[str, Any]:
    import hashlib

    data = parse_csv(payload, max_rows=5000, max_columns=64)
    validate(data, manifest)
    column(data, target)
    dataset_id = fingerprint([project, hashlib.sha256(payload).hexdigest(), target])
    return store.put(
        project,
        "version",
        {
            "dataset_id": dataset_id,
            "parent_id": None,
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "canonical_sha256": canonical(data),
            "schema_sha256": fingerprint(data.columns),
            "columns": data.columns,
            "rows": data.rows,
            "target": target,
            "record_ids": list(range(1, len(data.rows) + 1)),
            "split": {**asdict(manifest), "fingerprint": manifest.fingerprint},
            "transformation": None,
            "affected_records": [],
            "affected_features": [],
            "provenance": {
                "source_name": filename,
                "source": "explicit_local_registration",
            },
        },
    )


def derive(version: dict[str, Any], plan: Transform) -> dict[str, Any]:
    original = table(version)
    manifest = manifest_of(version)
    validate(original, manifest)
    target = version["target"]
    index = column(original, target)
    stable = version["record_ids"]
    if len(set(stable)) != len(stable) or len(stable) != len(original.rows):
        raise DatasetError("record_identity", "Stored record identities are invalid.")
    position = {record: i for i, record in enumerate(stable)}
    training = {stable[i - 1] for i in manifest.partitions["train"]}
    lists = (
        plan.remove_records,
        plan.remove_features,
        plan.constant_features,
        plan.review_records,
        plan.ambiguous_records,
    )
    if any(len(set(values)) != len(values) for values in lists):
        raise DatasetError(
            "duplicate_transform", "Transformation requests must be unique."
        )
    corrected = dict(plan.corrections)
    if len(corrected) != len(plan.corrections):
        raise DatasetError(
            "duplicate_transform", "A record can receive one replacement label."
        )
    if (
        not 0 < plan.max_fraction <= 0.20
        or not 1 <= plan.minimum_class_support <= 100
        or not 1 <= plan.minimum_group_support <= 100
    ):
        raise DatasetError("transform_policy", "Invalid transformation safety policy.")
    requested_ids = (
        *plan.remove_records,
        *corrected,
        *plan.review_records,
        *plan.ambiguous_records,
    )
    if any(type(record) is not int or record < 1 for record in requested_ids):
        raise DatasetError("record_identity", "Use positive integer record identities.")
    selected = (
        set(plan.remove_records)
        | set(corrected)
        | set(plan.review_records)
        | set(plan.ambiguous_records)
    )
    if not selected <= training:
        raise DatasetError(
            "training_only",
            "Changes and review flags must refer to training record IDs.",
        )
    removed = set(plan.remove_records)
    if plan.remove_duplicates:
        seen = set()
        for record in sorted(training):
            duplicate_row = original.rows[position[record]]
            if duplicate_row in seen:
                removed.add(record)
            seen.add(duplicate_row)
    if removed & set(corrected) or removed & (
        set(plan.review_records) | set(plan.ambiguous_records)
    ):
        raise DatasetError(
            "transform_conflict",
            "Removed rows cannot also receive corrections or review flags.",
        )
    if len(removed) > int(len(training) * plan.max_fraction):
        raise DatasetError(
            "removal_cap", "Removal exceeds the configured training fraction."
        )
    vocabulary = {original.rows[position[i]][index] for i in training}
    if any(
        label not in vocabulary or not label.strip() for label in corrected.values()
    ):
        raise DatasetError(
            "replacement_schema",
            "Replacement labels must match an existing nonblank training class.",
        )
    features = set(plan.remove_features) | set(plan.constant_features)
    protected = {target, manifest.config.group, manifest.config.time}
    if features & protected or not features <= set(original.columns):
        raise DatasetError(
            "protected_feature", "Target and split metadata cannot be removed."
        )
    if len(features) >= len(original.columns) - len(
        {name for name in protected if name is not None}
    ):
        raise DatasetError("no_features", "Retain at least one predictive feature.")
    for name in plan.constant_features:
        j = column(original, name)
        if (
            len(
                {
                    original.rows[position[i]][j]
                    for i in training
                    if original.rows[position[i]][j].strip()
                }
            )
            != 1
        ):
            raise DatasetError(
                "nonconstant_feature",
                "Selected constant feature is not constant in training.",
            )
    kept_columns = [
        j for j, name in enumerate(original.columns) if name not in features
    ]
    ids = [record for record in stable if record not in removed]
    rows = []
    originals = []
    for record in ids:
        row = list(original.rows[position[record]])
        if record in corrected:
            originals.append(
                {
                    "record_id": record,
                    "old_label": row[index],
                    "new_label": corrected[record],
                }
            )
            row[index] = corrected[record]
        rows.append(tuple(row[j] for j in kept_columns))
    data = Dataset(tuple(original.columns[j] for j in kept_columns), tuple(rows))
    new_index = column(data, target)
    retained_train = [record for record in ids if record in training]
    from collections import Counter

    before = Counter(original.rows[position[record]][index] for record in training)
    after = Counter(
        data.rows[ids.index(record)][new_index] for record in retained_train
    )
    if any(
        after[label] < min(count, plan.minimum_class_support)
        for label, count in before.items()
    ):
        raise DatasetError(
            "class_preservation", "Transformation violates retained class support."
        )
    if manifest.config.group:
        g = column(original, manifest.config.group)
        before_groups = Counter(original.rows[position[i]][g] for i in training)
        after_groups = Counter(original.rows[position[i]][g] for i in retained_train)
        if any(
            after_groups[key] < min(count, plan.minimum_group_support)
            for key, count in before_groups.items()
        ):
            raise DatasetError(
                "group_preservation", "Transformation violates retained group support."
            )
    new_position = {record: i + 1 for i, record in enumerate(ids)}
    parts = {
        name: [
            new_position[stable[i - 1]]
            for i in records
            if stable[i - 1] in new_position
        ]
        for name, records in manifest.partitions.items()
    }
    derived_manifest = Manifest(canonical(data), manifest.config, parts)
    validate(data, derived_manifest)
    return {
        "dataset_id": version["dataset_id"],
        "parent_id": version["id"],
        "source_sha256": version["source_sha256"],
        "canonical_sha256": canonical(data),
        "schema_sha256": fingerprint(data.columns),
        "target": target,
        "columns": data.columns,
        "rows": data.rows,
        "record_ids": ids,
        "split": {
            **asdict(derived_manifest),
            "fingerprint": derived_manifest.fingerprint,
        },
        "transformation": asdict(plan),
        "affected_records": sorted(selected | removed),
        "affected_features": sorted(features),
        "provenance": {
            "label_changes": originals,
            "review_records": plan.review_records,
            "ambiguous_records": plan.ambiguous_records,
            "parent": version["id"],
        },
    }


def preview(
    store: Store, project: str, version_id: str, plan: Transform
) -> dict[str, Any]:
    result = derive(store.get(project, version_id, "version"), plan)
    return {
        key: result[key]
        for key in (
            "parent_id",
            "canonical_sha256",
            "affected_records",
            "affected_features",
        )
    } | {
        "rows": len(result["rows"]),
        "columns": len(result["columns"]),
        "dry_run": True,
    }


def apply(
    store: Store, project: str, version_id: str, plan: Transform
) -> dict[str, Any]:
    result = derive(store.get(project, version_id, "version"), plan)
    return store.put(project, "version", result)


def compare_versions(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if left["dataset_id"] != right["dataset_id"]:
        raise DatasetError(
            "version_lineage", "Versions belong to different registered datasets."
        )
    a, b = set(left["record_ids"]), set(right["record_ids"])
    return {
        "left": left["id"],
        "right": right["id"],
        "removed_ids": sorted(a - b),
        "added_ids": sorted(b - a),
        "removed_features": sorted(set(left["columns"]) - set(right["columns"])),
        "same_content": left["canonical_sha256"] == right["canonical_sha256"],
    }


def reconstruct(store: Store, project: str, version_id: str) -> dict[str, Any]:
    version = store.get(project, version_id, "version")
    if version["parent_id"] is None:
        table(version)
        return version
    parent = store.get(project, version["parent_id"], "version")
    spec = version["transformation"]
    result = derive(
        parent,
        Transform(
            **{
                **spec,
                "corrections": tuple(tuple(pair) for pair in spec["corrections"]),
            }
        ),
    )
    if (
        result["canonical_sha256"] != version["canonical_sha256"]
        or result["record_ids"] != version["record_ids"]
    ):
        raise DatasetError(
            "reconstruction_failed",
            "Version reconstruction differs from stored content.",
        )
    return version
