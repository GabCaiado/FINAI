"""The Alembic history must produce exactly the schema the models declare."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import Base, engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def _drop_everything() -> None:
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def clean_database(schema: None) -> Iterator[None]:
    _drop_everything()
    yield
    _drop_everything()
    Base.metadata.create_all(engine)  # restore what the session-scoped fixture promised


def test_migrated_check_constraints_behave_like_the_models(clean_database: None):
    """The parity check ignores CHECK text, so exercise the constraints on a migrated database
    (this catches encoding damage such as 'TransferÃªncias' in a migration file)."""
    command.upgrade(_config(), "head")
    insert_tx = text(
        "INSERT INTO transactions (id, user_id, account_id, date, description_raw,"
        " description_clean, merchant, merchant_key, amount_cents, category, category_source,"
        " confidence, is_recurring, is_internal, status, dedupe_hash)"
        " VALUES (:id, 'u1', 'a1', '2026-11-01', 'X', 'X', '', '', :amount, :category, 'rule',"
        " 0.9, false, false, 'confirmed', :id)"
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, name, consent_at)"
                " VALUES ('u1', 'a@b.com', 'x', 'A', '2026-11-01')"
            )
        )
        conn.execute(
            text("INSERT INTO accounts (id, user_id, name, kind) VALUES ('a1', 'u1', 'C', 'cash')")
        )
        # Income may be Renda, Transferências or Outros.
        conn.execute(insert_tx, {"id": "t1", "amount": 1000, "category": "Transferências"})
    for amount, category in [(1000, "Mercado"), (-1000, "Renda")]:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert_tx, {"id": f"x{amount}", "amount": amount, "category": category})


def test_migrations_match_models_and_are_reversible(clean_database: None):
    cfg = _config()
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, {"compare_type": True}), Base.metadata
        )
    assert diff == [], f"models and migrations drifted: {diff}"

    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        remaining = set(Base.metadata.tables) & set(
            __import__("sqlalchemy").inspect(conn).get_table_names()
        )
    assert remaining == set()
