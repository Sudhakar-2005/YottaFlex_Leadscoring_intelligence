from __future__ import annotations

import pytest
from sqlalchemy import func, select

from yottaflex.config import CountsConfig, Settings
from yottaflex.db.models import Activity, Company, Contact, Lead, Opportunity, Task
from yottaflex.ids import (
    ACTIVITY_RE,
    COMPANY_RE,
    CONTACT_RE,
    LEAD_RE,
    OPPORTUNITY_RE,
    TASK_RE,
    is_valid_business_id,
)


@pytest.fixture
def business_id_session(session, mini_settings: Settings):
    from yottaflex.engines.data_generator import generate_all

    generate_all(session, mini_settings)
    yield session


def test_business_id_formats(business_id_session):
    sess = business_id_session
    for company in sess.scalars(select(Company).limit(5)).all():
        assert COMPANY_RE.match(company.business_id)
        assert is_valid_business_id("company", company.business_id)
    for contact in sess.scalars(select(Contact).limit(5)).all():
        assert CONTACT_RE.match(contact.business_id)
    for lead in sess.scalars(select(Lead).limit(5)).all():
        assert LEAD_RE.match(lead.business_id)
        assert lead.business_id.startswith("LEAD-2026-")
    for activity in sess.scalars(select(Activity).limit(5)).all():
        assert ACTIVITY_RE.match(activity.business_id)
        # activity business id nests the lead business id (FK parity)
        lead = sess.get(Lead, activity.lead_id)
        assert activity.business_id.startswith(f"ACT-{lead.business_id}-")


def test_business_ids_unique(business_id_session):
    sess = business_id_session
    for model in (Company, Contact, Lead):
        total = sess.scalar(select(func.count()).select_from(model)) or 0
        distinct = sess.scalar(
            select(func.count(func.distinct(model.business_id))).select_from(model)
        ) or 0
        assert total == distinct, f"{model.__tablename__} business_id not unique"


def test_business_ids_zero_padded_and_sequential(business_id_session):
    sess = business_id_session
    rows = sess.execute(
        select(Company.business_id, Company.name).order_by(Company.business_id).limit(3)
    ).all()
    assert [r[0] for r in rows] == ["CO-000001", "CO-000002", "CO-000003"]
    lead_rows = sess.execute(
        select(Lead.business_id).order_by(Lead.business_id).limit(2)
    ).all()
    assert [r[0] for r in lead_rows] == ["LEAD-2026-000001", "LEAD-2026-000002"]


def test_task_and_opportunity_business_ids(business_id_session, mini_settings: Settings):
    """Tasks and opportunities get deterministic business IDs at creation."""
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.opportunity import convert_qualified_leads
    from yottaflex.engines.scoring import score_all_leads
    from yottaflex.engines.task_management import create_followup_tasks

    sess = business_id_session
    score_all_leads(sess, mini_settings)
    assign_leads(sess, mini_settings)
    create_followup_tasks(sess, mini_settings)

    tasks = sess.scalars(select(Task).limit(5)).all()
    assert tasks
    for task in tasks:
        assert TASK_RE.match(task.business_id), task.business_id
        lead = sess.get(Lead, task.lead_id)
        assert task.business_id.startswith(f"TASK-{lead.business_id}-")

    convert_qualified_leads(sess, mini_settings, target_count=5)
    opps = sess.scalars(select(Opportunity).limit(5)).all()
    assert opps
    for opp in opps:
        assert OPPORTUNITY_RE.match(opp.business_id), opp.business_id


def test_business_ids_deterministic(seed=20261022):
    """Two generations with the same seed produce identical business IDs."""
    from yottaflex.db.schema import init_db, open_session
    from yottaflex.db.session import make_engine
    from yottaflex.engines.data_generator import generate_all

    counts = CountsConfig(
        companies=20, contacts=30, leads=40, opportunities=10, campaigns=3, sales_reps=6
    )

    def first_ids(settings: Settings) -> tuple[list, list, list]:
        eng = make_engine("sqlite:///:memory:", settings)
        init_db(eng)
        with open_session(eng) as s:
            generate_all(s, settings)
            c = s.execute(select(Company.business_id).order_by(Company.business_id)).scalars().all()
            l = s.execute(select(Lead.business_id).order_by(Lead.business_id).limit(5)).scalars().all()
            a = s.execute(select(Activity.business_id).order_by(Activity.business_id).limit(5)).scalars().all()
            return c, l, a

    s1 = Settings(seed=seed, counts=counts)
    s2 = Settings(seed=seed, counts=counts)
    c1, l1, a1 = first_ids(s1)
    c2, l2, a2 = first_ids(s2)
    assert c1 == c2
    assert l1 == l2
    assert a1 == a2
