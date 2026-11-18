"""Session handling: token rejection, account deletion (LGPD erasure) and log hygiene."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base
from app.models import (
    Account,
    Goal,
    ImportBatch,
    LlmUsage,
    RecurringItem,
    Transaction,
    User,
    UserRule,
)
from app.security import SESSION_COOKIE_NAME, create_token
from tests.factories import make_account, make_transaction, make_user, register_payload

ME = "/api/me"
LOGIN = "/api/auth/login"
REGISTER = "/api/auth/register"
DAY = timedelta(hours=24)


def sign_up(client: TestClient, **overrides: object) -> str:
    """Register through the API and return the user id."""
    response = client.post(REGISTER, json=register_payload(**overrides))
    assert response.status_code == 201
    return str(response.json()["id"])


def claims_for(user_id: str, now: datetime | None = None) -> dict[str, object]:
    issued = now or datetime.now(UTC)
    return {"sub": user_id, "iat": int(issued.timestamp()), "exp": int((issued + DAY).timestamp())}


def forged_with_old_signature(valid_token: str, other_user_id: str) -> str:
    header, _, signature = valid_token.split(".")
    payload = jwt.encode(claims_for(other_user_id), "x" * 64, algorithm="HS256").split(".")[1]
    return f"{header}.{payload}.{signature}"


# --- every way of being unauthenticated looks the same --------------------------------------------


def bad_cookies(user_id: str, valid_token: str) -> dict[str, str | None]:
    long_ago = datetime.now(UTC) - 3 * DAY
    return {
        "missing": None,
        "expired": create_token(user_id, secret=settings.jwt_secret, now=long_ago, expires_in=DAY),
        "tampered": forged_with_old_signature(valid_token, "someone-else"),
        "other_secret": jwt.encode(claims_for(user_id), "y" * 64, algorithm="HS256"),
        "alg_none": jwt.encode(claims_for(user_id), None, algorithm="none"),
        "garbage": "not-a-jwt",
    }


@pytest.mark.parametrize(
    "case", ["missing", "expired", "tampered", "other_secret", "alg_none", "garbage"]
)
def test_an_unusable_session_cookie_is_refused_with_one_identical_error(
    client: TestClient, case: str
):
    user_id = sign_up(client)
    valid_token = client.cookies[SESSION_COOKIE_NAME]
    assert client.get(ME).status_code == 200  # the cookie is what flips the answer
    client.cookies.clear()
    baseline = client.get(ME)  # no cookie at all
    cookie = bad_cookies(user_id, valid_token)[case]
    if cookie is not None:
        client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = client.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.json()["message"] == baseline.json()["message"]
    assert response.json()["details"] == baseline.json()["details"]


def test_a_valid_token_for_a_deleted_user_is_refused(client: TestClient, db: Session):
    sign_up(client)
    db.execute(delete(User))
    db.commit()

    response = client.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


# --- DELETE /me ---------------------------------------------------------------------------------


def seed_every_user_owned_table(db: Session, user: User) -> set[str]:
    """Give the user one row in each table that references them; return those table names."""
    account = db.scalars(select(Account).where(Account.user_id == user.id)).first()
    if account is None:
        account = make_account(db, user)
    batch = ImportBatch(
        user_id=user.id, account_id=account.id, filename="synthetic.csv", file_type="csv"
    )
    db.add(batch)
    db.flush()
    make_transaction(db, user, account, batch_id=batch.id)
    db.add_all(
        [
            UserRule(user_id=user.id, merchant_key="PADARIA", category="Alimentação"),
            RecurringItem(
                user_id=user.id,
                name="Aluguel",
                kind="fixed_expense",
                amount_cents=100000,
                category="Moradia",
                day_of_month=5,
            ),
            Goal(
                user_id=user.id,
                name="Viagem",
                target_cents=500000,
                deadline=datetime.now(UTC).date() + timedelta(days=90),
            ),
            LlmUsage(user_id=user.id, day=datetime.now(UTC).date(), rows_sent=3),
        ]
    )
    db.commit()
    return {
        model.__tablename__
        for model in (Account, ImportBatch, Transaction, UserRule, RecurringItem, Goal, LlmUsage)
    }


def owner_column(table: Table):
    if table.name == User.__tablename__:
        return table.c.id
    return table.c.get("user_id")


def rows_owned_by(db: Session, user_id: str) -> dict[str, int]:
    counts = {}
    for table in Base.metadata.sorted_tables:
        column = owner_column(table)
        if column is not None:
            counts[table.name] = db.scalar(
                select(func.count()).select_from(table).where(column == user_id)
            )
    return counts


def test_the_erasure_sweep_covers_every_table_that_belongs_to_a_user(db: Session):
    """A new table with a user_id must be added to the seeder, or this fails: that is what
    makes the DELETE /me sweep below meaningful for tables added later."""
    user = make_user(db)
    seeded = seed_every_user_owned_table(db, user) | {User.__tablename__}

    user_tables = {t.name for t in Base.metadata.sorted_tables if owner_column(t) is not None}

    assert seeded == user_tables


def test_delete_me_leaves_no_row_of_the_user_in_any_table(client: TestClient, db: Session):
    user_id = sign_up(client)
    user = db.get(User, user_id)
    assert user is not None
    seed_every_user_owned_table(db, user)
    assert all(count > 0 for count in rows_owned_by(db, user_id).values())

    response = client.delete(ME)

    assert response.status_code == 204
    db.expire_all()
    assert rows_owned_by(db, user_id) == {name: 0 for name in rows_owned_by(db, user_id)}


def test_delete_me_clears_the_cookie_and_the_old_cookie_stops_working(client: TestClient):
    sign_up(client)
    old_token = client.cookies[SESSION_COOKIE_NAME]

    response = client.delete(ME)
    client.cookies.set(SESSION_COOKIE_NAME, old_token)

    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get(ME).status_code == 401


def test_delete_me_keeps_other_users_data(client: TestClient, db: Session):
    other = make_user(db)
    other_account = make_account(db, other)
    make_transaction(db, other, other_account)
    db.commit()
    sign_up(client)

    client.delete(ME)

    db.expire_all()
    assert db.get(User, other.id) is not None
    assert db.scalar(select(func.count()).select_from(Transaction)) == 1
    assert db.scalar(select(func.count()).select_from(Account)) == 1


def test_delete_me_requires_a_session(client: TestClient):
    assert client.delete(ME).status_code == 401


# --- logs ---------------------------------------------------------------------------------------


def test_the_auth_flow_logs_no_email_password_or_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    email, password = "secret.person@example.com", "sup3r-secret-passphrase"
    # The app reconfigures the root logger at startup and drops pytest's handler: re-attach it.
    logging.getLogger().addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG):
            sign_up(client, email=email, password=password)
            token = client.cookies[SESSION_COOKIE_NAME]
            client.post(LOGIN, json={"email": email, "password": "wrong-passphrase"})
            client.post(LOGIN, json={"email": email, "password": password})
            client.delete(ME)
    finally:
        logging.getLogger().removeHandler(caplog.handler)

    assert any(r.name == "finai.request" for r in caplog.records), "nothing was captured"
    everything = " ".join(
        f"{r.getMessage()} {sorted(map(str, r.__dict__.values()))}" for r in caplog.records
    )
    for secret in (email, password, "wrong-passphrase", token, "argon2"):
        assert secret not in everything
