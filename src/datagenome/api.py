import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import __version__
from .drift import DriftConfig, detect_drift
from .ingestion import (
    DEFAULT_MAX_BYTES,
    DatasetError,
    check_size,
    parse_csv,
    validate_filename,
)
from .options import Options
from .profiling import Profile, profile

logger = logging.getLogger(__name__)

CSV_BODY = {
    "requestBody": {
        "required": True,
        "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
    }
}


class DriftUpload(BaseModel):
    reference_csv: str = Field(min_length=1)
    comparison_csv: str = Field(min_length=1)
    target: str | None = Field(default=None, max_length=255)
    iid: bool = False
    privacy_mode: Literal["detailed", "redacted", "summary"] = "summary"


class AnalysisQuery(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    max_depth: int = Field(default=8, ge=1, le=16)
    trees: int = Field(default=32, ge=1, le=64)
    univariate: bool = False
    univariate_folds: int = Field(default=3, ge=2, le=5)
    univariate_max_features: int = Field(default=16, ge=1, le=32)
    univariate_minimum_score: float = Field(default=0.90, gt=0, le=1)
    univariate_minimum_lift: float = Field(default=0.20, gt=0, le=1)
    method: Literal["loo", "shapley", "mc-shapley", "knn-shapley", "banzhaf"] = "loo"
    utility: Literal[
        "accuracy", "balanced_accuracy", "macro_f1", "negative_log_loss", "class_recall"
    ] = "accuracy"
    utility_class: str | None = None
    max_evaluations: int = Field(default=256, ge=1, le=1024)
    permutations: int = Field(default=16, ge=2, le=256)
    k: int = Field(default=3, ge=1, le=1000)
    valuation_seconds: float = Field(default=30, gt=0, le=120)
    removal_fraction: float = Field(default=0.1, gt=0, le=0.2)
    record_id: int | None = Field(default=None, ge=1)
    minimum_support: int = Field(default=10, ge=5, le=500)
    privacy_mode: Literal["detailed", "redacted", "summary"] | None = None
    sensitive_column: list[str] = Field(default_factory=list, max_length=3)
    positive_label: str | None = Field(default=None, max_length=255)
    association_threshold: float = Field(default=0.9, gt=0, le=1)
    candidate_limit: int = Field(default=10000, ge=1, le=100000)
    max_anomaly_rows: int = Field(default=2000, ge=5, le=5000)
    iqr_multiplier: float = Field(default=1.5, gt=0, le=100)
    z_threshold: float = Field(default=3.5, gt=0, le=100)
    contamination: float = Field(default=0.05, gt=0, le=0.5)
    missing_warning: float = Field(default=0.05, ge=0, le=1)
    missing_high: float = Field(default=0.30, ge=0, le=1)
    target: str | None = None
    strategy: Literal["random", "stratified", "group", "chronological"] = "random"
    seed: int = Field(default=42, ge=0, lt=2**32)
    group: str | None = None
    time: str | None = None
    train_ratio: float = Field(default=0.6, gt=0, lt=1)
    validation_ratio: float = Field(default=0.2, gt=0, lt=1)
    test_ratio: float = Field(default=0.2, gt=0, lt=1)
    audit_group: str | None = None
    audit_time: str | None = None
    cutoff: str | None = None
    unavailable: list[str] = Field(default_factory=list, max_length=128)
    model: Literal["dummy", "logistic-regression", "decision-tree", "random-forest"] = (
        "logistic-regression"
    )
    intervention: list[Literal["remove-duplicates"]] = Field(
        default_factory=list, max_length=1
    )
    constant_feature: list[str] = Field(default_factory=list, max_length=128)
    suspected_feature: list[str] = Field(default_factory=list, max_length=128)
    exclude_record: list[int] = Field(default_factory=list, max_length=1000)
    imputation: Literal["median", "mean", "most_frequent"] | None = None


def create_app(
    max_bytes: int | None = None,
    *,
    max_rows: int | None = None,
    max_columns: int | None = None,
) -> FastAPI:
    from .configuration import Settings

    settings = Settings.load()
    application_logger = logging.getLogger("datagenome")
    if not application_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        application_logger.addHandler(handler)
        application_logger.propagate = False
    application_logger.setLevel(settings.log_level)
    limit = (
        max_bytes
        if max_bytes is not None
        else int(os.environ.get("DATAGENOME_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    )
    rows = (
        max_rows
        if max_rows is not None
        else int(os.environ.get("DATAGENOME_MAX_ROWS", "20000"))
    )
    columns = (
        max_columns
        if max_columns is not None
        else int(os.environ.get("DATAGENOME_MAX_COLUMNS", "128"))
    )
    if limit < 1 or not 1 <= rows <= 20000 or not 1 <= columns <= 128:
        raise ValueError("Invalid DataGenome resource limits.")
    app = FastAPI(title="DataGenome", version=__version__)
    app.state.settings = settings
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts)
    )
    gate = asyncio.Lock()

    @app.exception_handler(DatasetError)
    async def dataset_error(_request: Request, error: DatasetError) -> JSONResponse:
        logger.warning(json.dumps({"event": "analysis_rejected", "code": error.code}))
        return JSONResponse(
            {"error": {"code": error.code, "message": str(error)}},
            status_code=error.status,
        )

    @app.exception_handler(RequestValidationError)
    async def request_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Check the query parameters.",
                }
            },
            status_code=422,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"version": __version__}

    async def upload(request: Request, filename: str) -> bytearray:
        validate_filename(filename)
        media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media != "text/csv":
            raise DatasetError("unsupported_media_type", "Expected text/csv.", 415)
        payload = bytearray()
        async for chunk in request.stream():
            check_size(len(payload) + len(chunk), limit)
            payload.extend(chunk)
        return payload

    @app.post("/api/v1/datasets/profile", openapi_extra=CSV_BODY)
    async def profile_upload(
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
        target: str | None = None,
    ) -> Profile:
        if gate.locked():
            raise DatasetError(
                "analysis_busy", "Retry when the active request finishes.", 503
            )
        async with gate:
            payload = await upload(request, filename)
            return await run_in_threadpool(
                lambda: profile(
                    parse_csv(payload, limit, max_rows=rows, max_columns=columns),
                    target,
                )
            )

    @app.post(
        "/api/v1/datasets/drift",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": DriftUpload.model_json_schema()}
                },
            }
        },
    )
    async def drift_upload(request: Request) -> dict[str, Any]:
        if gate.locked():
            raise DatasetError(
                "analysis_busy", "Retry when the active request finishes.", 503
            )
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise DatasetError(
                "unsupported_media_type", "Expected application/json.", 415
            )
        async with gate:
            payload = bytearray()
            async for chunk in request.stream():
                check_size(len(payload) + len(chunk), 2 * limit + 1024)
                payload.extend(chunk)
            try:
                spec = DriftUpload.model_validate_json(payload)
                a, b = (
                    spec.reference_csv.encode("utf-8"),
                    spec.comparison_csv.encode("utf-8"),
                )
            except (ValueError, UnicodeError):
                raise DatasetError(
                    "invalid_drift_upload", "Supply two valid CSV strings."
                ) from None

            def run() -> dict[str, Any]:
                left = parse_csv(
                    a, limit, max_rows=min(rows, 10000), max_columns=min(columns, 64)
                )
                right = parse_csv(
                    b, limit, max_rows=min(rows, 10000), max_columns=min(columns, 64)
                )
                return {
                    "schema_version": "1.0",
                    "drift": detect_drift(
                        left,
                        right,
                        DriftConfig(
                            iid=spec.iid, summary_only=spec.privacy_mode != "detailed"
                        ),
                        target=spec.target,
                    ),
                }

            return await run_in_threadpool(run)

    def endpoint(operation: str) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def run(
            request: Request, query: Annotated[AnalysisQuery, Query()]
        ) -> dict[str, Any]:
            if gate.locked():
                raise DatasetError(
                    "analysis_busy", "Retry when the active request finishes.", 503
                )
            async with gate:
                payload = await upload(request, query.filename)
                options = Options(
                    target=query.target,
                    strategy=query.strategy,
                    seed=query.seed,
                    group=query.group,
                    time=query.time,
                    ratios=(
                        query.train_ratio,
                        query.validation_ratio,
                        query.test_ratio,
                    ),
                    audit_group=query.audit_group,
                    audit_time=query.audit_time,
                    cutoff=query.cutoff,
                    unavailable=tuple(query.unavailable),
                    model=query.model,
                    intervention=tuple(query.intervention),
                    constant_feature=tuple(query.constant_feature),
                    suspected_feature=tuple(query.suspected_feature),
                    exclude_record=tuple(query.exclude_record),
                    imputation=query.imputation,
                    valuation_method=query.method,
                    utility=query.utility,
                    utility_class=query.utility_class,
                    max_evaluations=query.max_evaluations,
                    permutations=query.permutations,
                    k=query.k,
                    valuation_seconds=query.valuation_seconds,
                    removal_fraction=query.removal_fraction,
                    record_id=query.record_id,
                    minimum_support=query.minimum_support,
                    privacy_mode=query.privacy_mode
                    or (
                        "summary"
                        if operation
                        in {"audit-fairness", "fairness-comparison", "detect-proxies"}
                        else "detailed"
                    ),
                    audit_attributes=tuple(query.sensitive_column),
                    positive_label=query.positive_label,
                    candidate_limit=query.candidate_limit,
                    association_threshold=query.association_threshold,
                    univariate=query.univariate,
                    univariate_folds=query.univariate_folds,
                    univariate_max_features=query.univariate_max_features,
                    univariate_minimum_score=query.univariate_minimum_score,
                    univariate_minimum_lift=query.univariate_minimum_lift,
                    max_anomaly_rows=query.max_anomaly_rows,
                    iqr_multiplier=query.iqr_multiplier,
                    z_threshold=query.z_threshold,
                    contamination=query.contamination,
                    missing_warning=query.missing_warning,
                    missing_high=query.missing_high,
                    max_depth=query.max_depth,
                    trees=query.trees,
                )
                return await run_in_threadpool(
                    options.run, operation, payload, limit, rows, columns
                )

        return run

    for path, operation in (
        ("datasets/fairness", "audit-fairness"),
        ("datasets/proxies", "detect-proxies"),
        ("experiments/fairness-comparison", "fairness-comparison"),
        ("datasets/diagnose", "diagnose"),
        ("datasets/anomalies", "detect-anomalies"),
        ("datasets/leakage", "detect-leakage"),
        ("datasets/label-audit", "audit-labels"),
        ("models/investigate", "investigate"),
        ("models/error-slices", "analyze-errors"),
        ("experiments/interventions", "investigate-intervention"),
        ("datasets/valuation", "value-data"),
        ("experiments/data-removal", "compare-removal"),
        ("datasets/split", "split"),
        ("models/train", "train"),
        ("models/evaluate", "evaluate"),
        ("experiments/compare", "experiment"),
    ):
        app.add_api_route(
            "/api/v1/" + path,
            endpoint(operation),
            methods=["POST"],
            name=operation,
            openapi_extra=CSV_BODY,
            responses={
                code: {"description": description}
                for code, description in (
                    (413, "Resource limit exceeded"),
                    (415, "Unsupported upload"),
                    (422, "Invalid input or configuration"),
                    (503, "Analysis busy"),
                )
            },
        )
    from .platform_api import attach_platform

    attach_platform(app, settings.store)
    return app


app = create_app()
