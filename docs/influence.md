# Experimental logistic influence

The research engine fits a binary model with objective
`F(beta) = mean(log(1 + exp(x beta)) - y x beta) + lambda ||beta||^2 / 2`.
The intercept is a column of ones and receives the same L2 penalty. There are
no fit-time sample weights. This custom objective uses SciPy BFGS and checks
the infinity norm of the final gradient. It is separate from the scikit-learn
baseline and its regularization conventions.

The Hessian is `X.T diag(p(1-p)) X / n + lambda I`. Hessian-vector products
apply the same expression without forming the dense diagonal. For validation
loss gradient q, solve `(H + damping I) s = q`. Adding epsilon times example loss
has derivative `-g_i.T s`. Removing one record and renormalizing has approximate
validation loss change `(g_i - mean(g)).T s / (n-1)`. Positive removal change
means removing the record is expected to increase loss. For prediction-specific
estimates q is the gradient of that validation observation's logistic loss.
The calculation uses fixed preprocessing, and damping changes the approximation.

Tests check central finite differences for gradient and Hessian, symmetry,
Hessian-vector agreement, a small epsilon upweighting experiment, removal sign,
and rejection of an ill-conditioned solve. Numerical safeguards require final
training gradient infinity norm <= 1e-6, solve residual <= 1e-8 and damped
condition number <= 1e8. These checks validate the computation and do not certify
ranking precision. The investigator uses an unweighted binary model with lambda
0.1 and exposes influence as experimental evidence only.
[Original influence-functions paper](https://proceedings.mlr.press/v70/koh17a.html).

Run `python benchmarks/influence.py --output influence.report.json` to compare
with exact retraining using the same fixed design. On 16 benchmark configurations
across two seeds, regularization and damping settings, and well-conditioned and
correlated designs with duplicates, aggregate removal Spearman was 0.77–1.00
and sign agreement 90–98.75%. Prediction-specific Spearman was 0.94–1.00 and
sign agreement 93.75–100%. These are synthetic fixtures. Finite removal,
preprocessing refits, collinearity and damping can all change the agreement.
