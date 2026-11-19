"""Bounded public loaders and controlled corruptions. Truth never enters detectors."""

from dataclasses import dataclass
from random import Random

from .identity import canonical
from .ingestion import Dataset, DatasetError

SOURCES = {
    "iris": "https://archive.ics.uci.edu/dataset/53/iris",
    "wine": "https://archive.ics.uci.edu/dataset/109/wine",
    "wdbc": "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic",
    "digits01": "https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits",
}


def public(name: str) -> Dataset:
    from sklearn.datasets import load_breast_cancer, load_digits, load_iris, load_wine

    loaders = {
        "iris": load_iris,
        "wine": load_wine,
        "wdbc": load_breast_cancer,
        "digits01": load_digits,
    }
    if name not in loaders:
        raise DatasetError("benchmark_dataset", "Unknown built-in research dataset.")
    bunch = loaders[name]()
    indices = list(range(bunch.data.shape[1]))
    if name == "digits01":
        # Frozen central 4x4 pixels, not a fitted feature selection.
        indices = [8 * r + c for r in range(2, 6) for c in range(2, 6)]
    return Dataset(
        tuple(f"x{j}" for j in indices) + ("label",),
        tuple(
            tuple(str(float(x[j])) for j in indices) + (str(int(y)),)
            for x, y in zip(bunch.data, bunch.target, strict=True)
            if name != "digits01" or int(y) in {0, 1}
        ),
    )


def identities() -> dict[str, str]:
    return {name: canonical(public(name)) for name in SOURCES}


@dataclass(frozen=True)
class Corruption:
    data: Dataset
    changed: frozenset[int]
    kind: str
    intensity: float


KINDS = (
    "uniform_labels",
    "class_labels",
    "feature_labels",
    "missing",
    "systematic_missing",
    "duplicates",
    "conflicting_duplicates",
    "target_copy",
    "target_encoding",
    "anomalies",
    "redundant",
    "underrepresented",
    "mean_shift",
    "variance_shift",
    "categorical_shift",
    "new_category",
    "dependence_shift",
    "outcome_change",
    "cross_split",
    "group_overlap",
    "time_overlap",
)


def corrupt(
    data: Dataset, records: list[int], kind: str, intensity: float, seed: int
) -> Corruption:
    if kind not in KINDS or not 0 <= intensity <= 0.5 or len(data.rows) > 10000:
        raise DatasetError(
            "benchmark_corruption", "Invalid bounded corruption configuration."
        )
    if not set(records) <= set(range(1, len(data.rows) + 1)):
        raise DatasetError("benchmark_corruption", "Invalid record selection.")
    rng = Random(seed)
    rows = [list(row) for row in data.rows]
    columns = list(data.columns)
    label = columns.index("label")
    classes = sorted({row[label] for row in rows})
    pool = records.copy()
    if kind == "class_labels":
        pool = [i for i in pool if rows[i - 1][label] == classes[0]]
    if kind in {"feature_labels", "systematic_missing"}:
        pool.sort(key=lambda i: (float(rows[i - 1][0]), i), reverse=True)
    else:
        rng.shuffle(pool)
    chosen = pool[: min(int(len(records) * intensity), len(pool))]
    changed: set[int] = set()
    if kind in {"target_copy", "target_encoding", "group_overlap", "time_overlap"}:
        columns.append("injected")
        for i, row in enumerate(rows, 1):
            value = row[label] if kind == "target_copy" else "class:" + row[label]
            if kind == "group_overlap":
                value = str(i % 8)
            if kind == "time_overlap":
                value = f"2020-01-{1 + i % 20:02d}T00:00:00"
            row.append(value)
        # Leakage columns are globally defined, not intensity-controlled row errors.
        changed = set(records) if intensity else set()
        if not intensity:
            for i, row in enumerate(rows):
                row[-1] = str(i)
    else:
        for i in chosen:
            row = rows[i - 1]
            before = row.copy()
            if kind in {
                "uniform_labels",
                "class_labels",
                "feature_labels",
                "outcome_change",
            }:
                row[label] = rng.choice([c for c in classes if c != row[label]])
            elif kind in {"missing", "systematic_missing"}:
                row[0] = ""
            elif kind in {
                "duplicates",
                "redundant",
                "conflicting_duplicates",
                "cross_split",
            }:
                sources = (
                    [j for j in range(1, len(rows) + 1) if j not in records]
                    if kind == "cross_split"
                    else records
                )
                source = next((j for j in sources if j != i and j not in chosen), None)
                if source is not None:
                    row[:] = rows[source - 1]
                    if kind == "conflicting_duplicates":
                        row[label] = rng.choice([c for c in classes if c != row[label]])
            elif kind in {"anomalies", "mean_shift"}:
                row[0] = str(float(row[0]) + (100 if kind == "anomalies" else 2))
            elif kind == "variance_shift":
                row[0] = str(3 * float(row[0]))
            elif kind in {"categorical_shift", "new_category"}:
                row[0] = "new-category"
            elif kind == "dependence_shift":
                row[1] = str(-float(row[0]))
            elif kind == "underrepresented":
                # A resampled population change, not fabricated demographic semantics.
                row[:] = rows[records[0] - 1]
            if row != before:
                changed.add(i)
    return Corruption(
        Dataset(tuple(columns), tuple(tuple(r) for r in rows)),
        frozenset(changed),
        kind,
        intensity,
    )


def synthetic(seed: int, n: int = 240, features: int = 4) -> Dataset:
    rng = Random(seed)
    rows = []
    for _ in range(n):
        x = rng.gauss(0, 1)
        y = int(x + rng.gauss(0, 0.8) > 0)
        rows.append(
            (str(x), *(str(rng.gauss(0, 1)) for _ in range(features - 1)), str(y))
        )
    return Dataset(tuple(f"x{j}" for j in range(features)) + ("label",), tuple(rows))
