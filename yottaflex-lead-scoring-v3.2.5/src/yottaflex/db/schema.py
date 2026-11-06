from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from yottaflex.db import models  # noqa: F401 — registers tables on Base.metadata
from yottaflex.db.base import Base
from yottaflex.db.session import make_engine, make_session_factory


def init_db(engine: Engine | None = None) -> Engine:
    engine = engine or make_engine()
    Base.metadata.create_all(engine)
    return engine


def drop_db(engine: Engine) -> None:
    Base.metadata.drop_all(engine)


def open_session(engine: Engine | None = None):
    engine = engine or init_db()
    factory = make_session_factory(engine)
    return factory()
