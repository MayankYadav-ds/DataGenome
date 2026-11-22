# Contributing

Phase10 CI tests installed wheels on Windows/Linux and real-backend browser cohorts.
Keep security assertions and scientific safeguards intact. Use fresh synthetic
workspaces for independent cohorts; the unchanged 240/minute source-IP limit can
reject an unpaced combined browser burst. See [Phase10](docs/phase-10.md).
Run `python scripts/verify_operations.py` for a temporary installed-CLI restore drill.
Container failure probes may target only the explicitly isolated verification project.

Use Python 3.11 or newer in a virtual environment. Install with
`python -m pip install -e ".[api,dev]"` and run:

```text
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
python -m build
```

Include regression coverage for defects and use synthetic fixtures. For analytical
changes, document the calculation, assumptions, and limits.
