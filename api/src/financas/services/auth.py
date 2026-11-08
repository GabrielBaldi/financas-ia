"""Users, password checks and opaque bearer tokens (stored only as SHA-256 hashes)."""

import datetime as dt
import hashlib
import secrets

from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from financas.models import AuthToken, User, utc_now

password_hasher = PasswordHash.recommended()  # Argon2
_DUMMY_HASH = password_hasher.hash("not-a-real-password")


class EmailTakenError(Exception):
    pass


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(session: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailTakenError(email)
    user = User(email=email, password_hash=password_hasher.hash(password))
    session.add(user)
    session.commit()
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        # Spend the same time as a real check, so response time does not reveal which emails exist.
        password_hasher.verify(password, _DUMMY_HASH)
        return None
    return user if password_hasher.verify(password, user.password_hash) else None


def issue_token(session: Session, user: User, ttl: dt.timedelta) -> tuple[str, dt.datetime]:
    session.execute(delete(AuthToken).where(AuthToken.expires_at <= utc_now()))
    token = secrets.token_urlsafe(32)
    expires_at = utc_now() + ttl
    session.add(AuthToken(user_id=user.id, token_hash=_hash_token(token), expires_at=expires_at))
    session.commit()
    return token, expires_at


def user_for_token(session: Session, token: str) -> User | None:
    return session.scalar(
        select(User)
        .join(AuthToken, AuthToken.user_id == User.id)
        .where(AuthToken.token_hash == _hash_token(token), AuthToken.expires_at > utc_now())
    )


def revoke_token(session: Session, token: str) -> None:
    session.execute(delete(AuthToken).where(AuthToken.token_hash == _hash_token(token)))
    session.commit()
