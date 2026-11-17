from collections.abc import Sequence
from datetime import timedelta

from .ingestion import Dataset, DatasetError
from .splits import column, timestamp


def connected_groups(keys: Sequence[Sequence[object]]) -> list[int]:
    """Keep rows sharing any supplied key together, including transitive links."""
    parents = list(range(len(keys)))

    def root(i: int) -> int:
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen: dict[tuple[int, object], int] = {}
    for i, row in enumerate(keys):
        for j, key in enumerate(row):
            previous = seen.setdefault((j, key), i)
            parents[root(i)] = root(previous)
    return [root(i) for i in range(len(keys))]


def historical_folds(
    dataset: Dataset,
    records: list[int],
    time: str,
    folds: int,
    gap_seconds: int = 0,
    window_seconds: int | None = None,
) -> list[tuple[list[int], list[int]]]:
    if (
        type(gap_seconds) is not int
        or not 0 <= gap_seconds <= 31536000
        or not 2 <= folds <= 5
        or (window_seconds is not None and not 0 < window_seconds <= 31536000)
    ):
        raise DatasetError(
            "invalid_time_window", "Invalid historical fold count, gap, or window."
        )
    index = column(dataset, time)
    dates = [timestamp(dataset.rows[i - 1][index]) for i in records]
    unique = sorted(set(dates))
    if len(unique) < folds + 1:
        return []
    result = []
    for k in range(1, folds + 1):
        start, end = (
            k * len(unique) // (folds + 1),
            (k + 1) * len(unique) // (folds + 1),
        )
        first = unique[start]
        try:
            cutoff = first - timedelta(seconds=gap_seconds)
            floor = (
                cutoff - timedelta(seconds=window_seconds)
                if window_seconds is not None
                else None
            )
        except OverflowError as error:
            raise DatasetError(
                "invalid_time_window", "Configured gap exceeds the timestamp range."
            ) from error
        block = set(unique[start:end])
        fit = [
            i
            for i, t in enumerate(dates)
            if t < cutoff and (floor is None or t >= floor)
        ]
        score = [i for i, t in enumerate(dates) if t in block]
        if fit and score:
            result.append((fit, score))
    return result
