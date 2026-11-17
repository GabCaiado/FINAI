from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.categories import CATEGORIES, is_allowed
from app.db import engine
from app.main import app


def test_health_and_tables():
    with TestClient(app) as client:  # runs lifespan -> create_all
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    tables = set(inspect(engine).get_table_names())
    assert {"users", "import_batches", "transactions", "user_rules",
            "recurring_items", "goals", "llm_cache", "llm_usage"} <= tables


def test_categories_endpoint_and_sign_rules():
    with TestClient(app) as client:
        data = client.get("/api/categories").json()
    assert "Renda" not in data["expense"]
    assert len(CATEGORIES) == 13 and len(set(CATEGORIES)) == 13
    assert is_allowed("Renda", 1000) and not is_allowed("Renda", -1000)
    assert not is_allowed("Mercado", 1000)
