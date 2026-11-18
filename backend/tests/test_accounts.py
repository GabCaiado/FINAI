from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.errors import AppError
from app.main import app
from app.models import ACCOUNT_KINDS, Account, User
from app.schemas.accounts import AccountKind
from app.services import accounts as accounts_service
from tests.factories import make_account, make_transaction, make_user, register_payload

ACCOUNTS = "/api/accounts"
DEFAULT_NAME = "Conta principal"


def sign_up(client: TestClient) -> str:
    response = client.post("/api/auth/register", json=register_payload())
    assert response.status_code == 201
    return str(response.json()["id"])


@pytest.fixture
def user_id(client: TestClient) -> str:
    return sign_up(client)


@pytest.fixture
def other_client(client: TestClient, user_id: str) -> TestClient:
    """A second, separately authenticated user (own cookie jar); `client` is the first one."""
    second = TestClient(app)
    sign_up(second)
    return second


def create(client: TestClient, name: str = "Nubank", kind: str = "credit_card") -> Response:
    return client.post(ACCOUNTS, json={"name": name, "kind": kind})


def names(client: TestClient) -> list[str]:
    return [a["name"] for a in client.get(ACCOUNTS).json()]


def test_account_kind_literal_matches_the_database_enum():
    assert get_args(AccountKind) == ACCOUNT_KINDS


# --- CRUD ---------------------------------------------------------------------------------------


def test_list_starts_with_the_default_account(client: TestClient, user_id: str):
    response = client.get(ACCOUNTS)

    assert response.status_code == 200
    assert [(a["name"], a["kind"]) for a in response.json()] == [(DEFAULT_NAME, "checking")]
    assert set(response.json()[0]) == {"id", "name", "kind"}


def test_create_returns_201_and_the_account_appears_in_the_list(client: TestClient, user_id: str):
    response = create(client, name="  Nubank  ", kind="credit_card")

    assert response.status_code == 201
    assert (response.json()["name"], response.json()["kind"]) == ("Nubank", "credit_card")
    assert names(client) == [DEFAULT_NAME, "Nubank"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "X", "kind": "savings"},
        {"name": "", "kind": "cash"},
        {"name": "   ", "kind": "cash"},
        {"name": "x" * 61, "kind": "cash"},
        {"name": "X"},
        {"kind": "cash"},
    ],
)
def test_create_rejects_invalid_bodies(client: TestClient, user_id: str, body: dict[str, str]):
    assert client.post(ACCOUNTS, json=body).status_code == 422


@pytest.mark.parametrize("owner_field", ["user_id", "id", "created_at"])
def test_create_rejects_fields_the_client_must_not_control(
    client: TestClient, user_id: str, owner_field: str
):
    body = {"name": "Nubank", "kind": "cash", owner_field: user_id}

    assert client.post(ACCOUNTS, json=body).status_code == 422


def test_rename_and_retype(client: TestClient, user_id: str):
    account_id = create(client, "Carteira", "cash").json()["id"]

    renamed = client.patch(f"{ACCOUNTS}/{account_id}", json={"name": "Dinheiro"})
    retyped = client.patch(f"{ACCOUNTS}/{account_id}", json={"kind": "checking"})

    assert renamed.json() == {"id": account_id, "name": "Dinheiro", "kind": "cash"}
    assert retyped.json() == {"id": account_id, "name": "Dinheiro", "kind": "checking"}


def test_patching_the_name_to_its_current_value_is_allowed(client: TestClient, user_id: str):
    account_id = create(client, "Carteira", "cash").json()["id"]

    assert client.patch(f"{ACCOUNTS}/{account_id}", json={"name": "Carteira"}).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"kind": None},
        {"kind": "savings"},
        {"user_id": "x"},
        {"name": "", "kind": "cash"},
    ],
)
def test_patch_rejects_empty_null_unknown_and_invalid_bodies(
    client: TestClient, user_id: str, body: dict[str, object]
):
    account_id = create(client).json()["id"]

    assert client.patch(f"{ACCOUNTS}/{account_id}", json=body).status_code == 422


def test_delete_removes_an_empty_account(client: TestClient, user_id: str):
    account_id = create(client).json()["id"]

    response = client.delete(f"{ACCOUNTS}/{account_id}")

    assert response.status_code == 204
    assert names(client) == [DEFAULT_NAME]


# --- business rules -----------------------------------------------------------------------------


def test_creating_a_duplicate_name_is_409_and_leaves_one_account(client: TestClient, user_id: str):
    create(client, "Nubank")

    response = create(client, "Nubank", "cash")

    assert response.status_code == 409
    assert response.json()["code"] == "account_name_taken"
    assert names(client).count("Nubank") == 1


def test_name_uniqueness_is_case_sensitive_like_the_database_constraint(
    client: TestClient, user_id: str
):
    create(client, "Nubank")

    assert create(client, "nubank").status_code == 201


def test_renaming_to_another_accounts_name_is_409_and_keeps_the_old_name(
    client: TestClient, user_id: str
):
    create(client, "Nubank")
    carteira_id = create(client, "Carteira", "cash").json()["id"]

    response = client.patch(f"{ACCOUNTS}/{carteira_id}", json={"name": "Nubank"})

    assert response.status_code == 409
    assert response.json()["code"] == "account_name_taken"
    assert "Carteira" in names(client)


def test_two_users_may_use_the_same_account_name(client: TestClient, other_client: TestClient):
    assert names(client) == names(other_client) == [DEFAULT_NAME]  # both own "Conta principal"

    assert create(client, "Nubank").status_code == 201
    assert create(other_client, "Nubank").status_code == 201


def test_deleting_an_account_with_transactions_is_409_and_keeps_everything(
    client: TestClient, user_id: str, db: Session
):
    user = db.get(User, user_id)
    assert user is not None
    extra = create(client, "Nubank").json()["id"]
    account = db.get(Account, extra)
    assert account is not None
    make_transaction(db, user, account)
    db.commit()

    response = client.delete(f"{ACCOUNTS}/{extra}")

    assert response.status_code == 409
    assert response.json()["code"] == "account_not_empty"
    assert "Nubank" in names(client)


def test_deleting_the_last_account_is_409(client: TestClient, user_id: str):
    only_id = client.get(ACCOUNTS).json()[0]["id"]

    response = client.delete(f"{ACCOUNTS}/{only_id}")

    assert response.status_code == 409
    assert response.json()["code"] == "last_account"
    assert names(client) == [DEFAULT_NAME]


def test_the_default_account_can_be_deleted_once_another_exists(client: TestClient, user_id: str):
    create(client)
    default_id = client.get(ACCOUNTS).json()[0]["id"]

    assert client.delete(f"{ACCOUNTS}/{default_id}").status_code == 204


# --- services used by imports and manual entries ------------------------------------------------


def test_default_account_is_the_oldest_one(db: Session):
    user = make_user(db)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    make_account(db, user, name="Newer", created_at=base + timedelta(days=1))
    oldest = make_account(db, user, name="Older", created_at=base)
    other = make_user(db)
    make_account(db, other, name="Ancient", created_at=base - timedelta(days=9))

    assert accounts_service.get_default_account(db, user).id == oldest.id


def test_default_account_breaks_a_created_at_tie_by_id(db: Session):
    user = make_user(db)
    same_instant = datetime(2026, 1, 1, tzinfo=UTC)
    ids = sorted(make_account(db, user, name=f"A{i}", created_at=same_instant).id for i in range(3))

    assert accounts_service.get_default_account(db, user).id == ids[0]


def test_get_account_or_404_hides_other_users_accounts(db: Session):
    owner, intruder = make_user(db), make_user(db)
    account = make_account(db, owner)

    assert accounts_service.get_account_or_404(db, owner, account.id).id == account.id
    with pytest.raises(AppError) as exc:
        accounts_service.get_account_or_404(db, intruder, account.id)
    assert (exc.value.code, exc.value.status_code) == ("not_found", 404)


# --- isolation ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "body"),
    [("PATCH", {"name": "Hacked"}), ("DELETE", None)],
)
def test_another_users_account_is_404_not_403_and_untouched(
    client: TestClient, other_client: TestClient, method: str, body: dict[str, str] | None
):
    victim_id = create(client, "Nubank").json()["id"]

    response = other_client.request(method, f"{ACCOUNTS}/{victim_id}", json=body)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "Nubank" in names(client)


def test_a_missing_account_looks_exactly_like_another_users_account(
    client: TestClient, other_client: TestClient
):
    victim_id = create(client, "Nubank").json()["id"]

    foreign = other_client.delete(f"{ACCOUNTS}/{victim_id}")
    missing = other_client.delete(f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000")

    assert (foreign.status_code, foreign.json()["message"]) == (
        missing.status_code,
        missing.json()["message"],
    )


def test_the_list_never_shows_another_users_accounts(client: TestClient, other_client: TestClient):
    create(client, "Segredo A")

    assert "Segredo A" not in names(other_client)
    assert names(other_client) == [DEFAULT_NAME]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", ACCOUNTS, None),
        ("POST", ACCOUNTS, {"name": "X", "kind": "cash"}),
        ("PATCH", f"{ACCOUNTS}/x", {"name": "X"}),
        ("DELETE", f"{ACCOUNTS}/x", None),
    ],
)
def test_every_account_route_requires_a_session(
    client: TestClient, method: str, path: str, body: dict[str, str] | None
):
    response = client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
