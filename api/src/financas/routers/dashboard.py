from typing import Annotated

from fastapi import APIRouter, Query

from financas.deps import CurrentUser, SessionDep
from financas.schemas import DashboardOut
from financas.services.dashboard import build_dashboard
from financas.services.months import MONTH_PATTERN

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    user: CurrentUser,
    session: SessionDep,
    month: Annotated[str, Query(pattern=MONTH_PATTERN, examples=["2026-10"])],
) -> DashboardOut:
    """Spending by category in `month` and monthly totals for the 6 months ending there.

    Card bill payments and investments move money between the user's own accounts,
    so they count as neither spending nor income.
    """
    return build_dashboard(session, user.id, month)
