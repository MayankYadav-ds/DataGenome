from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .ingestion import DatasetError, check_size, parse_csv
from .jobs import JobService
from .orchestration import ENGINES, DiagnosticConfig, report_view
from .planner import evaluate_plans
from .reporting import export_report
from .splits import SplitConfig, split
from .store import Store
from .versions import (
    Transform,
    apply,
    compare_versions,
    preview,
    reconstruct,
    register,
    table,
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInfo(Contract):
    id: str
    created_at: str
    name: str


class VersionInfo(Contract):
    id: str
    dataset_id: str
    parent_id: str | None
    canonical_sha256: str
    schema_sha256: str
    created_at: str
    row_count: int
    column_count: int


class JobInfo(Contract):
    id: str
    project: str
    state: Literal[
        "created",
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ]
    cancel_requested: bool
    error: str | None
    result_id: str | None
    experiment_id: str | None = None
    created_at: str
    updated_at: str
    events: list[dict[str, Any]]


class ProjectRequest(Contract):
    name: str = Field(min_length=1, max_length=100)


class DatasetRequest(Contract):
    project_id: str = Field(min_length=32, max_length=32)
    csv: str = Field(min_length=1, max_length=5_242_880)
    target: str = Field(min_length=1, max_length=255)
    strategy: Literal["random", "stratified", "group", "chronological"] = "stratified"
    group: str | None = Field(default=None, max_length=255)
    time: str | None = Field(default=None, max_length=255)
    seed: int = Field(default=42, ge=0, lt=2**32)


class AnalysisRequest(Contract):
    project_id: str = Field(min_length=32, max_length=32)
    version_id: str = Field(min_length=32, max_length=32)
    engines: list[str] = Field(
        default_factory=lambda: [
            "profile",
            "intelligence",
            "leakage",
            "labels",
            "anomalies",
        ],
        min_length=1,
        max_length=12,
    )
    seconds: float = Field(default=60, gt=0, le=120)
    attributes: list[str] = Field(default_factory=list, max_length=3)
    record_id: int | None = Field(default=None, ge=1)
    privacy: Literal["summary", "redacted", "detailed"] = "summary"


class Correction(Contract):
    record_id: StrictInt = Field(ge=1)
    label: str = Field(min_length=1, max_length=255)


class PlanRequest(Contract):
    remove_records: list[StrictInt] = Field(default_factory=list, max_length=1000)
    corrections: list[Correction] = Field(default_factory=list, max_length=1000)
    remove_features: list[str] = Field(default_factory=list, max_length=64)
    constant_features: list[str] = Field(default_factory=list, max_length=64)
    review_records: list[StrictInt] = Field(default_factory=list, max_length=1000)
    ambiguous_records: list[StrictInt] = Field(default_factory=list, max_length=1000)
    remove_duplicates: bool = False
    max_fraction: float = Field(default=0.20, gt=0, le=0.20)
    minimum_class_support: int = Field(default=2, ge=1, le=100)
    minimum_group_support: int = Field(default=2, ge=1, le=100)

    def transform(self) -> Transform:
        if any(
            type(value) is not int or value < 1
            for value in self.remove_records
            + self.review_records
            + self.ambiguous_records
        ):
            raise DatasetError(
                "record_identity", "Record IDs must be positive integers."
            )
        return Transform(
            tuple(self.remove_records),
            tuple((item.record_id, item.label) for item in self.corrections),
            tuple(self.remove_features),
            tuple(self.constant_features),
            tuple(self.review_records),
            tuple(self.ambiguous_records),
            self.remove_duplicates,
            self.max_fraction,
            self.minimum_class_support,
            self.minimum_group_support,
        )


class SearchRequest(Contract):
    project_id: str = Field(min_length=32, max_length=32)
    version_id: str = Field(min_length=32, max_length=32)
    maximum_candidates: int = Field(default=4, ge=1, le=4)


class PreprocessingRequest(Contract):
    features: list[str] = Field(default_factory=list, max_length=32)
    numeric_imputation: Literal["median", "mean"] = "median"
    scaling: Literal["standard", "robust", "none"] = "standard"
    category_limit: int = Field(default=32, ge=2, le=32)


class InterventionRequest(Contract):
    project_id: str = Field(min_length=32, max_length=32)
    version_id: str = Field(min_length=32, max_length=32)
    plan: PlanRequest
    reviewed: bool = False


class ExperimentRequest(Contract):
    project_id: str = Field(min_length=32, max_length=32)
    version_id: str = Field(min_length=32, max_length=32)
    plans: list[PlanRequest] = Field(min_length=1, max_length=4)
    authorized: bool = False
    max_fits: int = Field(default=6, ge=2, le=6)
    seconds: float = Field(default=120, gt=0, le=120)


def version_metadata(version: dict[str, Any]) -> dict[str, Any]:
    return {
        key: version[key]
        for key in (
            "id",
            "dataset_id",
            "parent_id",
            "canonical_sha256",
            "schema_sha256",
            "created_at",
        )
    } | {"row_count": len(version["rows"]), "column_count": len(version["columns"])}


def attach_platform(app: FastAPI, database: Path) -> None:
    from .request_limits import PlatformBodyLimit

    app.add_middleware(PlatformBodyLimit)
    store = Store(database)
    import os
    import sqlite3

    from .auth import install_auth

    auth = install_auth(
        app,
        store,
        secure_cookie=os.environ.get("DATAGENOME_HTTPS") == "1",
        registration=os.environ.get("DATAGENOME_REGISTRATION", "1") == "1",
    )
    app.state.auth = auth
    service = JobService(store, recover=False)
    router = APIRouter(prefix="/api/v1")

    from threading import Event, Thread

    maintenance_stop = Event()
    maintenance_thread: Thread | None = None

    def maintenance() -> None:
        from .lifecycle import retention

        while not maintenance_stop.wait(60):
            try:
                auth.cleanup()
                days = os.environ.get("DATAGENOME_RETENTION_DAYS")
                if days is not None:
                    retention(store, int(days))
            except (DatasetError, ValueError, sqlite3.Error):
                # Configuration errors never expose sensitive artifacts in logs.
                continue

    def startup() -> None:
        # Recovery is only appropriate for the one owning application process.
        nonlocal service, maintenance_thread
        auth.cleanup()
        service = JobService(store, recover=True)
        service.start()
        maintenance_thread = Thread(
            target=maintenance, name="datagenome-retention", daemon=True
        )
        maintenance_thread.start()

    app.router.add_event_handler("startup", startup)

    def shutdown() -> None:
        maintenance_stop.set()
        if maintenance_thread is not None:
            maintenance_thread.join(timeout=2)
        service.close()

    app.router.add_event_handler("shutdown", shutdown)

    @router.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "diagnostic_engines": ENGINES,
            "versions": [
                "register",
                "preview",
                "derive",
                "compare",
                "reconstruct",
                "select_earlier_version",
            ],
            "jobs": {"workers": 1, "queue_limit": 8, "cooperative_cancellation": True},
            "security": "revocable local sessions, CSRF tokens and server-side project ownership",
            "authentication": {
                "guest": True,
                "registration": auth.registration,
                "https_cookie": auth.secure_cookie,
            },
            "experiments": {
                "asynchronous": True,
                "maximum_fits": 6,
                "maximum_seconds": 120,
            },
            "preprocessing": [
                "numeric_imputation",
                "categorical_imputation",
                "standard",
                "robust",
                "one_hot",
                "feature_selection",
            ],
            "unsupported": [
                "chronological_univariate",
                "label_horizon_purging",
                "predictive_proxy_verification",
                "subgroup_intervention_uncertainty",
                "automatic_recommendation_application",
            ],
            "experimental": [
                "logistic_influence",
                "health_score",
                "recommendation_priorities",
                "bootstrap_intervals",
            ],
        }

    @router.post("/projects", response_model=ProjectInfo)
    def create_project(spec: ProjectRequest, request: Request) -> dict[str, Any]:
        limit = 3 if request.state.user["guest"] else 50
        if len(store.list("", "project", 100)) >= limit:
            raise DatasetError(
                "project_quota", "Workspace reached its project limit.", 429
            )
        return store.project(spec.name)

    @router.get("/projects", response_model=list[ProjectInfo])
    def projects(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        return store.list("", "project", limit, offset)

    @router.post("/datasets", response_model=VersionInfo)
    async def dataset(request: Request) -> dict[str, Any]:
        payload = bytearray()
        async for chunk in request.stream():
            check_size(len(payload) + len(chunk), 6_000_000)
            payload.extend(chunk)
        try:
            spec = DatasetRequest.model_validate_json(payload)
        except ValueError:
            raise DatasetError(
                "dataset_request", "Invalid registration request."
            ) from None
        store.require_project(spec.project_id)
        data = parse_csv(spec.csv.encode(), max_rows=5000, max_columns=64)
        if request.state.user["guest"] and (
            len(data.rows) > 500 or len(data.columns) > 32
        ):
            raise DatasetError(
                "guest_dataset_limit",
                "Guest datasets allow 500 rows and 32 columns.",
                413,
            )
        manifest = split(
            data,
            SplitConfig(
                strategy=spec.strategy, seed=spec.seed, group=spec.group, time=spec.time
            ),
            spec.target,
        )
        return version_metadata(
            register(store, spec.project_id, spec.csv.encode(), spec.target, manifest)
        )

    @router.get("/datasets/{version_id}", response_model=VersionInfo)
    def dataset_info(version_id: str, project_id: str) -> dict[str, Any]:
        return version_metadata(store.get(project_id, version_id, "version"))

    @router.get("/datasets/{version_id}/versions", response_model=list[VersionInfo])
    def history(
        version_id: str,
        project_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        value = store.get(project_id, version_id, "version")
        return [
            version_metadata(item)
            for item in store.versions(project_id, value["dataset_id"], limit, offset)
            if item["dataset_id"] == value["dataset_id"]
        ]

    @router.get("/datasets/{version_id}/export")
    def dataset_export(
        version_id: str, project_id: str, reviewed: bool = False
    ) -> PlainTextResponse:
        if not reviewed:
            raise DatasetError(
                "export_review", "Explicitly approve exporting dataset content."
            )
        import csv
        import io

        value = reconstruct(store, project_id, version_id)
        data = table(value)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(data.columns)
        writer.writerows(data.rows)
        return PlainTextResponse(stream.getvalue(), media_type="text/csv")

    @router.get("/datasets/{version_id}/compare/{other_id}")
    def comparison(version_id: str, other_id: str, project_id: str) -> dict[str, Any]:
        return compare_versions(
            store.get(project_id, version_id, "version"),
            store.get(project_id, other_id, "version"),
        )

    @router.post("/interventions/preview")
    def intervention_preview(spec: InterventionRequest) -> dict[str, Any]:
        return preview(store, spec.project_id, spec.version_id, spec.plan.transform())

    @router.post("/interventions/apply", response_model=VersionInfo)
    def intervention_apply(spec: InterventionRequest) -> dict[str, Any]:
        if not spec.reviewed:
            raise DatasetError(
                "intervention_review",
                "Applying a derived version requires explicit review.",
            )
        return version_metadata(
            apply(store, spec.project_id, spec.version_id, spec.plan.transform())
        )

    @router.post("/analyses", response_model=JobInfo)
    def analysis(spec: AnalysisRequest, request: Request) -> dict[str, Any]:
        return service.submit(
            spec.project_id,
            spec.version_id,
            DiagnosticConfig(
                tuple(spec.engines),
                min(spec.seconds, 30) if request.state.user["guest"] else spec.seconds,
                tuple(spec.attributes),
                spec.record_id,
                privacy=spec.privacy,
            ),
        )

    @router.get("/jobs/{job_id}", response_model=JobInfo)
    def job(job_id: str, project_id: str) -> dict[str, Any]:
        return service.get(project_id, job_id)

    @router.post("/jobs/{job_id}/cancel", response_model=JobInfo)
    def cancel(job_id: str, project_id: str) -> dict[str, Any]:
        return service.cancel(project_id, job_id)

    @router.get("/analyses/{analysis_id}")
    def analysis_result(
        analysis_id: str,
        project_id: str,
        privacy: Literal["summary", "redacted", "detailed"] = "summary",
    ) -> dict[str, Any]:
        value = store.get(project_id, analysis_id, "analysis")
        return report_view(value["report"], privacy)

    @router.get("/analyses/{analysis_id}/recommendations")
    def recommendation_result(
        analysis_id: str, project_id: str, reviewed: bool = False
    ) -> dict[str, Any]:
        value = store.get(project_id, analysis_id, "analysis")
        if not reviewed:
            return {
                "count": len(value["report"]["recommendations"]),
                "requires_detailed_review": True,
            }
        return {"recommendations": value["report"]["recommendations"]}

    @router.post("/experiments")
    def experiment(spec: ExperimentRequest, request: Request) -> dict[str, Any]:
        if spec.authorized:
            guest = request.state.user["guest"]
            return service.submit_experiment(
                spec.project_id,
                spec.version_id,
                [asdict(plan.transform()) for plan in spec.plans],
                seconds=min(spec.seconds, 30) if guest else spec.seconds,
                max_fits=min(spec.max_fits, 3) if guest else spec.max_fits,
            )
        return evaluate_plans(
            store,
            spec.project_id,
            spec.version_id,
            [plan.transform() for plan in spec.plans],
            authorized=spec.authorized,
            max_fits=spec.max_fits,
        )

    @router.get("/experiments/{experiment_id}")
    def experiment_result(experiment_id: str, project_id: str) -> dict[str, Any]:
        value = store.get(project_id, experiment_id, "experiment")
        try:
            result = store.get(
                project_id, experiment_id + ".result", "experiment_result"
            )
        except DatasetError as error:
            if error.code != "artifact_not_found":
                raise
            with store.connection() as db:
                row = db.execute(
                    "SELECT state,error FROM jobs WHERE project=? AND json_extract(request,'$.experiment_id')=? ORDER BY created DESC LIMIT 1",
                    (project_id, experiment_id),
                ).fetchone()
            return {**value, **(dict(row) if row else {})}
        return {**value, **result}

    @router.get("/reports/{analysis_id}")
    def report(
        analysis_id: str,
        project_id: str,
        format: Literal["json", "markdown", "engine-csv"] = "json",
        privacy: Literal["summary", "redacted", "detailed"] = "summary",
    ) -> PlainTextResponse:
        value = store.get(project_id, analysis_id, "analysis")
        types = {
            "json": "application/json",
            "markdown": "text/markdown",
            "engine-csv": "text/csv",
        }
        return PlainTextResponse(
            export_report(value["report"], format, privacy), media_type=types[format]
        )

    from .lifecycle import delete_dataset, delete_project

    @router.get("/projects/{project_id}")
    def project_info(project_id: str) -> dict[str, Any]:
        return store.get("", project_id, "project")

    @router.patch("/projects/{project_id}", response_model=ProjectInfo)
    def rename(project_id: str, spec: ProjectRequest) -> dict[str, Any]:
        value = store.get("", project_id, "project")
        value["name"] = spec.name
        import json

        with store.connection() as db:
            db.execute(
                "UPDATE artifacts SET body=? WHERE id=? AND kind='project'",
                (json.dumps(value), project_id),
            )
        return value

    @router.delete("/projects/{project_id}")
    def erase_project(project_id: str) -> dict[str, str]:
        delete_project(store, project_id)
        return {"status": "deleted"}

    @router.delete("/datasets/{version_id}")
    def erase_dataset(version_id: str, project_id: str) -> dict[str, Any]:
        return delete_dataset(store, project_id, version_id)

    @router.get("/datasets/{version_id}/preview")
    def bounded_preview(
        version_id: str,
        project_id: str,
        reviewed: bool = False,
        limit: int = Query(default=10, ge=1, le=20),
    ) -> dict[str, Any]:
        value = store.get(project_id, version_id, "version")
        if not reviewed:
            raise DatasetError(
                "preview_review", "Explicit review is required to view raw rows."
            )
        return {
            "columns": value["columns"],
            "rows": value["rows"][:limit],
            "record_ids": value["record_ids"][:limit],
        }

    @router.get("/reports")
    def reports(
        project_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": value["id"],
                "created_at": value["created_at"],
                "version_id": value["version_id"],
            }
            for value in store.list(project_id, "analysis", limit, offset)
        ]

    @router.delete("/reports/{analysis_id}")
    def erase_report(analysis_id: str, project_id: str) -> dict[str, str]:
        store.get(project_id, analysis_id, "analysis")
        with store.connection() as db:
            db.execute(
                "DELETE FROM artifacts WHERE id=? AND project=? AND kind='analysis'",
                (analysis_id, project_id),
            )
        return {"status": "deleted"}

    @router.get("/analyses/{analysis_id}/findings")
    def findings(
        analysis_id: str,
        project_id: str,
        privacy: Literal["summary", "redacted", "detailed"] = "summary",
    ) -> dict[str, Any]:
        return report_view(
            store.get(project_id, analysis_id, "analysis")["report"], privacy
        )

    @router.get("/analyses/{analysis_id}/health")
    def health_result(analysis_id: str, project_id: str) -> dict[str, Any]:
        return dict(
            report_view(
                store.get(project_id, analysis_id, "analysis")["report"], "summary"
            )["health"]
        )

    @router.post("/datasets/demo")
    def demo(spec: ProjectRequest, request: Request) -> dict[str, Any]:
        # spec.name labels an explicitly requested new project.
        project = create_project(spec, request)
        text = "x,z,label\n" + "".join(f"{i},{i % 5},{i % 2}\n" for i in range(60))
        payload = text.encode()
        data = parse_csv(payload, max_rows=500, max_columns=32)
        version = register(
            store,
            project["id"],
            payload,
            "label",
            split(data, SplitConfig("stratified"), "label"),
        )
        return {"project": project, "version": version_metadata(version)}

    @router.post("/datasets/{version_id}/preprocessing")
    def fit_preprocessing(
        version_id: str, project_id: str, spec: PreprocessingRequest
    ) -> dict[str, Any]:
        from .preprocessing import LearnedConfig, persist_parameters

        result = persist_parameters(
            store,
            project_id,
            version_id,
            LearnedConfig(
                tuple(spec.features),
                spec.numeric_imputation,
                spec.scaling,
                spec.category_limit,
            ),
        )
        return {
            "id": result["id"],
            "parameters_sha256": result["parameters_sha256"],
            "output_width": result["parameters"]["output_width"],
        }

    @router.get("/preprocessing/{artifact_id}")
    def preprocessing_info(artifact_id: str, project_id: str) -> dict[str, Any]:
        result = store.get(project_id, artifact_id, "preprocessing")
        return {
            "id": result["id"],
            "version_id": result["parameters"]["version_id"],
            "output_width": result["parameters"]["output_width"],
            "parameters_sha256": result["parameters_sha256"],
        }

    @router.post("/preprocessing/{artifact_id}/preview")
    def preprocessing_preview(
        artifact_id: str, project_id: str, version_id: str, reviewed: bool = False
    ) -> dict[str, Any]:
        from .preprocessing import transform_parameters

        if not reviewed:
            raise DatasetError(
                "preview_review",
                "Explicit review is required for transformed row previews.",
            )
        artifact = store.get(project_id, artifact_id, "preprocessing")
        version = store.get(project_id, version_id, "version")
        return {
            "rows": transform_parameters(
                artifact,
                table(version),
                list(range(1, min(10, len(version["rows"])) + 1)),
            )
        }

    @router.post("/plans/search")
    def search(spec: SearchRequest) -> dict[str, Any]:
        from .search import generate_candidates

        return generate_candidates(
            store,
            spec.project_id,
            spec.version_id,
            maximum_candidates=spec.maximum_candidates,
        )

    app.include_router(router)

    def verified_openapi() -> dict[str, Any]:
        from fastapi.openapi.utils import get_openapi

        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, routes=app.routes
            )
            schema["paths"]["/api/v1/datasets"]["post"]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": DatasetRequest.model_json_schema()}
                },
            }
            schema.setdefault("components", {}).setdefault("securitySchemes", {})[
                "LocalSession"
            ] = {"type": "apiKey", "in": "cookie", "name": "datagenome_session"}
            public = {
                "/api/v1/capabilities",
                "/api/v1/auth/guest",
                "/api/v1/auth/register",
                "/api/v1/auth/login",
            }
            for path, operations in schema["paths"].items():
                for method, operation in operations.items():
                    if (
                        path.startswith("/api/v1/")
                        and path not in public
                        and isinstance(operation, dict)
                    ):
                        operation["security"] = [{"LocalSession": []}]
                        if method in {"post", "patch", "put", "delete"}:
                            operation.setdefault("parameters", []).append(
                                {
                                    "name": "X-CSRF-Token",
                                    "in": "header",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            )
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = verified_openapi  # type: ignore[method-assign]
