"""V3.2.2 regression tests: EX-02 independent temporal-leakage detection.

The detector must NOT depend on injected markers; it must use real timestamps +
activity evidence only, while ground truth stays separate (injection log).
"""
from __future__ import annotations

import json

from sqlalchemy import delete, func, select

from yottaflex.config import Settings
from yottaflex.db.models import (
    Activity,
    AnomalyInjectionLog,
    Lead,
    LeadScoreExplanation,
)
from yottaflex.engines import anomaly_injection
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.exceptions import exception_evaluation, run_exception_detection
from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
from yottaflex.engines.scoring import score_all_leads
from yottaflex.engines.task_management import create_followup_tasks

EX02 = "score_uses_post_conversion_event"


def _prep(session, settings: Settings, target: int = 20) -> None:
    score_all_leads(session, settings)
    assign_leads(session, settings)
    for lead in session.scalars(
        select(Lead).where(
            Lead.assigned_salesrep_id.is_not(None),
            Lead.lead_category.in_(["hot", "warm"]),
        )
    ).all():
        lead.status = "qualified"
    session.commit()
    convert_qualified_leads(session, settings, target_count=target)
    advance_opportunities_realistic(session, settings)
    create_followup_tasks(session, settings)


def test_injected_leaks_have_no_markers_and_are_detected_independently(
    generated_session, mini_settings: Settings
):
    """Detection works with zero marker fields present in the data."""
    sess = generated_session
    _prep(sess, mini_settings)
    injected = anomaly_injection.inject_all_anomalies(sess, mini_settings)
    assert injected["temporal_leakage"] > 0

    # 1) no marker artifacts anywhere in the data (injection no longer plants them)
    for expl in sess.scalars(select(LeadScoreExplanation)).all():
        blob = (expl.rules_fired_json or "") + (expl.weights_json or "")
        assert "INJECTED_POST_CONVERSION_EVENT" not in blob
        assert "post_conversion" not in blob

    # 2) independent detection finds every injected case
    records = run_exception_detection(sess)
    ex02 = [r for r in records if r.issue_type == EX02]
    assert len(ex02) == injected["temporal_leakage"]

    # 3) each detection cites REAL evidence: an activity strictly after conversion
    #    and at/before the explanation's scored_at
    for rec in ex02:
        evidence = json.loads(rec.evidence_json or "{}")
        activity = sess.get(Activity, evidence["activity_id"])
        expl = sess.get(LeadScoreExplanation, rec.affected_record_id)
        lead = sess.get(Lead, rec.related_lead_id)
        assert activity is not None and expl is not None and lead is not None
        assert activity.event_time > lead.converted_at
        assert activity.event_time <= expl.scored_at
        assert activity.activity_type in (
            "demo_request", "pricing_inquiry", "form_submit", "content_download",
        )


def test_detection_requires_real_post_conversion_evidence(
    generated_session, mini_settings: Settings
):
    """Remove the post-conversion activities -> no detections (no marker crutch)."""
    sess = generated_session
    _prep(sess, mini_settings)
    anomaly_injection.inject_all_anomalies(sess, mini_settings)

    converted = select(Lead.lead_id).where(Lead.converted_at.is_not(None))
    sess.execute(
        delete(Activity).where(
            Activity.lead_id.in_(converted),
            Activity.activity_id.in_(
                select(Activity.activity_id)
                .join(Lead, Lead.lead_id == Activity.lead_id)
                .where(Activity.event_time > Lead.converted_at)
            ),
        )
    )
    sess.commit()

    records = run_exception_detection(sess)
    ex02 = [r for r in records if r.issue_type == EX02]
    assert ex02 == [], "detector fired without any post-conversion evidence"


def test_pre_conversion_events_do_not_trigger_false_positives(
    generated_session, mini_settings: Settings
):
    """Legitimate pre-conversion activity (baseline) must never be flagged."""
    sess = generated_session
    _prep(sess, mini_settings)

    converted = sess.scalars(select(Lead).where(Lead.converted_at.is_not(None))).all()
    assert converted, "fixture must contain converted leads"
    intent_before = sess.scalar(
        select(func.count())
        .select_from(Activity)
        .join(Lead, Lead.lead_id == Activity.lead_id)
        .where(
            Lead.converted_at.is_not(None),
            Activity.event_time <= Lead.converted_at,
            Activity.activity_type.in_(
                ["demo_request", "pricing_inquiry", "form_submit", "content_download"]
            ),
        )
    )
    assert intent_before and intent_before > 0, "fixture must contain pre-conversion intent events"

    records = run_exception_detection(sess)
    ex02 = [r for r in records if r.issue_type == EX02]
    assert ex02 == []


def test_blind_metrics_recomputed_for_ex02(generated_session, mini_settings: Settings):
    """P/R/F1 recomputed from measured TP/FP/FN (no defaults, no claims)."""
    sess = generated_session
    _prep(sess, mini_settings)
    anomaly_injection.inject_all_anomalies(sess, mini_settings)
    run_exception_detection(sess)

    stats = exception_evaluation(sess)["by_type"][EX02]
    injected_n = sess.scalar(
        select(func.count())
        .select_from(AnomalyInjectionLog)
        .where(AnomalyInjectionLog.issue_type == EX02)
    )
    assert stats["detected"] == stats["tp"] + stats["fp"]
    assert stats["ground_truth"] == injected_n
    assert stats["tp"] == injected_n and stats["fp"] == 0
    # metrics are the measured ratios, not hardcoded claims
    assert stats["precision"] == round(stats["tp"] / (stats["tp"] + stats["fp"]), 4)
    assert stats["recall"] == round(stats["tp"] / (stats["tp"] + stats["fn"]), 4)
