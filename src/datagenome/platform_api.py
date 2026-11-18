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
    service = JobService(store, recover=False)
    router = APIRouter(prefix="/api/v1")

    def startup() -> None:
        # Recovery is only appropriate for the one owning application process.
        nonlocal service
        service = JobService(store, recover=True)
        service.start()

    app.router.add_event_handler("startup", startup)
    app.router.add_event_handler("shutdown", lambda: service.close())

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
            "security": "local single-user service; project scoping is not authentication",
            "unsupported": [
                "chronological_univariate",
                "label_horizon_purging",
                "learned_dataset_transforms",
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
    def create_project(spec: ProjectRequest) -> dict[str, Any]:
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
    def analysis(spec: AnalysisRequest) -> dict[str, Any]:
        return service.submit(
            spec.project_id,
            spec.version_id,
            DiagnosticConfig(
                tuple(spec.engines),
                spec.seconds,
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
    def experiment(spec: ExperimentRequest) -> dict[str, Any]:
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
            return value
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

    app.include_router(router)
