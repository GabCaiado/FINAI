from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import messages
from app.errors import AppError
from app.models import Account, Transaction, User
from app.schemas.accounts import AccountIn, AccountPatch

_OLDEST_FIRST = (Account.created_at, Account.id)  # id breaks ties within the same second


def list_accounts(db: Session, user: User) -> list[Account]:
    return list(
        db.scalars(select(Account).where(Account.user_id == user.id).order_by(*_OLDEST_FIRST))
    )


def get_default_account(db: Session, user: User) -> Account:
    """The user's oldest account. One always exists: registration creates it and the last
    account cannot be deleted, so a missing one is a broken invariant (surfaces as a 500)."""
    query = select(Account).where(Account.user_id == user.id).order_by(*_OLDEST_FIRST).limit(1)
    return db.scalars(query).one()


def get_account_or_404(db: Session, user: User, account_id: str) -> Account:
    """Another user's account is indistinguishable from a missing one (404, never 403)."""
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user.id))
    if account is None:
        raise AppError("not_found", messages.NOT_FOUND, 404)
    return account


def create_account(db: Session, user: User, data: AccountIn, now: datetime) -> Account:
    # created_at is set from ``now`` (microseconds) rather than the database default, whose
    # resolution can be a whole second: "oldest account" must be unambiguous.
    account = Account(user_id=user.id, name=data.name, kind=data.kind, created_at=now)
    db.add(account)
    _commit_or_name_taken(db)
    return account


def rename_or_retype_account(
    db: Session, user: User, account_id: str, patch: AccountPatch
) -> Account:
    account = get_account_or_404(db, user, account_id)
    for field in patch.model_fields_set:
        setattr(account, field, getattr(patch, field))
    _commit_or_name_taken(db)
    return account


def delete_account(db: Session, user: User, account_id: str) -> None:
    account = get_account_or_404(db, user, account_id)
    if _count_accounts(db, user) == 1:
        raise AppError("last_account", messages.LAST_ACCOUNT, 409)
    if _count_transactions(db, user, account) > 0:
        raise AppError("account_not_empty", messages.ACCOUNT_NOT_EMPTY, 409)
    db.delete(account)
    db.commit()


def _count_accounts(db: Session, user: User) -> int:
    query = select(func.count()).select_from(Account).where(Account.user_id == user.id)
    return db.scalar(query) or 0


def _count_transactions(db: Session, user: User, account: Account) -> int:
    query = (
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == user.id, Transaction.account_id == account.id)
    )
    return db.scalar(query) or 0


def _commit_or_name_taken(db: Session) -> None:
    """Uniqueness is the database's job (UNIQUE(user_id, name)): no check-then-write race."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("account_name_taken", messages.ACCOUNT_NAME_TAKEN, 409) from None
