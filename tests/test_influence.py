import numpy as np
import pytest
from scipy.optimize import minimize

from datagenome.influence import LogisticObjective, estimate


def test_influence_derivatives_and_retraining():
    x = np.array(
        [[1.0, -2.0], [1.0, -1.0], [1.0, 0.0], [1.0, 1.0], [1.0, 2.0], [1.0, 2.1]]
    )
    y = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    obj = LogisticObjective(x, y)
    beta = obj.fit()
    dx = np.eye(2) * 1e-5
    numeric_gradient = [(obj.loss(beta + h) - obj.loss(beta - h)) / (2e-5) for h in dx]
    numeric_hessian = np.column_stack(
        [(obj.gradient(beta + h) - obj.gradient(beta - h)) / (2e-5) for h in dx]
    )
    assert obj.gradient(beta) == pytest.approx(numeric_gradient, abs=1e-8)
    assert obj.hessian(beta) == pytest.approx(numeric_hessian, abs=1e-8)
    assert obj.hessian(beta) == pytest.approx(obj.hessian(beta).T)
    assert obj.hessian_vector(beta, np.array([1.0, 2.0])) == pytest.approx(
        obj.hessian(beta) @ [1.0, 2.0]
    )
    validation = LogisticObjective(x, y, 0)
    evidence = estimate(obj, beta, x, y)
    eps = 1e-4
    augmented = minimize(
        lambda b: obj.loss(b) + eps * (np.logaddexp(0, x[0] @ b) - y[0] * (x[0] @ b)),
        beta,
        jac=lambda b: obj.gradient(b) + eps * obj.per_row_gradient(b)[0],
        method="BFGS",
        options={"gtol": 1e-11},
    )
    actual = (validation.loss(augmented.x) - validation.loss(beta)) / eps
    assert actual == pytest.approx(evidence["upweight_loss_derivative"][0], abs=1e-4)
    retrained = LogisticObjective(x[1:], y[1:]).fit()
    change = validation.loss(retrained) - validation.loss(beta)
    assert np.sign(change) == np.sign(evidence["removal_loss_change"][0])
    assert evidence["relative_solver_residual"] < 1e-8


def test_influence_rejects_ill_conditioned_system():
    x = np.array([[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]])
    y = np.array([0.0, 1.0, 1.0])
    obj = LogisticObjective(x, y, 1e-12)
    beta = obj.fit()
    from datagenome.ingestion import DatasetError

    with pytest.raises(DatasetError, match="conditioning"):
        estimate(obj, beta, x, y)
