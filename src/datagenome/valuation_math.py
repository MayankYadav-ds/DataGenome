from collections.abc import Callable
from math import comb
from random import Random
from statistics import mean, stdev

Utility = Callable[[int], float]


def exact_values(n: int, utility: Utility, *, banzhaf: bool = False) -> list[float]:
    values = [0.0] * n
    for mask in range(1 << n):
        size = mask.bit_count()
        if size == n:
            continue
        weight = 1 / (1 << (n - 1)) if banzhaf else 1 / (n * comb(n - 1, size))
        baseline = utility(mask)
        for i in range(n):
            bit = 1 << i
            if not mask & bit:
                values[i] += weight * (utility(mask | bit) - baseline)
    return values


def sampled_values(
    n: int, utility: Utility, seed: int, permutations: int
) -> tuple[list[float], list[float], list[dict[str, float | int]]]:
    rng = Random(seed)
    samples: list[list[float]] = [[] for _ in range(n)]
    history = []
    previous: list[float] | None = None
    order = list(range(n))
    for iteration in range(1, permutations + 1):
        rng.shuffle(order)
        mask = 0
        before = utility(mask)
        for i in order:
            mask |= 1 << i
            after = utility(mask)
            samples[i].append(after - before)
            before = after
        if iteration & (iteration - 1) == 0 or iteration == permutations:
            current = [mean(row) for row in samples]
            if previous is not None:
                history.append(
                    {
                        "permutations": iteration,
                        "max_change": max(
                            abs(a - b) for a, b in zip(current, previous, strict=True)
                        ),
                    }
                )
            previous = current
    return [mean(row) for row in samples], [stdev(row) for row in samples], history


def knn_values(
    training: list[list[float]],
    validation: list[list[float]],
    train_labels: list[str],
    validation_labels: list[str],
    k: int,
    check_budget: Callable[[], None],
) -> list[float]:
    n = len(training)
    values = [0.0] * n
    for row, target in zip(validation, validation_labels, strict=True):
        check_budget()
        order = sorted(
            range(n),
            key=lambda i: (
                sum((a - b) ** 2 for a, b in zip(training[i], row, strict=True)),
                i,
            ),
        )
        match = [int(train_labels[i] == target) for i in order]
        contribution = match[-1] / n
        values[order[-1]] += contribution
        for j in range(n - 2, -1, -1):
            position = j + 1
            contribution += (
                (match[j] - match[j + 1]) * min(k, position) / (k * position)
            )
            values[order[j]] += contribution
    return [value / len(validation) for value in values]
