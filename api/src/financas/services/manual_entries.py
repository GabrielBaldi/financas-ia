"""Entries the user types in the Telegram bot, stored next to the statement rows.

They go through the same categorization pipeline as an import. When the statement with that
purchase was imported already, no new transaction is created: the entry's text becomes the
note of the statement row instead (see services/reconciliation.py).
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from financas.categorization.pipeline import Categorizer, TransactionText
from financas.models import Account, Origin, Transaction, User
from financas.services.accounts import MANUAL_ACCOUNT_NAME, get_account, get_or_create_account
from financas.services.imports import load_user_rules
from financas.services.reconciliation import (
    USER_DECIDED,
    apply_decision,
    decision_of,
    merged_decision,
    statement_row_for_entry,
)

# Statement rows are deduplicated by a 64-character hex SHA-256. A hash with this prefix can
# never be one of those, and a random id never repeats, so entries never collide with rows.
TELEGRAM_HASH_PREFIX = "telegram:"


@dataclass(frozen=True, slots=True)
class ManualEntry:
    amount_cents: int  # negative = money out, the same convention as statement rows
    description: str
    date: dt.date


@dataclass(frozen=True, slots=True)
class EntryOutcome:
    transaction: Transaction  # the new entry, or the statement row that absorbed it
    account: Account
    already_in_statement: bool


def default_entry_account(session: Session, user: User) -> Account:
    """The account chosen for Telegram entries, or one named 'Lançamentos manuais'."""
    if user.telegram_default_account_id is not None:
        account = get_account(session, user.id, user.telegram_default_account_id)
        if account is not None:
            return account
    return get_or_create_account(session, user.id, MANUAL_ACCOUNT_NAME)


def add_manual_entry(
    session: Session,
    *,
    user: User,
    entry: ManualEntry,
    categorizer: Categorizer,
    account: Account | None = None,
) -> EntryOutcome:
    account = account or default_entry_account(session, user)
    description = entry.description.strip()[:255]
    statement = statement_row_for_entry(
        session,
        user_id=user.id,
        account_id=account.id,
        amount_cents=entry.amount_cents,
        day=entry.date,
    )
    # If the statement row's category is the user's own choice it stays, so the AI is not asked.
    ask_ai = statement is None or statement.categorized_by not in USER_DECIDED
    decision = categorizer.categorize(
        [TransactionText(description, entry.amount_cents, ask_ai=ask_ai)],
        load_user_rules(session, user.id),
    ).decisions[0]

    if statement is not None:
        apply_decision(statement, merged_decision(decision_of(statement), decision))
        statement.note = description
        session.commit()
        return EntryOutcome(statement, account, already_in_statement=True)

    transaction = Transaction(
        user_id=user.id,
        account_id=account.id,
        date=entry.date,
        description=description,
        amount_cents=entry.amount_cents,
        dedup_hash=TELEGRAM_HASH_PREFIX + uuid.uuid4().hex,
        origin=Origin.TELEGRAM,
    )
    apply_decision(transaction, decision)
    session.add(transaction)
    session.commit()
    return EntryOutcome(transaction, account, already_in_statement=False)


def undo_last_entry(session: Session, user_id: int) -> Transaction | None:
    """Delete the newest entry still waiting for its statement row. Merged ones stay put."""
    entry = session.scalar(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.origin == Origin.TELEGRAM)
        .order_by(Transaction.id.desc())
        .limit(1)
    )
    if entry is not None:
        session.delete(entry)
        session.commit()
    return entry


def recent_entries(session: Session, user_id: int, limit: int = 5) -> Sequence[Transaction]:
    """Telegram entries, pending or already merged into a statement row (those have a note)."""
    return session.scalars(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            or_(Transaction.origin == Origin.TELEGRAM, Transaction.note.is_not(None)),
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
    ).all()
