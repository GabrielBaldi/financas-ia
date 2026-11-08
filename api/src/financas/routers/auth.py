import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from financas.deps import ContextDep, CurrentUser, SessionDep, TokenDep
from financas.schemas import RegisterIn, TokenOut, UserOut
from financas.services.auth import (
    EmailTakenError,
    authenticate,
    create_user,
    issue_token,
    revoke_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, session: SessionDep) -> UserOut:
    try:
        user = create_user(session, body.email, body.password)
    except EmailTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe uma conta com este e-mail."
        ) from None
    return UserOut.model_validate(user)


@router.post("/token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
    context: ContextDep,
) -> TokenOut:
    """OAuth2 password flow: send `username` (the e-mail) and `password` as a form."""
    user = authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")
    ttl = dt.timedelta(hours=context.settings.token_ttl_hours)
    token, expires_at = issue_token(session, user, ttl)
    return TokenOut(access_token=token, expires_at=expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(token: TokenDep, session: SessionDep) -> None:
    revoke_token(session, token)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
