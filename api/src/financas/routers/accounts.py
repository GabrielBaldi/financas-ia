from fastapi import APIRouter

from financas.deps import CurrentUser, SessionDep
from financas.schemas import AccountOut
from financas.services.accounts import list_accounts

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
def user_accounts(user: CurrentUser, session: SessionDep) -> list[AccountOut]:
    """The user's accounts, by name. One is created per account name typed on import."""
    return [AccountOut.model_validate(account) for account in list_accounts(session, user.id)]
