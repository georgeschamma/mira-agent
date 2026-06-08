from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mira_agent.config import get_settings
from mira_agent.exceptions import (
    ApiError,
    api_error_handler,
    request_validation_error_handler,
    unhandled_error_handler,
)
from mira_agent.routers import analyze, approvals, config, health, media_plan, reports


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MIRA Agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = f"req_{uuid4().hex}"
        return await call_next(request)

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(config.router)
    app.include_router(analyze.router)
    app.include_router(media_plan.router)
    app.include_router(approvals.router)
    app.include_router(reports.router)

    if settings.static_dir.exists():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="ui")

    return app


app = create_app()
