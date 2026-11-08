import datetime as dt
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from financas.db import Base, make_engine
from financas.models import AuthToken, User
from financas.seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo
from financas.services.auth import authenticate, issue_token, user_for_token
from financas.services.imports import list_imports
from financas.services.months import recent_months, shift_month
from financas.services.transactions import available_months

API_DIR = Path(__file__).resolve().parents[1]


def test_migrations_build_exactly_the_schema_of_the_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    config = Config()
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)

    command.upgrade(config, "head")
    engine = make_engine(url)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert differences == []
    command.downgrade(config, "base")


def test_seed_creates_three_months_of_demo_data_and_can_run_twice(session: Session) -> None:
    seed_demo(session, dt.date(2026, 11, 8))
    user = seed_demo(session, dt.date(2026, 11, 8))

    assert session.scalar(select(func.count(User.id))) == 1
    assert available_months(session, user.id) == ["2026-10", "2026-09", "2026-08"]
    imports = list_imports(session, user.id)
    assert len(imports) == 3
    assert all(batch.by_keyword > batch.to_review > 0 for batch in imports)
    assert all(batch.by_user_rule > 0 and batch.by_ai == 0 for batch in imports)
    assert authenticate(session, DEMO_EMAIL, DEMO_PASSWORD) is not None


def test_expired_tokens_stop_working(session: Session) -> None:
    seed_demo(session, dt.date(2026, 11, 8))
    user = session.scalars(select(User)).one()
    token, _ = issue_token(session, user, dt.timedelta(hours=-1))

    assert user_for_token(session, token) is None
    assert session.scalars(select(AuthToken)).all() != []  # cleaned up on the next login
    issue_token(session, user, dt.timedelta(hours=1))
    assert len(session.scalars(select(AuthToken)).all()) == 1


def test_month_helpers_cross_year_boundaries() -> None:
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2026-12", 1) == "2027-01"
    assert recent_months("2026-02", 3) == ["2025-12", "2026-01", "2026-02"]
