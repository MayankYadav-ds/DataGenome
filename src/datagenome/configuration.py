"""Validated single-instance settings; configuration errors never echo values."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .ingestion import DatasetError


@dataclass(frozen=True)
class Settings:
    environment: str
    store: Path
    ledger: Path
    origin: str | None
    trusted_hosts: tuple[str, ...]
    secure_cookie: bool
    registration: bool
    guest_seconds: int
    session_seconds: int
    queue_limit: int
    retention_days: int | None
    log_level: str

    @classmethod
    def load(cls) -> "Settings":
        try:
            mode = os.environ.get("DATAGENOME_ENV", "development")
            if mode not in {"development", "production"}:
                raise ValueError
            production = mode == "production"
            store = Path(
                os.environ.get("DATAGENOME_STORE", ".datagenome/platform.sqlite3")
            )
            ledger = Path(os.environ.get("DATAGENOME_LEDGER", ".datagenome-ledger"))
            origin = os.environ.get("DATAGENOME_PUBLIC_ORIGIN")
            hosts = tuple(
                os.environ.get(
                    "DATAGENOME_TRUSTED_HOSTS", "localhost,127.0.0.1,[::1],testserver"
                ).split(",")
            )
            secure = os.environ.get("DATAGENOME_HTTPS", "0")
            registration = os.environ.get(
                "DATAGENOME_REGISTRATION", "0" if production else "1"
            )
            guest = int(os.environ.get("DATAGENOME_GUEST_SECONDS", "3600"))
            session = int(os.environ.get("DATAGENOME_SESSION_SECONDS", "28800"))
            queue = int(os.environ.get("DATAGENOME_QUEUE_LIMIT", "8"))
            days = os.environ.get(
                "DATAGENOME_RETENTION_DAYS", "30" if production else ""
            )
            retention = int(days) if days else None
            log_level = os.environ.get(
                "DATAGENOME_LOG_LEVEL", "INFO" if production else "WARNING"
            )
            if log_level not in {"INFO", "WARNING", "ERROR"}:
                raise ValueError
            if secure not in {"0", "1"} or registration not in {"0", "1"}:
                raise ValueError
            if os.environ.get("DATAGENOME_WORKERS", "1") != "1":
                raise ValueError
            if (
                not 60 <= guest <= 3600
                or not 300 <= session <= 28800
                or not 1 <= queue <= 8
            ):
                raise ValueError
            if retention is not None and not 1 <= retention <= 365:
                raise ValueError
            if not hosts or any(
                not h or h.strip() != h or any(c in h for c in "/\\*@?#") for h in hosts
            ):
                raise ValueError
            if origin:
                url = urlsplit(origin)
                _ = (
                    url.port
                )  # Validate malformed/out-of-range ports without echoing them.
                if (
                    url.scheme not in {"http", "https"}
                    or not url.hostname
                    or url.username
                    or url.password
                    or url.path
                    or url.query
                    or url.fragment
                ):
                    raise ValueError
            if production and (
                not origin
                or urlsplit(origin).scheme != "https"
                or secure != "1"
                or not store.is_absolute()
                or not ledger.is_absolute()
                or "DATAGENOME_TRUSTED_HOSTS" not in os.environ
                or "testserver" in hosts
            ):
                raise ValueError
            return cls(
                mode,
                store,
                ledger,
                origin,
                hosts,
                secure == "1",
                registration == "1",
                guest,
                session,
                queue,
                retention,
                log_level,
            )
        except (ValueError, TypeError) as error:
            raise DatasetError(
                "configuration_invalid", "Invalid or unsafe deployment configuration."
            ) from error
