import builtins
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .ingestion import DatasetError
from .ownership import http_owner

SCHEMA = 2
STATES = {
    "created",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    """One local artifact database. All lookups are scoped by project ownership."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, SCHEMA):
                raise DatasetError(
                    "store_schema", "Unsupported artifact database schema."
                )
            db.execute("""CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL,
                body TEXT NOT NULL, created TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, state TEXT NOT NULL,
                request TEXT NOT NULL, result TEXT, error TEXT, cancel INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL, updated TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                job TEXT NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL,
                PRIMARY KEY(job, sequence))""")
            db.execute(
                "CREATE TABLE IF NOT EXISTS project_owners (project TEXT PRIMARY KEY,user_id TEXT NOT NULL)"
            )
            db.execute("PRAGMA user_version = 2")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def project(self, name: str) -> dict[str, Any]:
        if not name.strip() or len(name) > 100:
            raise DatasetError(
                "project_name", "Use a nonblank project name of up to 100 characters."
            )
        return self.put("", "project", {"name": name})

    def require_project(self, project: str) -> None:
        self.get("", project, "project")

    def put(
        self,
        project: str,
        kind: str,
        body: dict[str, Any],
        identifier: str | None = None,
    ) -> dict[str, Any]:
        if kind != "project":
            self.require_project(project)
        identifier = identifier or uuid4().hex
        value = {**body, "id": identifier, "created_at": now()}
        payload = json.dumps(value, allow_nan=False)
        if len(payload.encode()) > 16_000_000:
            raise DatasetError("artifact_limit", "Artifact exceeds 16 MB.")
        try:
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute(
                    "SELECT count(*) FROM artifacts WHERE project=?", (project,)
                ).fetchone()[0]
                if count >= 1000:
                    raise DatasetError(
                        "artifact_quota", "Project reached its 1,000-artifact quota."
                    )
                db.execute(
                    "INSERT INTO artifacts VALUES (?,?,?,?,?)",
                    (identifier, project, kind, payload, value["created_at"]),
                )
                if kind == "project" and (owner := http_owner.get()) is not None:
                    db.execute(
                        "INSERT INTO project_owners VALUES (?,?)", (identifier, owner)
                    )
        except sqlite3.IntegrityError as error:
            raise DatasetError(
                "immutable_artifact", "Artifact ID already exists."
            ) from error
        persisted: dict[str, Any] = json.loads(payload)
        return persisted

    def get(self, project: str, identifier: str, kind: str) -> dict[str, Any]:
        with self.connection() as db:
            owner = http_owner.get()
            project_key = identifier if kind == "project" else project
            if owner is not None:
                allowed = db.execute(
                    "SELECT 1 FROM project_owners WHERE project=? AND user_id=?",
                    (project_key, owner),
                ).fetchone()
                if allowed is None:
                    raise DatasetError(
                        "artifact_not_found",
                        "Artifact is absent from this workspace.",
                        404,
                    )
            row = db.execute(
                "SELECT body FROM artifacts WHERE id=? AND project=? AND kind=?",
                (identifier, project, kind),
            ).fetchone()
        if row is None:
            raise DatasetError(
                "artifact_not_found", "Artifact is absent from this project.", 404
            )
        value: dict[str, Any] = json.loads(row["body"])
        return value

    def list(
        self, project: str, kind: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or offset < 0:
            raise DatasetError(
                "pagination", "Use a limit of 1–100 and a nonnegative offset."
            )
        if http_owner.get() is not None and kind != "project":
            self.require_project(project)
        with self.connection() as db:
            if kind == "project" and http_owner.get() is not None:
                rows = db.execute(
                    "SELECT a.body FROM artifacts a JOIN project_owners o ON o.project=a.id WHERE a.kind='project' AND o.user_id=? ORDER BY a.created,a.id LIMIT ? OFFSET ?",
                    (http_owner.get(), limit, offset),
                ).fetchall()
                return [json.loads(row["body"]) for row in rows]
            rows = db.execute(
                "SELECT body FROM artifacts WHERE project=? AND kind=? ORDER BY created,id LIMIT ? OFFSET ?",
                (project, kind, limit, offset),
            ).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def versions(
        self, project: str, dataset_id: str, limit: int = 50, offset: int = 0
    ) -> builtins.list[dict[str, Any]]:
        if not 1 <= limit <= 100 or offset < 0:
            raise DatasetError(
                "pagination", "Use a limit of 1-100 and a nonnegative offset."
            )
        self.require_project(project)
        with self.connection() as db:
            rows = db.execute(
                "SELECT body FROM artifacts WHERE project=? AND kind='version' AND json_extract(body,'$.dataset_id')=? ORDER BY created,id LIMIT ? OFFSET ?",
                (project, dataset_id, limit, offset),
            ).fetchall()
        return [json.loads(row["body"]) for row in rows]
