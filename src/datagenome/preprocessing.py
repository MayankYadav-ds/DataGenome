from dataclasses import asdict, dataclass
from statistics import mean, median, pstdev, quantiles
from typing import Any

from .identity import fingerprint
from .ingestion import Dataset, DatasetError
from .numeric import number, numeric
from .splits import column
from .store import Store
from .versions import manifest_of, table


@dataclass(frozen=True)
class LearnedConfig:
    features: tuple[str, ...] = ()
    numeric_imputation: str = "median"
    scaling: str = "standard"
    category_limit: int = 32


def fit_parameters(
    version: dict[str, Any], config: LearnedConfig = LearnedConfig()
) -> dict[str, Any]:
    dataset = table(version)
    manifest = manifest_of(version)
    from .splits import validate

    validate(dataset, manifest)
    names = config.features or tuple(
        name
        for name in dataset.columns
        if name not in {version["target"], manifest.config.group, manifest.config.time}
    )
    if (
        not 1 <= len(names) <= 32
        or len(set(names)) != len(names)
        or config.numeric_imputation not in {"median", "mean"}
        or config.scaling not in {"standard", "robust", "none"}
        or not 2 <= config.category_limit <= 32
        or len(dataset.rows) > 5000
        or any(
            name in {version["target"], manifest.config.group, manifest.config.time}
            for name in names
        )
    ):
        raise DatasetError(
            "preprocessing_config",
            "Invalid selected features or preprocessing settings.",
        )
    specifications: list[dict[str, Any]] = []
    from collections import Counter

    for name in names:
        index = column(dataset, name)
        cells = [dataset.rows[i - 1][index] for i in manifest.partitions["train"]]
        observed = [cell for cell in cells if cell.strip()]
        if numeric(cells):
            values = [
                min(1e12, max(-1e12, value))
                for cell in observed
                if (value := number(cell)) is not None
            ]
            fill = (
                median(values)
                if config.numeric_imputation == "median"
                else mean(values)
            )
            filled = [
                fill if not cell.strip() else min(1e12, max(-1e12, float(cell)))
                for cell in cells
            ]
            center = (
                mean(filled)
                if config.scaling == "standard"
                else median(filled)
                if config.scaling == "robust"
                else 0.0
            )
            scale = (
                pstdev(filled)
                if config.scaling == "standard"
                else (
                    quantiles(filled, n=4, method="inclusive")[2]
                    - quantiles(filled, n=4, method="inclusive")[0]
                    if config.scaling == "robust" and len(filled) > 1
                    else 1.0
                )
            )
            specifications.append(
                {
                    "name": name,
                    "kind": "numeric",
                    "fill": fill,
                    "center": center,
                    "scale": scale if scale > 1e-12 else 1.0,
                }
            )
        else:
            counts = Counter(observed)
            category_fill = (
                sorted(counts, key=lambda item: (-counts[item], item))[0]
                if counts
                else None
            )
            categories = sorted(counts, key=lambda item: (-counts[item], item))[
                : config.category_limit
            ]
            specifications.append(
                {
                    "name": name,
                    "kind": "categorical",
                    "fill": category_fill,
                    "categories": categories,
                }
            )
    width = sum(
        1 if spec["kind"] == "numeric" else max(1, len(spec["categories"]))
        for spec in specifications
    )
    if width > 256:
        raise DatasetError("preprocessing_width", "Encoded feature width exceeds 256.")
    plan = {
        "schema_version": 1,
        "version_id": version["id"],
        "source_schema": dataset.columns,
        "split_sha256": manifest.fingerprint,
        "fit_record_ids": [
            version["record_ids"][i - 1] for i in manifest.partitions["train"]
        ],
        "config": asdict(config),
        "features": specifications,
        "output_width": width,
    }
    # Normalize tuples before hashing and persistence.
    import json

    plan = json.loads(json.dumps(plan, allow_nan=False))
    return {"parameters": plan, "parameters_sha256": fingerprint(plan)}


def transform_parameters(
    artifact: dict[str, Any], dataset: Dataset, records: list[int]
) -> list[list[float]]:
    import math

    try:
        plan = artifact["parameters"]
        if (
            fingerprint(plan) != artifact["parameters_sha256"]
            or plan["schema_version"] != 1
            or list(dataset.columns) != plan["source_schema"]
            or not 1 <= len(plan["features"]) <= 32
            or not 1 <= plan["output_width"] <= 256
            or len(records) > 5000
            or any(
                type(i) is not int or not 1 <= i <= len(dataset.rows) for i in records
            )
        ):
            raise ValueError
        output = []
        for i in records:
            result = []
            for spec in plan["features"]:
                cell = dataset.rows[i - 1][column(dataset, spec["name"])]
                if spec["kind"] == "numeric":
                    value = number(cell)
                    value = (
                        spec["fill"] if value is None else min(1e12, max(-1e12, value))
                    )
                    if spec["scale"] <= 0:
                        raise ValueError
                    result.append((value - spec["center"]) / spec["scale"])
                elif spec["kind"] == "categorical":
                    category_value = cell if cell.strip() else spec["fill"]
                    categories = spec["categories"]
                    result.extend(
                        float(category_value == category) for category in categories
                    )
                    if not categories:
                        result.append(0.0)
                else:
                    raise ValueError
            if len(result) != plan["output_width"] or not all(
                math.isfinite(value) for value in result
            ):
                raise ValueError
            output.append(result)
        return output
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as error:
        raise DatasetError(
            "preprocessing_artifact",
            "Corrupt or schema-incompatible preprocessing artifact.",
        ) from error


def persist_parameters(
    store: Store, project: str, version_id: str, config: LearnedConfig = LearnedConfig()
) -> dict[str, Any]:
    version = store.get(project, version_id, "version")
    result = fit_parameters(version, config)
    return store.put(project, "preprocessing", result)
