import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from random import Random

from datagenome.ingestion import Dataset
from datagenome.modeling import ModelConfig, classification_pipeline
from datagenome.splits import SplitConfig, split
from datagenome.uncertainty import ResamplingConfig, paired_interval

URL = "https://archive.ics.uci.edu/static/public/240/human%2Bactivity%2Brecognition%2Busing%2Bsmartphones.zip"
PROVENANCE = "https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones"
MAX_BYTES = 75_000_000


def acquire(path: Path) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".download")
        try:
            with (
                urllib.request.urlopen(URL, timeout=60) as source,
                temporary.open("xb") as destination,
            ):
                size = 0
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError(
                            "Download exceeds the documented archive budget."
                        )
                    destination.write(chunk)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Archive exceeds size limit.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Dataset:
    with zipfile.ZipFile(path) as outer:
        # UCI publishes an outer archive containing the original dataset ZIP.
        inner = [
            name for name in outer.namelist() if name.endswith("UCI HAR Dataset.zip")
        ]
        if inner:
            member = outer.getinfo(inner[0])
            if member.file_size > MAX_BYTES:
                raise ValueError("Inner archive exceeds the size budget.")
            archive = zipfile.ZipFile(io.BytesIO(outer.read(inner[0])))
        else:
            archive = outer
        try:
            rows = []
            for partition in ("train", "test"):
                prefix = "UCI HAR Dataset/" + partition + "/"
                names = [
                    prefix + "X_" + partition + ".txt",
                    prefix + "y_" + partition + ".txt",
                    prefix + "subject_" + partition + ".txt",
                ]
                with (
                    archive.open(names[0]) as features,
                    archive.open(names[1]) as target,
                    archive.open(names[2]) as subject,
                ):
                    for i, (x, y, g) in enumerate(
                        zip(features, target, subject, strict=True)
                    ):
                        if i % 6 == 0:
                            values = x.decode("ascii").split()[:6]
                            if len(values) != 6:
                                raise ValueError("Unexpected feature schema.")
                            rows.append(
                                (
                                    *values,
                                    g.decode("ascii").strip(),
                                    y.decode("ascii").strip(),
                                )
                            )
            return Dataset(
                (
                    "tBodyAcc-mean-X",
                    "tBodyAcc-mean-Y",
                    "tBodyAcc-mean-Z",
                    "tBodyAcc-std-X",
                    "tBodyAcc-std-Y",
                    "tBodyAcc-std-Z",
                    "subject",
                    "activity",
                ),
                tuple(rows),
            )
        finally:
            if archive is not outer:
                archive.close()


def run(data: Dataset, seed: int) -> dict:
    manifest = split(
        data, SplitConfig("group", (0.5, 0.4, 0.1), seed, group="subject"), "activity"
    )
    train, validation = manifest.partitions["train"], manifest.partitions["validation"]
    selected = list(range(6))
    ids = sorted(Random(seed).sample(train, max(1, len(train) // 20)))
    variants = {}
    correctness = []
    from threadpoolctl import threadpool_limits

    for name, training in (
        ("baseline", train),
        ("random_5pct_removal", [i for i in train if i not in set(ids)]),
    ):
        model = ModelConfig(seed=seed)
        pipeline, _, design, _, _ = classification_pipeline(
            data, selected, training, model
        )
        with threadpool_limits(limits=1):
            pipeline.fit(design(training), [data.rows[i - 1][-1] for i in training])
            predicted = pipeline.predict(design(validation)).tolist()
        observed = [
            float(pred == data.rows[i - 1][-1])
            for pred, i in zip(predicted, validation, strict=True)
        ]
        correctness.append(observed)
        variants[name] = {
            "accuracy": sum(observed) / len(observed),
            "training_records": len(training),
        }
    return {
        "seed": seed,
        "partitions": {key: len(value) for key, value in manifest.partitions.items()},
        "validation_subjects": len({data.rows[i - 1][-2] for i in validation}),
        "scores": variants,
        "paired_uncertainty": paired_interval(
            correctness[0],
            correctness[1],
            [data.rows[i - 1][-2] for i in validation],
            ResamplingConfig(samples=199, seed=seed),
        ),
        "held_out_evaluated": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checksum = acquire(args.archive)
    data = load(args.archive)
    trials = [run(data, seed) for seed in (19, 47)]
    args.output.write_text(
        json.dumps(
            {
                "source": PROVENANCE,
                "license": "CC BY 4.0",
                "attribution": "Reyes-Ortiz, Anguita, Ghio, Oneto and Parra (2013), UCI HAR",
                "archive_sha256": checksum,
                "rows": len(data.rows),
                "feature_policy": "First six documented body-acceleration means/stds.",
                "sampling_policy": "Every sixth row of each published source partition.",
                "trials": trials,
                "limitations": [
                    "Overlapping sensor windows are dependent within subjects.",
                    "This experiment screens an explicit random removal policy on group validation.",
                    "Window order is not an independently verified event timestamp.",
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
