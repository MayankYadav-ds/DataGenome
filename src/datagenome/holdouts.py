"""Local, fail-closed overlap receipts; not a distributed or tamper-proof service."""

import json
from pathlib import Path

from .identity import fingerprint
from .ingestion import Dataset, DatasetError
from .splits import Manifest, column


def claim(
    manifest: Manifest,
    ledger: Path,
    protocol_id: str,
    dataset: Dataset | None = None,
    target: str | None = None,
) -> str:
    ledger.mkdir(parents=True, exist_ok=True)
    key = fingerprint([manifest.dataset_sha256, sorted(manifest.partitions["test"])])
    records = set(manifest.partitions["test"])
    tokens: set[str] = set()
    if dataset is not None:
        label = column(dataset, target)
        features = [j for j in range(len(dataset.columns)) if j != label]
        tokens = {
            fingerprint(
                [(dataset.columns[j], dataset.rows[i - 1][j]) for j in features]
            )
            for i in records
        }
    lock = ledger / ".claim-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise DatasetError(
            "holdout_busy", "The ledger is locked; scoring is refused."
        ) from error
    try:
        receipts = list(ledger.glob("*.json"))
        if len(receipts) > 10000:
            raise DatasetError(
                "holdout_ledger_budget", "Ledger receipt limit exceeded."
            )
        for path in receipts:
            if path.name.endswith(".result.json"):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    raise ValueError
                previous = json.loads(path.read_text(encoding="utf-8"))
                # Old receipts cannot establish non-overlap. Do not silently migrate them.
                if "record_ids" not in previous or (
                    tokens and not previous.get("feature_tokens")
                ):
                    raise DatasetError(
                        "holdout_legacy_ledger",
                        "Legacy receipts cannot establish non-overlap; scoring is refused.",
                    )
                overlap = (
                    previous["dataset_sha256"] == manifest.dataset_sha256
                    and bool(records.intersection(previous["record_ids"]))
                ) or bool(tokens.intersection(previous.get("feature_tokens", [])))
                if overlap:
                    raise DatasetError(
                        "holdout_consumed",
                        "Evaluation records are already claimed in this ledger.",
                    )
            except DatasetError:
                raise
            except (ValueError, TypeError, KeyError) as error:
                raise DatasetError(
                    "holdout_invalid_ledger", "Invalid ledger receipt."
                ) from error
        receipt = {
            "status": "claimed",
            "protocol_sha256": protocol_id,
            "held_out_scored": False,
            "dataset_sha256": manifest.dataset_sha256,
            "record_ids": sorted(records),
            "feature_tokens": sorted(tokens),
        }
        with (ledger / (key + ".json")).open("x", encoding="utf-8") as file:
            json.dump(receipt, file, allow_nan=False, sort_keys=True)
        return key
    finally:
        lock.rmdir()
