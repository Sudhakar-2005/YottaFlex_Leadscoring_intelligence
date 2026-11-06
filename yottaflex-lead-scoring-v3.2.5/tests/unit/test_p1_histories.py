from __future__ import annotations

from sqlalchemy import func, select

from yottaflex.config import Settings
from yottaflex.db.models import (
    Consent,
    Lead,
    LeadStatusHistory,
)
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.lead_status_history import (
    append_status_change,
    get_timeline,
    record_initial_status,
    validate_timeline,
)
from yottaflex.engines.scoring import score_all_leads


def test_initial_timeline_rows(generated_session, mini_settings: Settings):
    """P1-1: every lead has an initial None -> new timeline row."""
    sess = generated_session
    total_leads = sess.scalar(select(func.count()).select_from(Lead)) or 0
    initial = sess.scalar(
        select(func.count())
        .select_from(LeadStatusHistory)
        .where(LeadStatusHistory.from_status.is_(None), LeadStatusHistory.to_status == "new")
    ) or 0
    assert initial == total_leads


def test_timeline_is_reconstructable(generated_session, mini_settings: Settings):
    """P1-1: timeline order is monotonic, from/to chained, ends at current status."""
    sess = generated_session
    score_all_leads(sess, mini_settings)
    assign_leads(sess, mini_settings)

    converter = sess.scalars(
        select(Lead).where(Lead.is_duplicate_of.is_(None)).limit(5)
    ).all()
    assert converter
    for lead in converter:
        rows = get_timeline(sess, lead.lead_id)
        assert rows, f"lead {lead.lead_id} missing timeline"
        assert rows[0].from_status is None
        assert rows[-1].to_status == lead.status
        assert validate_timeline(sess, lead.lead_id) == []
        for prev, nxt in zip(rows, rows[1:]):
            assert nxt.from_status == prev.to_status


def test_timeline_append_only_no_op_on_same_status(generated_session, mini_settings: Settings):
    score_all_leads(generated_session, mini_settings)
    lead = sess_lead = generated_session.scalars(select(Lead).limit(1)).first()
    from datetime import datetime

    before = sess_lead.status
    row = append_status_change(
        generated_session,
        sess_lead,
        before,  # same status -> no-op
        datetime(2025, 4, 1),
        reason="noop",
    )
    assert row is None


def test_consent_typed_fks(generated_session):
    """P1-3: consent rows carry enforced typed FKs."""
    sess = generated_session
    bad_lead = sess.scalar(
        select(func.count())
        .select_from(Consent)
        .where(Consent.subject_type == "lead", Consent.lead_id.is_(None))
    ) or 0
    bad_contact = sess.scalar(
        select(func.count())
        .select_from(Consent)
        .where(Consent.subject_type == "contact", Consent.contact_id.is_(None))
    ) or 0
    assert bad_lead == 0
    assert bad_contact == 0
    # referenced leads exist
    assert (sess.scalar(select(func.count()).select_from(Consent).where(Consent.lead_id.is_not(None))) or 0) > 0


def test_converted_link_fk_integrity(generated_session, mini_settings: Settings):
    """P1-2: lead.converted_opportunity_id resolves to an existing opportunity."""
    from yottaflex.engines.opportunity import convert_qualified_leads

    sess = generated_session
    score_all_leads(sess, mini_settings)
    assign_leads(sess, mini_settings)
    convert_qualified_leads(sess, mini_settings, target_count=5)

    from yottaflex.db.models import Opportunity

    dangling = sess.execute(
        select(Lead.lead_id)
        .outerjoin(Opportunity, Opportunity.opportunity_id == Lead.converted_opportunity_id)
        .where(Lead.converted_opportunity_id.is_not(None), Opportunity.opportunity_id.is_(None))
    ).all()
    assert dangling == []
    linked = sess.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.converted_opportunity_id.is_not(None))
    ) or 0
    assert linked == 5


def test_resolution_history_written_by_patch(generated_session, mini_settings: Settings):
    """P1-4: exception resolution appends history; re-detection safe."""
    from fastapi.testclient import TestClient

    from yottaflex.api.main import app
    from yottaflex.engines import anomaly_injection
    from yottaflex.engines.exceptions import run_exception_detection
    from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
    from yottaflex.engines.task_management import create_followup_tasks

    sess = generated_session
    score_all_leads(sess, mini_settings)
    assign_leads(sess, mini_settings)
    for lead in sess.scalars(
        select(Lead).where(
            Lead.assigned_salesrep_id.is_not(None),
            Lead.lead_category.in_(["hot", "warm"]),
        )
    ).all():
        lead.status = "qualified"
    sess.commit()
    convert_qualified_leads(sess, mini_settings, target_count=10)
    advance_opportunities_realistic(sess, mini_settings)
    create_followup_tasks(sess, mini_settings)
    anomaly_injection.inject_all_anomalies(sess, mini_settings)
    records = run_exception_detection(sess)
    assert records

    # patch one exception through the API surface
    from yottaflex.db.models import ExceptionRecord

    rec = records[0]
    client = TestClient(app)
    # bind test client to this session engine
    from yottaflex.api.main import get_session

    engine = sess.get_bind()
    from yottaflex.db.session import make_session_factory

    factory = make_session_factory(engine)

    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    try:
        resp = client.patch(
            f"/api/v1/exceptions/{rec.exception_id}",
            json={"resolution_status": "resolved", "note": "fixed via test", "actor_id": "tester"},
        )
        assert resp.status_code == 200
        resp2 = client.get(f"/api/v1/exceptions/{rec.exception_id}/resolutions")
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["count"] == 1
        assert body["resolutions"][0]["to_status"] == "resolved"
        assert body["resolutions"][0]["reason"] == "fixed via test"

        # lead status history endpoint
        resp3 = client.get("/api/v1/leads/1/status-history")
        assert resp3.status_code == 200
        assert resp3.json()["history"]
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_coverage_metrics(generated_session, mini_settings: Settings):
    from yottaflex.engines import analytics

    sess = generated_session
    m = analytics.summary_metrics(sess, mini_settings)
    for key in [
        "opt_out_rate",
        "disqualified_rate",
        "stale_lead_rate",
        "consent_coverage_rate",
    ]:
        assert key in m
        assert 0.0 <= m[key]["value"] <= 1.0
    assert m["opt_out_rate"]["opted_out_leads"] > 0
