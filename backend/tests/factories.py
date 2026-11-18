"""Small builders for tests. They create valid rows; tests override the field under test."""

from datetime import UTC, date, datetime
from itertools import count

from sqlalchemy.orm import Session

from app.models import Account, Transaction, User

_seq = count(1)


def make_user(db: Session, **overrides: object) -> User:
    n = next(_seq)
    user = User(
        email=f"user{n}@example.com",
        password_hash="x",
        name=f"User {n}",
        consent_at=datetime.now(UTC),
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    db.add(user)
    db.flush()
    return user


def make_account(db: Session, user: User, **overrides: object) -> Account:
    account = Account(user_id=user.id, name=f"Conta {next(_seq)}", kind="checking")
    for key, value in overrides.items():
        setattr(account, key, value)
    db.add(account)
    db.flush()
    return account


def make_transaction(db: Session, user: User, account: Account, **overrides: object) -> Transaction:
    n = next(_seq)
    fields: dict[str, object] = {
        "user_id": user.id,
        "account_id": account.id,
        "date": date(2026, 11, 1),
        "description_raw": "PADARIA X",
        "description_clean": "PADARIA X",
        "merchant": "Padaria",
        "merchant_key": "PADARIA X",
        "amount_cents": -1500,
        "category": "Alimentação",
        "category_source": "rule",
        "confidence": 0.95,
        "status": "confirmed",
        "dedupe_hash": f"hash-{n}",
    }
    fields.update(overrides)
    tx = Transaction(**fields)
    db.add(tx)
    db.flush()
    return tx


def register_payload(**overrides: object) -> dict[str, object]:
    """A valid body for POST /api/auth/register; tests override the field under test."""
    payload: dict[str, object] = {
        "email": f"person{next(_seq)}@example.com",
        "password": "correct-horse-battery",
        "name": "Pessoa Teste",
        "consent": True,
    }
    payload.update(overrides)
    return payload
