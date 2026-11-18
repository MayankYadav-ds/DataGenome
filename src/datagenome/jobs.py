import json
from threading import Event, Thread
from time import monotonic
from typing import Any
from uuid import uuid4

from .ingestion import DatasetError
from .orchestration import DiagnosticConfig, orchestrate
from .store import Store, now
from .versions import manifest_of, table


class JobService:
    """One worker per application process, with persisted requests and cooperative cancellation."""

    def __init__(self, store: Store, *, recover: bool = True) -> None:
        self.store = store
        self.stop_event = Event()
        self.thread: Thread | None = None
        if recover:
            with store.connection() as db:
                db.execute(
                    "UPDATE jobs SET state='interrupted',updated=? WHERE state='running'",
                    (now(),),
                )
                # Experiments have immutable execution metadata and explicit terminal records.
                pending = db.execute(
                    "SELECT id,project FROM artifacts WHERE kind='experiment' AND id NOT IN (SELECT json_extract(request,'$.experiment_id') FROM jobs WHERE state='queued' AND json_extract(request,'$.experiment_id') IS NOT NULL)"
                ).fetchall()
            for row in pending:
                try:
                    store.get(
                        row["project"], row["id"] + ".result", "experiment_result"
                    )
                except DatasetError as error:
                    if error.code != "artifact_not_found":
                        raise
                    with store.connection() as db:
                        terminal_job = db.execute(
                            "SELECT state FROM jobs WHERE project=? AND json_extract(request,'$.experiment_id')=? ORDER BY created DESC LIMIT 1",
                            (row["project"], row["id"]),
                        ).fetchone()
                    terminal_state = (
                        "cancelled"
                        if terminal_job and terminal_job["state"] == "cancelled"
                        else "interrupted"
                    )
                    store.put(
                        row["project"],
                        "experiment_result",
                        {"experiment_id": row["id"], "state": terminal_state},
                        row["id"] + ".result",
                    )

    def submit(
        self, project: str, version_id: str, config: DiagnosticConfig
    ) -> dict[str, Any]:
        self.store.get(project, version_id, "version")
        from dataclasses import asdict

        if (
            not 0 < config.seconds <= 120
            or not 1 <= len(config.engines) <= 12
            or len(set(config.engines)) != len(config.engines)
            or any(
                not isinstance(name, str) or not 1 <= len(name) <= 64
                for name in config.engines
            )
            or len(config.attributes) > 3
            or config.privacy not in {"summary", "redacted", "detailed"}
        ):
            raise DatasetError("job_budget", "Execution deadline must be in (0, 120].")
        identifier = uuid4().hex
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('queued','running')"
            ).fetchone()[0]
            stored_count = db.execute(
                "SELECT count(*) FROM jobs WHERE project=?", (project,)
            ).fetchone()[0]
            if stored_count >= 1000:
                raise DatasetError("job_quota", "Project reached its 1,000-job quota.")
            if count >= 8:
                raise DatasetError("queue_full", "The local queue is full.", 429)
            db.execute(
                "INSERT INTO jobs(id,project,state,request,created,updated) VALUES (?,?,?,?,?,?)",
                (
                    identifier,
                    project,
                    "queued",
                    json.dumps({"version_id": version_id, "config": asdict(config)}),
                    now(),
                    now(),
                ),
            )
        return self.get(project, identifier)

    def submit_experiment(
        self,
        project: str,
        version_id: str,
        plans: list[dict[str, Any]],
        *,
        seconds: float = 120,
        max_fits: int = 6,
    ) -> dict[str, Any]:
        from .identity import fingerprint
        from .versions import Transform, derive

        version = self.store.get(project, version_id, "version")
        if not 1 <= len(plans) <= 4 or not 2 <= max_fits <= 6 or not 0 < seconds <= 120:
            raise DatasetError(
                "experiment_budget", "Invalid experiment request budget."
            )
        for plan in plans:
            derive(
                version,
                Transform(
                    **{
                        **plan,
                        "corrections": tuple(
                            tuple(pair) for pair in plan.get("corrections", ())
                        ),
                    }
                ),
            )
        request = {
            "kind": "experiment",
            "version_id": version_id,
            "plans": plans,
            "seconds": seconds,
            "max_fits": max_fits,
        }
        config_hash = fingerprint(request)
        identifier = uuid4().hex
        experiment_id = uuid4().hex
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                """SELECT id FROM jobs WHERE project=? AND state IN ('queued','running')
                 AND json_extract(request,'$.config_sha256')=?""",
                (project, config_hash),
            ).fetchone()
            if prior is not None:
                existing = prior["id"]
            else:
                active = db.execute(
                    "SELECT count(*) FROM jobs WHERE state IN ('queued','running')"
                ).fetchone()[0]
                if active >= 8:
                    raise DatasetError("queue_full", "The local queue is full.", 429)
                if (
                    db.execute(
                        "SELECT count(*) FROM jobs WHERE project=?", (project,)
                    ).fetchone()[0]
                    >= 1000
                ):
                    raise DatasetError(
                        "job_quota", "This project reached its job quota."
                    )
                if (
                    db.execute(
                        "SELECT count(*) FROM artifacts WHERE project=?", (project,)
                    ).fetchone()[0]
                    >= 990
                ):
                    raise DatasetError(
                        "artifact_quota",
                        "Insufficient artifact capacity for this experiment.",
                    )
                metadata = {
                    "id": experiment_id,
                    "created_at": now(),
                    "state": "queued",
                    "version_id": version_id,
                    "plans": plans,
                    "configuration_sha256": config_hash,
                }
                db.execute(
                    "INSERT INTO artifacts VALUES (?,?,?,?,?)",
                    (
                        experiment_id,
                        project,
                        "experiment",
                        json.dumps(metadata, allow_nan=False),
                        now(),
                    ),
                )
                request.update(experiment_id=experiment_id, config_sha256=config_hash)
                db.execute(
                    "INSERT INTO jobs(id,project,state,request,created,updated) VALUES (?,?,?,?,?,?)",
                    (
                        identifier,
                        project,
                        "queued",
                        json.dumps(request, allow_nan=False),
                        now(),
                        now(),
                    ),
                )
                existing = identifier
        return self.get(project, existing)

    def get(self, project: str, job_id: str) -> dict[str, Any]:
        self.store.require_project(project)
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND project=?", (job_id, project)
            ).fetchone()
            events = (
                db.execute(
                    "SELECT sequence,body FROM events WHERE job=? ORDER BY sequence LIMIT 100",
                    (job_id,),
                ).fetchall()
                if row
                else []
            )
        if row is None:
            raise DatasetError("job_not_found", "Job is absent from this project.", 404)
        return {
            "id": row["id"],
            "project": row["project"],
            "state": row["state"],
            "cancel_requested": bool(row["cancel"]),
            "error": row["error"],
            "result_id": row["result"],
            "experiment_id": json.loads(row["request"]).get("experiment_id"),
            "created_at": row["created"],
            "updated_at": row["updated"],
            "events": [
                {"sequence": item["sequence"], **json.loads(item["body"])}
                for item in events
            ],
        }

    def cancel(self, project: str, job_id: str) -> dict[str, Any]:
        self.get(project, job_id)
        with self.store.connection() as db:
            db.execute(
                """UPDATE jobs SET cancel=1,
                state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,updated=?
                WHERE id=? AND project=? AND state IN ('queued','running')""",
                (now(), job_id, project),
            )
        return self.get(project, job_id)

    def run_one(self) -> bool:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute(
                "SELECT * FROM jobs WHERE state='queued' ORDER BY created,id LIMIT 1"
            ).fetchone()
            if job is None:
                return False
            db.execute(
                "UPDATE jobs SET state='running',updated=? WHERE id=?",
                (now(), job["id"]),
            )
        started = monotonic()
        request = json.loads(job["request"])
        project, identifier = job["project"], job["id"]

        def cancelled() -> bool:
            with self.store.connection() as db:
                row = db.execute(
                    "SELECT cancel FROM jobs WHERE id=?", (identifier,)
                ).fetchone()
            return row is None or bool(row["cancel"]) or self.stop_event.is_set()

        def progress(value: dict[str, Any]) -> None:
            with self.store.connection() as db:
                sequence = db.execute(
                    "SELECT coalesce(max(sequence),0)+1 FROM events WHERE job=?",
                    (identifier,),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO events VALUES (?,?,?)",
                    (identifier, sequence, json.dumps(value)),
                )

        state, result_id, error_code = "completed", None, None
        try:
            if cancelled():
                raise DatasetError("job_cancelled", "Cancelled before execution.")
            if request.get("kind") == "experiment":
                from .planner import evaluate_plans
                from .versions import Transform

                plans = [
                    Transform(
                        **{
                            **plan,
                            "corrections": tuple(
                                tuple(pair) for pair in plan.get("corrections", ())
                            ),
                        }
                    )
                    for plan in request["plans"]
                ]
                result = evaluate_plans(
                    self.store,
                    project,
                    request["version_id"],
                    plans,
                    authorized=True,
                    max_fits=request["max_fits"],
                    seconds=request["seconds"],
                    cancelled=cancelled,
                    event=progress,
                    experiment_id=request["experiment_id"],
                )
                result_id = result["id"]
            else:
                version = self.store.get(project, request["version_id"], "version")
                config = DiagnosticConfig(
                    **{
                        **request["config"],
                        "engines": tuple(request["config"]["engines"]),
                        "attributes": tuple(request["config"]["attributes"]),
                    }
                )
                data = table(version)
                import csv
                import io

                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                writer.writerow(data.columns)
                writer.writerows(data.rows)
                result = orchestrate(
                    data,
                    stream.getvalue().encode(),
                    version["target"],
                    manifest_of(version),
                    config,
                    store=self.store,
                    project=project,
                    event=progress,
                    cancelled=cancelled,
                )
                if cancelled():
                    raise DatasetError(
                        "job_cancelled", "Cancellation observed after engine execution."
                    )
                result["version_id"] = version["id"]
                result["record_identity"] = {
                    "engine_records": "one_based_current_version_positions",
                    "position_to_stable_id": version["record_ids"],
                    "recommendation_records": "registered_stable_record_ids",
                }
                for recommendation in result["recommendations"]:
                    recommendation["records"] = [
                        version["record_ids"][i - 1] for i in recommendation["records"]
                    ]
                if monotonic() - started > config.seconds:
                    result["warnings"] = [
                        "Cooperative deadline passed before the last engine returned."
                    ]
                stored = self.store.put(
                    project, "analysis", {"version_id": version["id"], "report": result}
                )
                result_id = stored["id"]
        except DatasetError as error:
            state = "cancelled" if error.code == "job_cancelled" else "failed"
            error_code = error.code
        except Exception as error:
            state, error_code = "failed", type(error).__name__
        with self.store.connection() as db:
            db.execute(
                "UPDATE jobs SET state=?,result=?,error=?,updated=? WHERE id=?",
                (state, result_id, error_code, now(), identifier),
            )
        return True

    def start(self) -> None:
        if self.thread is not None:
            return

        def work() -> None:
            while not self.stop_event.is_set():
                if not self.run_one():
                    self.stop_event.wait(0.2)

        self.thread = Thread(target=work, name="datagenome-worker", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
