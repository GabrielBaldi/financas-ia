"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-08 05:10:54
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _user_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        _user_fk(),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk(),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])

    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk(),
        sa.UniqueConstraint("user_id", "pattern"),
    )
    op.create_index("ix_rules_user_id", "rules", ["user_id"])

    op.create_table(
        "imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("by_user_rule", sa.Integer(), nullable=False),
        sa.Column("by_keyword", sa.Integer(), nullable=False),
        sa.Column("by_ai", sa.Integer(), nullable=False),
        sa.Column("to_review", sa.Integer(), nullable=False),
        sa.Column("ai_input_tokens", sa.Integer(), nullable=False),
        sa.Column("ai_output_tokens", sa.Integer(), nullable=False),
        sa.Column("ai_cost_usd", sa.Float(), nullable=False),
        _user_fk(),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_imports_user_id", "imports", ["user_id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("categorized_by", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("suggested_category", sa.String(length=32), nullable=True),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        _user_fk(),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["import_id"], ["imports.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("account_id", "dedup_hash"),
    )
    op.create_index("ix_transactions_user_date", "transactions", ["user_id", "date"])


def downgrade() -> None:
    for table in ("transactions", "imports", "rules", "auth_tokens", "accounts", "users"):
        op.drop_table(table)
