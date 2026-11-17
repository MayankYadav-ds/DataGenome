import math
from collections.abc import Sequence


def number(value: str) -> float | None:
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def numeric(values: Sequence[str]) -> bool:
    observed = [value for value in values if value.strip()]
    return bool(observed) and all(number(value) is not None for value in observed)
