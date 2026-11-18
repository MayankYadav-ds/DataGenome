import argparse
import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from random import Random

from datagenome.ingestion import Dataset
from datagenome.modeling import ModelConfig, classification_pipeline
from datagenome.splits import SplitConfig, split, timestamp
from datagenome.uncertainty import ResamplingConfig, paired_interval

URL = "https://archive.ics.uci.edu/static/public/357/occupancy+detection.zip"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.archive.exists():
        with urllib.request.urlopen(URL, timeout=60) as source:
            raw = source.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError("Occupancy archive exceeds budget.")
        with args.archive.open("xb") as out:
            out.write(raw)
    if args.archive.stat().st_size > 3_000_000:
        raise ValueError("Archive exceeds size budget.")
    names = (
        "Temperature",
        "Humidity",
        "Light",
        "CO2",
        "HumidityRatio",
        "date",
        "Occupancy",
    )
    rows = {}
    duplicates = 0
    conflicting_timestamps: set[str] = set()
    with zipfile.ZipFile(args.archive) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".txt"):
                continue
            info = archive.getinfo(name)
            if info.file_size > 4_000_000:
                raise ValueError("Unexpected table size.")
            reader = csv.reader(io.TextIOWrapper(archive.open(name), encoding="utf-8"))
            header = next(reader)
            for i, values in enumerate(reader):
                if i % 10:
                    continue
                if len(values) != len(header) + 1:
                    raise ValueError(
                        "Expected UCI source row number followed by documented columns."
                    )
                row = dict(zip(header, values[1:], strict=True))
                if any(key not in row for key in names):
                    raise ValueError("Unexpected occupancy schema.")
                key = row["date"]
                if key in rows:
                    duplicates += 1
                    if rows[key] != tuple(row[n] for n in names):
                        conflicting_timestamps.add(key)
                rows[key] = tuple(row[n] for n in names)
    data = Dataset(
        names,
        tuple(
            rows[key]
            for key in sorted(rows, key=timestamp)
            if key not in conflicting_timestamps
        ),
    )
    results = []
    for seed in (19, 47):
        manifest = split(
            data, SplitConfig("chronological", seed=seed, time="date"), "Occupancy"
        )
        train, validation = (
            manifest.partitions["train"],
            manifest.partitions["validation"],
        )
        removed = set(Random(seed).sample(train, len(train) // 20))
        scores = []
        for ids in (train, [i for i in train if i not in removed]):
            pipeline, _, design, _, _ = classification_pipeline(
                data, list(range(5)), ids, ModelConfig(seed=seed)
            )
            from threadpoolctl import threadpool_limits

            with threadpool_limits(limits=1):
                pipeline.fit(design(ids), [data.rows[i - 1][-1] for i in ids])
                predictions = pipeline.predict(design(validation))
            scores.append(
                [
                    float(pred == data.rows[i - 1][-1])
                    for pred, i in zip(predictions, validation, strict=True)
                ]
            )
        units = [data.rows[i - 1][-2] for i in validation]
        results.append(
            {
                "seed": seed,
                "validation_records": len(validation),
                "baseline_accuracy": sum(scores[0]) / len(scores[0]),
                "random_removal_accuracy": sum(scores[1]) / len(scores[1]),
                "paired_uncertainty": paired_interval(
                    *scores,
                    units,
                    ResamplingConfig(
                        mode="temporal", samples=199, seed=seed, block_length=12
                    ),
                ),
                "held_out_evaluated": False,
            }
        )
    args.output.write_text(
        json.dumps(
            {
                "source": "https://archive.ics.uci.edu/dataset/357/occupancy+detection",
                "attribution": "Candanedo and Feldheim, Occupancy Detection (2016), UCI",
                "archive_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                "rows": len(data.rows),
                "sampling": "Every tenth source row, exact repeated timestamps deduplicated, then sorted by recorded date.",
                "duplicate_timestamps": duplicates,
                "excluded_inconsistent_timestamps": len(conflicting_timestamps),
                "trials": results,
                "limitations": [
                    "Block length is prespecified as 12 sampled timestamps.",
                    "Stationarity and representative blocks remain assumptions.",
                    "Concurrent environmental measurements do not establish future feature availability.",
                ],
            },
            allow_nan=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
