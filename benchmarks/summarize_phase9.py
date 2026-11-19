"""Publish aggregate artifacts and traceable web summaries from executed trials."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, stdev


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--destination", type=Path, default=Path("benchmarks/results/phase9")
    )
    args = parser.parse_args()
    suites = []
    all_trials = []
    index = {}
    for name in (
        "smoke",
        "leakage",
        "labels",
        "valuation",
        "influence",
        "fairness",
        "drift",
        "interventions",
        "performance",
    ):
        source = args.input / name / "results.json"
        if not source.exists():
            raise RuntimeError(f"Missing completed suite: {name}")
        result = json.loads(source.read_text(encoding="utf-8"))
        # Re-serialize public summaries only. Local ledger and per-record arm
        # selections are deliberately not copied into public research artifacts.
        destination = args.destination / name
        destination.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(result, allow_nan=False, sort_keys=True, indent=2) + "\n"
        (destination / "results.json").write_text(
            payload, encoding="utf-8", newline="\n"
        )
        for filename in ("summary.csv", "report.md"):
            (destination / filename).write_bytes(
                (source.parent / filename).read_bytes()
            )
        index[name] = {
            "sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "trials": len(result["trials"]),
            "protocol": result["protocol_sha256"],
        }
        suites.append(
            {
                "suite": name,
                "trials": len(result["trials"]),
                "evaluated": sum(t["status"] == "evaluated" for t in result["trials"]),
                "failed": sum(t["status"] != "evaluated" for t in result["trials"]),
                "seconds": round(result["seconds"], 3),
            }
        )
        all_trials += [{**t, "registry_suite": name} for t in result["trials"]]

    def selected(suite):
        return [
            t
            for t in all_trials
            if t["registry_suite"] == suite
            and t["suite"] == suite
            and t["status"] == "evaluated"
        ]

    leak = selected("leakage")
    positives = [
        t["result"]["expected_method_detected"]
        for t in leak
        if t["result"]["injected_violation_or_agreement"]
    ]
    controls = [t for t in leak if not t["result"]["injected_violation_or_agreement"]]
    observations = [
        {
            "topic": "Leakage",
            "artifact": "leakage",
            "finding": f"Expected structural/agreement methods detected {sum(positives)}/{len(positives)} injected scenarios. {sum(t['result']['heuristic_alerts'] > 0 for t in controls)}/{len(controls)} legitimate/control scenarios produced heuristic alerts; {sum(t['result']['confirmed_alerts'] > 0 for t in controls)} produced confirmed split violations. These heterogeneous scenario counts are not pooled feature-level precision.",
        }
    ]
    label_rows = defaultdict(list)
    for t in selected("labels"):
        c = t["result"]["corruption"]
        for method, metrics in t["result"]["methods"].items():
            label_rows[(t["dataset"], c["kind"], c["intensity"], method)].append(
                metrics
            )
    table = [
        "# Executed Phase 9 summaries",
        "",
        "All individual runs, warnings and unsuccessful cases are retained in suite JSON artifacts. Repeated seeds and duplicated clean controls are not independent domains.",
        "",
        "## Public-data injected-label benchmark",
        "",
        "AP is undefined for clean controls. Means below are descriptive across three seeds on each dataset/condition. No pooled cross-domain superiority test.",
        "",
        "| Dataset | Noise | Rate | Method | AP mean | FPR mean | Precision mean | Recall mean |",
        "|---|---|---|---|---|---|---|---|",
    ]

    def avg(rows, key):
        values = [r[key] for r in rows if r.get(key) is not None]
        return f"{mean(values):.4f}" if values else "undefined"

    for key, rows in sorted(label_rows.items()):
        table.append(
            "| "
            + " | ".join(map(str, key))
            + " | "
            + " | ".join(
                avg(rows, k)
                for k in (
                    "average_precision",
                    "false_positive_rate",
                    "precision",
                    "recall",
                )
            )
            + " |"
        )
    dg = [
        t["result"]["methods"]["datagenome"]
        for t in selected("labels")
        if t["result"]["corruption"]["intensity"] > 0
    ]
    clean = [
        t["result"]["methods"]["datagenome"]["false_positive_rate"]
        for t in selected("labels")
        if t["result"]["corruption"]["intensity"] == 0
    ]
    observations.append(
        {
            "topic": "Label audit",
            "artifact": "labels",
            "finding": f"DataGenome AP across nonzero-corruption conditions ranged {min(r['average_precision'] for r in dg):.4f}–{max(r['average_precision'] for r in dg):.4f}. Clean-control false-positive rates ranged {min(clean):.4f}–{max(clean):.4f}. Random, OOF disagreement, low observed-label probability and neighborhood controls are retained per condition. No natural-label correctness claim.",
        }
    )
    values = selected("valuation")
    refs = [t["result"] for t in values if "shapley_max_error" in t["result"]]
    mc = defaultdict(list)
    for t in values:
        for name, r in t["result"].get("comparisons_to_shapley", {}).items():
            if name.startswith("mc-shapley"):
                mc[(t["result"]["utility"], name)].append(r["mean_absolute_error"])
    observations.append(
        {
            "topic": "Valuation",
            "artifact": "valuation",
            "finding": f"Permutation-reference maximum Shapley error: {max(r['shapley_max_error'] for r in refs):.3g}. MC absolute-error ranges by separate utility/budget: "
            + "; ".join(
                f"{k[0]} / {k[1]}: {min(v):.5g}–{max(v):.5g}"
                for k, v in sorted(mc.items())
            )
            + ". Six-player synthetic games only; other methods estimate different quantities. Cross-domain ranking stability remains unestablished.",
        }
    )
    inf = selected("influence")
    ranks = [
        t["result"]["comparison"]["spearman"]
        for t in inf
        if t["result"]["comparison"]["spearman"] is not None
    ]
    observations.append(
        {
            "topic": "Influence approximation",
            "artifact": "influence",
            "finding": f"{len(inf)} evaluated configurations; deletion-loss rank correlation ranged {min(ranks):.4f}–{max(ranks):.4f}. Maximum finite-difference gradient/Hessian errors: {max(t['result']['gradient_max_error'] for t in inf):.3g}/{max(t['result']['hessian_max_error'] for t in inf):.3g}. This validates a bounded binary regularized objective, not arbitrary models or causation.",
        }
    )
    fair = selected("fairness")
    exact = all(
        r["selection"] == r["reference_selection"]
        and r["tpr"] == r["reference_tpr"]
        and r["fpr"] == r["reference_fpr"]
        for t in fair
        for r in t["result"]["reference_fixtures"]
    )
    observations.append(
        {
            "topic": "Fairness",
            "artifact": "fairness",
            "finding": f"Independent selection/TPR/FPR count fixtures agree: {exact}. Synthetic audit and planted-proxy screens only; predictive proxy verification and dependence-aware subgroup intervention uncertainty remain NOT RUN.",
        }
    )
    drift = selected("drift")
    drift_groups = defaultdict(list)
    for t in drift:
        r = t["result"]
        drift_groups[(r["scenario"], r["rows_per_window"])].append(r)
    table += [
        "",
        "## Drift sensitivity and false alerts",
        "",
        "Three prespecified seeds per condition; effect screens and formal IID inference are distinct. Small counts do not establish population sensitivity or false-positive calibration.",
        "",
        "| Scenario | Rows/window | Trials | Any effect alert | Any Holm rejection including MMD |",
        "|---|---|---|---|---|",
    ]
    for (scenario, size), rows in sorted(drift_groups.items()):
        effect = sum(r["effect_alerts"] > 0 for r in rows)
        formal = sum(
            r["formal_rejections"] > 0
            or r["multivariate"].get("adjusted_p_value", 1) <= 0.05
            for r in rows
        )
        table.append(f"| {scenario} | {size} | {len(rows)} | {effect} | {formal} |")
    null = [t for t in drift if t["result"]["scenario"] == "clean"]
    observations.append(
        {
            "topic": "Drift",
            "artifact": "drift",
            "finding": f"{sum(t['result']['formal_rejections'] > 0 or t['result']['multivariate'].get('adjusted_p_value', 1) <= 0.05 for t in null)}/{len(null)} independently sampled null trials had a Holm-adjusted formal rejection; {sum(t['result']['effect_alerts'] > 0 for t in null)}/{len(null)} had descriptive effect alerts. Conditional outcome changes are not identified from covariate drift alone. Only six null trials: insufficient power to calibrate a population false-positive rate.",
        }
    )
    changes = []
    eligible = Counter()
    table += [
        "",
        "## Prespecified record-disjoint Digits interventions",
        "",
        "Oracle arms use known injected truth, not model-predicted replacement labels. Writer dependence is unknown; bootstrap intervals are conditional on IID rows. All removals target the same prespecified count; insufficient candidate arms are unavailable.",
        "",
        "| Seed | Arm | Status | Independent accuracy | Paired accuracy delta | 95% paired bootstrap |",
        "|---|---|---|---|---|---|",
    ]
    for t in selected("interventions"):
        for name, arm in t["result"]["arms"].items():
            eligible[arm["status"]] += 1
            delta = arm.get("paired_differences", {}).get("accuracy")
            if delta is not None:
                changes.append(delta)
            accuracy = arm.get("metrics", {}).get("independent", {}).get("accuracy")
            interval = (
                arm.get("uncertainty", {}).get("accuracy", {}).get("percentile_95")
            )
            table.append(
                f"| {t['seed']} | {name} | {arm['status']} | {accuracy} | {delta} | {interval} |"
            )
    observations.append(
        {
            "topic": "Independent intervention outcomes",
            "artifact": "interventions",
            "finding": f"Prespecified record-disjoint Digits blocks: {len(selected('interventions'))}. Scored arms: {eligible['scored']}; insufficient candidate arms: {eligible['insufficient_candidates']}. Relative to baseline, {sum(d > 0 for d in changes)} improved, {sum(d == 0 for d in changes)} were unchanged and {sum(d < 0 for d in changes)} degraded in accuracy. Deltas ranged {min(changes):.4f}–{max(changes):.4f}. Includes explicit oracle controls; no outcome-based arm selection.",
        }
    )
    perf = selected("performance")
    observations.append(
        {
            "topic": "Computational limits",
            "artifact": "performance",
            "finding": f"Measured {len(perf)} profiling/diagnostic configurations, 100–10,000 rows with 3/16 features. Per-trial runtime ranged {min(t['seconds'] for t in perf):.3f}–{max(t['seconds'] for t in perf):.3f} s; peak traced Python allocations reached {max(t['python_peak_bytes'] for t in perf) / 1048576:.2f} MiB. Native allocations and process peak working set are NOT measured. Exponential games are restricted to six players.",
        }
    )
    table += [
        "",
        "## Runtime distribution",
        "",
        "| Suite | Trials | Non-evaluated | Mean s | Median s | SD s | Max Python MiB |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in suites:
        rows = [t for t in all_trials if t["registry_suite"] == s["suite"]]
        seconds = [t["seconds"] for t in rows]
        if seconds:
            table.append(
                f"| {s['suite']} | {len(rows)} | {sum(t['status'] != 'evaluated' for t in rows)} | {mean(seconds):.4f} | {median(seconds):.4f} | {stdev(seconds) if len(seconds) > 1 else 0:.4f} | {max(t['python_peak_bytes'] for t in rows) / 1048576:.2f} |"
            )
    (args.destination / "summary.md").write_text(
        "\n".join(table) + "\n", encoding="utf-8"
    )
    (args.destination / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "protocol_sha256": all_trials[-1]["protocol_sha256"],
        "source_commit": all_trials[-1]["git_commit"],
        "scope": "Prespecified CPU-only research. Public Iris/Wine/WDBC label experiments are exploratory; final Digits blocks are record-disjoint within this execution. Other scientific studies are explicitly synthetic.",
        "suites": suites,
        "observations": observations,
        "limitations": [
            "Not peer reviewed; no superiority, deployment or universal fairness claim.",
            "Seeds on one dataset are not independent domains. Small samples and unavailable writer IDs limit inference.",
            "Earlier HAR evaluation remains compromised/descriptive; it is never relabeled independent.",
            "OpenDataVal execution, Confident Learning, label-horizon purging and predictive proxy verification are NOT RUN.",
            "No natural label-error ground truth, new public categorical/temporal/group benchmark, or unconditional intervention benefit is established.",
        ],
    }
    Path("frontend/public/research-results.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    Path("research/results.md").write_text(
        "# Phase 9 observed evidence\n\n"
        + "\n\n".join(
            f"## {o['topic']}\n\n{o['finding']}\n\n[Individual trials](../benchmarks/results/phase9/{o['artifact']}/results.json)"
            for o in observations
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
