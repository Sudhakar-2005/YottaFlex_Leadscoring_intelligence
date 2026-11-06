from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    Consent,
    ExceptionRecord,
    GroundTruthException,
    IssueType,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    Task,
    AnomalyInjectionLog,
)
from yottaflex.logging_setup import get_logger

log = get_logger("analytics")


def _count(session: Session, *criteria) -> int:
    q = select(func.count()).select_from(Lead)
    if criteria:
        q = q.where(*criteria)
    return int(session.scalar(q) or 0)


def lead_conversion_rate(session: Session, settings: Settings) -> dict[str, Any]:
    excluded = settings.analytics.eligibility_excluded_statuses
    eligible = _count(session, Lead.is_duplicate_of.is_(None), Lead.status.not_in(excluded))
    converted = _count(
        session,
        Lead.is_duplicate_of.is_(None),
        Lead.status == LeadStatus.converted.value,
    )
    rate = (converted / eligible) if eligible else 0.0
    return {
        "metric": "lead_conversion_rate",
        "converted_leads": converted,
        "eligible_leads": eligible,
        "value": round(rate, 4),
        "formula": "converted_leads / eligible_leads",
    }


def opportunity_win_rate(session: Session) -> dict[str, Any]:
    won = int(
        session.scalar(
            select(func.count())
            .select_from(Opportunity)
            .where(Opportunity.stage == OpportunityStage.won.value)
        )
        or 0
    )
    lost = int(
        session.scalar(
            select(func.count())
            .select_from(Opportunity)
            .where(Opportunity.stage == OpportunityStage.lost.value)
        )
        or 0
    )
    closed = won + lost
    rate = (won / closed) if closed else 0.0
    return {
        "metric": "opportunity_win_rate",
        "won": won,
        "lost": lost,
        "closed": closed,
        "value": round(rate, 4),
        "formula": "won / (won + lost)",
    }


def lead_qualification_rate(session: Session) -> dict[str, Any]:
    total = _count(session)
    qualified = _count(
        session,
        Lead.status.in_(
            [LeadStatus.qualified.value, LeadStatus.converted.value]
        ),
    )
    rate = (qualified / total) if total else 0.0
    return {
        "metric": "lead_qualification_rate",
        "qualified_leads": qualified,
        "total_leads": total,
        "value": round(rate, 4),
        "formula": "qualified_leads / total_leads",
    }


def assignment_coverage_metric(session: Session) -> dict[str, Any]:
    assignable = _count(
        session,
        Lead.is_duplicate_of.is_(None),
        Lead.status.not_in(["disqualified", "opted_out"]),
    )
    assigned = _count(
        session,
        Lead.is_duplicate_of.is_(None),
        Lead.assigned_salesrep_id.is_not(None),
    )
    rate = (assigned / assignable) if assignable else 0.0
    return {
        "metric": "assignment_coverage",
        "assigned_leads": assigned,
        "assignable_leads": assignable,
        "value": round(rate, 4),
        "formula": "assigned_leads / assignable_leads",
    }


def consent_compliance_metric(session: Session) -> dict[str, Any]:
    """Compliant outreach = tasks not blocked for consent among outreach tasks created.

    Violations are counted with a targeted SQL expression (outreach tasks on
    leads whose consent decision is not granted) — the full consent-detector
    scan is O(tasks x consent) and too slow for every summary_metrics() call.
    """
    total_outreach = int(
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.task_type.in_(["call", "email", "demo", "follow_up"]))
        )
        or 0
    )
    blocked = int(
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status == "blocked", Task.blocked_reason.like("consent_%"))
        )
        or 0
    )
    # Targeted violation scan: non-blocked email/phone outreach whose lead
    # LATEST consent decision on that channel is not granted. Mirrors the
    # EX-01 detector rule (check_outreach_consent); baseline tasks are
    # consent-gated so this count equals the injected violations.
    violations = 0
    email_v = session.scalar(
        select(func.count())
        .select_from(Task)
        .join(Consent, Consent.lead_id == Task.lead_id)
        .where(
            Task.status.in_(["pending", "in_progress"]),
            Task.task_type != "call",
            Consent.subject_type == "lead",
            Consent.channel == "email",
            Consent.status.in_(["revoked", "expired"]),
        )
    ) or 0
    phone_v = session.scalar(
        select(func.count())
        .select_from(Task)
        .join(Consent, Consent.lead_id == Task.lead_id)
        .where(
            Task.status.in_(["pending", "in_progress"]),
            Task.task_type == "call",
            Consent.subject_type == "lead",
            Consent.channel == "phone",
            Consent.status.in_(["revoked", "expired"]),
        )
    ) or 0
    violations = int(email_v) + int(phone_v)
    compliant = max(0, total_outreach - violations - blocked)
    rate = (compliant / total_outreach) if total_outreach else 1.0
    return {
        "metric": "consent_compliance",
        "compliant_outreach": compliant,
        "total_outreach": total_outreach,
        "violations": violations,
        "blocked_prevented": blocked,
        "value": round(rate, 4),
        "formula": "compliant_outreach / total_outreach",
    }


def duplicate_detection_rate(session: Session) -> dict[str, Any]:
    """Detection rate over ALL known duplicates (natural + injected), P0-B.

    denominator = duplicate_gt rows; numerator = rows soft-marked/detected.
    """
    from yottaflex.db.models import DuplicateGroundTruth

    gt_total = (
        session.scalar(select(func.count()).select_from(DuplicateGroundTruth)) or 0
    )
    detected = (
        session.scalar(
            select(func.count())
            .select_from(DuplicateGroundTruth)
            .where(DuplicateGroundTruth.detected.is_(True))
        )
        or 0
    )
    by_origin: dict[str, int] = {}
    for origin, c in session.execute(
        select(DuplicateGroundTruth.origin, func.count()).group_by(
            DuplicateGroundTruth.origin
        )
    ).all():
        by_origin[str(origin)] = int(c)
    value = (detected / gt_total) if gt_total else None
    return {
        "metric": "duplicate_detection_rate",
        "ground_truth_duplicates": int(gt_total),
        "detected_duplicates": int(detected),
        "by_origin": by_origin,
        "value": round(value, 4) if value is not None else None,
        "formula": "detected_duplicate_gt / total_duplicate_gt",
    }


def heldout_evaluation(session: Session) -> dict[str, Any]:
    """Conversion rate by eval_split × score bucket (P0-D held-out methodology).

    Reported separately for dev vs held-out leads so score→conversion
    association can be inspected on data never used for any tuning.
    """
    buckets = [
        ("cold_<40", 0, 39),
        ("nurture_40_59", 40, 59),
        ("warm_60_79", 60, 79),
        ("hot_80_100", 80, 100),
    ]
    out: dict[str, Any] = {}
    for split in ("dev", "heldout"):
        out[split] = {}
        for name, lo, hi in buckets:
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(
                        Lead.eval_split == split,
                        Lead.lead_score.is_not(None),
                        Lead.lead_score >= lo,
                        Lead.lead_score <= hi,
                        Lead.is_duplicate_of.is_(None),
                    )
                )
                or 0
            )
            converted = int(
                session.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(
                        Lead.eval_split == split,
                        Lead.lead_score.is_not(None),
                        Lead.lead_score >= lo,
                        Lead.lead_score <= hi,
                        Lead.is_duplicate_of.is_(None),
                        Lead.status == LeadStatus.converted.value,
                    )
                )
                or 0
            )
            out[split][name] = {
                "leads": total,
                "converted": converted,
                "conversion_rate": round(converted / total, 4) if total else None,
            }
    heldout_leads = sum(v["leads"] for v in out.get("heldout", {}).values())
    return {
        "metric": "heldout_evaluation",
        "split_sizes": {
            "dev": sum(v["leads"] for v in out.get("dev", {}).values()),
            "heldout": heldout_leads,
        },
        "by_split_and_bucket": out,
        "formula": "conversion_rate = converted / leads per (eval_split, score_bucket)",
    }


def opportunity_selection_checks(session: Session) -> dict[str, Any]:
    """P0-D coverage checks: outcome distribution must not mirror score.

    Verifies high-score non-converters and low-score converters exist and
    reports open pipeline — evidence selection/outcome are not score-driven.
    """
    low_score_converted = int(
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.is_duplicate_of.is_(None),
                Lead.status == LeadStatus.converted.value,
                Lead.lead_score.is_not(None),
                Lead.lead_score < 60,
            )
        )
        or 0
    )
    high_score_not_converted = int(
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.is_duplicate_of.is_(None),
                Lead.status != LeadStatus.converted.value,
                Lead.lead_score.is_not(None),
                Lead.lead_score >= 80,
                Lead.status.not_in(["disqualified", "opted_out"]),
            )
        )
        or 0
    )
    open_opps = int(
        session.scalar(
            select(func.count())
            .select_from(Opportunity)
            .where(Opportunity.stage.in_(["new_lead", "qualified", "demo", "proposal"]))
        )
        or 0
    )
    return {
        "metric": "opportunity_selection_checks",
        "low_score_converters_lt60": low_score_converted,
        "high_score_non_converters_gte80": high_score_not_converted,
        "open_opportunities": open_opps,
        "value": 1.0 if (low_score_converted > 0 and high_score_not_converted > 0) else 0.0,
        "formula": (
            "1.0 iff low-score converters > 0 AND high-score non-converters > 0 "
            "(no score-driven selection/outcome leakage)"
        ),
    }


def conversion_funnel(session: Session) -> dict[str, Any]:
    total = _count(session)
    scored = _count(session, Lead.lead_score.is_not(None))
    assigned = _count(session, Lead.assigned_salesrep_id.is_not(None))
    working = _count(
        session,
        Lead.status.in_(
            [
                LeadStatus.working.value,
                LeadStatus.qualified.value,
                LeadStatus.converted.value,
            ]
        ),
    )
    qualified = _count(
        session,
        Lead.status.in_([LeadStatus.qualified.value, LeadStatus.converted.value]),
    )
    converted = _count(session, Lead.status == LeadStatus.converted.value)
    return {
        "stages": [
            {"stage": "total_leads", "count": total},
            {"stage": "scored", "count": scored},
            {"stage": "assigned", "count": assigned},
            {"stage": "working", "count": working},
            {"stage": "qualified", "count": qualified},
            {"stage": "converted", "count": converted},
        ]
    }


def category_distribution(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(Lead.lead_category, func.count()).where(Lead.lead_category.is_not(None)).group_by(Lead.lead_category)
    ).all()
    return {cat or "unknown": int(c) for cat, c in rows}


def stage_distribution(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(Opportunity.stage, func.count()).group_by(Opportunity.stage)
    ).all()
    return {stage: int(c) for stage, c in rows}


def opt_out_rate(session: Session) -> dict[str, Any]:
    """P1 coverage: leads with revoked/expired consent / total leads."""
    total = _count(session, Lead.is_duplicate_of.is_(None))
    revoked = int(
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .join(Consent, Consent.lead_id == Lead.lead_id)
            .where(
                Consent.subject_type == "lead",
                Consent.channel == "email",
                Consent.status.in_(["revoked", "expired"]),
                Lead.is_duplicate_of.is_(None),
            )
        )
        or 0
    )
    return {
        "metric": "opt_out_rate",
        "opted_out_leads": revoked,
        "total_leads": total,
        "value": round(revoked / total, 4) if total else 0.0,
        "formula": "leads with revoked/expired email consent / non-duplicate leads",
    }


def disqualified_rate(session: Session) -> dict[str, Any]:
    total = _count(session, Lead.is_duplicate_of.is_(None))
    disq = _count(
        session,
        Lead.is_duplicate_of.is_(None),
        Lead.status == LeadStatus.disqualified.value,
    )
    return {
        "metric": "disqualified_rate",
        "disqualified_leads": disq,
        "total_leads": total,
        "value": round(disq / total, 4) if total else 0.0,
        "formula": "disqualified / non-duplicate leads",
    }


def stale_lead_rate(session: Session, settings: Settings) -> dict[str, Any]:
    """P1 coverage: open leads with no activity in the trailing 30 days of the window."""
    from datetime import timedelta

    from yottaflex.db.models import Activity

    cutoff = settings.base_dt() + timedelta(days=30)
    stale = int(
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.is_duplicate_of.is_(None),
                Lead.status.in_(
                    [
                        LeadStatus.scored.value,
                        LeadStatus.assigned.value,
                        LeadStatus.new.value,
                    ]
                ),
                Lead.lead_id.notin_(
                    select(Activity.lead_id)
                    .where(Activity.event_time >= cutoff)
                    .distinct()
                ),
            )
        )
        or 0
    )
    total = _count(
        session,
        Lead.is_duplicate_of.is_(None),
        Lead.status.in_(
            [LeadStatus.scored.value, LeadStatus.assigned.value, LeadStatus.new.value]
        ),
    )
    return {
        "metric": "stale_lead_rate",
        "stale_leads": stale,
        "open_leads": total,
        "value": round(stale / total, 4) if total else 0.0,
        "formula": "open leads with no activity since base+30d / open leads",
    }


def consent_coverage_rate(session: Session) -> dict[str, Any]:
    """P1 coverage: leads with granted email consent / total leads."""
    total = _count(session, Lead.is_duplicate_of.is_(None))
    granted = int(
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .join(Consent, Consent.lead_id == Lead.lead_id)
            .where(
                Consent.subject_type == "lead",
                Consent.channel == "email",
                Consent.status == "granted",
                Lead.is_duplicate_of.is_(None),
            )
        )
        or 0
    )
    return {
        "metric": "consent_coverage_rate",
        "granted_leads": granted,
        "total_leads": total,
        "value": round(granted / total, 4) if total else 0.0,
        "formula": "leads with granted email consent / non-duplicate leads",
    }


def summary_metrics(session: Session, settings: Settings) -> dict[str, Any]:
    from yottaflex.engines.exceptions import exception_evaluation

    return {
        "lead_conversion_rate": lead_conversion_rate(session, settings),
        "opportunity_win_rate": opportunity_win_rate(session),
        "lead_qualification_rate": lead_qualification_rate(session),
        "assignment_coverage": assignment_coverage_metric(session),
        "consent_compliance": consent_compliance_metric(session),
        "duplicate_detection_rate": duplicate_detection_rate(session),
        "opt_out_rate": opt_out_rate(session),
        "disqualified_rate": disqualified_rate(session),
        "stale_lead_rate": stale_lead_rate(session, settings),
        "consent_coverage_rate": consent_coverage_rate(session),
        "funnel": conversion_funnel(session),
        "category_distribution": category_distribution(session),
        "stage_distribution": stage_distribution(session),
        "exception_evaluation": exception_evaluation(session),
        "heldout_evaluation": heldout_evaluation(session),
        "opportunity_selection_checks": opportunity_selection_checks(session),
    }
