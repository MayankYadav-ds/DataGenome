from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warning"]


@dataclass(frozen=True)
class Finding:
    id: str
    category: str
    severity: Severity
    evidence: dict[str, int | float]
    affected_columns: tuple[str, ...]
    affected_records: tuple[int, ...]
    explanation: str
    suggested_remediation: str
    method_limitations: str


def finding(
    category: str,
    columns: tuple[str, ...],
    evidence: dict[str, int | float],
    explanation: str,
    remediation: str,
    limitations: str,
    *,
    records: list[int] | None = None,
    severity: Severity = "warning",
) -> Finding:
    identifier = category + "".join(f":{len(column)}:{column}" for column in columns)
    if records is not None:
        limitations += " At most 100 one-based data record indices are listed."
    return Finding(
        identifier,
        category,
        severity,
        evidence,
        columns,
        tuple((records or [])[:100]),
        explanation,
        remediation,
        limitations,
    )
