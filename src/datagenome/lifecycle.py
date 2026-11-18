from typing import Any

from .ingestion import DatasetError
from .store import Store


def delete_project(store: Store, project: str) -> None:
    store.require_project(project)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        running = db.execute(
            "SELECT count(*) FROM jobs WHERE project=? AND state='running'", (project,)
        ).fetchone()[0]
        if running:
            raise DatasetError(
                "project_busy", "Cancel running jobs before deletion.", 409
            )
        db.execute(
            "DELETE FROM events WHERE job IN (SELECT id FROM jobs WHERE project=?)",
            (project,),
        )
        db.execute("DELETE FROM jobs WHERE project=?", (project,))
        db.execute("DELETE FROM artifacts WHERE project=? OR id=?", (project, project))
        db.execute("DELETE FROM project_owners WHERE project=?", (project,))


def delete_dataset(store: Store, project: str, version_id: str) -> dict[str, Any]:
    value = store.get(project, version_id, "version")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM jobs WHERE project=? AND state='running'", (project,)
        ).fetchone():
            raise DatasetError(
                "project_busy",
                "Wait for running jobs before deleting dataset artifacts.",
                409,
            )
        ids = [
            row["id"]
            for row in db.execute(
                "SELECT id FROM artifacts WHERE project=? AND kind='version' AND json_extract(body,'$.dataset_id')=?",
                (project, value["dataset_id"]),
            )
        ]
        # Clear derived reports and caches conservatively within the same project.
        db.execute(
            "DELETE FROM events WHERE job IN (SELECT id FROM jobs WHERE project=?)",
            (project,),
        )
        db.execute("DELETE FROM jobs WHERE project=?", (project,))
        db.execute(
            "DELETE FROM artifacts WHERE project=? AND kind NOT IN ('version')",
            (project,),
        )
        for identifier in ids:
            db.execute(
                "DELETE FROM artifacts WHERE id=? AND project=?", (identifier, project)
            )
    return {"status": "deleted", "versions": len(ids), "cleared_project_results": True}


def retention(store: Store, days: int) -> int:
    from datetime import UTC, datetime, timedelta

    if not 1 <= days <= 365:
        raise DatasetError("retention_days", "Use 1–365 artifact retention days.")
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with store.connection() as db:
        cursor = db.execute(
            """DELETE FROM artifacts WHERE kind IN ('analysis','cache','experiment_result')
            AND created<? AND project NOT IN (SELECT project FROM jobs WHERE state IN ('queued','running'))""",
            (cutoff,),
        )
        return cursor.rowcount
