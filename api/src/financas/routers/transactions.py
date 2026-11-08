from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from financas.categories import Category
from financas.categorization.user_rules import suggest_pattern
from financas.deps import CurrentUser, SessionDep
from financas.models import Transaction
from financas.schemas import CategoryUpdate, SimilarOut, TransactionOut, TransactionPage
from financas.services.months import MONTH_PATTERN
from financas.services.transactions import (
    TransactionFilter,
    available_months,
    get_transaction,
    list_transactions,
    matching_transactions,
    set_category,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _owned_or_404(session: Session, user_id: int, transaction_id: int) -> Transaction:
    transaction = get_transaction(session, user_id, transaction_id)
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transação não encontrada.")
    return transaction


@router.get("")
def search_transactions(
    user: CurrentUser,
    session: SessionDep,
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN, examples=["2026-10"])] = None,
    category: Category | None = None,
    to_review: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    filters = TransactionFilter(month=month, category=category, only_to_review=to_review)
    items, total = list_transactions(session, user.id, filters, limit, offset)
    return TransactionPage(items=[TransactionOut.model_validate(t) for t in items], total=total)


@router.get("/months")
def months_with_data(user: CurrentUser, session: SessionDep) -> list[str]:
    """Months that have transactions, newest first ('AAAA-MM')."""
    return available_months(session, user.id)


@router.patch("/{transaction_id}")
def change_category(
    transaction_id: int, body: CategoryUpdate, user: CurrentUser, session: SessionDep
) -> TransactionOut:
    transaction = _owned_or_404(session, user.id, transaction_id)
    set_category(session, transaction, body.category)
    return TransactionOut.model_validate(transaction)


@router.get("/{transaction_id}/similar")
def similar_transactions(transaction_id: int, user: CurrentUser, session: SessionDep) -> SimilarOut:
    """Suggest a rule pattern for this description and count what it would cover."""
    transaction = _owned_or_404(session, user.id, transaction_id)
    pattern = suggest_pattern(transaction.description)
    return SimilarOut(pattern=pattern, count=len(matching_transactions(session, user.id, pattern)))
