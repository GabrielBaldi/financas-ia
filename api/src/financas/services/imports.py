"""Store a parsed statement: skip rows already imported, categorize the rest, keep the stats.

New rows that turn out to be purchases already logged through Telegram absorb those entries
(see services/reconciliation.py), so nothing is counted twice.
"""

import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.categories import Source
from financas.categorization.ai import TokenUsage
from financas.categorization.pipeline import Categorizer, TransactionText
from financas.categorization.user_rules import UserRule
from financas.importers import ParsedRow
from financas.models import ImportBatch, Origin, Rule, Transaction
from financas.services.accounts import get_or_create_account
from financas.services.reconciliation import (
    apply_decision,
    decision_of,
    entries_for_statement_rows,
    merged_decision,
)
from financas.text import normalize


@dataclass(frozen=True, slots=True)
class AIPricing:
    input_per_mtok: float
    output_per_mtok: float

    def cost_usd(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * self.input_per_mtok + usage.output_tokens * self.output_per_mtok
        ) / 1_000_000


def dedup_hashes(rows: Sequence[ParsedRow]) -> list[str]:
    """Hash date + amount + normalized description, so importing a file twice adds nothing.

    Identical rows inside one file (two R$ 5,00 coffees on the same day) get an occurrence
    number: both are kept the first time and both are recognized as duplicates the second time.
    """
    occurrences: Counter[str] = Counter()
    hashes = []
    for row in rows:
        key = f"{row.date.isoformat()}|{row.amount_cents}|{normalize(row.description)}"
        occurrences[key] += 1
        hashes.append(hashlib.sha256(f"{key}|{occurrences[key]}".encode()).hexdigest())
    return hashes


def load_user_rules(session: Session, user_id: int) -> list[UserRule]:
    rules = session.scalars(select(Rule).where(Rule.user_id == user_id))
    return [UserRule(rule.pattern, rule.category) for rule in rules]


def import_rows(
    session: Session,
    *,
    user_id: int,
    account_name: str,
    filename: str,
    file_format: str,
    rows: Sequence[ParsedRow],
    categorizer: Categorizer,
    pricing: AIPricing | None,
) -> ImportBatch:
    account = get_or_create_account(session, user_id, account_name)
    hashes = dedup_hashes(rows)
    already_imported = set(
        session.scalars(
            select(Transaction.dedup_hash).where(
                Transaction.account_id == account.id, Transaction.dedup_hash.in_(hashes)
            )
        )
    )
    new_rows = [
        (row, row_hash)
        for row, row_hash in zip(rows, hashes, strict=True)
        if row_hash not in already_imported
    ]

    entries = entries_for_statement_rows(
        session, user_id=user_id, account_id=account.id, rows=[row for row, _ in new_rows]
    )
    result = categorizer.categorize(
        [
            # The AI is only asked about a matched row when the entry has no category to give.
            TransactionText(
                row.description,
                row.amount_cents,
                ask_ai=index not in entries or entries[index].category is None,
            )
            for index, (row, _) in enumerate(new_rows)
        ],
        load_user_rules(session, user_id),
    )
    decisions = [
        merged_decision(decision, decision_of(entries[index])) if index in entries else decision
        for index, decision in enumerate(result.decisions)
    ]
    sources = Counter(decision.source for decision in decisions)

    batch = ImportBatch(
        user_id=user_id,
        account=account,
        filename=filename,
        file_format=file_format,
        total_rows=len(rows),
        inserted=len(new_rows),
        duplicates=len(rows) - len(new_rows),
        by_user_rule=sources[Source.USER_RULE],
        by_keyword=sources[Source.KEYWORD],
        by_ai=sources[Source.AI],
        to_review=sources[Source.REVIEW],
        ai_input_tokens=result.usage.input_tokens,
        ai_output_tokens=result.usage.output_tokens,
        # Without a price (NVIDIA's hosted API) the cost is recorded as 0, not guessed.
        ai_cost_usd=pricing.cost_usd(result.usage) if pricing is not None else 0.0,
        reconciled=len(entries),
    )
    session.add(batch)
    session.flush()
    for index, ((row, row_hash), decision) in enumerate(zip(new_rows, decisions, strict=True)):
        transaction = Transaction(
            user_id=user_id,
            account_id=account.id,
            import_id=batch.id,
            date=row.date,
            description=row.description[:255],
            amount_cents=row.amount_cents,
            dedup_hash=row_hash,
            origin=Origin.IMPORT,
        )
        apply_decision(transaction, decision)
        if entry := entries.get(index):
            transaction.note = entry.description
            session.delete(entry)
        session.add(transaction)
    session.commit()
    return batch


def list_imports(session: Session, user_id: int) -> Sequence[ImportBatch]:
    return session.scalars(
        select(ImportBatch)
        .where(ImportBatch.user_id == user_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    ).all()
