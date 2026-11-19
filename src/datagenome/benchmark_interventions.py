"""One frozen multi-arm comparison per disjoint evaluation block."""

from dataclasses import replace
from pathlib import Path
from random import Random
from typing import Any

from .benchmark_data import corrupt, public
from .holdouts import claim
from .identity import canonical, fingerprint
from .independent import create_json, final_metrics
from .ingestion import Dataset, DatasetError
from .label_audit import LabelAuditConfig, audit_labels
from .modeling import ModelConfig, classification_pipeline, metrics
from .splits import Manifest, SplitConfig
from .uncertainty import ResamplingConfig, metric_intervals
from .valuation import ValuationConfig, value_data


def study(seed: int, block: int, output: Path, protocol_hash: str) -> dict[str, Any]:
    clean = public("digits01")
    # Reserve the entire final pool before any diagnostic fitting. Every block
    # is disjoint across seeds; no final outcomes enter arm selection.
    per_class: dict[str, list[int]] = {}
    for i, row in enumerate(clean.rows, 1):
        per_class.setdefault(row[-1], []).append(i)
    rng = Random(901)
    train: list[int] = []
    validation: list[int] = []
    final_blocks: list[list[int]] = [[], [], []]
    for ids in per_class.values():
        rng.shuffle(ids)
        cut = len(ids) // 2
        development, final = ids[:cut], ids[cut:]
        train.extend(development[: len(development) * 2 // 3])
        validation.extend(development[len(development) * 2 // 3 :])
        for k in range(3):
            final_blocks[k].extend(final[k::3])
    if not 0 <= block < 3:
        raise DatasetError(
            "benchmark_block", "Only three prespecified evaluation blocks exist."
        )
    # Unused final blocks remain protected and are absent from this trial dataset.
    kept = sorted(train + validation + final_blocks[block])
    mapping = {old: new for new, old in enumerate(kept, 1)}
    clean = Dataset(clean.columns, tuple(clean.rows[i - 1] for i in kept))
    train = sorted(mapping[i] for i in train)
    validation = sorted(mapping[i] for i in validation)
    test = sorted(mapping[i] for i in final_blocks[block])
    manifest = Manifest(
        canonical(clean),
        SplitConfig(seed=seed),
        {"train": train, "validation": validation, "test": test},
    )
    changed = corrupt(clean, train, "uniform_labels", 0.1, seed)
    data = changed.data
    manifest_changed = replace(manifest, dataset_sha256=canonical(data))
    values = value_data(
        data,
        "label",
        manifest_changed,
        ValuationConfig(method="knn-shapley", seed=seed, seconds=120),
    )
    low = [
        r["record_id"]
        for r in sorted(values["records"], key=lambda r: (r["score"], r["record_id"]))
    ]
    high = [r["record_id"] for r in values["records"]]
    random_ids = train.copy()
    Random(seed).shuffle(random_ids)
    audit = audit_labels(data, "label", manifest_changed, LabelAuditConfig(folds=3))
    suspected = [r["record_id"] for r in audit["candidates"]]
    count = max(1, int(0.05 * len(train)))

    def select(order: list[int]) -> list[int]:
        counts = {
            y: sum(data.rows[i - 1][-1] == y for i in train)
            for y in {data.rows[i - 1][-1] for i in train}
        }
        caps = {y: max(0, int(n * 0.1)) for y, n in counts.items()}
        out = []
        for i in order:
            y = data.rows[i - 1][-1]
            if caps[y] and i not in out:
                caps[y] -= 1
                out.append(i)
            if len(out) == count:
                break
        return out

    arms: dict[str, dict[str, Any]] = {"original": {"removed": [], "oracle": False}}
    for name, order in (
        ("random", random_ids),
        ("lowest", low),
        ("highest", high),
        ("label_exclusion", suspected),
    ):
        removed = select(order)
        arms[name] = {
            "removed": removed,
            "oracle": False,
            "eligible": len(removed) == count,
        }
    seen = set()
    duplicates = []
    for i in train:
        row = data.rows[i - 1]
        if row in seen:
            duplicates.append(i)
        seen.add(row)
    duplicate_ids = select(duplicates)
    arms["duplicates"] = {
        "removed": duplicate_ids,
        "oracle": False,
        "eligible": len(duplicate_ids) == count,
    }
    arms["oracle_correction"] = {"removed": [], "oracle": True}
    arms["combined"] = {
        "removed": arms["lowest"]["removed"],
        "oracle": True,
        "eligible": arms["lowest"]["eligible"],
    }
    frozen = {
        "registry_protocol": protocol_hash,
        "seed": seed,
        "block": block,
        "dataset_sha256": canonical(data),
        "source_sha256": canonical(clean),
        "split_sha256": manifest.fingerprint,
        "model": {"model": "logistic-regression", "seed": seed, "imputation": "median"},
        "arms": arms,
        "matched_removal_count": count,
        "oracle_changed_count": len(changed.changed),
    }
    identifier = fingerprint(frozen)
    create_json(
        output / f"intervention-{seed}.protocol.json",
        {"plan": frozen, "protocol_sha256": identifier},
    )
    # Claim the clean feature signatures, so training label changes cannot reset reuse.
    claim(manifest, output / "ledger", identifier, clean, "label")
    features = list(range(len(data.columns) - 1))
    development_keys = {data.rows[i - 1][:-1] for i in train + validation}
    if any(data.rows[i - 1][:-1] in development_keys for i in test):
        raise DatasetError(
            "holdout_contamination", "Exact evaluation/development feature overlap."
        )
    outcomes: dict[str, Any] = {}
    predictions: dict[str, list[str]] = {}
    truth = [clean.rows[i - 1][-1] for i in test]
    for name, arm in arms.items():
        if arm.get("eligible", True) is False:
            outcomes[name] = {
                "status": "insufficient_candidates",
                "requested_count": count,
                "eligible_count": len(arm["removed"]),
            }
            continue
        source = clean if arm["oracle"] else data
        retained = [i for i in train if i not in arm["removed"]]
        pipeline, _, design, _, _ = classification_pipeline(
            source, features, retained, ModelConfig(seed=seed)
        )
        pipeline.fit(design(retained), [source.rows[i - 1][-1] for i in retained])
        scored = {}
        for partition, ids in (("validation", validation), ("independent", test)):
            pred = pipeline.predict(design(ids)).tolist()
            actual = [source.rows[i - 1][-1] for i in ids]
            scored[partition] = final_metrics(
                metrics(
                    actual,
                    pred,
                    pipeline.predict_proba(design(ids)),
                    pipeline.classes_.tolist(),
                )
            )
            if partition == "independent":
                predictions[name] = pred
        outcomes[name] = {
            "status": "scored",
            "training_records": len(retained),
            "removed_count": len(arm["removed"]),
            "oracle": arm["oracle"],
            "metrics": scored,
        }
    baseline = outcomes["original"]["metrics"]["independent"]
    for name, arm in outcomes.items():
        if arm["status"] != "scored" or name == "original":
            continue
        arm["paired_differences"] = {
            k: arm["metrics"]["independent"][k] - baseline[k]
            for k in ("accuracy", "balanced_accuracy", "macro_f1", "negative_log_loss")
        }
        arm["uncertainty"] = metric_intervals(
            truth,
            predictions["original"],
            predictions[name],
            [str(i) for i in test],
            ResamplingConfig(mode="independent", samples=199, seed=seed),
        )
    result = {
        "protocol_sha256": identifier,
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "evaluation_records": len(test),
        "held_out_scored": True,
        "arms": outcomes,
        "warning": "Record-disjoint within this run; unidentified writers may induce dependence. Bootstrap assumes IID rows and is conditional, not domain-level uncertainty. Oracle corrections use known synthetic truth and are not deployable label predictions.",
    }
    create_json(output / f"intervention-{seed}.result.json", result)
    return result
