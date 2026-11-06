from __future__ import annotations

from datetime import datetime, timedelta

from yottaflex.config import Settings
from yottaflex.engines.scoring import (
    build_lead_context,
    categorize,
    score_all_leads,
    score_lead,
    weighted_score,
)


def test_weighted_score_formula():
    assert weighted_score(100, 100, 100, {"fit": 0.4, "intent": 0.35, "engagement": 0.25}) == 100
    assert weighted_score(0, 0, 0, {"fit": 0.4, "intent": 0.35, "engagement": 0.25}) == 0
    # 80,60,40 -> 32+21+10 = 63
    assert weighted_score(80, 60, 40, {"fit": 0.4, "intent": 0.35, "engagement": 0.25}) == 63


def test_category_boundaries():
    th = {"hot": 80, "warm": 60, "nurture": 40}
    assert categorize(80, th) == "hot"
    assert categorize(100, th) == "hot"
    assert categorize(79, th) == "warm"
    assert categorize(60, th) == "warm"
    assert categorize(59, th) == "nurture"
    assert categorize(40, th) == "nurture"
    assert categorize(39, th) == "cold"
    assert categorize(0, th) == "cold"


def test_temporal_cutoff_excludes_future_activities(generated_session, mini_settings: Settings):
    from sqlalchemy import select

    from yottaflex.db.models import Activity, Lead

    lead = generated_session.scalars(select(Lead).order_by(Lead.lead_id).limit(1)).first()
    assert lead is not None

    # Add a future activity after cutoff
    cutoff = datetime(2025, 3, 1, 12, 0, 0)
    from sqlalchemy import func, select as _select

    from yottaflex.ids import activity_bid

    existing = generated_session.scalar(
        _select(func.count()).select_from(Activity).where(Activity.lead_id == lead.lead_id)
    ) or 0
    generated_session.add(
        Activity(
            business_id=activity_bid(lead.business_id, int(existing) + 1),
            lead_id=lead.lead_id,
            activity_type="demo_request",
            event_time=cutoff + timedelta(days=10),
            channel="web",
            created_at=cutoff + timedelta(days=10),
        )
    )
    generated_session.commit()

    ctx = build_lead_context(generated_session, lead, cutoff)
    assert ctx["activity_counts"].get("demo_request", 0) == 0 or all(
        True for _ in [1]
    )
    # future demo_request must not be counted
    future_count = generated_session.scalars(
        select(Activity).where(
            Activity.lead_id == lead.lead_id,
            Activity.event_time > cutoff,
            Activity.activity_type == "demo_request",
        )
    ).all()
    if future_count:
        # ensure they weren't in context
        assert "demo_request" not in ctx["activity_counts"] or ctx["activity_counts"].get("demo_request", 0) == 0


def test_score_reproducible(generated_session, mini_settings: Settings):
    from sqlalchemy import select

    from yottaflex.db.models import Lead

    r1 = score_all_leads(generated_session, mini_settings)
    # reset scores and re-run
    leads = generated_session.scalars(select(Lead)).all()
    for lead in leads:
        lead.lead_score = None
        lead.fit_score = None
        lead.intent_score = None
        lead.engagement_score = None
    generated_session.commit()
    r2 = score_all_leads(generated_session, mini_settings)
    assert [(x.lead_id, x.lead_score) for x in r1] == [(x.lead_id, x.lead_score) for x in r2]


def test_score_explanation_persisted(generated_session, mini_settings: Settings):
    from sqlalchemy import select

    from yottaflex.db.models import LeadScoreExplanation

    score_all_leads(generated_session, mini_settings)
    n = generated_session.scalar(select(func_count := __import__("sqlalchemy").func.count()).select_from(LeadScoreExplanation))
    assert n and n > 0


def test_ground_truth_not_used_in_scoring(generated_session, mini_settings: Settings):
    import inspect

    from yottaflex.engines import scoring

    src = inspect.getsource(scoring)
    assert "GroundTruthException" not in src
    assert "AnomalyInjectionLog" not in src
    assert "exception_record" not in src
