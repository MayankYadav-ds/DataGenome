# Reproduce the Phase 9 studies

Use Python3.11+, the project API/dev extras, and a CPU environment. The local
Windows verification uses sklearn1.6.1, NumPy2.2.6 and SciPy1.17.1 because Windows
Application Control blocked a newer native module; do not bypass OS controls.
Dependency versions and execution commit appear in every trial. Different native
versions/BLAS/hardware can change timings, ties and optimization results.

From the repository root in PowerShell:

```powershell
python -m pip install ".[api,dev]"
python -m datagenome benchmark --suite smoke --output .datagenome/research/smoke
python -m datagenome benchmark --suite leakage --output .datagenome/research/leakage
python -m datagenome benchmark --suite labels --output .datagenome/research/labels
python -m datagenome benchmark --suite valuation --output .datagenome/research/valuation
python -m datagenome benchmark --suite influence --output .datagenome/research/influence
python -m datagenome benchmark --suite fairness --output .datagenome/research/fairness
python -m datagenome benchmark --suite drift --output .datagenome/research/drift
python -m datagenome benchmark --suite interventions --output .datagenome/research/interventions
python -m datagenome benchmark --suite performance --output .datagenome/research/performance
python benchmarks/summarize_phase9.py .datagenome/research
```

The default checked-in frozen protocol must match dataset identities and seeds.
For a new explicitly exploratory protocol, choose a new `--protocol` path and
`--seeds 11 23 37`; run `--freeze-only` before any final scoring. Maximum five seeds
are accepted generally, but only three disjoint prespecified final blocks exist;
additional intervention blocks are unsupported. A completed output refuses
overwrite. Do not remove receipts or choose new output folders to advertise a
previously scored public record as new independent evidence. External reproduction
is replication of a published protocol, not a fresh unseen-confirmation claim.

Each suite writes JSON, CSV and Markdown plus an append-only trial journal. Failed
and unsupported cases remain visible. Intervention plans are written exclusively
before their local holdout claim and score; interrupted claims remain consumed.
The ledger detects overlapping unchanged feature vectors across label changes and
subset reindexing, but cannot detect arbitrary feature edits or other ledgers.
Old receipts without adequate identities cause refusal, not automatic migration.

Public summary generation copies aggregate results only; it does not publish local
holdout ledgers or arm record-ID selections. The index hashes exact published JSON
bytes; every web observation links to the corresponding individual trials. Review
the generated files before committing. Outputs contain no credentials or user
workspaces. Raw masks stay separate from detector inputs and are not published.

Single-thread model/native math runs use threadpoolctl. Per-suite cooperative limit
is 1,800s/600 trials, per-trial180s checked at return, and ≤10,000 rows/32 features;
exact coalition runs use six players. Native calls are not hard-preempted. Python
tracemalloc peaks exclude native allocations and process peak working set. The
measured machine has an AMD Ryzen7 7840HS, 8 cores/16 logical processors and
16,415,322,112 bytes physical RAM. Timings are not cross-machine service guarantees.

Full gates:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m build
python -m pip check
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Expensive research suites are optional, not automatically run on every CI push.
CI runs scientific regressions and the existing real-backend browser workflows.
