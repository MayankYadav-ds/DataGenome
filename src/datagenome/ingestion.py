import csv
import io
from dataclasses import dataclass
from typing import BinaryIO

DEFAULT_MAX_BYTES = 5 * 1024 * 1024


class DatasetError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Dataset:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def validate_filename(name: str) -> None:
    if not name.lower().endswith(".csv"):
        raise DatasetError("unsupported_file", "Expected a .csv filename.", 415)


def check_size(size: int, limit: int) -> None:
    if size > limit:
        raise DatasetError(
            "file_too_large", "CSV exceeds the configured byte limit.", 413
        )


def load_csv(source: BinaryIO, name: str, limit: int = DEFAULT_MAX_BYTES) -> Dataset:
    validate_filename(name)
    return parse_csv(source.read(limit + 1), limit)


def parse_csv(
    payload: bytes | bytearray,
    limit: int = DEFAULT_MAX_BYTES,
    *,
    max_rows: int | None = None,
    max_columns: int | None = None,
) -> Dataset:
    check_size(len(payload), limit)
    try:
        content = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DatasetError("invalid_encoding", "Expected UTF-8 CSV.") from None
    if "\x00" in content:
        raise DatasetError("malformed_csv", "CSV contains a NUL character.")
    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        columns = tuple(next(reader, []))
        if max_columns is not None and len(columns) > max_columns:
            raise DatasetError(
                "column_limit", "CSV exceeds the configured column limit.", 413
            )
        if not columns:
            raise DatasetError("empty_dataset", "CSV has no header.")
        if any(not col.strip() for col in columns) or len(set(columns)) != len(columns):
            raise DatasetError("invalid_header", "Headers must be nonblank and unique.")
        rows: list[tuple[str, ...]] = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(columns):
                raise DatasetError(
                    "malformed_csv",
                    f"Wrong number of fields at line {reader.line_num}.",
                )
            if max_rows is not None and len(rows) >= max_rows:
                raise DatasetError(
                    "row_limit", "CSV exceeds the configured row limit.", 413
                )
            rows.append(tuple(row))
    except csv.Error:
        raise DatasetError(
            "malformed_csv", f"Invalid CSV at line {reader.line_num}."
        ) from None
    if not rows:
        raise DatasetError("empty_dataset", "CSV has no data rows.")
    return Dataset(columns, tuple(rows))
