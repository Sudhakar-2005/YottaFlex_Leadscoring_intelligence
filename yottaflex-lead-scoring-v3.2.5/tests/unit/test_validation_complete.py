from __future__ import annotations

from sqlalchemy import select

from yottaflex.config import Settings
from yottaflex.db.models import Lead
from yottaflex.engines.scoring import score_all_leads
from yottaflex.engines.validation import validate_dataset


def test_clean_data_passes_full_score_validation(generated_session, mini_settings: Settings):
    """V3.2: full-range + arithmetic checks pass on clean data."""
    score_all_leads(generated_session, mini_settings)
    report = validate_dataset(generated_session, settings=mini_settings)
    assert report.passed, [i.__dict__ for i in report.issues]


def test_score_range_check_covers_records_beyond_first_50(generated_session, mini_settings: Settings):
    """V3.2 regression: a corrupt score on a high lead_id must be detected."""
    score_all_leads(generated_session, mini_settings)
    victim = generated_session.scalars(
        select(Lead).where(Lead.lead_score.is_not(None)).order_by(Lead.lead_id.desc())
    ).first()
    assert victim is not None and victim.lead_id > 50, (
        f"need a victim beyond the old sample window, got lead_id={victim.lead_id}"
    )
    victim.lead_score = 999
    generated_session.commit()

    report = validate_dataset(generated_session, settings=mini_settings)
    range_issues = [i for i in report.issues if i.check == "lead_score_range"]
    assert range_issues, "score range violation beyond first 50 leads was not detected"
    assert range_issues[0].severity == "critical"
    assert "outside 0-100" in range_issues[0].message


def test_score_arithmetic_check_covers_all_records(generated_session, mini_settings: Settings):
    """V3.2: weighted-formula identity is verified for every scored lead."""
    score_all_leads(generated_session, mini_settings)
    victim = generated_session.scalars(
        select(Lead)
        .where(Lead.lead_score.is_not(None), Lead.lead_score > 10, Lead.lead_score < 90)
        .order_by(Lead.lead_id.desc())
    ).first()
    assert victim is not None and victim.lead_id > 50
    victim.lead_score = victim.lead_score + 1  # one-point drift
    generated_session.commit()

    report = validate_dataset(generated_session, settings=mini_settings)
    arithmetic = [i for i in report.issues if i.check == "lead_score_arithmetic"]
    assert arithmetic, "score arithmetic drift was not detected"
    assert arithmetic[0].record_id == victim.lead_id
