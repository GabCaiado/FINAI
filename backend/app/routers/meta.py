from fastapi import APIRouter

from app.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/categories")
def categories() -> dict:
    return {"expense": EXPENSE_CATEGORIES, "income": INCOME_CATEGORIES}
