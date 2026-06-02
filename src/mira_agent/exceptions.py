from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class ApiError(Exception):
    code: str
    message: str
    status_code: int = 400


def error_payload(error: ApiError, request_id: str | None = None) -> dict[str, dict[str, str]]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "request_id": request_id or f"req_{uuid4().hex}",
        }
    }


async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=error.status_code, content=error_payload(error, request_id))


async def unhandled_error_handler(request: Request, error: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    payload = error_payload(
        ApiError(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            status_code=500,
        ),
        request_id,
    )
    return JSONResponse(status_code=500, content=payload)

