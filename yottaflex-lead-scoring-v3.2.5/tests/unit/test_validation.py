from __future__ import annotations

from yottaflex.config import Settings
from yottaflex.engines.validation import validate_dataset
from sqlalchemy import func, select
from yottaflex.db.models import Lead


def test_validation_passes_on_clean_generated_data(generated_session, mini_settings: Settings):
    expected = {
        "company": mini_settings.counts.companies,
        "contact": mini_settings.counts.contacts,
        "lead": mini_settings.counts.leads,
    }
    report = validate_dataset(generated_session, expected=expected)
    assert report.passed, report.to_dict()["issues"]
    assert report.critical_count == 0


def test_validation_detects_bad_status(generated_session, mini_settings: Settings):
    lead = generated_session.scalars(select(Lead).limit(1)).first()
    lead.status = "bogus_status"
    generated_session.commit()
    report = validate_dataset(generated_session)
    assert any(i.check == "lead_status_domain" for i in report.issues)
