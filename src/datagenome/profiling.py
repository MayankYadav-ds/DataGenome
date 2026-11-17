import math
import re
from collections import Counter
from dataclasses import dataclass
from statistics import mean, median

from .diagnostics import Finding, finding
from .ingestion import Dataset, DatasetError

INTEGER = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    missing_count: int
    missing_percentage: float
    unique_count: int
    constant: bool
    numeric: dict[str, int | float] | None


@dataclass(frozen=True)
class Profile:
    row_count: int
    column_count: int
    duplicate_row_count: int
    columns: list[ColumnProfile]
    target: str | None
    target_distribution: dict[str, int] | None
    findings: list[Finding]


def infer_dtype(values: set[str]) -> str:
    if not values:
        return "empty"
    if all(value.lower() in {"true", "false"} for value in values):
        return "boolean"
    if any(
        not NUMBER.fullmatch(value)
        or (value.lstrip("+-").isdigit() and not INTEGER.fullmatch(value))
        for value in values
    ):
        return "string"
    return "integer" if all(INTEGER.fullmatch(value) for value in values) else "float"


def numeric_stats(values: list[str]) -> dict[str, int | float] | None:
    numbers = [float(value) for value in values]
    if not all(math.isfinite(value) for value in numbers):
        return None
    middle = median(numbers)
    if not math.isfinite(middle):
        ordered = sorted(numbers)
        index = len(ordered) // 2
        middle = ordered[index - 1] / 2 + ordered[index] / 2
    return {
        "min": min(numbers),
        "max": max(numbers),
        "mean": mean(numbers),
        "median": middle,
    }


def profile(dataset: Dataset, target: str | None = None) -> Profile:
    if target is not None and target not in dataset.columns:
        raise DatasetError("unknown_target", "Target must match a CSV header.")
    row_count = len(dataset.rows)
    columns = []
    findings = []
    seen = set()
    duplicates = []
    for index, row in enumerate(dataset.rows, 1):
        if row in seen:
            duplicates.append(index)
        seen.add(row)
    if duplicates:
        findings.append(
            finding(
                "duplicate_rows",
                dataset.columns,
                {"count": len(duplicates)},
                "Rows repeat an earlier record.",
                "Review repeats before deduplicating.",
                "Exact parsed-cell comparison includes the target and whitespace.",
                records=duplicates,
            )
        )

    distribution = None
    for name, cells in zip(dataset.columns, zip(*dataset.rows), strict=True):
        missing = [index for index, cell in enumerate(cells, 1) if not cell.strip()]
        values = [cell for cell in cells if cell.strip()]
        unique = set(values)
        dtype = infer_dtype(unique)
        stats = None
        if dtype in {"integer", "float"}:
            stats = numeric_stats(values)
            if stats is None:
                dtype = "string"
        percentage = 100 * len(missing) / row_count
        columns.append(
            ColumnProfile(
                name,
                dtype,
                len(missing),
                percentage,
                len(unique),
                len(unique) == 1,
                stats,
            )
        )
        if missing:
            findings.append(
                finding(
                    "missing_values",
                    (name,),
                    {"count": len(missing), "percentage": percentage},
                    "Blank or whitespace-only cells are present.",
                    "Review missingness before choosing a treatment.",
                    "Only blank and whitespace-only cells count as missing.",
                    records=missing,
                )
            )
        if len(unique) == 1:
            findings.append(
                finding(
                    "constant_column",
                    (name,),
                    {"unique_count": 1},
                    "All observed cells have the same value.",
                    "Review whether this column can be omitted.",
                    "Missing cells are excluded from the distinct count.",
                    severity="info",
                )
            )
        if target == name:
            distribution = dict(sorted(Counter(values).items()))
            if len(distribution) < 2:
                findings.append(
                    finding(
                        "insufficient_target_classes",
                        (name,),
                        {"classes": len(distribution)},
                        "The target has fewer than two observed classes.",
                        "Verify the target and collect labels for other classes.",
                        "Blank and whitespace-only labels are excluded.",
                    )
                )
            elif (share := max(distribution.values()) / len(values)) >= 0.8:
                findings.append(
                    finding(
                        "class_imbalance",
                        (name,),
                        {"largest_class_share": share},
                        "One class accounts for at least 80% of observed labels.",
                        "Inspect per-class metrics and use a split suited to the data.",
                        "The threshold is heuristic and does not measure model impact.",
                    )
                )
    return Profile(
        row_count,
        len(columns),
        len(duplicates),
        columns,
        target,
        distribution,
        findings,
    )
