import datetime as dt
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from financas.categories import Category, Source
from financas.db import Base, make_engine, make_session_factory
from financas.models import Account, AuthToken, ImportBatch, Origin, Rule, Transaction, User
from financas.seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo
from financas.services.auth import authenticate, issue_token, user_for_token
from financas.services.imports import list_imports
from financas.services.months import recent_months, shift_month
from financas.services.transactions import available_months

API_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_migrations_build_exactly_the_schema_of_the_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    config = alembic_config(url)

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


# One user with data in every table, as revision 0001 stored it.
REVISION_0001_DATA = """
INSERT INTO users (id, email, password_hash, created_at)
    VALUES (1, 'ana@example.com', 'hash', '2026-10-01 12:00:00.000000');
INSERT INTO accounts (id, user_id, name) VALUES (1, 1, 'Conta Nubank');
INSERT INTO auth_tokens (id, user_id, token_hash, expires_at)
    VALUES (1, 1, 'abc', '2030-01-01 00:00:00.000000');
INSERT INTO rules (id, user_id, pattern, category, created_at)
    VALUES (1, 1, 'bistro da vila', 'alimentacao', '2026-10-01 12:00:00.000000');
INSERT INTO imports (id, user_id, account_id, filename, file_format, created_at, total_rows,
    inserted, duplicates, by_user_rule, by_keyword, by_ai, to_review, ai_input_tokens,
    ai_output_tokens, ai_cost_usd)
    VALUES (1, 1, 1, 'extrato.csv', 'csv_generico', '2026-10-02 12:00:00.000000', 2, 2, 0,
    0, 1, 0, 1, 0, 0, 0.0);
INSERT INTO transactions (id, user_id, account_id, import_id, date, description, amount_cents,
    category, categorized_by, confidence, suggested_category, dedup_hash) VALUES
    (1, 1, 1, 1, '2026-10-01', 'Padaria Pão Quente', -1200, 'alimentacao', 'keyword', NULL,
     NULL, 'h1'),
    (2, 1, 1, 1, '2026-10-02', 'MP *LOJADOZE', -3990, NULL, 'review', 0.4, 'compras', 'h2');
"""


def test_upgrading_a_database_with_data_keeps_every_row(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    config = alembic_config(url)
    command.upgrade(config, "0001")
    engine = make_engine(url)
    with engine.begin() as connection:
        for statement in REVISION_0001_DATA.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)

    command.upgrade(config, "head")

    with make_session_factory(engine)() as session:
        user = session.get(User, 1)
        assert user is not None
        assert (user.email, user.telegram_chat_id, user.telegram_default_account_id) == (
            "ana@example.com",
            None,
            None,
        )
        rows = session.scalars(select(Transaction).order_by(Transaction.id)).all()
        assert [(t.description, t.import_id, t.origin, t.note) for t in rows] == [
            ("Padaria Pão Quente", 1, Origin.IMPORT, None),
            ("MP *LOJADOZE", 1, Origin.IMPORT, None),
        ]
        assert (rows[1].categorized_by, rows[1].suggested_category) == (
            Source.REVIEW,
            Category.COMPRAS,
        )
        assert session.scalars(select(ImportBatch.reconciled)).all() == [0]
        assert session.scalar(select(func.count(Rule.id))) == 1
        assert session.scalar(select(func.count(AuthToken.id))) == 1
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []

        # The rebuilt users table still owns everything: deleting the user cascades.
        session.execute(delete(User).where(User.id == 1))
        session.commit()
        assert session.scalar(select(func.count(Account.id))) == 0
        assert session.scalar(select(func.count(Transaction.id))) == 0
    engine.dispose()


def test_downgrading_keeps_the_rows_too(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    config = alembic_config(url)
    command.upgrade(config, "0001")
    engine = make_engine(url)
    with engine.begin() as connection:
        for statement in REVISION_0001_DATA.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)

    command.upgrade(config, "head")
    command.downgrade(config, "0001")

    with engine.connect() as connection:
        counts = [
            connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar()  # noqa: S608
            for table in ("users", "accounts", "auth_tokens", "rules", "imports", "transactions")
        ]
        linked = connection.exec_driver_sql(
            "SELECT count(*) FROM transactions WHERE import_id = 1"
        ).scalar()
    engine.dispose()
    assert counts == [1, 1, 1, 1, 1, 2]
    assert linked == 2
