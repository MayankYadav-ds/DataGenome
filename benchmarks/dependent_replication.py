"""One-use frozen scoring with cross-seed final-partition eligibility checks."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from random import Random

from public_grouped import load as load_har
from public_temporal import load as load_occupancy
from threadpoolctl import threadpool_limits

from datagenome.identity import canonical, fingerprint
from datagenome.modeling import ModelConfig, classification_pipeline
from datagenome.splits import SplitConfig, split
from datagenome.uncertainty import ResamplingConfig, metric_intervals


def load(kind, archive):
    return load_har(archive) if kind == "har" else load_occupancy(archive)[0]


def freeze(kind, archive, folder):
    data = load(kind, archive)
    manifest = split(
        data,
        SplitConfig("group", (0.5, 0.4, 0.1), 19, group="subject")
        if kind == "har"
        else SplitConfig("chronological", seed=19, time="date"),
        data.columns[-1],
    )
    previously_scored = set()
    for prior_seed in (19, 47):
        previous = split(
            data,
            SplitConfig("group", (0.5, 0.4, 0.1), prior_seed, group="subject")
            if kind == "har"
            else SplitConfig("chronological", seed=prior_seed, time="date"),
            data.columns[-1],
        )
        previously_scored.update(previous.partitions["validation"])
    overlap = len(previously_scored & set(manifest.partitions["test"]))
    removed = sorted(
        Random(19).sample(
            manifest.partitions["train"], len(manifest.partitions["train"]) // 20
        )
    )
    protocol = {
        "schema_version": 1,
        "dataset": kind,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "canonical_sha256": canonical(data),
        "manifest": asdict(manifest),
        "model": asdict(ModelConfig(seed=19)),
        "features": list(range(6 if kind == "har" else 5)),
        "removal_ids": removed,
        "evaluation": "Phase 7 seed-19 test partition; cross-seed prior-validation eligibility checked",
        "previously_scored_validation_overlap_records": overlap,
        "outcomes": ["accuracy", "balanced_accuracy", "macro_f1"],
        "subgroups": None,
        "resampling": asdict(
            ResamplingConfig(
                mode="group" if kind == "har" else "temporal",
                seed=19,
                samples=199,
                block_length=12,
            )
        ),
        "ineligible_arms": {
            "low_value_removal": "No frozen validated dependence-aware valuation selection policy.",
            "label_audit_exclusion": "No frozen validated dependence-aware exclusion policy.",
            "other_improvement": "No evidence-based eligible intervention prespecified.",
        },
    }
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (kind + ".protocol.json")).open("x", encoding="utf-8") as out:
        json.dump(
            {"protocol": protocol, "sha256": fingerprint(protocol)}, out, indent=2
        )


def score(kind, archive, folder):
    envelope = json.loads(
        (folder / (kind + ".protocol.json")).read_text(encoding="utf-8")
    )
    protocol = envelope["protocol"]
    if (
        fingerprint(protocol) != envelope["sha256"]
        or hashlib.sha256(archive.read_bytes()).hexdigest()
        != protocol["archive_sha256"]
    ):
        raise ValueError("Frozen protocol or archive changed")
    data = load(kind, archive)
    if canonical(data) != protocol["canonical_sha256"]:
        raise ValueError("Dataset changed")
    if protocol.get("previously_scored_validation_overlap_records") != 0:
        raise ValueError(
            "Independent scoring blocked: prior validation overlap or missing eligibility evidence"
        )
    # Claim before fitting or scoring. A failed attempt remains consumed.
    with (folder / (kind + ".consumed")).open("x", encoding="utf-8") as claim:
        claim.write(envelope["sha256"])
    partitions = protocol["manifest"]["partitions"]
    train, test = partitions["train"], partitions["test"]
    predictions = []
    for ids in (train, [i for i in train if i not in set(protocol["removal_ids"])]):
        pipeline, _, design, _, _ = classification_pipeline(
            data, protocol["features"], ids, ModelConfig(**protocol["model"])
        )
        with threadpool_limits(limits=1):
            pipeline.fit(design(ids), [data.rows[i - 1][-1] for i in ids])
            predictions.append(pipeline.predict(design(test)).tolist())
    actual = [data.rows[i - 1][-1] for i in test]
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

    scores = [
        {
            "accuracy": float(accuracy_score(actual, p)),
            "balanced_accuracy": float(balanced_accuracy_score(actual, p)),
            "macro_f1": float(f1_score(actual, p, average="macro", zero_division=0)),
        }
        for p in predictions
    ]
    units = [data.rows[i - 1][-2] for i in test]
    result = {
        "dataset": kind,
        "protocol_sha256": envelope["sha256"],
        "rows": len(data.rows),
        "evaluation_records": len(test),
        "baseline": scores[0],
        "matched_random_5pct_removal": scores[1],
        "uncertainty": metric_intervals(
            actual, *predictions, units, ResamplingConfig(**protocol["resampling"])
        ),
        "ineligible_arms": protocol["ineligible_arms"],
        "limitations": [
            "One frozen partition per dataset; no claim of universal improvement.",
            "HAR windows depend on subjects; Occupancy blocks assume adequate temporal dependence coverage.",
            "No sensitive subgroup definitions were supplied; subgroup outcomes are unavailable.",
            "This local ledger cannot prevent deliberate reuse in a different directory.",
        ],
    }
    with (folder / (kind + ".results.json")).open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "score"])
    parser.add_argument("--dataset", choices=["har", "occupancy"], required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args()
    (freeze if args.action == "freeze" else score)(
        args.dataset, args.archive, args.folder
    )


if __name__ == "__main__":
    main()
