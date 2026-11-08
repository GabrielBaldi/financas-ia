"""Reviewing transactions: filtering, manual corrections and rules learned from them."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from financas.categories import Category, Source
from financas.categorization.user_rules import match_user_rules
from financas.models import Rule, Transaction
from financas.services.imports import load_user_rules
from financas.services.months import month_bounds
from financas.text import contains_phrase, normalize


@dataclass(frozen=True, slots=True)
class TransactionFilter:
    month: str | None = None
    category: Category | None = None
    only_to_review: bool = False


def list_transactions(
    session: Session, user_id: int, filters: TransactionFilter, limit: int, offset: int
) -> tuple[Sequence[Transaction], int]:
    query = select(Transaction).where(Transaction.user_id == user_id)
    if filters.month:
        start, end = month_bounds(filters.month)
        query = query.where(Transaction.date >= start, Transaction.date < end)
    if filters.category:
        query = query.where(Transaction.category == filters.category)
    if filters.only_to_review:
        query = query.where(Transaction.category.is_(None))

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(
        query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset)
    ).all()
    return items, total


def available_months(session: Session, user_id: int) -> list[str]:
    year = extract("year", Transaction.date)
    month = extract("month", Transaction.date)
    rows = session.execute(
        select(year, month)
        .where(Transaction.user_id == user_id)
        .distinct()
        .order_by(year.desc(), month.desc())
    ).all()
    return [f"{int(y):04d}-{int(m):02d}" for y, m in rows]


def get_transaction(session: Session, user_id: int, transaction_id: int) -> Transaction | None:
    return session.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )


def set_category(session: Session, transaction: Transaction, category: Category) -> None:
    transaction.category = category
    transaction.categorized_by = Source.MANUAL
    transaction.confidence = None
    transaction.suggested_category = None
    session.commit()


def matching_transactions(session: Session, user_id: int, pattern: str) -> list[Transaction]:
    """Transactions whose description contains the pattern. Manual choices are never touched."""
    candidates = session.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id, Transaction.categorized_by != Source.MANUAL
        )
    )
    return [t for t in candidates if contains_phrase(normalize(t.description), pattern)]


def save_rule(session: Session, user_id: int, pattern: str, category: Category) -> tuple[Rule, int]:
    """Create (or update) a rule and re-categorize the existing transactions it covers.

    Returns the rule and how many transactions changed. The winner for each transaction is
    computed with all of the user's rules, exactly as the pipeline does on the next import.
    """
    pattern = normalize(pattern)
    rule = session.scalar(select(Rule).where(Rule.user_id == user_id, Rule.pattern == pattern))
    if rule is None:
        rule = Rule(user_id=user_id, pattern=pattern, category=category)
        session.add(rule)
    else:
        rule.category = category
    session.flush()

    user_rules = load_user_rules(session, user_id)
    changed = 0
    for transaction in matching_transactions(session, user_id, pattern):
        winner = match_user_rules(normalize(transaction.description), user_rules)
        if winner is None:
            continue
        if transaction.category != winner or transaction.categorized_by != Source.USER_RULE:
            changed += 1
        transaction.category = winner
        transaction.categorized_by = Source.USER_RULE
        transaction.confidence = None
        transaction.suggested_category = None
    session.commit()
    return rule, changed


def list_rules(session: Session, user_id: int) -> Sequence[Rule]:
    return session.scalars(
        select(Rule).where(Rule.user_id == user_id).order_by(Rule.created_at.desc(), Rule.id.desc())
    ).all()


def delete_rule(session: Session, user_id: int, rule_id: int) -> bool:
    """Existing transactions keep their category; only future imports are affected."""
    rule = session.scalar(select(Rule).where(Rule.id == rule_id, Rule.user_id == user_id))
    if rule is None:
        return False
    session.delete(rule)
    session.commit()
    return True
