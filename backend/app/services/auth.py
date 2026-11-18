from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import messages
from app.errors import AppError
from app.models import Account, User
from app.schemas.auth import RegisterIn
from app.security import DUMMY_PASSWORD_HASH, hash_password, verify_password


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, data: RegisterIn, now: datetime) -> User:
    """Create the user and the default account in one transaction.

    Uniqueness is left to the database: check-then-insert would race between two requests.
    """
    if not data.consent:
        raise AppError("consent_required", messages.CONSENT_REQUIRED, 400)
    user = User(
        email=normalize_email(data.email),
        password_hash=hash_password(data.password),
        name=data.name,
        consent_at=now,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError("email_already_registered", messages.EMAIL_ALREADY_REGISTERED, 409) from None
    default_account = Account(
        user_id=user.id, name=messages.DEFAULT_ACCOUNT_NAME, kind="checking", created_at=now
    )
    db.add(default_account)
    db.commit()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # Always verify, even for an unknown e-mail, so both failures take the same time.
    stored_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_matches = verify_password(stored_hash, password)
    if user is None or not password_matches:
        raise AppError("invalid_credentials", messages.INVALID_CREDENTIALS, 401)
    return user


def delete_user(db: Session, user: User) -> None:
    """Delete the user; the database cascades to every row they own (LGPD erasure)."""
    db.delete(user)
    db.commit()
