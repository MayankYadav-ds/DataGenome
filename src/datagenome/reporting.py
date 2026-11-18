import csv
import io
from typing import Any

from .ingestion import DatasetError
from .orchestration import report_view


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
            f"- {name}: {engine['status']}" for name, engine in view["engines"].items()
        ]
        lines += ["", "## Scientific limitations", ""]
        lines += ["- " + line for line in view["limitations"]]
        return "\n".join(lines) + "\n"
    if format == "engine-csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(("engine", "status"))
        writer.writerows(
            (name, item["status"]) for name, item in view["engines"].items()
        )
        return stream.getvalue()
    raise DatasetError("report_format", "Use json, markdown or engine-csv.")
