"""telegram entries and statement reconciliation

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08 09:00:00

Additive only: every new column is nullable or has a server default, so rows that already
exist keep working (they become origin 'import' with nothing reconciled) and code from the
previous revision can still read and write the upgraded database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ACCOUNT_FK = "fk_users_telegram_default_account_id"
CHAT_ID_INDEX = "ix_users_telegram_chat_id"


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(
            sa.Column("origin", sa.String(length=32), nullable=False, server_default="import")
        )
        batch.add_column(sa.Column("note", sa.String(length=255), nullable=True))

    with op.batch_alter_table("imports") as batch:
        batch.add_column(sa.Column("reconciled", sa.Integer(), nullable=False, server_default="0"))

    # On SQLite the new foreign key makes batch mode rebuild `users` (copy, drop, rename).
    # migrations/env.py switches foreign keys off meanwhile, so the drop cascades nowhere.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("telegram_linked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("telegram_default_account_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("telegram_pairing_code_hash", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("telegram_pairing_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            DEFAULT_ACCOUNT_FK,
            "accounts",
            ["telegram_default_account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(CHAT_ID_INDEX, ["telegram_chat_id"], unique=True)

    op.create_table(
        "telegram_pairing_attempts",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Entries logged through Telegram stay as ordinary transactions.
    op.drop_table("telegram_pairing_attempts")

    with op.batch_alter_table("users") as batch:
        batch.drop_index(CHAT_ID_INDEX)
        batch.drop_constraint(DEFAULT_ACCOUNT_FK, type_="foreignkey")
        for column in (
            "telegram_pairing_expires_at",
            "telegram_pairing_code_hash",
            "telegram_default_account_id",
            "telegram_linked_at",
            "telegram_chat_id",
        ):
            batch.drop_column(column)

    with op.batch_alter_table("imports") as batch:
        batch.drop_column("reconciled")

    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("note")
        batch.drop_column("origin")
