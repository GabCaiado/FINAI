"""Uniform API error contract.

Every error response has the same body::

    {"code": "email_already_registered", "message": "<PT-BR text>", "details": {...} | null,
     "request_id": "..."}

``code`` is stable and machine-readable (the frontend switches on it); ``message`` is a
ready-to-show PT-BR default. Error bodies never echo request input, so passwords or statement
lines cannot leak into responses or logs through validation errors.
"""

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.request_context import get_request_id

logger = logging.getLogger("finai.errors")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


_HTTP_DEFAULTS: dict[int, tuple[str, str]] = {
    401: ("unauthorized", "Faça login para continuar."),
    403: ("forbidden", "Você não tem permissão para esta ação."),
    404: ("not_found", "Recurso não encontrado."),
    405: ("method_not_allowed", "Método não permitido."),
    413: ("payload_too_large", "Arquivo grande demais."),
    429: ("rate_limited", "Muitas tentativas. Aguarde um instante e tente novamente."),
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorBody(code=code, message=message, details=details, request_id=get_request_id())
    return JSONResponse(status_code=status_code, content=body.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_DEFAULTS.get(exc.status_code, ("http_error", "Erro na requisição."))
        return error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Only location and message: pydantic's "input" field would echo user data.
        errors = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return error_response(
            422, "validation_error", "Dados inválidos.", details={"errors": errors}
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log where it failed, never the exception message (it may contain user data).
        last = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
        logger.error(
            "unhandled_exception",
            extra={
                "error_type": type(exc).__name__,
                "error_at": f"{last.filename}:{last.lineno}" if last else None,
            },
        )
        return error_response(500, "internal_error", "Erro interno. Tente novamente em instantes.")
