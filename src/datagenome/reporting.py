import csv
import io
from typing import Any

from .ingestion import DatasetError
from .orchestration import report_view


def csv_cell(value: str) -> str:
    """Escape derived report cells, never mutate original dataset values."""
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@"))
        or value.startswith(("\t", "\r", "\n"))
        else value
    )


def markdown_cell(value: str) -> str:
    import html
    import re

    return re.sub(
        r"([\\`*_{}\[\]()#+.!|>~-])",
        r"\\\1",
        html.escape(value.replace("\r", " ").replace("\n", " ")),
    )


def export_report(
    report: dict[str, Any], format: str = "json", privacy: str = "summary"
) -> str:
    import json

    view = report_view(report, privacy)
    if format == "json":
        return json.dumps(view, allow_nan=False, indent=2) + "\n"
    if format == "markdown":
        lines = [
            "# DataGenome diagnostic report",
            "",
            f"Coverage: {view['health']['coverage']:.1%}",
        ]
        score = view["health"]["score"]
        lines.append(
            "Health score: unassessed"
            if score is None
            else f"Health score: {score:.2f}"
        )
        lines += ["", "## Engines", ""]
        lines += [
            f"- {markdown_cell(name)}: {markdown_cell(engine['status'])}"
            for name, engine in view["engines"].items()
        ]
        lines += ["", "## Scientific limitations", ""]
        lines += ["- " + line for line in view["limitations"]]
        return "\n".join(lines) + "\n"
    if format == "engine-csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(("engine", "status"))
        writer.writerows(
            (csv_cell(name), csv_cell(item["status"]))
            for name, item in view["engines"].items()
        )
        return stream.getvalue()
    raise DatasetError("report_format", "Use json, markdown or engine-csv.")
