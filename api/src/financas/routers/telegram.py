from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from financas.deps import CurrentUser, SessionDep
from financas.models import User, utc_now
from financas.schemas import AccountOut, DefaultAccountIn, PairingCodeOut, TelegramStatusOut
from financas.services.accounts import get_account
from financas.services.telegram_link import (
    issue_pairing_code,
    set_default_account,
    unlink_telegram,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _status(session: Session, user: User) -> TelegramStatusOut:
    account = None
    if user.telegram_default_account_id is not None:
        account = get_account(session, user.id, user.telegram_default_account_id)
    return TelegramStatusOut(
        linked=user.telegram_chat_id is not None,
        linked_at=user.telegram_linked_at,
        default_account=AccountOut.model_validate(account) if account else None,
    )


@router.get("")
def telegram_status(user: CurrentUser, session: SessionDep) -> TelegramStatusOut:
    """Whether a Telegram chat is linked, since when, and where its entries go."""
    return _status(session, user)


@router.post("/pairing-code", status_code=status.HTTP_201_CREATED)
def new_pairing_code(user: CurrentUser, session: SessionDep) -> PairingCodeOut:
    """A 6-digit code to send to the bot as `/conectar CODE`. It works once, for 10 minutes.

    Only a hash is stored, so the code appears in this response and nowhere else. Asking for
    a new one cancels the previous code.
    """
    code, expires_at = issue_pairing_code(session, user, utc_now())
    return PairingCodeOut(code=code, expires_at=expires_at)


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink(user: CurrentUser, session: SessionDep) -> None:
    """Disconnect the chat. Entries already logged stay."""
    unlink_telegram(session, user)


@router.put("/default-account")
def change_default_account(
    body: DefaultAccountIn, user: CurrentUser, session: SessionDep
) -> TelegramStatusOut:
    """Where entries without a #account go. `null` means "Lançamentos manuais"."""
    account = None
    if body.account_id is not None:
        account = get_account(session, user.id, body.account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conta não encontrada.")
    set_default_account(session, user, account)
    return _status(session, user)
