from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.db import get_db
from app.errors import AppError

router = APIRouter(tags=["meta"])


class HealthOut(BaseModel):
    status: str


class CategoriesOut(BaseModel):
    expense: list[str]
    income: list[str]


@router.get("/health")
def health() -> HealthOut:
    """Liveness: the process is up. Does not touch the database."""
    return HealthOut(status="ok")


@router.get("/health/ready")
def ready(db: Annotated[Session, Depends(get_db)]) -> HealthOut:
    """Readiness: the database answers. For post-deploy smoke tests, not as the host health
    check (probing it constantly would keep a serverless Postgres awake)."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError("db_unavailable", "Banco de dados indisponível.", 503) from exc
    return HealthOut(status="ok")


@router.get("/categories")
def categories() -> CategoriesOut:
    return CategoriesOut(expense=EXPENSE_CATEGORIES, income=INCOME_CATEGORIES)
