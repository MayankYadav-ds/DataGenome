import argparse
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .ingestion import DEFAULT_MAX_BYTES, DatasetError, load_csv, validate_filename
from .profiling import profile

logger = logging.getLogger(__name__)


def main() -> int:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        from .benchmark import main as benchmark_main

        return benchmark_main(sys.argv[2:])
    parser = argparse.ArgumentParser(prog="datagenome")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    descriptions = {
        "profile": "Profile a local CSV dataset.",
        "diagnose": "Produce expanded diagnostics and anomaly scores.",
        "value-data": "Value training records on the validation partition.",
        "compare-removal": "Compare class-capped training removal strategies.",
        "investigate": "Inspect a validation prediction.",
        "audit-fairness": "Audit binary classification by supplied attributes.",
        "fairness-comparison": "Check subgroup changes after explicit training exclusions.",
        "detect-proxies": "Screen training features for sensitive-attribute associations.",
        "analyze-errors": "Find exploratory validation error slices.",
        "audit-labels": "Rank potentially unreliable training labels for review.",
        "detect-leakage": "Audit a reproducible split for leakage.",
        "detect-anomalies": "Calculate independent anomaly scores.",
        "split": "Generate a verified split manifest.",
        "train": "Fit and score training and validation partitions.",
        "evaluate": "Fit the selected baseline and evaluate the held-out test.",
        "experiment": "Compare an explicit training intervention on validation.",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description)
        command.add_argument("dataset", type=Path)
        command.add_argument("--target")
        command.add_argument("--output", type=Path)
        command.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
        if name == "profile":
            continue
        command.add_argument("--max-rows", type=int, default=20000)
        command.add_argument("--max-columns", type=int, default=128)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument(
            "--strategy",
            choices=("random", "stratified", "group", "chronological"),
            default="random",
        )
        command.add_argument("--ratios", type=float, nargs=3, default=(0.6, 0.2, 0.2))
        command.add_argument(
            "--manifest", type=Path, help="Reuse a saved split report."
        )
        if name in {"audit-fairness", "fairness-comparison", "detect-proxies"}:
            command.add_argument("--sensitive-column", action="append", default=[])
            command.add_argument("--positive-label")
            command.add_argument("--minimum-support", type=int, default=20)
            command.add_argument(
                "--privacy-mode",
                choices=("detailed", "redacted", "summary"),
                default="summary",
            )
        if name in {"investigate", "analyze-errors"}:
            command.add_argument(
                "--record-id", type=int, help="One-based validation record ID."
            )
            command.add_argument("--minimum-support", type=int, default=10)
            command.add_argument(
                "--privacy-mode",
                choices=("detailed", "redacted", "summary"),
                default="detailed",
            )
        command.add_argument("--max-depth", type=int, default=8)
        command.add_argument("--trees", type=int, default=32)
        command.add_argument("--association-threshold", type=float, default=0.9)
        command.add_argument(
            "--univariate",
            action="store_true",
            help="Score individual features in training-only folds.",
        )
        command.add_argument("--univariate-folds", type=int, default=3)
        command.add_argument("--univariate-max-features", type=int, default=16)
        command.add_argument("--univariate-minimum-score", type=float, default=0.90)
        command.add_argument("--univariate-minimum-lift", type=float, default=0.20)
        if name in {"value-data", "compare-removal"}:
            command.add_argument(
                "--method",
                choices=("loo", "shapley", "mc-shapley", "knn-shapley", "banzhaf"),
                default="loo",
            )
            command.add_argument(
                "--utility",
                choices=(
                    "accuracy",
                    "balanced_accuracy",
                    "macro_f1",
                    "negative_log_loss",
                    "class_recall",
                ),
                default="accuracy",
            )
            command.add_argument("--utility-class")
            command.add_argument("--max-evaluations", type=int, default=256)
            command.add_argument("--permutations", type=int, default=16)
            command.add_argument("--k", type=int, default=3)
            command.add_argument("--valuation-seconds", type=float, default=30)
            command.add_argument("--removal-fraction", type=float, default=0.1)
        command.add_argument("--candidate-limit", type=int, default=10000)
        command.add_argument("--max-anomaly-rows", type=int, default=2000)
        command.add_argument("--iqr-multiplier", type=float, default=1.5)
        command.add_argument("--z-threshold", type=float, default=3.5)
        command.add_argument("--contamination", type=float, default=0.05)
        command.add_argument("--missing-warning", type=float, default=0.05)
        command.add_argument("--missing-high", type=float, default=0.30)
        command.add_argument("--group")
        command.add_argument("--time")
        command.add_argument("--audit-group")
        command.add_argument("--audit-time")
        command.add_argument("--cutoff")
        command.add_argument("--unavailable", action="append", default=[])
        command.add_argument(
            "--model",
            choices=("dummy", "logistic-regression", "decision-tree", "random-forest"),
            default="logistic-regression",
        )
        command.add_argument(
            "--intervention",
            choices=("remove-duplicates",),
            action="append",
            default=[],
        )
        command.add_argument("--constant-feature", action="append", default=[])
        command.add_argument("--suspected-feature", action="append", default=[])
        command.add_argument("--exclude-record", type=int, action="append", default=[])
        command.add_argument(
            "--imputation", choices=("median", "mean", "most_frequent")
        )
    args = parser.parse_args()
    if args.max_bytes < 1 or (
        args.command != "profile"
        and (not 1 <= args.max_rows <= 20000 or not 1 <= args.max_columns <= 128)
    ):
        parser.error("Resource limits must be positive and within supported bounds.")
    try:
        validate_filename(args.dataset.name)
        with args.dataset.open("rb") as source:
            if args.command == "profile":
                result = asdict(
                    profile(
                        load_csv(source, args.dataset.name, args.max_bytes), args.target
                    )
                )
            else:
                from .options import Options
                from .splits import restore

                manifest = None
                if args.manifest:
                    with args.manifest.open("rb") as manifest_file:
                        raw = manifest_file.read(DEFAULT_MAX_BYTES + 1)
                    if len(raw) > DEFAULT_MAX_BYTES:
                        raise DatasetError(
                            "invalid_manifest", "Split report exceeds the byte limit."
                        )
                    try:
                        manifest = restore(json.loads(raw))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise DatasetError(
                            "invalid_manifest", "Split report must be JSON."
                        ) from None

                options = Options(
                    args.target,
                    args.strategy,
                    args.seed,
                    args.group,
                    args.time,
                    tuple(args.ratios),
                    args.audit_group,
                    args.audit_time,
                    args.cutoff,
                    tuple(args.unavailable),
                    args.model,
                    tuple(args.intervention),
                    tuple(args.constant_feature),
                    tuple(args.suspected_feature),
                    tuple(args.exclude_record),
                    args.imputation,
                    manifest,
                    valuation_method=getattr(args, "method", "loo"),
                    utility=getattr(args, "utility", "accuracy"),
                    utility_class=getattr(args, "utility_class", None),
                    max_evaluations=getattr(args, "max_evaluations", 256),
                    permutations=getattr(args, "permutations", 16),
                    k=getattr(args, "k", 3),
                    valuation_seconds=getattr(args, "valuation_seconds", 30),
                    removal_fraction=getattr(args, "removal_fraction", 0.1),
                    record_id=getattr(args, "record_id", None),
                    minimum_support=getattr(args, "minimum_support", 10),
                    privacy_mode=getattr(args, "privacy_mode", "detailed"),
                    audit_attributes=tuple(getattr(args, "sensitive_column", [])),
                    positive_label=getattr(args, "positive_label", None),
                    candidate_limit=args.candidate_limit,
                    association_threshold=args.association_threshold,
                    univariate=args.univariate,
                    univariate_folds=args.univariate_folds,
                    univariate_max_features=args.univariate_max_features,
                    univariate_minimum_score=args.univariate_minimum_score,
                    univariate_minimum_lift=args.univariate_minimum_lift,
                    max_anomaly_rows=args.max_anomaly_rows,
                    iqr_multiplier=args.iqr_multiplier,
                    z_threshold=args.z_threshold,
                    contamination=args.contamination,
                    missing_warning=args.missing_warning,
                    missing_high=args.missing_high,
                    max_depth=args.max_depth,
                    trees=args.trees,
                )
                result = options.run(
                    args.command,
                    source.read(args.max_bytes + 1),
                    args.max_bytes,
                    args.max_rows,
                    args.max_columns,
                )
        report = json.dumps(result, indent=2, allow_nan=False)
        if args.output:
            if args.output.exists() and os.path.samefile(args.output, args.dataset):
                raise DatasetError(
                    "invalid_output", "Output must differ from the input CSV."
                )
            args.output.write_text(report + "\n", encoding="utf-8")
        else:
            print(report)
    except DatasetError as error:
        logger.error(
            json.dumps(
                {"event": "analysis_failed", "code": error.code, "message": str(error)}
            )
        )
        return 2
    except (OSError, OverflowError):
        logger.error(
            json.dumps(
                {
                    "event": "analysis_failed",
                    "code": "io_error",
                    "message": "Could not read the input or write the report.",
                }
            )
        )
        return 2
    return 0
