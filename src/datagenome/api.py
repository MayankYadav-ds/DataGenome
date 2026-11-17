import json
import logging
import os
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import __version__
from .ingestion import (
    DEFAULT_MAX_BYTES,
    DatasetError,
    check_size,
    parse_csv,
    validate_filename,
)
from .profiling import Profile, profile

logger = logging.getLogger(__name__)


def create_app(max_bytes: int | None = None) -> FastAPI:
    limit = (
        max_bytes
        if max_bytes is not None
        else int(os.environ.get("DATAGENOME_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    )
    if limit < 1:
        raise ValueError("DATAGENOME_MAX_BYTES must be positive.")
    app = FastAPI(title="DataGenome", version=__version__)

    @app.exception_handler(DatasetError)
    async def dataset_error(_request: Request, error: DatasetError) -> JSONResponse:
        logger.warning(json.dumps({"event": "profile_rejected", "code": error.code}))
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

    @app.post(
        "/api/v1/datasets/profile",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "text/csv": {"schema": {"type": "string", "format": "binary"}}
                },
            }
        },
    )
    async def profile_upload(
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
        target: str | None = None,
    ) -> Profile:
        validate_filename(filename)
        media_type = (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if media_type != "text/csv":
            raise DatasetError("unsupported_media_type", "Expected text/csv.", 415)
        payload = bytearray()
        async for chunk in request.stream():
            check_size(len(payload) + len(chunk), limit)
            payload.extend(chunk)
        return await run_in_threadpool(
            lambda: profile(parse_csv(payload, limit), target)
        )

    return app


app = create_app()
