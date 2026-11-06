from __future__ import annotations

from yottaflex.config import CountsConfig, Settings
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_engine
from yottaflex.engines.data_generator import generate_all
from sqlalchemy import func, select

from yottaflex.db.models import Company, Contact, Lead


def _counts(settings: Settings) -> dict[str, int]:
    eng = make_engine("sqlite:///:memory:", settings)
    init_db(eng)
    with open_session(eng) as session:
        generate_all(session, settings)
        return {
            "company": session.scalar(select(func.count()).select_from(Company)) or 0,
            "contact": session.scalar(select(func.count()).select_from(Contact)) or 0,
            "lead": session.scalar(select(func.count()).select_from(Lead)) or 0,
        }


def test_exact_dataset_sizes():
    settings = Settings(
        seed=42,
        counts=CountsConfig(
            companies=50,
            contacts=80,
            leads=120,
            opportunities=20,
            campaigns=5,
            sales_reps=12,
        ),
    )
    counts = _counts(settings)
    assert counts["company"] == 50
    assert counts["contact"] == 80
    assert counts["lead"] == 120


def test_determinism_same_seed():
    s1 = Settings(seed=7, counts=CountsConfig(companies=30, contacts=40, leads=50, opportunities=10, campaigns=3, sales_reps=8))
    s2 = Settings(seed=7, counts=CountsConfig(companies=30, contacts=40, leads=50, opportunities=10, campaigns=3, sales_reps=8))
    c1, c2 = _counts(s1), _counts(s2)
    assert c1 == c2

    # deeper determinism: first lead email
    def first_email(settings):
        eng = make_engine("sqlite:///:memory:", settings)
        init_db(eng)
        with open_session(eng) as session:
            generate_all(session, settings)
            row = session.scalars(select(Lead).order_by(Lead.lead_id).limit(1)).first()
            return row.email_normalized if row else None

    assert first_email(s1) == first_email(s2)


def test_different_seed_differs():
    s1 = Settings(seed=1, counts=CountsConfig(companies=30, contacts=40, leads=50, opportunities=10, campaigns=3, sales_reps=8))
    s2 = Settings(seed=999, counts=CountsConfig(companies=30, contacts=40, leads=50, opportunities=10, campaigns=3, sales_reps=8))

    def first_email(settings):
        eng = make_engine("sqlite:///:memory:", settings)
        init_db(eng)
        with open_session(eng) as session:
            generate_all(session, settings)
            row = session.scalars(select(Lead).order_by(Lead.lead_id).limit(1)).first()
            return row.email_normalized if row else None

    assert first_email(s1) != first_email(s2)
