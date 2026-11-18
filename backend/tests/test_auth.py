from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_now
from app.main import app
from app.models import Account, User
from app.security import DUMMY_PASSWORD_HASH, SESSION_COOKIE_NAME
from app.services import auth as auth_service
from tests.factories import register_payload

REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"
LOGOUT = "/api/auth/logout"
ME = "/api/me"
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def register(client: TestClient, **overrides: object) -> Response:
    return client.post(REGISTER, json=register_payload(**overrides))


def error_signature(response: Response) -> tuple[int, str, str]:
    """Everything of an error that must not differ between failure causes (request_id may)."""
    body = response.json()
    return response.status_code, body["code"], body["message"]


# --- register -----------------------------------------------------------------------------------


def test_register_returns_the_public_user_and_creates_a_session(client: TestClient):
    response = register(client, email="ana@example.com", name="Ana")

    assert response.status_code == 201
    assert set(response.json()) == {"id", "email", "name"}
    assert response.json()["email"] == "ana@example.com"
    assert client.get(ME).status_code == 200


def test_register_sets_a_hardened_session_cookie(client: TestClient):
    cookie = register(client).headers["set-cookie"].lower()

    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert f"max-age={settings.jwt_expire_hours * 3600}" in cookie
    assert "path=/" in cookie


def test_register_marks_the_cookie_secure_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "cookie_secure", True)

    cookie = register(client).headers["set-cookie"].lower()

    assert "secure" in cookie.split("; ")


def test_register_creates_the_default_account_with_the_user(client: TestClient, db: Session):
    register(client)

    accounts = db.scalars(select(Account)).all()
    assert [(a.name, a.kind) for a in accounts] == [("Conta principal", "checking")]
    assert accounts[0].user_id == db.scalar(select(User.id))


def test_register_stores_the_consent_instant_and_never_the_plain_password(
    client: TestClient, db: Session
):
    app.dependency_overrides[get_now] = lambda: NOW
    try:
        register(client, password="correct-horse-battery")
    finally:
        app.dependency_overrides.pop(get_now)

    user = db.scalars(select(User)).one()
    assert user.consent_at.replace(tzinfo=None) == NOW.replace(tzinfo=None)
    assert user.password_hash.startswith("$argon2id$")
    assert "correct-horse-battery" not in user.password_hash


def test_register_lowercases_the_email(client: TestClient, db: Session):
    register(client, email="Mixed.Case@Example.COM")

    assert db.scalars(select(User.email)).one() == "mixed.case@example.com"


@pytest.mark.parametrize("second_email", ["dup@example.com", "DUP@Example.com"])
def test_register_rejects_a_duplicate_email_whatever_its_case(
    client: TestClient, db: Session, second_email: str
):
    register(client, email="dup@example.com")

    response = register(client, email=second_email)

    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Account)) == 1


def test_register_without_consent_is_refused_and_creates_nothing(client: TestClient, db: Session):
    response = register(client, consent=False)

    assert response.status_code == 400
    assert response.json()["code"] == "consent_required"
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password", "x" * (settings.password_min_length - 1)),
        ("email", "not-an-email-secret-value"),
    ],
)
def test_register_validation_error_never_echoes_the_submitted_value(
    client: TestClient, field: str, value: str
):
    response = register(client, **{field: value})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert value not in response.text


@pytest.mark.parametrize("extra", ["user_id", "id", "is_admin"])
def test_register_rejects_fields_it_does_not_define(client: TestClient, extra: str):
    response = register(client, **{extra: "x"})

    assert response.status_code == 422


# --- login --------------------------------------------------------------------------------------


def test_login_with_valid_credentials_starts_a_session(client: TestClient):
    register(client, email="ana@example.com", password="correct-horse-battery")
    client.cookies.clear()

    response = client.post(
        LOGIN, json={"email": "ANA@example.com", "password": "correct-horse-battery"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "ana@example.com"
    assert client.get(ME).status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_response(client: TestClient):
    register(client, email="ana@example.com")

    wrong_password = client.post(LOGIN, json={"email": "ana@example.com", "password": "nope-nope"})
    unknown_email = client.post(LOGIN, json={"email": "ghost@example.com", "password": "nope-nope"})

    assert error_signature(wrong_password) == error_signature(unknown_email)
    assert error_signature(wrong_password)[:2] == (401, "invalid_credentials")
    assert wrong_password.json()["details"] == unknown_email.json()["details"]


def test_login_with_an_unknown_email_still_runs_the_password_verifier(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    seen: list[str] = []
    real_verify = auth_service.verify_password

    def spy(password_hash: str, password: str) -> bool:
        seen.append(password_hash)
        return real_verify(password_hash, password)

    monkeypatch.setattr(auth_service, "verify_password", spy)

    client.post(LOGIN, json={"email": "ghost@example.com", "password": "whatever"})

    assert seen == [DUMMY_PASSWORD_HASH]


def test_login_is_rate_limited_in_the_error_contract(client: TestClient):
    attempts = int(settings.login_rate_limit.split("/")[0])
    body = {"email": "ghost@example.com", "password": "whatever"}

    statuses = [client.post(LOGIN, json=body).status_code for _ in range(attempts)]
    blocked = client.post(LOGIN, json=body)

    assert set(statuses) == {401}
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"
    assert blocked.json()["request_id"] == blocked.headers["x-request-id"]


def test_login_rate_limit_does_not_leak_between_tests(client: TestClient):
    response = client.post(LOGIN, json={"email": "ghost@example.com", "password": "whatever"})

    assert response.status_code == 401


def test_login_from_a_foreign_origin_is_refused_by_the_origin_check(client: TestClient):
    response = client.post(
        LOGIN,
        json={"email": "a@example.com", "password": "whatever"},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_origin"


# --- logout and me ------------------------------------------------------------------------------


def test_logout_clears_the_cookie(client: TestClient):
    register(client)

    response = client.post(LOGOUT)

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.cookies.get(SESSION_COOKIE_NAME) is None
    assert client.get(ME).status_code == 401


def test_logout_works_without_a_session(client: TestClient):
    assert client.post(LOGOUT).status_code == 204


def test_me_returns_the_authenticated_user_only(client: TestClient):
    register(client, email="ana@example.com", name="Ana")
    client.cookies.clear()
    register(client, email="bia@example.com", name="Bia")

    assert client.get(ME).json()["email"] == "bia@example.com"


def test_no_auth_response_contains_the_password_hash_or_password(client: TestClient):
    password = "correct-horse-battery"
    responses = [
        register(client, email="ana@example.com", password=password),
        client.get(ME),
        client.post(LOGIN, json={"email": "ana@example.com", "password": password}),
        client.post(LOGIN, json={"email": "ana@example.com", "password": "wrong-password"}),
        client.post(LOGOUT),
    ]

    for response in responses:
        assert "password_hash" not in response.text
        assert "argon2" not in response.text
        assert password not in response.text
