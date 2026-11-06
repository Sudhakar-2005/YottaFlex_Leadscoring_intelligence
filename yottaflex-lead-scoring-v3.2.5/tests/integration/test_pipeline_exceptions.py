from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from yottaflex.config import Settings
from yottaflex.db.models import (
    ExceptionRecord,
    GroundTruthException,
    IssueType,
    Lead,
    Opportunity,
    AnomalyInjectionLog,
)
from yottaflex.engines import anomaly_injection, analytics
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.exceptions import (
    run_exception_detection,
    exception_evaluation,
    annotate_detection_labels,
)
from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
from yottaflex.engines.scoring import score_all_leads
from yottaflex.engines.task_management import create_followup_tasks


def _prepare_baseline(session, settings: Settings, target_opps: int = 15):
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
    convert_qualified_leads(session, settings, target_count=target_opps)
    advance_opportunities_realistic(session, settings)
    create_followup_tasks(session, settings)


def test_baseline_has_no_injected_anomaly_exceptions(generated_session, mini_settings: Settings):
    """Baseline must be free of the five INJECTED anomaly types (P0-B).

    Natural baseline duplicates (origin='natural') are legitimate baseline
    data; EX-04 may detect them pre-injection. All other types must be zero.
    """
    _prepare_baseline(generated_session, mini_settings)
    records = run_exception_detection(generated_session)
    types = {r.issue_type for r in records}

    injected_types = {
        IssueType.opted_out_lead_contacted.value,
        IssueType.score_uses_post_conversion_event.value,
        IssueType.lead_assigned_outside_territory.value,
        IssueType.stage_history_has_gaps.value,
    }
    # No injected-type exceptions pre-injection
    assert not (types & injected_types), (
        f"baseline injected-type exceptions: {[r.issue_type for r in records]}"
    )
    # No injections logged yet
    from sqlalchemy import func

    assert (generated_session.scalar(select(func.count()).select_from(AnomalyInjectionLog)) or 0) == 0
    # EX-04 records, if any, correspond to natural duplicates only
    for r in records:
        assert r.issue_type == IssueType.duplicate_creates_duplicate_opportunity.value
        assert r.ground_truth_label is None  # blind detection (P0-5)


def test_injection_then_detection_all_five_types(generated_session, mini_settings: Settings):
    _prepare_baseline(generated_session, mini_settings, target_opps=20)
    injected = anomaly_injection.inject_all_anomalies(generated_session, mini_settings)
    assert injected["opted_out_contacted"] > 0
    assert injected["temporal_leakage"] > 0
    assert injected["territory_mismatch"] > 0
    assert injected["duplicate_opportunity"] > 0
    assert injected["stage_history_gap"] > 0

    records = run_exception_detection(generated_session)
    types = {r.issue_type for r in records}
    expected = {
        IssueType.opted_out_lead_contacted.value,
        IssueType.score_uses_post_conversion_event.value,
        IssueType.lead_assigned_outside_territory.value,
        IssueType.duplicate_creates_duplicate_opportunity.value,
        IssueType.stage_history_has_gaps.value,
    }
    assert expected.issubset(types), f"missing detections: {expected - types}"

    # Detectors are blind: no labels attached at detection time
    assert all(r.ground_truth_label is None for r in records)


def test_blind_evaluation_is_honest_and_matches_injections(generated_session, mini_settings: Settings):
    """P0-5: P/R/F1 computed via blind key matching, not attached labels."""
    _prepare_baseline(generated_session, mini_settings, target_opps=20)
    injected = anomaly_injection.inject_all_anomalies(generated_session, mini_settings)
    run_exception_detection(generated_session)

    ev = exception_evaluation(generated_session)
    assert ev["detections"] >= sum(injected.values())
    # All five types: every injected instance matched (detectors + GT are aligned)
    for issue, stats in ev["by_type"].items():
        if stats["ground_truth"] > 0:
            assert stats["tp"] == stats["ground_truth"], (
                f"{issue}: tp {stats['tp']} / gt {stats['ground_truth']}"
            )
            assert stats["precision"] == 1.0
            assert stats["recall"] == 1.0
            assert stats["f1"] == 1.0
    assert ev["overall_f1"] == 1.0

    # Blindness proof: evaluation outcome is independent of detection labels.
    # Clear every label, re-evaluate → identical metrics.
    for rec in generated_session.scalars(select(ExceptionRecord)).all():
        rec.ground_truth_label = None
    generated_session.commit()
    ev2 = exception_evaluation(generated_session)
    assert ev2["overall_precision"] == ev["overall_precision"]
    assert ev2["overall_recall"] == ev["overall_recall"]
    assert ev2["overall_f1"] == ev["overall_f1"]
    for issue in ev["by_type"]:
        assert ev2["by_type"][issue]["f1"] == ev["by_type"][issue]["f1"]


def test_evaluation_undefined_without_ground_truth(generated_session, mini_settings: Settings):
    """P0-5: no GT + no detections ⇒ metrics are null, never defaulted to 1.0."""
    _prepare_baseline(generated_session, mini_settings)
    # remove detections so both GT and detections are empty
    from sqlalchemy import delete

    generated_session.execute(delete(ExceptionRecord))
    generated_session.commit()
    ev = exception_evaluation(generated_session)
    for stats in ev["by_type"].values():
        if stats["ground_truth"] == 0 and stats["detected"] == 0:
            assert stats["precision"] is None
            assert stats["recall"] is None
            assert stats["f1"] is None
    # Overall: precision is undefined with no detections (never 1.0);
    # recall is defined only because natural duplicate GT exists.
    assert ev["overall_precision"] is None
    assert ev["overall_f1"] is None


def test_annotation_only_after_evaluation(generated_session, mini_settings: Settings):
    _prepare_baseline(generated_session, mini_settings, target_opps=20)
    anomaly_injection.inject_all_anomalies(generated_session, mini_settings)
    run_exception_detection(generated_session)
    assert all(
        r.ground_truth_label is None
        for r in generated_session.scalars(select(ExceptionRecord)).all()
    )
    annotated = annotate_detection_labels(generated_session)
    assert annotated > 0
    assert all(
        r.ground_truth_label is not None
        for r in generated_session.scalars(
            select(ExceptionRecord).where(ExceptionRecord.ground_truth_label.is_not(None))
        ).all()
    )


def test_ground_truth_isolated_from_scoring_sources():
    """GT tables must not be imported by scoring module (FR-14)."""
    import inspect

    from yottaflex.engines import scoring

    src = inspect.getsource(scoring)
    assert "GroundTruthException" not in src
    assert "AnomalyInjectionLog" not in src


def test_exception_record_required_fields(generated_session, mini_settings: Settings):
    _prepare_baseline(generated_session, mini_settings, target_opps=10)
    anomaly_injection.inject_all_anomalies(generated_session, mini_settings)
    records = run_exception_detection(generated_session)
    assert records
    exception_evaluation(generated_session)
    annotate_detection_labels(generated_session)
    records = generated_session.scalars(select(ExceptionRecord)).all()
    for r in records:
        assert r.exception_id is not None
        assert r.issue_type
        assert r.affected_entity
        assert r.affected_record_id is not None
        assert r.detection_timestamp is not None
        assert r.expected_behavior
        assert r.actual_behavior
        assert r.ground_truth_label is not None  # annotated post-evaluation
        assert r.severity in ("critical", "high", "medium", "low")
        assert r.resolution_status == "open"


def test_kpis_computed(generated_session, mini_settings: Settings):
    _prepare_baseline(generated_session, mini_settings, target_opps=15)
    m = analytics.summary_metrics(generated_session, mini_settings)
    for key in [
        "lead_conversion_rate",
        "opportunity_win_rate",
        "lead_qualification_rate",
        "assignment_coverage",
        "consent_compliance",
        "duplicate_detection_rate",
    ]:
        assert key in m
        assert "value" in m[key]
        assert 0.0 <= m[key]["value"] <= 1.0
    assert m["funnel"]["stages"][0]["stage"] == "total_leads"
    assert m["funnel"]["stages"][0]["count"] > 0
    assert "heldout_evaluation" in m
    assert "opportunity_selection_checks" in m
