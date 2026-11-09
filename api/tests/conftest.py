from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from financas.app import create_app
from financas.categorization.pipeline import Categorizer
from financas.config import Settings
from financas.db import Base, make_engine, make_session_factory
from financas.telegram.bot import TelegramBot
from tests.helpers import FakeClassifier, FakeClock, make_settings, register_and_login


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # A developer's local .env (and API keys) must never leak into tests.
    return make_settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


@pytest.fixture
def session_factory(settings: Settings) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


@pytest.fixture
def fake_ai() -> FakeClassifier:
    return FakeClassifier()


@pytest.fixture
def categorizer(fake_ai: FakeClassifier) -> Categorizer:
    return Categorizer(fake_ai)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def bot(
    session_factory: sessionmaker[Session], categorizer: Categorizer, clock: FakeClock
) -> TelegramBot:
    return TelegramBot(session_factory, categorizer, clock)


@pytest.fixture
def app(settings: Settings, fake_ai: FakeClassifier) -> FastAPI:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return create_app(settings, classifier=fake_ai)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def headers(client: TestClient) -> dict[str, str]:
    return register_and_login(client)
