# Contributing

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
