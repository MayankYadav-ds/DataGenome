# DataGenome

Debug the data, not just the model.

DataGenome profiles local CSV datasets and reports observations that can help explain model
failures. Phase 0 measures data properties and identifies issues for review. Finding counts
are computed from the input. The class imbalance assessment uses a heuristic threshold.

## Install

Python 3.11 or newer. From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install ".[api]"
```

Install `.` for the CLI alone. You can also run `python -m datagenome` from the activated environment. The profiling engine uses the Python standard library.
The optional API uses FastAPI (MIT) and Uvicorn (BSD-3-Clause), which are compatible
with the project's Apache-2.0 license.

## Run the reproducible demonstration

```powershell
python examples/generate_demo.py demo.csv
.\.venv\Scripts\datagenome --help
.\.venv\Scripts\datagenome --version
.\.venv\Scripts\datagenome profile demo.csv
.\.venv\Scripts\datagenome profile demo.csv --target label --output report.json
```

Seed 42 produces 20 base records plus one copy of the first record. Expect two blank
measurements, a constant batch feature, and 20 majority labels versus one minority label.

## API

```powershell
.\.venv\Scripts\python -m uvicorn datagenome.api:app --host 127.0.0.1
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/version
curl.exe -H "Content-Type: text/csv" --data-binary "@demo.csv" "http://127.0.0.1:8000/api/v1/datasets/profile?filename=demo.csv&target=label"
```

The profile endpoint accepts a raw CSV body and a required `filename` query parameter.
Use `target` to count classification labels. Input failures return a JSON error code
and message with status 413, 415, or 422. The default input limit is 5 MiB. Set
`DATAGENOME_MAX_BYTES` for the API or pass `--max-bytes` to the CLI.

## Architecture and limits

The CLI and API share a CSV parser, immutable dataset representation, profiler, and
structured findings. The parser accepts comma-separated UTF-8 with an optional BOM.
Headers must be unique and nonblank. Blank physical lines are ignored. Whitespace-only
cells count as missing. Duplicates and distinct counts use exact parsed text. Numeric
statistics use finite binary64 values and may round large numbers. Leading-zero integer
tokens are treated as text. A target is interpreted as categorical when supplied.
The CLI and API process each dataset in memory. Reports include label values if a target
is supplied, so handle reports with the same care as source data. The API is intended
for local use.

## Research and roadmap

Phase 0 uses descriptive statistics. Future data valuation experiments can use
[OpenDataVal](https://papers.nips.cc/paper_files/paper/2023/hash/5b047c7d862059a5df623c1ce2982fca-Abstract-Datasets_and_Benchmarks.html),
a NeurIPS 2023 benchmark for comparing valuation algorithms. The next phase should
define split-aware diagnostics and a controlled baseline for testing data interventions
against a fixed held-out set. Label quality, attribution, drift, fairness, and a web
interface are planned. See [research references](research/README.md) for the original papers.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and
[SECURITY.md](SECURITY.md) for vulnerability reporting.
