"""FastAPI dependencies shared by the routers."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker

from financas.categorization.pipeline import Categorizer
from financas.config import Settings
from financas.models import User
from financas.services.auth import user_for_token
from financas.services.imports import AIPricing


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    session_factory: sessionmaker[Session]
    categorizer: Categorizer
    pricing: AIPricing | None  # None: the AI provider has no price configured (NVIDIA)


def get_context(request: Request) -> AppContext:
    context: AppContext = request.app.state.context
    return context


ContextDep = Annotated[AppContext, Depends(get_context)]


def get_session(context: ContextDep) -> Iterator[Session]:
    with context.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
TokenDep = Annotated[str, Depends(oauth2_scheme)]


def get_current_user(token: TokenDep, session: SessionDep) -> User:
    user = user_for_token(session, token)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sessão inválida ou expirada. Entre de novo.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
