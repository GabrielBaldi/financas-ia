from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    if not database_url.startswith("sqlite"):
        return create_engine(database_url, pool_pre_ping=True)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry) -> None:
        # SQLite ignores ON DELETE CASCADE unless foreign keys are switched on per connection.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
