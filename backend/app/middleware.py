import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.config import settings
from app.errors import error_response
from app.request_context import set_request_id

logger = logging.getLogger("finai.request")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

CallNext = Callable[[Request], Awaitable[Response]]


def install_middleware(app: FastAPI) -> None:
    # Starlette runs the LAST registered middleware first. Runtime order (outer -> inner):
    # security headers -> request id + access log -> origin check -> app.
    # Short-circuit responses (e.g. 403) therefore still carry headers and a request id.

    @app.middleware("http")
    async def origin_check(request: Request, call_next: CallNext) -> Response:
        """CSRF defence in depth on top of SameSite=Lax: browsers always send ``Origin`` on
        cross-site unsafe requests, so a mismatching one is rejected. Requests without
        ``Origin`` come from non-browser clients (tests, curl) and carry no ambient cookie."""
        if request.method in _UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin != settings.cors_origin:
                return error_response(403, "forbidden_origin", "Origem não permitida.")
        return await call_next(request)

    @app.middleware("http")
    async def request_id_and_log(request: Request, call_next: CallNext) -> Response:
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        set_request_id(rid)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,  # never the query string
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next: CallNext) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
