from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Account, Goal, ImportBatch, RecurringItem, Transaction, User, UserRule
from tests.factories import make_account, make_transaction, make_user


def _rejects(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_sign_is_the_only_source_of_income_vs_expense(db: Session):
    user = make_user(db)
    account = make_account(db, user)
    income = make_transaction(db, user, account, amount_cents=5000, category="Renda")
    expense = make_transaction(db, user, account, amount_cents=-5000)
    assert (income.type, expense.type) == ("income", "expense")


@pytest.mark.parametrize(
    "fields",
    [
        {"amount_cents": 0},  # zero-value rows are meaningless
        {"amount_cents": -100, "category": "Renda"},  # Renda never on an expense
        {"amount_cents": 100, "category": "Mercado"},  # income only Renda/Transferências/Outros
        {"confidence": 1.5},
        {"status": "weird"},
        {"category_source": "magic"},
    ],
)
def test_transaction_check_constraints(db: Session, fields: dict[str, object]):
    user = make_user(db)
    account = make_account(db, user)
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            date=date(2026, 11, 1),
            description_raw="X",
            description_clean="X",
            amount_cents=fields.get("amount_cents", -100),
            category=fields.get("category", "Outros"),
            dedupe_hash="h",
            **{k: v for k, v in fields.items() if k not in {"amount_cents", "category"}},
        )
    )
    _rejects(db)


def test_dedupe_hash_is_unique_per_account_not_global(db: Session):
    user = make_user(db)
    a1, a2 = make_account(db, user), make_account(db, user)
    make_transaction(db, user, a1, dedupe_hash="same")
    make_transaction(db, user, a2, dedupe_hash="same")  # other account: fine
    with pytest.raises(IntegrityError):  # factories flush immediately
        make_transaction(db, user, a1, dedupe_hash="same")
    db.rollback()


def test_external_id_unique_per_account_and_nulls_never_collide(db: Session):
    user = make_user(db)
    account = make_account(db, user)
    make_transaction(db, user, account, external_id=None)
    make_transaction(db, user, account, external_id=None)  # many NULLs allowed
    make_transaction(db, user, account, external_id="FITID-1")
    with pytest.raises(IntegrityError):
        make_transaction(db, user, account, external_id="FITID-1")
    db.rollback()


def test_email_must_be_lowercase(db: Session):
    with pytest.raises(IntegrityError):
        make_user(db, email="Maria@Example.com")
    db.rollback()


def test_user_rule_is_unique_per_user_and_merchant(db: Session):
    user = make_user(db)
    db.add_all(
        [
            UserRule(user_id=user.id, merchant_key="PADARIA X", category="Alimentação"),
            UserRule(user_id=user.id, merchant_key="PADARIA X", category="Mercado"),
        ]
    )
    _rejects(db)


@pytest.mark.parametrize("day", [0, 29])
def test_recurring_item_day_of_month_range(db: Session, day: int):
    user = make_user(db)
    db.add(
        RecurringItem(
            user_id=user.id,
            name="Aluguel",
            kind="fixed_expense",
            amount_cents=100000,
            category="Moradia",
            day_of_month=day,
        )
    )
    _rejects(db)


def test_goal_target_must_be_positive(db: Session):
    user = make_user(db)
    db.add(Goal(user_id=user.id, name="Viagem", target_cents=0, deadline=date(2027, 1, 1)))
    _rejects(db)


def test_account_name_is_unique_per_user_and_kind_is_checked(db: Session):
    user = make_user(db)
    db.add_all(
        [
            Account(user_id=user.id, name="Nubank", kind="checking"),
            Account(user_id=user.id, name="Nubank", kind="credit_card"),
        ]
    )
    _rejects(db)
    user = make_user(db)
    db.add(Account(user_id=user.id, name="X", kind="crypto"))
    _rejects(db)


def test_deleting_a_user_cascades_to_every_table(db: Session):
    user = make_user(db)
    account = make_account(db, user)
    batch = ImportBatch(user_id=user.id, account_id=account.id, filename="e.csv", file_type="csv")
    db.add(batch)
    db.flush()
    make_transaction(db, user, account, batch_id=batch.id)
    db.add(UserRule(user_id=user.id, merchant_key="K", category="Outros"))
    db.add(Goal(user_id=user.id, name="G", target_cents=1, deadline=date(2027, 1, 1)))
    db.commit()

    other = make_user(db)
    other_account = make_account(db, other)
    make_transaction(db, other, other_account)
    db.commit()

    db.delete(db.get(User, user.id))
    db.commit()

    for model in (Account, ImportBatch, Transaction, UserRule, Goal):
        assert (
            db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id)) == 0
        )
    # Another user's data is untouched.
    assert db.scalar(select(func.count()).select_from(Transaction)) == 1


def test_transaction_user_matches_account_owner_factory_invariant(db: Session):
    """Documented invariant: transactions.user_id equals accounts.user_id. Services must
    always derive both from the authenticated user; this guards the factories we test with."""
    user = make_user(db)
    account = make_account(db, user)
    tx = make_transaction(db, user, account)
    assert tx.user_id == account.user_id
