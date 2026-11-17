import argparse
import json
from pathlib import Path
from time import perf_counter

from valuation import fixture, ranking

from datagenome.modeling import ModelConfig
from datagenome.valuation import ValuationConfig, value_data

BUDGETS = (16, 32, 64, 128, 256)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = perf_counter()
    results = []
    for case in ("clean", "duplicates"):
        for seed in (19, 47):
            data, manifest, _ = fixture(case, seed, 6)
            for metric in ("accuracy", "negative_log_loss"):
                model = ModelConfig(seed=seed)
                base = value_data(
                    data,
                    "label",
                    manifest,
                    ValuationConfig(method="shapley", metric=metric, seed=seed),
                    model=model,
                )
                for budget in BUDGETS:
                    sampled = value_data(
                        data,
                        "label",
                        manifest,
                        ValuationConfig(
                            method="mc-shapley",
                            metric=metric,
                            seed=seed,
                            permutations=budget,
                        ),
                        model=model,
                    )
                    agreement = ranking(sampled["records"], base["records"], 2)
                    bottom = {row["record_id"] for row in sampled["records"][-2:]}
                    exact_bottom = {row["record_id"] for row in base["records"][-2:]}
                    results.append(
                        {
                            "scenario": case,
                            "seed": seed,
                            "metric": metric,
                            "permutations": budget,
                            **agreement,
                            "bottom_k_overlap": len(bottom & exact_bottom) / 2,
                            "runtime_seconds": sampled["elapsed_seconds"],
                            "utility_evaluations": sampled["utility_evaluations"],
                            "exact_ties": len(base["records"])
                            - len({round(row["score"], 10) for row in base["records"]}),
                        }
                    )
    args.output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "seconds": perf_counter() - started,
                "trials": results,
            },
            allow_nan=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
