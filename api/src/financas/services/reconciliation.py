"""Telegram entries and statement rows that are the same money.

An entry typed in Telegram and a statement row match when they belong to the same user and
account, have exactly the same amount and are at most 3 days apart (a card purchase can post a
day or two later). Each side matches at most once. When there is a choice, the closest dates
pair first; a tie goes to the older date, then to the row created first (lowest id), so the
result never depends on query order.

The statement row is what stays: it is the bank's record, keeps its date and description, and
gets the entry's text as `note`. Which category it keeps is decided by `merged_decision`.
"""

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.categories import Source
from financas.categorization.pipeline import Decision
from financas.importers import ParsedRow
from financas.models import Origin, Transaction

MAX_DAYS_APART = 3

# Categories the user chose (by hand or with a rule) are never replaced by a guess.
USER_DECIDED = frozenset({Source.MANUAL, Source.USER_RULE})


def decision_of(transaction: Transaction) -> Decision:
    return Decision(
        transaction.category,
        transaction.categorized_by,
        transaction.confidence,
        transaction.suggested_category,
    )


def apply_decision(transaction: Transaction, decision: Decision) -> None:
    transaction.category = decision.category
    transaction.categorized_by = decision.source
    transaction.confidence = decision.confidence
    transaction.suggested_category = decision.suggestion


def merged_decision(statement: Decision, entry: Decision) -> Decision:
    """The category a statement row keeps after absorbing a Telegram entry.

    The user's own choices come first: a manual choice on either side, then a user rule that
    decided the statement row. Otherwise the entry wins (the user's words say more than
    'PAG*XYZ'), unless the pipeline could not categorize it.
    """
    if statement.source is Source.MANUAL:
        return statement
    if entry.source is Source.MANUAL:
        return entry
    if statement.source is Source.USER_RULE or entry.category is None:
        return statement
    return entry


def _days_apart(first: dt.date, second: dt.date) -> int:
    return abs((first - second).days)


def statement_row_for_entry(
    session: Session, *, user_id: int, account_id: int, amount_cents: int, day: dt.date
) -> Transaction | None:
    """The imported row a new Telegram entry describes, if the statement already has it.

    Rows that already carry a note have absorbed another entry, so they are not candidates.
    """
    window = dt.timedelta(days=MAX_DAYS_APART)
    candidates = session.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.amount_cents == amount_cents,
            Transaction.origin == Origin.IMPORT,
            Transaction.note.is_(None),
            Transaction.date >= day - window,
            Transaction.date <= day + window,
        )
    )
    return min(
        candidates,
        key=lambda row: (_days_apart(row.date, day), row.date, row.id),
        default=None,
    )


def entries_for_statement_rows(
    session: Session, *, user_id: int, account_id: int, rows: Sequence[ParsedRow]
) -> dict[int, Transaction]:
    """Pair new statement rows (by index) with the Telegram entries they turn out to be.

    Greedy over every candidate pair, closest dates first: with entries on the 10th and 11th
    and statement rows on the 11th and 12th, the 11th pairs with the 11th, then 10th with 12th.
    """
    if not rows:
        return {}
    window = dt.timedelta(days=MAX_DAYS_APART)
    entries = session.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.origin == Origin.TELEGRAM,
            Transaction.amount_cents.in_(sorted({row.amount_cents for row in rows})),
            Transaction.date >= min(row.date for row in rows) - window,
            Transaction.date <= max(row.date for row in rows) + window,
        )
    ).all()

    candidates = sorted(
        (
            (index, entry)
            for index, row in enumerate(rows)
            for entry in entries
            if entry.amount_cents == row.amount_cents
            and _days_apart(row.date, entry.date) <= MAX_DAYS_APART
        ),
        key=lambda pair: (
            _days_apart(rows[pair[0]].date, pair[1].date),
            pair[1].date,
            pair[1].id,
            pair[0],
        ),
    )
    pairs: dict[int, Transaction] = {}
    used_entries: set[int] = set()
    for index, entry in candidates:
        if index in pairs or entry.id in used_entries:
            continue
        pairs[index] = entry
        used_entries.add(entry.id)
    return pairs
