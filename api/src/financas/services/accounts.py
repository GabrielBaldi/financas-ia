"""A user's accounts: one per bank account or card, named when a statement is imported."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.models import Account
from financas.text import normalize

# Where Telegram entries go when the user has not chosen a default account.
MANUAL_ACCOUNT_NAME = "Lançamentos manuais"


def list_accounts(session: Session, user_id: int) -> Sequence[Account]:
    return session.scalars(
        select(Account).where(Account.user_id == user_id).order_by(Account.name, Account.id)
    ).all()


def get_account(session: Session, user_id: int, account_id: int) -> Account | None:
    return session.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )


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


def accounts_starting_with(session: Session, user_id: int, query: str) -> list[Account]:
    """Accounts named by the start of their name, or of a word in it.

    Case, accents and punctuation are ignored, and '_' reads as a space, so a #hashtag can
    name two words: 'cartao', 'cartao_nu' and 'nubank' all find 'Cartão Nubank'. The closest
    kind of match wins: the exact name, then the start of the name, then the start of a word.
    """
    wanted = normalize(query)
    if not wanted:
        return []
    names = [(account, normalize(account.name)) for account in list_accounts(session, user_id)]
    for matches in (
        [account for account, name in names if name == wanted],
        [account for account, name in names if name.startswith(wanted)],
        [account for account, name in names if f" {wanted}" in f" {name}"],
    ):
        if matches:
            return matches
    return []
