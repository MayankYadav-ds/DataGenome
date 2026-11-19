"""CPU-only research runner. Expensive suites are explicit and cooperatively bounded."""

import argparse
import json
import tracemalloc
import warnings
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

from .benchmark_data import SOURCES, public, synthetic
from .benchmark_protocol import SUITES, environment, freeze, publish
from .identity import canonical, fingerprint
from .ingestion import Dataset, DatasetError, parse_csv
from .splits import SplitConfig, split


def drift_study(seed: int, scenario: str, size: int) -> dict[str, Any]:
    import numpy as np

    from .drift import DriftConfig, detect_drift

    rng = np.random.default_rng(seed)
    a = rng.normal(size=(size, 2))
    b = rng.normal(size=(size, 2))
    if scenario == "small_mean":
        b[:, 0] += 0.25
    if scenario == "large_mean":
        b[:, 0] += 2
    if scenario == "variance":
        b[:, 0] *= 3
    if scenario == "dependence":
        a[:, 1] = a[:, 0]
        b[:, 1] = -b[:, 0]

    def table(x: Any, comparison: bool) -> Dataset:
        rows = []
        for i, r in enumerate(x):
            category = "A" if i % 2 else "B"
            if comparison and scenario == "category" and i % 4:
                category = "A"
            if comparison and scenario == "new_category" and i % 3 == 0:
                category = "C"
            value = (
                "" if comparison and scenario == "missing" and i % 3 == 0 else str(r[0])
            )
            y = int(r[0] > 0)
            if comparison and scenario == "label_frequency":
                y = int(i % 10 != 0)
            if comparison and scenario == "conditional":
                y = 1 - y
            rows.append((value, str(r[1]), category, str(y)))
        return Dataset(("x", "z", "category", "label"), tuple(rows))

    left, right = table(a, False), table(b, True)
    report = detect_drift(
        left,
        right,
        DriftConfig(iid=True, seed=seed, permutations=99, summary_only=False),
        target="label",
    )
    findings = report["findings"]
    return {
        "dataset_sha256": canonical(left),
        "comparison_sha256": canonical(right),
        "scenario": scenario,
        "rows_per_window": size,
        "effect_alerts": report["review_count"],
        "formal_rejections": sum(
            r.get("adjusted_p_value", 1) <= 0.05 for r in findings
        ),
        "findings": [
            {
                k: r.get(k)
                for k in (
                    "feature",
                    "kind",
                    "effect",
                    "threshold",
                    "p_value",
                    "adjusted_p_value",
                    "severity",
                    "status",
                )
            }
            for r in findings
        ],
        "multivariate": report["multivariate"],
        "warning": "Covariate/label marginal diagnostics cannot identify conditional concept changes. Unchanged samples are independently drawn, not reused copies. Multiple tests are Holm-adjusted jointly including MMD.",
    }


def performance(seed: int, n: int, p: int) -> dict[str, Any]:
    from .intelligence import analyze
    from .label_audit import LabelAuditConfig, audit_labels
    from .leakage import inspect_leakage
    from .orchestration import health, recommendations
    from .profiling import profile

    data = synthetic(seed, n, p)
    manifest = split(data, SplitConfig("stratified", seed=seed), "label")
    timings: dict[str, float] = {}

    def measure(name: str, action: Callable[[], Any]) -> Any:
        start = perf_counter()
        value = action()
        timings[name] = perf_counter() - start
        return value

    payload = (
        ",".join(data.columns) + "\n" + "\n".join(",".join(row) for row in data.rows)
    ).encode()
    measure("ingestion", lambda: parse_csv(payload, max_rows=10000, max_columns=64))
    prof = measure("profile", lambda: asdict(profile(data, "label")))
    measure("intelligence", lambda: analyze(data, "label"))
    leakage = measure(
        "leakage", lambda: [asdict(r) for r in inspect_leakage(data, "label", manifest)]
    )
    label = (
        measure(
            "labels",
            lambda: audit_labels(data, "label", manifest, LabelAuditConfig(folds=3)),
        )
        if n <= 5000
        else {"status": "unsupported"}
    )
    results = {
        "profile": {"result": prof},
        "leakage": {"result": {"leakage": leakage}},
        "labels": {"result": {"label_audit": label}},
    }
    score = measure("health", lambda: health(results))
    altered = measure(
        "health_weight_sensitivity", lambda: health(results, {"completeness": 10})
    )
    rec = measure(
        "recommendations",
        lambda: recommendations(results, set(manifest.partitions["train"])),
    )
    measure(
        "report_serialization",
        lambda: json.dumps({"health": score, "recommendations": rec}, allow_nan=False),
    )
    return {
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "rows": n,
        "features": p,
        "seconds_by_component": timings,
        "measured_component_total_seconds": sum(timings.values()),
        "health_score": score["score"],
        "health_coverage": score["coverage"],
        "health_weighted_score": altered["score"],
        "recommendations": len(rec),
        "all_require_review": all(r["required_review"] for r in rec),
        "warning": "Component total excludes models, valuation and experiments. Python allocation peak is recorded in trial envelope, excludes native allocations. Other suites time their own models; no process peak working-set measurement.",
    }


def investigator_study(seed: int) -> dict[str, Any]:
    from .error_slices import analyze_errors
    from .investigator import inspect_prediction

    data = synthetic(seed, 100, 3)
    manifest = split(data, SplitConfig("stratified", seed=seed), "label")
    outcomes = []
    for record in manifest.partitions["validation"][:3]:
        result = inspect_prediction(data, "label", manifest, record)
        c = result["contribution"]
        edges = result["evidence_graph"]["edges"]
        outcomes.append(
            {
                "correct": result["prediction_correct"],
                "logit_residual": abs(c["logit"] - c["reconstructed_logit"]),
                "neighbors": len(result["neighbors"]),
                "distances_ordered": all(
                    a["distance"] <= b["distance"]
                    for a, b in zip(result["neighbors"], result["neighbors"][1:])
                ),
                "edge_count": len(edges),
                "valuation_status": result["global_valuation_status"],
                "experimental_influence_available": result.get("prediction_influence")
                is not None,
            }
        )
    slices = analyze_errors(data, "label", manifest, min_support=5, summary_only=True)
    return {
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "predictions": outcomes,
        "error_slices": slices,
        "warning": "First three validation records fixed before inspection; they need not be errors. Relations describe measured neighbors or heuristic evidence, not causal sources.",
    }


def run(
    suite: str, output: Path, protocol: Path, seeds: tuple[int, ...]
) -> dict[str, Any]:
    from threadpoolctl import threadpool_limits

    from . import benchmark_studies as studies
    from .benchmark_interventions import study as interventions

    artifact = freeze(protocol, seeds)
    if output.exists() and (output / "results.json").exists():
        raise DatasetError(
            "benchmark_output_exists", "Results already exist; overwriting is refused."
        )
    output.mkdir(parents=True, exist_ok=True)
    env = environment()
    trials: list[dict[str, Any]] = []
    began = perf_counter()

    def emit(
        kind: str,
        name: str,
        seed: int,
        config: dict[str, Any],
        fn: Callable[[], dict[str, Any]],
    ) -> None:
        if len(trials) >= 600 or perf_counter() - began > 1800:
            raise DatasetError(
                "benchmark_budget",
                "Suite budget exhausted; completed trials remain in journal.",
            )
        start = perf_counter()
        tracemalloc.start()
        result: dict[str, Any] = {}
        status = "evaluated"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                result = fn()
            except DatasetError as error:
                status = "unsupported"
                result = {"reason": error.code}
            except Exception as error:
                # Keep failed cases without leaking paths or private exception strings.
                status = "failed"
                result = {"exception_type": type(error).__name__}
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        elapsed = perf_counter() - start
        if elapsed > 180:
            status = "budget_exceeded"
        identifier = f"{kind}-{name}-{seed}-{fingerprint(config)[:10]}"
        trial = {
            "experiment_id": identifier,
            "protocol_version": "phase9-v1",
            "protocol_sha256": artifact["protocol_sha256"],
            **env,
            "suite": kind,
            "dataset": name,
            "provenance": SOURCES.get(
                name,
                "Explicit synthetic generator; not observed demographic or temporal metadata",
            ),
            "seed": seed,
            "configuration": config,
            "model_configuration": artifact["plan"]["model"],
            "budget": artifact["plan"]["budgets"],
            "dataset_sha256": result.get("dataset_sha256"),
            "split_sha256": result.get("split_sha256"),
            "status": status,
            "seconds": elapsed,
            "python_peak_bytes": peak,
            "warnings": sorted({type(w.message).__name__ for w in caught}),
            "result": result,
        }
        trials.append(trial)
        # Append-only checkpoint survives interruptions and preserves unsuccessful cases.
        with (output / "journal.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(trial, allow_nan=False, sort_keys=True) + "\n")

    with threadpool_limits(limits=1):
        if suite == "smoke":
            emit(
                "valuation",
                "synthetic-game",
                seeds[0],
                {},
                lambda: studies.mathematical_reference(seeds[0]),
            )
            emit(
                "leakage",
                "synthetic",
                seeds[0],
                {"scenario": "target_copy"},
                lambda: studies.leakage(seeds[0], "target_copy"),
            )
            emit(
                "fairness",
                "synthetic",
                seeds[0],
                {},
                lambda: studies.fairness_study(seeds[0]),
            )
        for seed in seeds:
            if suite == "leakage":
                for kind in (
                    "clean",
                    "target_copy",
                    "target_encoding",
                    "cross_split",
                    "group_overlap",
                    "time_overlap",
                    "strong_predictor",
                    "cardinality",
                ):
                    emit(
                        suite,
                        "synthetic",
                        seed,
                        {"scenario": kind},
                        lambda: studies.leakage(seed, kind),
                    )
            if suite == "labels":
                for name in ("iris", "wine", "wdbc"):
                    for kind in ("uniform_labels", "class_labels", "feature_labels"):
                        for intensity in (0.0, 0.1, 0.2):
                            emit(
                                suite,
                                name,
                                seed,
                                {"kind": kind, "intensity": intensity},
                                lambda: studies.label_study(
                                    public(name), seed, kind, intensity
                                ),
                            )
            if suite == "valuation":
                emit(
                    suite,
                    "synthetic-game",
                    seed,
                    {},
                    lambda: studies.mathematical_reference(seed),
                )
                for model in ("logistic-regression", "decision-tree"):
                    for utility in ("accuracy", "negative_log_loss"):
                        emit(
                            suite,
                            "synthetic",
                            seed,
                            {"model": model, "utility": utility},
                            lambda: studies.valuation_study(seed, model, utility),
                        )
            if suite == "influence":
                for scenario in (
                    "regular",
                    "correlated",
                    "duplicates",
                    "separable",
                    "influential",
                ):
                    for regularization in (0.01, 0.1, 1.0):
                        for damping in (0.0, 0.01, 0.1):
                            emit(
                                suite,
                                "synthetic",
                                seed,
                                {
                                    "scenario": scenario,
                                    "regularization": regularization,
                                    "damping": damping,
                                },
                                lambda: studies.influence_study(
                                    seed, scenario, regularization, damping
                                ),
                            )
                emit(
                    "investigator",
                    "synthetic",
                    seed,
                    {},
                    lambda: investigator_study(seed),
                )
            if suite == "fairness":
                emit(suite, "synthetic", seed, {}, lambda: studies.fairness_study(seed))
            if suite == "drift":
                for scenario in (
                    "clean",
                    "small_mean",
                    "large_mean",
                    "variance",
                    "category",
                    "new_category",
                    "missing",
                    "dependence",
                    "label_frequency",
                    "conditional",
                ):
                    for size in (40, 200):
                        emit(
                            suite,
                            "synthetic",
                            seed,
                            {"scenario": scenario, "size": size},
                            lambda: drift_study(seed, scenario, size),
                        )
            if suite == "interventions":
                emit(
                    suite,
                    "digits01",
                    seed,
                    {"block": seeds.index(seed)},
                    lambda: interventions(
                        seed, seeds.index(seed), output, artifact["protocol_sha256"]
                    ),
                )
            if suite == "performance":
                for n in (100, 500, 1000, 5000, 10000):
                    for p in (3, 16):
                        emit(
                            suite,
                            "synthetic",
                            seed,
                            {"rows": n, "features": p},
                            lambda: performance(seed, n, p),
                        )
    result = {
        "schema_version": "1.0",
        "suite": suite,
        "protocol_sha256": artifact["protocol_sha256"],
        "environment": env,
        "seconds": perf_counter() - began,
        "trials": trials,
        "status": "partial"
        if any(t["status"] != "evaluated" for t in trials)
        else "completed",
    }
    publish(output, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute frozen, bounded CPU research protocols."
    )
    parser.add_argument("--suite", choices=SUITES, default="smoke")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--protocol", type=Path, default=Path("benchmarks/protocols/phase9-v1.json")
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 23, 37])
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.freeze_only:
            artifact = freeze(args.protocol, tuple(args.seeds))
            print(
                json.dumps(
                    {"status": "frozen", "protocol_sha256": artifact["protocol_sha256"]}
                )
            )
        else:
            result = run(args.suite, args.output, args.protocol, tuple(args.seeds))
            print(
                json.dumps(
                    {
                        "status": result["status"],
                        "trials": len(result["trials"]),
                        "suite": args.suite,
                    }
                )
            )
            return int(
                any(
                    t["status"] in {"failed", "budget_exceeded"}
                    for t in result["trials"]
                )
            )
    except (DatasetError, OSError) as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": error.code
                    if isinstance(error, DatasetError)
                    else "benchmark_io",
                }
            )
        )
        return 2
    return 0
