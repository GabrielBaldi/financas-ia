"""Linking a private Telegram chat to a user, with a one-time code shown in the web app.

The code has 6 digits, lasts 10 minutes, works once and is stored only as a SHA-256 hash.
A chat that sends 5 wrong codes is ignored for 15 minutes, so guessing gets nowhere: about
20 tries an hour against a million possible codes that expire every 10 minutes.
"""

import datetime as dt
import hashlib
import re
import secrets
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from financas.models import Account, TelegramPairingAttempt, User

PAIRING_CODE_TTL = dt.timedelta(minutes=10)
MAX_WRONG_CODES = 5
LOCKOUT = dt.timedelta(minutes=15)

_CODE = re.compile(r"\d{6}")


class PairingResult(StrEnum):
    LINKED = "linked"
    WRONG_CODE = "wrong_code"
    LOCKED_OUT = "locked_out"  # this wrong code was the last one allowed


@dataclass(frozen=True, slots=True)
class Pairing:
    result: PairingResult
    user: User | None = None


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def issue_pairing_code(session: Session, user: User, now: dt.datetime) -> tuple[str, dt.datetime]:
    """A new code for the user, replacing any previous one. Returned once, never stored."""
    while True:
        code = f"{secrets.randbelow(10**6):06d}"
        # Two people holding the same live code would make /conectar ambiguous.
        clash = session.scalar(
            select(User.id).where(
                User.id != user.id,
                User.telegram_pairing_code_hash == _hash_code(code),
                User.telegram_pairing_expires_at > now,
            )
        )
        if clash is None:
            break
    expires_at = now + PAIRING_CODE_TTL
    user.telegram_pairing_code_hash = _hash_code(code)
    user.telegram_pairing_expires_at = expires_at
    session.commit()
    return code, expires_at


def user_for_chat(session: Session, chat_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_chat_id == chat_id))


def chat_is_locked(session: Session, chat_id: int, now: dt.datetime) -> bool:
    attempt = session.get(TelegramPairingAttempt, chat_id)
    return attempt is not None and attempt.locked_until is not None and attempt.locked_until > now


def redeem_pairing_code(session: Session, chat_id: int, code: str, now: dt.datetime) -> Pairing:
    """Link `chat_id` to the user whose live code this is. Callers check the lock first."""
    code = code.strip()
    user = None
    if _CODE.fullmatch(code):
        user = session.scalar(
            select(User).where(
                User.telegram_pairing_code_hash == _hash_code(code),
                User.telegram_pairing_expires_at > now,
            )
        )
    if user is None:
        return _count_wrong_code(session, chat_id, now)

    # One chat per user and one user per chat. The code proves the user agrees to the move.
    previous = user_for_chat(session, chat_id)
    if previous is not None and previous.id != user.id:
        previous.telegram_chat_id = None
        previous.telegram_linked_at = None
        session.flush()  # free the unique chat id before giving it to `user`
    user.telegram_chat_id = chat_id
    user.telegram_linked_at = now
    user.telegram_pairing_code_hash = None
    user.telegram_pairing_expires_at = None
    if (attempt := session.get(TelegramPairingAttempt, chat_id)) is not None:
        session.delete(attempt)
    session.commit()
    return Pairing(PairingResult.LINKED, user)


def _count_wrong_code(session: Session, chat_id: int, now: dt.datetime) -> Pairing:
    attempt = session.get(TelegramPairingAttempt, chat_id)
    if attempt is None:
        attempt = TelegramPairingAttempt(chat_id=chat_id, failures=0, last_failure_at=now)
        session.add(attempt)
    elif now - attempt.last_failure_at > LOCKOUT:
        attempt.failures = 0  # old typos are forgiven after a quiet period

    attempt.failures += 1
    attempt.last_failure_at = now
    locked = attempt.failures >= MAX_WRONG_CODES
    if locked:
        attempt.failures = 0
        attempt.locked_until = now + LOCKOUT
    session.commit()
    return Pairing(PairingResult.LOCKED_OUT if locked else PairingResult.WRONG_CODE)


def unlink_telegram(session: Session, user: User) -> None:
    """Disconnect the chat and void any code still waiting to be used."""
    user.telegram_chat_id = None
    user.telegram_linked_at = None
    user.telegram_pairing_code_hash = None
    user.telegram_pairing_expires_at = None
    session.commit()


def set_default_account(session: Session, user: User, account: Account | None) -> None:
    user.telegram_default_account_id = account.id if account is not None else None
    session.commit()
