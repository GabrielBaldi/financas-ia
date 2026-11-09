from logging.config import fileConfig

from alembic import context

import financas.models  # noqa: F401  (registers every table on Base.metadata)
from financas.config import get_settings
from financas.db import Base, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    # Tests point Alembic at a temporary database through the config object.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url())
    with engine.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        if is_sqlite:
            # Batch mode changes a SQLite table by copying it and dropping the original. With
            # foreign keys on, dropping `users` would cascade-delete every row that points to
            # it, so they stay off during the migration and are checked at the end instead.
            # The pragma only works outside a transaction; committing right away also keeps
            # Alembic from mistaking this connection for one inside an external transaction.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        # Batch mode lets future ALTERs work on SQLite too.
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        if is_sqlite:
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if broken:
                raise RuntimeError(f"Migration left {len(broken)} broken foreign key(s)")
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
