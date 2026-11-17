import argparse
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .ingestion import DEFAULT_MAX_BYTES, DatasetError, load_csv
from .profiling import profile

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(prog="datagenome")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("profile", help="Profile a local CSV dataset.")
    command.add_argument("dataset", type=Path)
    command.add_argument("--target")
    command.add_argument("--output", type=Path)
    command.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    if args.max_bytes < 1:
        parser.error("--max-bytes must be positive")
    try:
        with args.dataset.open("rb") as source:
            dataset = load_csv(source, args.dataset.name, args.max_bytes)
        report = json.dumps(
            asdict(profile(dataset, args.target)), indent=2, allow_nan=False
        )
        if args.output:
            if args.output.exists() and os.path.samefile(args.output, args.dataset):
                raise DatasetError(
                    "invalid_output", "Output must differ from the input CSV."
                )
            args.output.write_text(report + "\n", encoding="utf-8")
        else:
            print(report)
    except DatasetError as error:
        logger.error(
            json.dumps(
                {"event": "profile_failed", "code": error.code, "message": str(error)}
            )
        )
        return 2
    except OSError:
        logger.error(
            json.dumps(
                {
                    "event": "profile_failed",
                    "code": "io_error",
                    "message": "Could not read the input or write the report.",
                }
            )
        )
        return 2
    return 0
