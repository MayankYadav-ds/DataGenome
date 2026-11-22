"""Kernel-backed local process lease; released by the OS after process death."""

import sys
from pathlib import Path
from typing import BinaryIO

from .ingestion import DatasetError


class Lease:
    def __init__(self, store: Path, *, recovery: bool = False) -> None:
        self.path = store.with_suffix(store.suffix + ".runtime.lock")
        self.pending = store.with_suffix(store.suffix + ".restore-pending.json")
        self.recovery = recovery
        self.file: BinaryIO | None = None

    def acquire(self) -> None:
        if self.pending.exists() and not self.recovery:
            raise DatasetError(
                "restore_pending",
                "An interrupted restore requires explicit operator recovery.",
            )
        if self.file is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = self.path.open("a+b")
        try:
            file.seek(0, 2)
            if not file.tell():
                file.write(b"0")
                file.flush()
            file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            file.close()
            raise DatasetError(
                "workspace_in_use",
                "Stop the owning service before this operation.",
                409,
            ) from error
        self.file = file

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self) -> "Lease":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
