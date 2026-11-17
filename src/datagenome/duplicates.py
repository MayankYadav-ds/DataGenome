from collections import defaultdict
from collections.abc import Iterator, Sequence

from .ingestion import DatasetError


def groups(rows: Sequence[tuple[str, ...]]) -> list[list[int]]:
    index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for record, row in enumerate(rows, 1):
        index[row].append(record)
    return [ids for ids in index.values() if len(ids) > 1]


def near_pairs(
    rows: Sequence[tuple[str, ...]], limit: int
) -> Iterator[tuple[int, int]]:
    if not 1 <= limit <= 100000:
        raise DatasetError(
            "invalid_candidate_limit", "Candidate limit must be between 1 and 100,000."
        )
    if len(rows) < 2 or len(rows[0]) < 2:
        return
    order = sorted(range(len(rows)), key=rows.__getitem__)
    reverse = sorted(order, key=lambda index: rows[index][::-1])
    seen: set[tuple[int, int]] = set()
    for ordering in (order, reverse):
        for left, right in zip(ordering, ordering[1:]):
            pair = min(left, right) + 1, max(left, right) + 1
            if pair in seen:
                continue
            if len(seen) >= limit:
                return
            seen.add(pair)
            if sum(a != b for a, b in zip(rows[left], rows[right], strict=True)) == 1:
                yield pair
