"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import audit
from ..config import get_settings
from ..errors import AppError
from .routers import auth, core

log = logging.getLogger("quoteguard.api")


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=s.LOG_LEVEL, format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')
    app = FastAPI(title="QuoteGuard API", version="1.0.0", description="Evidence-grounded procurement with version-bound approval and PayPal Sandbox checkout.",
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-CSRF-Token"])

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        cid = uuid.uuid4().hex[:16]
        token = audit.correlation_id.set(cid)
        t0 = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            audit.correlation_id.reset(token)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/v1") and request.method != "GET" or "/events" in request.url.path:
            response.headers.setdefault("Cache-Control", "no-store")
        log.info("%s %s %s %dms cid=%s", request.method, request.url.path, response.status_code, int((time.monotonic() - t0) * 1000), cid)
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message, "details": exc.details, "correlation_id": audit.correlation_id.get()}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()][:10]
        return JSONResponse({"error": {"code": "VALIDATION_FAILED", "message": "Some fields are missing or not allowed.", "details": {"fields": fields}, "correlation_id": audit.correlation_id.get()}}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        cid = audit.correlation_id.get()
        log.exception("unhandled error cid=%s", cid)
        return JSONResponse({"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong. Quote the correlation ID if you report it.", "correlation_id": cid}}, status_code=500)

    app.include_router(auth.router)
    app.include_router(core.router)
    return app


app = create_app()
