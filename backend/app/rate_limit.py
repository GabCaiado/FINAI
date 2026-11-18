from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app import messages
from app.config import settings
from app.errors import error_response

UNKNOWN_CLIENT = "unknown"


def client_ip(request: Request) -> str:
    """The limiter key: the real client IP.

    Behind the host's proxy this is only correct when uvicorn runs with ``--proxy-headers``,
    which rewrites ``request.client`` from ``X-Forwarded-For`` for trusted proxies (ARCHITECTURE
    14.1). We never parse that header ourselves: a client could forge it to dodge the limit.
    """
    return request.client.host if request.client else UNKNOWN_CLIENT


limiter = Limiter(key_func=client_ip)


def login_limit() -> str:
    """Callable so the value is read per request, not frozen when this module is imported."""
    return settings.login_rate_limit


def _rate_limited(_: Request, __: Exception) -> JSONResponse:
    return error_response(429, "rate_limited", messages.RATE_LIMITED)


def install_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limited)
