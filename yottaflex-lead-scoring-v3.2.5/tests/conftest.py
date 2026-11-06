from __future__ import annotations

import pytest

from yottaflex.config import CountsConfig, Settings
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_engine


@pytest.fixture
def mini_settings() -> Settings:
    return Settings(
        seed=42,
        counts=CountsConfig(
            companies=60,
            contacts=90,
            leads=150,
            opportunities=30,
            campaigns=6,
            sales_reps=14,
            territories=16,
            products=10,
        ),
    )


@pytest.fixture
def engine(mini_settings: Settings):
    eng = make_engine("sqlite:///:memory:", mini_settings)
    init_db(eng)
    return eng


@pytest.fixture
def session(engine):
    with open_session(engine) as s:
        yield s


@pytest.fixture
def generated_session(session, mini_settings: Settings):
    from yottaflex.engines.data_generator import generate_all

    generate_all(session, mini_settings)
    yield session
