"""Offline operator tools. Filesystem access is privileged, never exposed via HTTP."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from .configuration import Settings
from .ingestion import DatasetError
from .lease import Lease

RECEIPT = re.compile(r"[a-f0-9]{64}(?:\.result)?\.json")
MAX_BACKUP = 512 * 1024 * 1024


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_root(path: Path) -> Path:
    absolute = path.absolute()
    if any(p.is_symlink() for p in (absolute, *absolute.parents)):
        raise DatasetError(
            "unsafe_operator_path", "Symlinked operator paths are refused."
        )
    return absolute.resolve()


def managed_scope(store: Path, ledger: Path) -> None:
    if ledger == store or ledger in store.parents or ledger.parent == ledger:
        raise DatasetError(
            "operator_scope",
            "The ledger must be a dedicated directory separate from the database and its ancestors.",
        )


def receipts(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if (root / ".claim-lock").exists():
        raise DatasetError(
            "ledger_busy", "Stop evaluation commands before backup or restore."
        )
    result: list[Path] = []
    for path in root.iterdir():
        if len(result) >= 10000:
            raise DatasetError("ledger_budget", "Too many ledger receipts.")
        if path.is_symlink() or not path.is_file() or not RECEIPT.fullmatch(path.name):
            raise DatasetError("ledger_format", "Unexpected entry in managed ledger.")
        if path.stat().st_size > 2_000_000:
            raise DatasetError("ledger_budget", "Ledger receipt exceeds its budget.")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or "protocol_sha256" not in value:
            raise DatasetError("ledger_format", "Invalid managed ledger receipt.")
        result.append(path)
    if len(result) > 10000:
        raise DatasetError("ledger_budget", "Too many ledger receipts.")
    return result


def integrity(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise DatasetError(
            "workspace_missing", "A regular workspace database is required."
        )
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        ok = db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        schema = db.execute("PRAGMA user_version").fetchone()[0]
        required = {"artifacts", "jobs", "events", "project_owners"}
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not ok or schema != 2 or not required <= tables:
            raise DatasetError(
                "workspace_integrity", "Workspace integrity/schema validation failed."
            )
        orphaned = db.execute(
            "SELECT count(*) FROM artifacts a WHERE kind<>'project' AND NOT EXISTS (SELECT 1 FROM artifacts p WHERE p.id=a.project AND p.kind='project')"
        ).fetchone()[0]
        foreign = db.execute("PRAGMA foreign_key_check").fetchall()
    if orphaned or foreign:
        raise DatasetError(
            "workspace_integrity", "Workspace references are inconsistent."
        )
    return {"status": "ok", "schema": schema, "orphaned_artifacts": orphaned}


def verify_backup(folder: Path) -> dict[str, Any]:
    folder = safe_root(folder)
    manifest_path = folder / "manifest.json"
    if (
        not manifest_path.is_file()
        or manifest_path.stat().st_size > 2_000_000
        or manifest_path.is_symlink()
    ):
        raise DatasetError("backup_manifest", "A bounded backup manifest is required.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("backup_schema") != 1
        or not isinstance(manifest.get("files"), dict)
    ):
        raise DatasetError("backup_manifest", "Unsupported backup manifest.")
    expected = manifest["files"]
    if "workspace.sqlite3" not in expected or len(expected) > 10001:
        raise DatasetError("backup_manifest", "Invalid backup scope.")
    actual: set[str] = set()
    total = 0
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise DatasetError("backup_path", "Backup symlinks are refused.")
        if path.is_dir() and path.relative_to(folder).as_posix() != "ledger":
            raise DatasetError("backup_path", "Unexpected backup directory.")
        if path.is_file() and path.name != "manifest.json":
            name = path.relative_to(folder).as_posix()
            if name != "workspace.sqlite3" and not (
                name.startswith("ledger/") and RECEIPT.fullmatch(name[7:])
            ):
                raise DatasetError("backup_path", "Unexpected backup entry.")
            total += path.stat().st_size
            if (
                total > MAX_BACKUP
                or name not in expected
                or checksum(path) != expected[name]
            ):
                raise DatasetError("backup_integrity", "Backup file identity failed.")
            actual.add(name)
    if actual != set(expected):
        raise DatasetError("backup_integrity", "Backup file inventory differs.")
    integrity(folder / "workspace.sqlite3")
    receipts(folder / "ledger")
    return {
        "status": "verified",
        "files": len(actual),
        "bytes": total,
        "encrypted": False,
        "authenticity": "not_established_by_checksums",
    }


def backup(store: Path, ledger: Path, destination: Path) -> dict[str, Any]:
    store, ledger, destination = map(safe_root, (store, ledger, destination))
    managed_scope(store, ledger)
    if (
        destination.exists()
        or destination == ledger
        or destination.is_relative_to(ledger)
    ):
        raise DatasetError(
            "backup_destination", "Use a new destination outside the ledger."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        Lease(store),
        tempfile.TemporaryDirectory(
            prefix=".dg-backup-", dir=destination.parent
        ) as temporary,
    ):
        integrity(store)
        entries = receipts(ledger)
        stage = Path(temporary)
        snapshot = stage / "workspace.sqlite3"
        with (
            closing(sqlite3.connect(store.as_uri() + "?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(snapshot)) as target,
        ):
            if (
                source.execute("PRAGMA page_count").fetchone()[0]
                * source.execute("PRAGMA page_size").fetchone()[0]
                > MAX_BACKUP
            ):
                raise DatasetError(
                    "backup_budget", "Workspace exceeds the supported snapshot size."
                )
            source.backup(target)
            if target.execute(
                "SELECT 1 FROM sqlite_master WHERE name='sessions'"
            ).fetchone():
                target.execute("DELETE FROM sessions")
            target.commit()
            target.execute("PRAGMA journal_mode=DELETE")
        (stage / "ledger").mkdir()
        for path in entries:
            shutil.copyfile(path, stage / "ledger" / path.name)
        files = {
            p.relative_to(stage).as_posix(): checksum(p)
            for p in stage.rglob("*")
            if p.is_file()
        }
        (stage / "manifest.json").write_text(
            json.dumps(
                {
                    "backup_schema": 1,
                    "files": files,
                    "database_schema": 2,
                    "sessions": "excluded",
                    "encryption": "none",
                    "scope": "SQLite-contained datasets/reports/experiments/accounts plus configured evaluation ledger; no other ledgers or external files",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        result = verify_backup(stage)
        os.replace(stage, destination)
    return {**result, "status": "backed_up"}


def restore(
    store: Path, ledger: Path, source: Path, *, apply: bool = False
) -> dict[str, Any]:
    store, ledger, source = map(safe_root, (store, ledger, source))
    managed_scope(store, ledger)
    verified = verify_backup(source)
    if (
        source == ledger
        or store.is_relative_to(source)
        or source.is_relative_to(ledger)
        or ledger.is_relative_to(source)
    ):
        raise DatasetError(
            "restore_scope", "Backup and managed ledger must be separate."
        )
    with Lease(store):
        current = receipts(ledger)
        incoming = {p.name: p for p in receipts(source / "ledger")}
        for path in current:
            if path.name in incoming and json.loads(path.read_text()) != json.loads(
                incoming[path.name].read_text()
            ):
                raise DatasetError(
                    "restore_ledger_conflict",
                    "Conflicting evaluation receipts require operator investigation.",
                )
        if not apply:
            return {
                **verified,
                "status": "dry_run",
                "preserved_current_receipts": len(current),
                "sessions_after_restore": 0,
            }
        store.parent.mkdir(parents=True, exist_ok=True)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".dg-restore-", dir=store.parent))
        pending = store.with_suffix(store.suffix + ".restore-pending.json")
        try:
            candidate = stage / "workspace.sqlite3"
            shutil.copyfile(source / "workspace.sqlite3", candidate)
            with closing(sqlite3.connect(candidate)) as db:
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='sessions'"
                ).fetchone():
                    db.execute("DELETE FROM sessions")
                db.execute(
                    "UPDATE jobs SET state='interrupted' WHERE state IN ('running','queued')"
                )
                db.commit()
            integrity(candidate)
            new_ledger = stage / "ledger"
            new_ledger.mkdir()
            for name, path in {**incoming, **{p.name: p for p in current}}.items():
                shutil.copyfile(path, new_ledger / name)
            old_db, old_ledger = (
                stage / "previous.sqlite3",
                ledger.with_name(ledger.name + ".restore-rollback"),
            )
            if old_ledger.exists():
                raise DatasetError(
                    "restore_rollback_pending",
                    "Resolve the prior rollback directory first.",
                )
            if store.exists():
                with closing(sqlite3.connect(store)) as db:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    db.execute("PRAGMA journal_mode=DELETE")
            moved_db = moved_ledger = installed_db = installed_ledger = False
            with pending.open("x", encoding="utf-8") as file:
                json.dump(
                    {
                        "stage": str(stage),
                        "ledger": str(ledger),
                        "had_store": store.exists(),
                        "had_ledger": ledger.exists(),
                        "prior_sha256": checksum(store) if store.exists() else None,
                    },
                    file,
                )
                file.flush()
                os.fsync(file.fileno())
            try:
                if store.exists():
                    os.replace(store, old_db)
                    moved_db = True
                if ledger.exists():
                    os.replace(ledger, old_ledger)
                    moved_ledger = True
                os.replace(candidate, store)
                installed_db = True
                os.replace(new_ledger, ledger)
                installed_ledger = True
                integrity(store)
            except Exception:
                if installed_db:
                    store.unlink()
                if installed_ledger:
                    shutil.rmtree(ledger)
                if moved_db:
                    os.replace(old_db, store)
                if moved_ledger:
                    os.replace(old_ledger, ledger)
                pending.unlink()
                raise
            if moved_ledger:
                shutil.rmtree(old_ledger)
            pending.unlink()
        finally:
            # A failed rollback or process death leaves the journal and original
            # data for explicit recovery; never delete the only surviving copy.
            if not pending.exists():
                shutil.rmtree(stage)
    return {
        "status": "restored",
        "sessions_after_restore": 0,
        "preserved_current_receipts": len(current),
        "encrypted": False,
    }


def recover_restore(
    store: Path, ledger: Path, *, apply: bool = False
) -> dict[str, Any]:
    store, ledger = map(safe_root, (store, ledger))
    managed_scope(store, ledger)
    marker = store.with_suffix(store.suffix + ".restore-pending.json")
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
        raise DatasetError(
            "restore_journal", "No bounded restore journal is available."
        )
    value = json.loads(marker.read_text())
    if (
        not isinstance(value, dict)
        or not {"stage", "ledger", "had_store", "had_ledger", "prior_sha256"}
        <= value.keys()
        or not isinstance(value["stage"], str)
        or not isinstance(value["ledger"], str)
        or type(value["had_store"]) is not bool
        or type(value["had_ledger"]) is not bool
    ):
        raise DatasetError("restore_journal", "Invalid restore journal.")
    stage = safe_root(Path(value["stage"]))
    if (
        stage.parent != store.parent
        or not stage.name.startswith(".dg-restore-")
        or value["ledger"] != str(ledger)
    ):
        raise DatasetError("restore_journal", "Restore journal scope is invalid.")
    old_db = stage / "previous.sqlite3"
    old_ledger = ledger.with_name(ledger.name + ".restore-rollback")
    with Lease(store, recovery=True):
        if value["had_store"]:
            original = old_db if old_db.exists() else store
            if checksum(original) != value["prior_sha256"]:
                raise DatasetError(
                    "restore_journal", "Original database identity failed."
                )
        if not apply:
            return {
                "status": "recovery_dry_run",
                "action": "rollback_interrupted_restore",
            }
        if old_db.exists():
            os.replace(old_db, store)
        elif not value["had_store"] and store.exists():
            store.unlink()
        if old_ledger.exists():
            if ledger.exists():
                shutil.rmtree(ledger)
            os.replace(old_ledger, ledger)
        elif not value["had_ledger"] and ledger.exists():
            shutil.rmtree(ledger)
        marker.unlink()
        shutil.rmtree(stage)
    return {"status": "restore_rolled_back"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline operator commands; OS account authorization is required."
    )
    parser.add_argument(
        "operation",
        choices=(
            "doctor",
            "backup",
            "verify-backup",
            "restore",
            "recover-restore",
            "integrity-check",
            "cleanup",
            "create-account",
        ),
    )
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--store", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--username")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = Settings.load()
        store, ledger = (
            safe_root(args.store or cfg.store),
            safe_root(args.ledger or cfg.ledger),
        )
        result: dict[str, Any]
        if args.operation == "create-account":
            import getpass
            import secrets
            import sys

            from .auth import Auth, Credentials
            from .store import Store

            password = (
                sys.stdin.readline().rstrip("\r\n")
                if args.password_stdin
                else getpass.getpass("New account password: ")
            )
            spec = Credentials(username=args.username or "", password=password)
            with Lease(store):
                auth = Auth(Store(store), registration=False)
                with auth.hashing_slot():
                    hashed = auth.hasher.hash(spec.password)
                with auth.store.connection() as db:
                    db.execute(
                        "INSERT INTO users VALUES (?,?,?,0,NULL)",
                        (secrets.token_hex(16), spec.username.casefold(), hashed),
                    )
            result = {"status": "account_created", "sessions_created": 0}
        elif args.operation in {"doctor", "integrity-check", "cleanup"}:
            result = integrity(store)
            result.update(
                environment=cfg.environment,
                worker_topology="single_process",
                ledger_receipts=len(receipts(ledger)),
            )
            if args.operation == "cleanup":
                result.update(
                    status="dry_run",
                    mutating_cleanup="unsupported_use_reviewed_application_retention",
                )
        elif args.operation == "backup" and args.output:
            result = backup(store, ledger, args.output)
        elif args.operation == "verify-backup" and args.source:
            result = verify_backup(args.source)
        elif args.operation == "restore" and args.source:
            result = restore(
                store, ledger, args.source, apply=args.apply and not args.dry_run
            )
        elif args.operation == "recover-restore":
            result = recover_restore(
                store, ledger, apply=args.apply and not args.dry_run
            )
        else:
            parser.error("Supply --output for backup or a source for verify/restore.")
        print(json.dumps(result, allow_nan=False))
    except (DatasetError, OSError, sqlite3.Error, ValueError) as error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": error.code
                        if isinstance(error, DatasetError)
                        else "operator_validation_failed",
                        "message": "Operator operation refused or failed; inspect configuration and verified backup scope.",
                    }
                }
            )
        )
        return 2
    return 0
