import argparse
import json
from pathlib import Path
from random import Random
from statistics import mean

from datagenome.experiments import Intervention, compare
from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.label_audit import audit_labels
from datagenome.modeling import ModelConfig
from datagenome.splits import Manifest, SplitConfig, split


def trial(seed: int) -> dict:
    rng = Random(seed)
    rows = []
    for i in range(600):
        y = i % 3
        rows.append((str(3 * y + rng.gauss(0, 0.75)), str(rng.gauss(0, 1)), str(y)))
    data = Dataset(("signal", "noise", "label"), tuple(rows))
    manifest = split(data, SplitConfig("stratified", seed=seed), "label")
    train = manifest.partitions["train"]
    flipped = set(rng.sample(train, round(0.1 * len(train))))
    corrupted = Dataset(
        data.columns,
        tuple(
            (x, z, str((int(y) + 1) % 3) if i in flipped else y)
            for i, (x, z, y) in enumerate(rows, 1)
        ),
    )
    corrupted_manifest = Manifest(
        canonical(corrupted), manifest.config, manifest.partitions
    )
    clean = audit_labels(data, "label", manifest)
    audit = audit_labels(corrupted, "label", corrupted_manifest)
    assert clean["status"] == audit["status"] == "evaluated"
    flagged = {item["record_id"] for item in audit["candidates"]}
    true = len(flagged & flipped)
    result = {
        "seed": seed,
        "training_records": len(train),
        "flipped_records": len(flipped),
        "true_positives": true,
        "false_positives": len(flagged - flipped),
        "false_negatives": len(flipped - flagged),
        "precision": true / len(flagged) if flagged else None,
        "recall": true / len(flipped),
        "clean_alerts": clean["candidate_count"],
        "validation_comparison": None,
    }
    if flagged:
        comparison = compare(
            corrupted,
            "label",
            corrupted_manifest,
            Intervention(excluded_records=tuple(sorted(flagged))),
            ModelConfig(seed=seed),
        )
        if comparison["status"] == "compared":
            result["validation_comparison"] = {
                "before": comparison["original"]["metrics"]["validation"]["accuracy"],
                "after": comparison["modified"]["metrics"]["validation"]["accuracy"],
                "delta": comparison["validation_differences"]["accuracy"],
                "held_out_evaluated": comparison["held_out_evaluated"],
            }
        else:
            result["validation_comparison"] = {"status": comparison["status"]}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    trials = [trial(seed) for seed in (11, 23, 37, 53, 71)]
    scored = [
        item["validation_comparison"]
        for item in trials
        if item["validation_comparison"] and "delta" in item["validation_comparison"]
    ]
    report = {
        "schema_version": "1.0",
        "trials": trials,
        "mean_validation_accuracy_delta": mean(item["delta"] for item in scored)
        if scored
        else None,
    }
    result = json.dumps(report, allow_nan=False, indent=2)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
