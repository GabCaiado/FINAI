import os

# Must run before `app` is imported: tests read backend/.env.test, never the developer's .env.
# Real environment variables still win, which is how CI points DATABASE_URL at Postgres.
from pathlib import Path  # noqa: E402

os.environ.setdefault("ENV_FILE", str(Path(__file__).resolve().parents[1] / ".env.test"))

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402, F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


def _truncate_all() -> None:
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(scope="session")
def schema() -> Iterator[None]:
    """Fresh schema for the whole run. Alembic parity is checked in test_migrations.py."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    if engine.url.get_backend_name() == "sqlite" and engine.url.database:
        Path(engine.url.database).unlink(missing_ok=True)


@pytest.fixture
def db(schema: None) -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        _truncate_all()


@pytest.fixture
def client(schema: None) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    _truncate_all()
