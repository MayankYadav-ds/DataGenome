import argparse
import json
from pathlib import Path
from random import Random
from time import perf_counter

from datagenome.error_slices import analyze_errors
from datagenome.experiments import Intervention
from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.investigator import inspect_prediction
from datagenome.splits import Manifest, SplitConfig


def run(seed):
    rng = Random(seed)
    rows = []
    for i in range(120):
        label = int(i % 4 == 0)
        subgroup = i % 3 == 0
        signal = 3 * label + rng.gauss(0, 0.55)
        if i >= 72 and subgroup:
            signal = 3 * (1 - label) + rng.gauss(0, 0.55)
        if i in {4, 8, 12, 16}:
            label = 1 - label
        rows.append((str(signal), str(int(subgroup)), str(label)))
    data = Dataset(("signal", "shift_group", "label"), tuple(rows))
    parts = {
        "train": list(range(1, 73)),
        "validation": list(range(73, 109)),
        "test": list(range(109, 121)),
    }
    manifest = Manifest(canonical(data), SplitConfig(seed=seed), parts)
    failed = 73
    incorrect = inspect_prediction(
        data, "label", manifest, failed, Intervention(excluded_records=(5, 9, 13, 17))
    )
    correct = inspect_prediction(data, "label", manifest, 74)
    slices = analyze_errors(data, "label", manifest, min_support=6)
    return {
        "seed": seed,
        "injected_training_flips": 4,
        "predictions": [
            {
                "correct": case["prediction_correct"],
                "logit_residual": abs(
                    case["contribution"]["logit"]
                    - case["contribution"]["reconstructed_logit"]
                ),
                "neighbor_count": len(case["neighbors"]),
            }
            for case in (incorrect, correct)
        ],
        "intervention": {
            key: incorrect["intervention"][key]
            for key in ("status", "validation_accuracy_delta", "class_recall_delta")
        },
        "slices": slices["slices"][:5],
        "baseline_error_rate": slices["baseline_error_rate"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = perf_counter()
    trials = [run(seed) for seed in (19, 47)]
    args.output.write_text(
        json.dumps(
            {"trials": trials, "runtime_seconds": perf_counter() - start},
            allow_nan=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
