from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from yottaflex.config import Settings, load_settings


def _configure_sqlite(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(database_url: str | None = None, settings: Settings | None = None) -> Engine:
    settings = settings or load_settings()
    url = database_url or settings.resolved_database_url()
    connect_args = {}
    pool_kwargs: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool

            pool_kwargs["poolclass"] = StaticPool
    engine = create_engine(url, future=True, connect_args=connect_args, **pool_kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
