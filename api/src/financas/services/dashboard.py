"""Aggregates for the dashboard, in portable SQL (the same queries run on SQLite and Postgres)."""

from sqlalchemy import ColumnElement, case, extract, func, or_, select
from sqlalchemy.orm import Session

from financas.categories import NOT_CASH_FLOW
from financas.models import Transaction
from financas.schemas import CategoryTotal, DashboardOut, MonthTotal
from financas.services.months import month_bounds, recent_months

CHART_MONTHS = 6


def _counts_as_cash_flow() -> ColumnElement[bool]:
    # `category NOT IN (...)` is NULL for uncategorized rows, so they must be included explicitly.
    return or_(Transaction.category.is_(None), Transaction.category.not_in(NOT_CASH_FLOW))


def spending_by_category(session: Session, user_id: int, month: str) -> list[CategoryTotal]:
    start, end = month_bounds(month)
    rows = session.execute(
        select(Transaction.category, func.sum(Transaction.amount_cents))
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.amount_cents < 0,
            _counts_as_cash_flow(),
        )
        .group_by(Transaction.category)
    ).all()
    totals = [CategoryTotal(category=category, total_cents=-int(total)) for category, total in rows]
    return sorted(totals, key=lambda item: item.total_cents, reverse=True)


def monthly_totals(session: Session, user_id: int, last_month: str) -> list[MonthTotal]:
    months = recent_months(last_month, CHART_MONTHS)
    start, _ = month_bounds(months[0])
    _, end = month_bounds(last_month)

    year = extract("year", Transaction.date)
    month = extract("month", Transaction.date)
    amount = Transaction.amount_cents
    expenses = func.sum(case((amount < 0, -amount), else_=0))
    income = func.sum(case((amount > 0, amount), else_=0))
    rows = session.execute(
        select(year, month, expenses, income)
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start,
            Transaction.date < end,
            _counts_as_cash_flow(),
        )
        .group_by(year, month)
    ).all()

    found: dict[str, MonthTotal] = {}
    for y, m, spent, received in rows:
        key = f"{int(y):04d}-{int(m):02d}"
        found[key] = MonthTotal(month=key, expenses_cents=int(spent), income_cents=int(received))
    return [
        found.get(key, MonthTotal(month=key, expenses_cents=0, income_cents=0)) for key in months
    ]


def build_dashboard(session: Session, user_id: int, month: str) -> DashboardOut:
    monthly = monthly_totals(session, user_id, month)
    current = monthly[-1]
    return DashboardOut(
        month=month,
        expenses_cents=current.expenses_cents,
        income_cents=current.income_cents,
        by_category=spending_by_category(session, user_id, month),
        monthly=monthly,
    )
