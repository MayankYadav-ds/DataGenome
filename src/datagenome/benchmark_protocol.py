"""Prespecification and result registry; aggregate reports contain no raw records."""

import csv
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .benchmark_data import SOURCES, identities
from .identity import fingerprint
from .independent import create_json
from .ingestion import DatasetError

SUITES = (
    "smoke",
    "leakage",
    "labels",
    "valuation",
    "influence",
    "fairness",
    "drift",
    "interventions",
    "performance",
)


def definition(seeds: tuple[int, ...] = (11, 23, 37)) -> dict[str, Any]:
    if (
        not 1 <= len(seeds) <= 5
        or len(set(seeds)) != len(seeds)
        or any(not 0 <= s < 2**32 for s in seeds)
    ):
        raise DatasetError("benchmark_seed", "Use 1–5 distinct valid seeds.")
    return {
        "protocol_version": "phase9-v1",
        "seeds": list(seeds),
        "datasets": identities(),
        "provenance": SOURCES,
        "license": "UCI source pages: CC BY 4.0; bundled sklearn copies; derived numeric CSV representation",
        "model": {
            "model": "logistic-regression",
            "imputation": "median",
            "max_depth": 8,
            "trees": 32,
        },
        "intensities": [0.0, 0.1, 0.2],
        "label_folds": 3,
        "label_thresholds": {"alternative_probability": 0.6, "probability_gap": 0.3},
        "univariate": {
            "folds": 3,
            "max_features": 16,
            "minimum_score": 0.9,
            "minimum_lift": 0.2,
        },
        "valuation": {
            "train": 6,
            "validation": 12,
            "mc_permutations": [8, 32, 128],
            "max_evaluations": 256,
            "seconds": 120,
        },
        "influence": {
            "regularization": [0.01, 0.1, 1.0],
            "damping": [0.0, 0.01, 0.1],
            "gradient_atol": 1e-5,
            "hessian_atol": 1e-5,
            "solve_rtol": 1e-8,
        },
        "independent": {
            "dataset": "digits01",
            "partition_seed": 901,
            "evaluation_blocks": 3,
            "training_label_flip_fraction": 0.1,
            "removal_fraction": 0.05,
            "selection": "fixed rules; no outcome-based arm selection",
            "legacy_datasets": "iris, wine, WDBC, HAR and Occupancy are descriptive only; prior outcomes exist",
            "uncertainty": "paired row bootstrap, conditional on IID assumption; writer identifiers unavailable",
        },
        "budgets": {
            "max_trial_seconds": 180,
            "max_suite_seconds": 1800,
            "max_rows": 10000,
            "max_features": 32,
            "exact_players": 6,
            "max_trials": 600,
        },
        "interpretation": "Exploratory diagnostics; prespecified record-disjoint digits evaluation; no domain-level replication or guarantee of improvement.",
    }


def freeze(path: Path, seeds: tuple[int, ...]) -> dict[str, Any]:
    plan = definition(seeds)
    artifact = {"plan": plan, "protocol_sha256": fingerprint(plan)}
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != artifact:
            raise DatasetError(
                "benchmark_protocol_changed",
                "Frozen protocol differs from requested configuration.",
            )
    else:
        create_json(path, artifact)
    return artifact


def environment() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    return {
        "git_commit": commit,
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "dependencies": {
            n: version(n) for n in ("datagenome", "numpy", "scipy", "scikit-learn")
        },
    }


def publish(folder: Path, result: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    create_json(folder / "results.json", result)
    with (folder / "summary.csv").open("x", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["experiment", "suite", "dataset", "seed", "status", "seconds"])
        for trial in result["trials"]:
            writer.writerow(
                [
                    trial[k]
                    for k in (
                        "experiment_id",
                        "suite",
                        "dataset",
                        "seed",
                        "status",
                        "seconds",
                    )
                ]
            )
    lines = [
        "# Executed research benchmark",
        "",
        f"Protocol: `{result['protocol_sha256']}`",
        "",
        "| Experiment | Status | Seconds |",
        "|---|---|---|",
    ]
    lines += [
        f"| {t['experiment_id']} | {t['status']} | {t['seconds']:.4f} |"
        for t in result["trials"]
    ]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
