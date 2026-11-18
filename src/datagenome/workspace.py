import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from .ingestion import DEFAULT_MAX_BYTES, DatasetError, parse_csv
from .jobs import JobService
from .orchestration import DiagnosticConfig, orchestrate
from .planner import evaluate_plans
from .reporting import export_report
from .splits import SplitConfig, split
from .store import Store
from .versions import Transform, apply, compare_versions, preview, reconstruct, register


def read_plan(path: Path) -> Transform:
    try:
        with path.open("rb") as source:
            raw = source.read(100_001)
        if len(raw) > 100_000:
            raise ValueError
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        allowed = {
            "remove_records",
            "corrections",
            "remove_features",
            "constant_features",
            "review_records",
            "ambiguous_records",
            "remove_duplicates",
            "max_fraction",
            "minimum_class_support",
            "minimum_group_support",
        }
        if set(value) - allowed:
            raise ValueError
        for key in ("remove_records", "review_records", "ambiguous_records"):
            entries = value.get(key, [])
            if (
                not isinstance(entries, list)
                or len(entries) > 1000
                or any(type(i) is not int or i < 1 for i in entries)
            ):
                raise ValueError
        for key in ("remove_features", "constant_features"):
            entries = value.get(key, [])
            if (
                not isinstance(entries, list)
                or len(entries) > 64
                or any(not isinstance(i, str) for i in entries)
            ):
                raise ValueError
        corrections = value.get("corrections", [])
        if not isinstance(corrections, list) or len(corrections) > 1000:
            raise ValueError
        pairs = []
        for correction in corrections:
            if (
                not isinstance(correction, dict)
                or set(correction) != {"record_id", "label"}
                or type(correction["record_id"]) is not int
                or correction["record_id"] < 1
                or not isinstance(correction["label"], str)
            ):
                raise ValueError
            pairs.append((correction["record_id"], correction["label"]))
        if (
            "remove_duplicates" in value
            and type(value["remove_duplicates"]) is not bool
        ):
            raise ValueError
        for key in ("max_fraction", "minimum_class_support", "minimum_group_support"):
            if key in value and type(value[key]) not in (int, float):
                raise ValueError
        return Transform(**{**value, "corrections": tuple(pairs)})
    except (ValueError, TypeError):
        raise DatasetError(
            "plan_format", "Expected a bounded JSON transformation plan."
        ) from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Local dataset improvement workspace.")
    parser.add_argument(
        "--store", type=Path, default=Path(".datagenome/platform.sqlite3")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    project = commands.add_parser("project")
    project.add_argument("name")
    upload = commands.add_parser("register")
    upload.add_argument("csv", type=Path)
    upload.add_argument("--target", required=True)
    upload.add_argument("--project", required=True)
    upload.add_argument(
        "--strategy",
        choices=("random", "stratified", "group", "chronological"),
        default="stratified",
    )
    upload.add_argument("--group")
    upload.add_argument("--time")
    upload.add_argument("--seed", type=int, default=42)
    for name in (
        "diagnose",
        "recommend",
        "report",
        "preview-intervention",
        "apply-intervention",
        "optimize-data",
        "history",
        "export",
        "compare-versions",
    ):
        command = commands.add_parser(name)
        command.add_argument("version")
        command.add_argument("--project", required=True)
        if name in {"diagnose", "recommend", "report"}:
            command.add_argument(
                "--engines",
                nargs="+",
                default=["profile", "intelligence", "leakage", "labels", "anomalies"],
            )
            command.add_argument(
                "--privacy",
                choices=("summary", "detailed", "redacted"),
                default="summary",
            )
        if name in {"preview-intervention", "apply-intervention", "optimize-data"}:
            command.add_argument("--plan", type=Path, required=True)
            command.add_argument("--reviewed", action="store_true")
        if name == "report":
            command.add_argument(
                "--format",
                choices=("json", "markdown", "engine-csv"),
                default="markdown",
            )
        if name in {"export", "report"}:
            command.add_argument("--output", type=Path, required=True)
        if name == "export":
            command.add_argument("--reviewed", action="store_true")
        if name == "compare-versions":
            command.add_argument("other_version")
    worker = commands.add_parser("work-one")
    worker.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    try:
        result: Any
        store = Store(args.store)
        if args.command == "project":
            result = store.project(args.name)
        elif args.command == "register":
            with args.csv.open("rb") as source:
                payload = source.read(DEFAULT_MAX_BYTES + 1)
            data = parse_csv(payload, max_rows=5000, max_columns=64)
            manifest = split(
                data,
                SplitConfig(
                    args.strategy, seed=args.seed, group=args.group, time=args.time
                ),
                args.target,
            )
            result = register(
                store, args.project, payload, args.target, manifest, args.csv.name
            )
            result = {
                "id": result["id"],
                "dataset_id": result["dataset_id"],
                "rows": len(result["rows"]),
            }
        elif args.command == "work-one":
            result = {"ran_job": JobService(store, recover=args.recover).run_one()}
        else:
            version = reconstruct(store, args.project, args.version)
            if args.command in {
                "preview-intervention",
                "apply-intervention",
                "optimize-data",
            }:
                plan = read_plan(args.plan)
                if args.command == "preview-intervention":
                    result = preview(store, args.project, args.version, plan)
                elif args.command == "apply-intervention":
                    if not args.reviewed:
                        raise DatasetError(
                            "review_required", "Explicit --reviewed is required."
                        )
                    created = apply(store, args.project, args.version, plan)
                    result = {"id": created["id"], "parent_id": created["parent_id"]}
                else:
                    result = evaluate_plans(
                        store,
                        args.project,
                        args.version,
                        [plan],
                        authorized=args.reviewed,
                    )
            elif args.command == "compare-versions":
                result = compare_versions(
                    version, reconstruct(store, args.project, args.other_version)
                )
            elif args.command == "history":
                result = [
                    {"id": item["id"], "parent_id": item["parent_id"]}
                    for item in store.versions(args.project, version["dataset_id"], 100)
                    if item["dataset_id"] == version["dataset_id"]
                ]
            elif args.command == "export":
                if not args.reviewed:
                    raise DatasetError(
                        "export_review", "Dataset export requires --reviewed."
                    )
                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                writer.writerow(version["columns"])
                writer.writerows(version["rows"])
                with args.output.open("x", encoding="utf-8", newline="") as output:
                    output.write(stream.getvalue())
                result = {"exported": True}
            else:
                from .versions import manifest_of, table

                data = table(version)
                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                writer.writerow(data.columns)
                writer.writerows(data.rows)
                report = orchestrate(
                    data,
                    stream.getvalue().encode(),
                    version["target"],
                    manifest_of(version),
                    DiagnosticConfig(tuple(args.engines)),
                    store=store,
                    project=args.project,
                )
                if args.command == "report":
                    with args.output.open("x", encoding="utf-8", newline="") as output:
                        output.write(export_report(report, args.format, args.privacy))
                    result = {"exported": True}
                else:
                    from .orchestration import report_view

                    result = report_view(report, args.privacy)
                    if args.command == "recommend" and args.privacy == "detailed":
                        result = {"recommendations": report["recommendations"]}
        print(json.dumps(result, allow_nan=False, indent=2))
    except DatasetError as error:
        parser.exit(2, json.dumps({"code": error.code, "message": str(error)}) + "\n")
    except OSError:
        parser.exit(2, '{"code":"workspace_io_error"}\n')


if __name__ == "__main__":
    main()
