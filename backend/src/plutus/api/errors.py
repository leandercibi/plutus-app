from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str


def _request_id(request: Request) -> str:
    existing = request.headers.get("X-Request-ID")
    return existing or str(uuid.uuid4())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        body = ErrorOut(
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def fallback(request: Request, exc: Exception) -> JSONResponse:
        rid = _request_id(request)
        # Full trace to logs; sanitized message in the response body.
        logger.exception("unhandled error", extra={"request_id": rid})
        body = ErrorOut(
            code="internal_error",
            message="internal server error",
            request_id=rid,
        )
        return JSONResponse(status_code=500, content=body.model_dump())
