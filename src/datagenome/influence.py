from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import expit

from .ingestion import DatasetError

Array = NDArray[np.float64]


@dataclass(frozen=True)
class LogisticObjective:
    x: Array
    y: Array
    regularization: float = 0.1

    def loss(self, beta: Array) -> float:
        logits = self.x @ beta
        return float(
            np.mean(np.logaddexp(0, logits) - self.y * logits)
            + 0.5 * self.regularization * (beta @ beta)
        )

    def per_row_gradient(self, beta: Array) -> Array:
        return np.asarray((expit(self.x @ beta) - self.y)[:, None] * self.x)

    def gradient(self, beta: Array) -> Array:
        return np.asarray(
            self.per_row_gradient(beta).mean(axis=0) + self.regularization * beta,
            dtype=np.float64,
        )

    def hessian(self, beta: Array) -> Array:
        p = expit(self.x @ beta)
        return np.asarray(
            self.x.T @ ((p * (1 - p))[:, None] * self.x) / len(p)
            + self.regularization * np.eye(self.x.shape[1])
        )

    def hessian_vector(self, beta: Array, vector: Array) -> Array:
        p = expit(self.x @ beta)
        return np.asarray(
            self.x.T @ (p * (1 - p) * (self.x @ vector)) / len(p)
            + self.regularization * vector
        )

    def fit(self) -> Array:
        result = minimize(
            self.loss,
            np.zeros(self.x.shape[1]),
            jac=self.gradient,
            method="BFGS",
            options={"gtol": 1e-9, "maxiter": 200},
        )
        beta = np.asarray(result.x, dtype=np.float64)
        residual = float(np.linalg.norm(self.gradient(beta), ord=np.inf))
        if (
            not np.isfinite(residual)
            or residual > 1e-6
            or not np.all(np.isfinite(beta))
        ):
            raise DatasetError(
                "influence_fit_failed",
                "The logistic optimum failed the gradient tolerance.",
            )
        return beta


def estimate(
    objective: LogisticObjective,
    beta: Array,
    validation_x: Array,
    validation_y: Array,
    damping: float = 0,
) -> dict[str, Any]:
    if not 0 <= damping <= 1:
        raise DatasetError("invalid_damping", "Damping must be between zero and one.")
    gradients = objective.per_row_gradient(beta)
    hessian = objective.hessian(beta)
    operator = hessian + damping * np.eye(len(beta))
    condition = float(np.linalg.cond(operator))
    if not np.isfinite(condition) or condition > 1e8:
        raise DatasetError(
            "influence_conditioning",
            "The Hessian exceeds the supported conditioning limit.",
        )
    validation_gradient = np.mean(
        (expit(validation_x @ beta) - validation_y)[:, None] * validation_x, axis=0
    )
    solved = np.linalg.solve(operator, validation_gradient)
    residual = float(
        np.linalg.norm(operator @ solved - validation_gradient)
        / max(1.0, float(np.linalg.norm(validation_gradient)))
    )
    if not np.isfinite(residual) or residual > 1e-8:
        raise DatasetError(
            "influence_residual", "The Hessian solve failed its residual tolerance."
        )
    removal = ((gradients - gradients.mean(axis=0)) @ solved) / (len(gradients) - 1)
    return {
        "upweight_loss_derivative": -(gradients @ solved),
        "removal_loss_change": removal,
        "hessian_condition": condition,
        "relative_solver_residual": residual,
        "fit_gradient_inf": float(np.linalg.norm(objective.gradient(beta), ord=np.inf)),
        "damping": damping,
    }
