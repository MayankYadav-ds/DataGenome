import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau, spearmanr

from datagenome.influence import LogisticObjective, estimate


def run():
    rows = []
    for seed in (19, 47):
        rng = np.random.default_rng(seed)
        raw = rng.normal(size=(114, 3))
        labels = (
            raw[:, 0] + 0.3 * raw[:, 1] + rng.normal(scale=0.4, size=114) > 0
        ).astype(float)
        for condition in ("well", "correlated"):
            data = raw.copy()
            y = labels.copy()
            if condition == "correlated":
                data[:, 2] = data[:, 0] + 1e-5 * data[:, 2]
                data[1], y[1] = data[0], y[0]
            design = np.column_stack((np.ones(len(data)), data))
            x, v = design[:80], design[80:]
            validation = LogisticObjective(v, y[80:], 0)
            for reg in (0.001, 0.1):
                obj = LogisticObjective(x, y[:80], reg)
                beta = obj.fit()
                full = validation.loss(beta)
                actual = []
                point = LogisticObjective(v[:1], y[80:81], 0)
                point_actual = []
                point_baseline = point.loss(beta)
                for i in range(len(x)):
                    keep = np.arange(len(x)) != i
                    retrained = LogisticObjective(x[keep], y[:80][keep], reg).fit()
                    actual.append(validation.loss(retrained) - full)
                    point_actual.append(point.loss(retrained) - point_baseline)
                actual = np.array(actual)
                for damp in (0, 0.01):
                    report = estimate(obj, beta, v, y[80:], damp)
                    approx = report["removal_loss_change"]
                    point_estimates = estimate(obj, beta, v[:1], y[80:81], damp)[
                        "removal_loss_change"
                    ]

                    def order(values):
                        return set(
                            np.argsort(-np.abs(values), kind="stable")[:8].tolist()
                        )

                    rows.append(
                        {
                            "seed": seed,
                            "scenario": condition,
                            "regularization": reg,
                            "damping": damp,
                            "prediction_spearman": float(
                                spearmanr(point_actual, point_estimates).statistic
                            ),
                            "prediction_mae": float(
                                np.mean(
                                    np.abs(np.asarray(point_actual) - point_estimates)
                                )
                            ),
                            "prediction_sign_agreement": float(
                                np.mean(
                                    np.sign(point_actual) == np.sign(point_estimates)
                                )
                            ),
                            "spearman": float(spearmanr(actual, approx).statistic),
                            "kendall": float(kendalltau(actual, approx).statistic),
                            "mae": float(np.mean(np.abs(actual - approx))),
                            "sign_agreement": float(
                                np.mean(np.sign(actual) == np.sign(approx))
                            ),
                            "top_8_overlap": len(order(actual) & order(approx)) / 8,
                            "hessian_condition": report["hessian_condition"],
                            "solver_residual": report["relative_solver_residual"],
                        }
                    )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(run(), allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
