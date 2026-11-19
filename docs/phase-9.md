# Phase9 execution record — 0.6.0

Starting checkpoint independently verified: public `main` at
`7ed7dfbc379954e3c9b611b9c89bd5b22245fa66`, clean and synchronized; hosted Windows
CI passed. Frozen scientific execution source: `34a5563d67621fef853155810749be4e29c1cd85`.
The experiment artifacts retain their actual pre-release package metadata0.5.0;
0.6.0 packages the verified toolkit, evidence and research interface.

## Scope and checkpoints

| Checkpoints | Status / evidence |
|---|---|
| 9A source audit | Complete bounded source inventory, formulations, assumptions, numerical/statistical limits and P0 correction in [the audit](../research/scientific-audit.md) |
| 9B registry | Frozen protocol/hash, identities, seeds, configs, budgets, journals and JSON/CSV/Markdown results |
| 9C–9D data/corruptions | Public Iris/Wine/WDBC numeric binary/multiclass core and fixed Digits task; synthetic generator families; broader public mixed/group/time and exhaustive corruption validation partial |
| 9E–9F leakage/labels | 24 synthetic leakage and 81 public-data label trials, controls retained; forward-only univariate scorer added; no horizon purge or Confident Learning claim |
| 9G–9H valuation/interoperability | 15 synthetic finite-game/model/utility trials; exact/MC/KNN/LOO/Banzhaf comparisons; same-player cross-seed/public stability partial; OpenDataVal execution NOT RUN due incompatible native/dependency stack |
| 9I–9J influence/investigation | 135 fixed-objective retraining configurations plus three investigator studies; derivative/solve tolerances checked, reconstruction/neighbors retained; no arbitrary-model or causal claim |
| 9K–9L fairness/drift | Three synthetic fairness/proxy studies, 60 drift trials; independent count references, suppression/undefined behavior covered by regressions; predictive proxies/subgroup dependence intervals NOT RUN |
| 9M independent interventions | Three record-disjoint Digits blocks, frozen arms, same conditions, local overlap ledger, explicit oracle controls, paired conditional uncertainty; no positive accuracy changes |
| 9N–9Q health/reliability/statistics/resources | Existing safeguards plus 30 measured workloads; score/coverage/weight sensitivity, review requirements, runtime and Python peaks; native/process peak memory NOT RUN |
| 9R–9T research interface/toolkit/report | Generated traceable Research page; practical module commands; [open technical report](../research/technical-report.md) and primary references; not peer reviewed |
| 9U regressions | Full installed-wheel, frontend and production-browser gates below; existing difficult tests preserved |

## Observed evidence

357 trial envelopes across nine suites are published in [the artifact index](../benchmarks/results/phase9/index.json).
The smoke suite repeats a small subset for plumbing and is excluded from full-suite
scientific summaries. Three investigator cases are embedded in the influence
suite. Successful execution does not mean a detector is scientifically effective.
Three duplicate-removal arms were unavailable due insufficient candidates.

[Generated findings](../research/results.md) and [per-condition tables](../benchmarks/results/phase9/summary.md)
retain the actual values, adverse results and limited uncertainty. In particular,
the final study has18 non-baseline comparisons:0 accuracy improvements,14 unchanged
and4 degradations. Oracle results are separate from deployable review rules.
These small conditional comparisons do not establish population equivalence.

## Verification on Windows

- Installed-wheel Python regression suite: **114 passed**,59.81s. Coverage NOT RUN.
- Wheel imports from site-packages; all55 Python source modules match installed bytes.
- Ruff lint/format and strict mypy pass. No existing test removed or weakened.
- Frontend strict types, ESLint, formatting,18 unit tests and optimized build pass.
- Real production browser workflows: **7 passed**,55.3s. Research-only screenshot
  verification also passes,8.2s including service startup.
- Research page applicable axe WCAG2.2AA checks pass; six widths360/390/768/1024/1440/1920
  have no document overflow. Screenshot inspected: [research evidence](screenshots/research-phase9.png).
- Wheel and source archives build; source includes safe research/frontend artifacts
  and excludes dependencies, compiled bundles, local ledgers, databases and secrets.
- `pip check` and `python -m datagenome --version` pass; module reports0.6.0.
- npm runtime dependency advisory scan reports0 known vulnerabilities at verification.

The full-suite contract test caught an outdated OpenAPI version after the release
bump; the contract was regenerated from the actual app. Hash verification caught
Windows CRLF conversion; exports now write explicit LF bytes and checkout attributes
preserve them. Neither fix changes measured outcomes or disables checks.

## Reproduce and interpret

```powershell
python -m datagenome benchmark --suite smoke --output .datagenome/research/smoke
```

See [all commands, dependency constraints and hardware](../research/reproducibility.md).
Preserve local holdout receipts. Legacy receipts without adequate record identities
refuse scoring; changing ledgers is not permission to call old evaluations new.
The ledger is local and not tamper proof or a guarantee of global reuse detection.
Writer dependence is unknown; final-row bootstrap intervals assume IID conditionally.

Scientific validation is **PARTIAL** beyond the explicit bounded core scope.
[Remaining checkpoints](../research/threats-to-validity.md) are not marked complete.
No production deployment, formal accessibility certification, general accuracy
improvement, universal fairness or causal influence claim is made. Phase10 is not
started. No repository access/visibility/history changes or paid services are used.
Expenditure: **₹0**. Final commit/remote/hosted CI status is reported after publication.
