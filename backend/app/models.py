"""SQLAlchemy models (schema owned by Alembic: see ``migrations/``).

Invariants are enforced by the database, not only by application code:
CHECK constraints for enums and numeric ranges, UNIQUE constraints for dedupe and
per-user rules, and ON DELETE CASCADE so ``DELETE /me`` leaves no row behind.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Allowed values for string "enums". Kept as tuples so schema, API and tests share them.
ACCOUNT_KINDS = ("checking", "credit_card", "cash")
FILE_TYPES = ("csv", "pdf", "ofx")
BATCH_STATUSES = ("processing", "staged", "confirmed", "discarded", "failed")
TRANSACTION_STATUSES = ("staged", "confirmed")
# "pending": waiting for the LLM layer of an import that is still processing.
CATEGORY_SOURCES = ("user", "rule", "llm", "manual", "pending")
RECURRING_KINDS = ("income", "fixed_expense")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    """Where transactions live (checking account, credit card, cash). Dedupe is scoped per
    account, and card-bill payments are not counted twice (see ARCHITECTURE section 11)."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        CheckConstraint(_in("kind", ACCOUNT_KINDS), name="kind"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(_in("file_type", FILE_TYPES), name="file_type"),
        CheckConstraint(_in("status", BATCH_STATUSES), name="status"),
        CheckConstraint(
            "total_rows >= 0 AND classified_rows >= 0 AND classified_rows <= total_rows",
            name="progress",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String)  # raw file itself is never stored
    file_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="processing")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    classified_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """``amount_cents`` is signed (negative = expense) and is the only source of truth for
    income vs expense: there is deliberately no ``type`` column."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "dedupe_hash"),
        UniqueConstraint("account_id", "external_id"),  # OFX FITID; NULLs never collide
        CheckConstraint("amount_cents <> 0", name="amount_nonzero"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(_in("status", TRANSACTION_STATUSES), name="status"),
        CheckConstraint(_in("category_source", CATEGORY_SOURCES), name="category_source"),
        # Sign rules: "Renda" never on expenses; income only Renda/Transferências/Outros.
        CheckConstraint(
            "NOT (amount_cents < 0 AND category = 'Renda')"
            " AND (amount_cents < 0 OR category IN ('Renda', 'Transferências', 'Outros'))",
            name="sign_category",
        ),
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_user_status_date", "user_id", "status", "date"),
        Index("ix_transactions_batch", "batch_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # user_id is redundant with account -> user on purpose: every query filters on it
    # (isolation), and tests assert both always agree.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date)
    description_raw: Mapped[str] = mapped_column(String)
    description_clean: Mapped[str] = mapped_column(String)
    merchant: Mapped[str] = mapped_column(String, default="")
    merchant_key: Mapped[str] = mapped_column(String, default="")  # user memory + recurring
    amount_cents: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String)
    suggested_category: Mapped[str | None] = mapped_column(String, nullable=True)
    category_source: Mapped[str] = mapped_column(String, default="pending")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    # Movement between the user's own accounts or a card-bill payment: excluded from income and
    # expense totals so it is not counted twice. PIX to third parties is NOT internal.
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="staged")
    # sha256(account|date|amount|description_clean|occurrence): see ARCHITECTURE section 9.
    dedupe_hash: Mapped[str] = mapped_column(String)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def type(self) -> str:
        return "income" if self.amount_cents > 0 else "expense"


class UserRule(Base):
    """Learned preferences (objective 6): merchant_key -> category, per user."""

    __tablename__ = "user_rules"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_key: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecurringItem(Base):
    __tablename__ = "recurring_items"
    __table_args__ = (
        CheckConstraint(_in("kind", RECURRING_KINDS), name="kind"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("day_of_month BETWEEN 1 AND 28", name="day_of_month"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String)
    day_of_month: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("target_cents > 0", name="target_positive"),
        CheckConstraint("saved_cents >= 0", name="saved_non_negative"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    target_cents: Mapped[int] = mapped_column(Integer)
    saved_cents: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmCache(Base):
    """Global cache of LLM answers keyed by (masked cleaned description, prompt version), so
    changing the prompt or category list invalidates old answers."""

    __tablename__ = "llm_cache"
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),)

    description_clean: Mapped[str] = mapped_column(String, primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    merchant: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmUsage(Base):
    """Per-user, per-day rows sent to the LLM (cost guard)."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "day"),
        CheckConstraint("rows_sent >= 0", name="rows_non_negative"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    rows_sent: Mapped[int] = mapped_column(Integer, default=0)
