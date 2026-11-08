import datetime as dt
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Dialect,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from financas.categories import Category, Source
from financas.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """Stores datetimes in UTC and always reads them back timezone-aware.

    SQLite has no timezone support and returns naive datetimes otherwise.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def enum_column[E: StrEnum](enum_type: type[E]) -> Enum:
    """A portable VARCHAR column that stores the enum *value* (e.g. 'mercado'), not its name."""
    return Enum(
        enum_type,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class Rule(Base):
    """A user rule: descriptions containing `pattern` (normalized) get `category`."""

    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("user_id", "pattern"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pattern: Mapped[str] = mapped_column(String(120))
    category: Mapped[Category] = mapped_column(enum_column(Category))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class ImportBatch(Base):
    """One uploaded statement, with a snapshot of how the pipeline categorized it."""

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    total_rows: Mapped[int]
    inserted: Mapped[int]
    duplicates: Mapped[int]
    by_user_rule: Mapped[int]
    by_keyword: Mapped[int]
    by_ai: Mapped[int]
    to_review: Mapped[int]
    ai_input_tokens: Mapped[int]
    ai_output_tokens: Mapped[int]
    ai_cost_usd: Mapped[float] = mapped_column(Float)

    account: Mapped[Account] = relationship(lazy="joined")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "dedup_hash"),
        Index("ix_transactions_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    import_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"))
    date: Mapped[dt.date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255))
    # Money is stored as integer cents: exact arithmetic and the same type on SQLite and Postgres.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    category: Mapped[Category | None] = mapped_column(enum_column(Category))
    categorized_by: Mapped[Source] = mapped_column(enum_column(Source))
    confidence: Mapped[float | None] = mapped_column(Float)
    suggested_category: Mapped[Category | None] = mapped_column(enum_column(Category))
    dedup_hash: Mapped[str] = mapped_column(String(64))
