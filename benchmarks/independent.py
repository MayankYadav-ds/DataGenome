import argparse
import json
import tempfile
import tracemalloc
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from random import Random
from time import perf_counter

from sklearn.datasets import load_breast_cancer, load_iris, load_wine

from datagenome.identity import canonical
from datagenome.independent import freeze_removal, score_frozen
from datagenome.ingestion import Dataset, DatasetError
from datagenome.modeling import ModelConfig
from datagenome.splits import SplitConfig, split
from datagenome.valuation import ValuationConfig

SEEDS = (11, 23, 37)
LOADERS = {
    "wisconsin-diagnostic": load_breast_cancer,
    "wine": load_wine,
    "iris": load_iris,
}


def run(folder: Path):
    outcomes = []
    for name, loader in LOADERS.items():
        data = loader()
        rows = tuple(
            (*map(str, row), str(y))
            for row, y in zip(data.data, data.target, strict=True)
        )
        clean = Dataset((*data.feature_names, "label"), rows)
        for seed in SEEDS:
            original = split(clean, SplitConfig("stratified", seed=seed), "label")
            rng = Random(seed + 500)
            train = original.partitions["train"]
            mask = set(rng.sample(train, len(train) // 10))
            classes = len(set(map(str, data.target)))
            changed = Dataset(
                clean.columns,
                tuple(
                    (*row[:-1], str((int(row[-1]) + 1) % classes)) if i in mask else row
                    for i, row in enumerate(clean.rows, 1)
                ),
            )
            for variant, dataset in (
                ("clean", clean),
                ("training-label-flips", changed),
            ):
                manifest = replace(original, dataset_sha256=canonical(dataset))
                stem = f"{name}-{seed}-{variant}"
                path = folder / (stem + ".json")
                outcome = {
                    "dataset": name,
                    "seed": seed,
                    "variant": variant,
                    "injected_labels": len(mask) if variant != "clean" else 0,
                }
                try:
                    frozen = freeze_removal(
                        dataset,
                        "label",
                        manifest,
                        ValuationConfig(method="knn-shapley", seed=seed),
                        ModelConfig(seed=seed),
                        0.10,
                        path,
                    )
                    outcome["exploratory_accuracy_deltas"] = {
                        key: arm["accuracy_change"]
                        for key, arm in frozen["exploratory"]["arms"].items()
                        if arm["status"] == "evaluated"
                    }
                    outcome["unavailable_arms"] = frozen["plan"]["unavailable_arms"]
                    outcome["exploratory_seconds"] = frozen["exploratory"][
                        "elapsed_seconds"
                    ]
                    outcome["independent"] = score_frozen(
                        dataset, path, folder / "ledger"
                    )
                except DatasetError as error:
                    outcome["unscored_reason"] = error.code
                outcomes.append(outcome)
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        tracemalloc.start()
        start = perf_counter()
        trials = run(Path(temporary))
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    result = {
        "schema_version": "1.0",
        "scikit_learn": version("scikit-learn"),
        "seconds": perf_counter() - start,
        "python_peak_bytes": peak,
        "removal_fraction": 0.10,
        "seeds": SEEDS,
        "trials": trials,
    }
    args.output.write_text(
        json.dumps(result, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
