"""Store a parsed statement: skip rows already imported, categorize the rest, keep the stats."""

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
from financas.models import Account, ImportBatch, Rule, Transaction
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


def get_or_create_account(session: Session, user_id: int, name: str) -> Account:
    name = name.strip()
    account = session.scalar(
        select(Account).where(Account.user_id == user_id, Account.name == name)
    )
    if account is None:
        account = Account(user_id=user_id, name=name)
        session.add(account)
        session.flush()
    return account


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
    pricing: AIPricing,
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

    result = categorizer.categorize(
        [TransactionText(row.description, row.amount_cents) for row, _ in new_rows],
        load_user_rules(session, user_id),
    )
    sources = Counter(decision.source for decision in result.decisions)

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
        ai_cost_usd=pricing.cost_usd(result.usage),
    )
    session.add(batch)
    session.flush()
    session.add_all(
        Transaction(
            user_id=user_id,
            account_id=account.id,
            import_id=batch.id,
            date=row.date,
            description=row.description[:255],
            amount_cents=row.amount_cents,
            category=decision.category,
            categorized_by=decision.source,
            confidence=decision.confidence,
            suggested_category=decision.suggestion,
            dedup_hash=row_hash,
        )
        for (row, row_hash), decision in zip(new_rows, result.decisions, strict=True)
    )
    session.commit()
    return batch


def list_imports(session: Session, user_id: int) -> Sequence[ImportBatch]:
    return session.scalars(
        select(ImportBatch)
        .where(ImportBatch.user_id == user_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    ).all()
