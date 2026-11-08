from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from financas.app import create_app
from financas.config import Settings
from financas.db import Base, make_engine, make_session_factory
from tests.helpers import FakeClassifier, register_and_login


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None: a developer's local .env (and API key) must never leak into tests.
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        anthropic_api_key=None,
    )


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture
def fake_ai() -> FakeClassifier:
    return FakeClassifier()


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
