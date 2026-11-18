from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import install_error_handlers
from app.logging_config import configure_logging
from app.middleware import install_middleware
from app.rate_limit import install_rate_limiting
from app.routers import accounts, auth, meta


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The schema is owned by Alembic (`alembic upgrade head`), never created at startup.
    configure_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="FINAI",
        lifespan=lifespan,
        # Interactive docs and the schema are for development only.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    install_middleware(app)
    install_error_handlers(app)
    install_rate_limiting(app)
    app.include_router(meta.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    return app


app = create_app()
