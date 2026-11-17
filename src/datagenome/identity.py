import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .ingestion import Dataset


def fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical(dataset: Dataset) -> str:
    digest = hashlib.sha256()
    digest.update(bytes.fromhex(fingerprint(dataset.columns)))
    for row in dataset.rows:
        digest.update(bytes.fromhex(fingerprint(row)))
    return digest.hexdigest()


@dataclass(frozen=True)
class Identity:
    source_sha256: str
    canonical_sha256: str
    schema_sha256: str
    version_id: str
    records: int
    features: int
    target: str | None
    created_at: str
    configuration_sha256: str
    split_configuration: dict[str, object] | None
    parent_id: str | None


def identify(
    dataset: Dataset,
    source: bytes | bytearray,
    target: str | None = None,
    split: dict[str, object] | None = None,
    parent: str | None = None,
) -> Identity:
    configuration = fingerprint([target, split])
    content = canonical(dataset)
    return Identity(
        hashlib.sha256(source).hexdigest(),
        content,
        fingerprint(dataset.columns),
        fingerprint([content, configuration, parent]),
        len(dataset.rows),
        len(dataset.columns) - int(target in dataset.columns),
        target,
        datetime.now(UTC).isoformat(),
        configuration,
        split,
        parent,
    )


def metadata(
    dataset: Dataset,
    source: bytes | bytearray,
    target: str | None,
    split: dict[str, object] | None,
) -> dict[str, object]:
    return asdict(identify(dataset, source, target, split))
