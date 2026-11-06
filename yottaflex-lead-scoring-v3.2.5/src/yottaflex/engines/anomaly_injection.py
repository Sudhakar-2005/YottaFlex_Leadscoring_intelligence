from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    ALLOWED_STAGE_TRANSITIONS,
    AnomalyInjectionLog,
    GroundTruthException,
    IssueType,
    Lead,
    LeadScoreExplanation,
    Opportunity,
    OpportunityStage,
    Severity,
    StageHistory,
    Task,
    Consent,
)
from yottaflex.logging_setup import get_logger

log = get_logger("anomaly_injection")


def clear_injections(session: Session) -> None:
    """Remove prior injection artifacts so re-injection is idempotent.

    Does not restore soft-injected state fully — best effort for demo reruns
    (documented limitation: full re-run of baseline pipeline preferred).
    """
    session.execute(delete(AnomalyInjectionLog))
    session.execute(delete(GroundTruthException))
    # Injected duplicate-opportunity GT rows (natural baseline GT preserved)
    from yottaflex.db.models import DuplicateGroundTruth

    session.execute(
        delete(DuplicateGroundTruth).where(
            DuplicateGroundTruth.origin == "injected",
            DuplicateGroundTruth.entity == "opportunity",
        )
    )
    session.commit()


def _log_injection(
    session: Session,
    issue_type: str,
    target_entity: str,
    target_record_id: int,
    gt_label: str,
    at: datetime,
    related_lead_id: int | None = None,
    details: dict | None = None,
    expected: str = "",
    actual: str = "",
    severity: str = Severity.high.value,
) -> None:
    session.add(
        AnomalyInjectionLog(
            issue_type=issue_type,
            target_entity=target_entity,
            target_record_id=target_record_id,
            related_lead_id=related_lead_id,
            injected_at=at,
            gt_label=gt_label,
            details_json=json.dumps(details or {}),
        )
    )
    session.add(
        GroundTruthException(
            issue_type=issue_type,
            affected_entity=target_entity,
            affected_record_id=target_record_id,
            related_lead_id=related_lead_id,
            expected_behavior=expected,
            actual_behavior=actual,
            severity=severity,
            injected_at=at,
        )
    )


def inject_opted_out_contacted(session: Session, settings: Settings, at: datetime, n: int) -> int:
    """EX-01: create outreach tasks on leads with revoked/missing email consent."""
    # Find leads with revoked email consent
    revoked = session.scalars(
        select(Lead)
        .join(Consent, Consent.subject_id == Lead.lead_id)
        .where(
            Consent.subject_type == "lead",
            Consent.channel == "email",
            Consent.status == "revoked",
            Lead.assigned_salesrep_id.is_not(None),
            Lead.is_duplicate_of.is_(None),
        )
        .order_by(Lead.lead_id)
        .limit(n)
    ).all()

    injected = 0
    for lead in revoked:
        # Skip if already has blocked task for this lead
        existing = session.scalars(
            select(Task).where(Task.lead_id == lead.lead_id, Task.status == "blocked")
        ).first()
        from yottaflex.ids import task_bid

        task_seq = (
            session.scalar(
                select(func.count()).select_from(Task).where(Task.lead_id == lead.lead_id)
            )
            or 0
        )
        task = Task(
            business_id=task_bid(lead.business_id, int(task_seq) + 1),
            lead_id=lead.lead_id,
            salesrep_id=lead.assigned_salesrep_id,  # type: ignore[arg-type]
            task_type="email",
            title=f"[INJECTED] Outreach to opted-out lead {lead.lead_id}",
            description="Injected anomaly: outreach without valid consent",
            due_date=at,
            status="pending",  # violation: not blocked
            priority="high",
            consent_checked=False,
            blocked_reason=None,
            created_at=at,
            updated_at=at,
        )
        session.add(task)
        session.flush()
        _log_injection(
            session,
            IssueType.opted_out_lead_contacted.value,
            "task",
            task.task_id,
            f"opt_out_contacted_task_{task.task_id}",
            at,
            related_lead_id=lead.lead_id,
            expected="No outreach task for revoked-consent lead",
            actual=f"Pending outreach task {task.task_id} created for lead {lead.lead_id}",
            severity=Severity.critical.value,
            details={"lead_id": lead.lead_id},
        )
        injected += 1
    session.commit()
    return injected


def inject_temporal_leakage(session: Session, settings: Settings, at: datetime, n: int) -> int:
    """EX-02 (V3.2.2): create score explanations AFTER conversion that incorporate
    post-conversion intent activity — the actual temporal violation.

    Previous revisions planted a magic marker rule ("INJECTED_POST_CONVERSION_EVENT")
    which made the detector test circular. The injected scenario now contains REAL
    evidence (an intent activity after converted_at + a score computed after it)
    so detection can be performed independently from timestamps and activity data.
    """
    from yottaflex.db.models import Activity
    from yottaflex.ids import activity_bid

    leads = session.scalars(
        select(Lead)
        .where(
            Lead.converted_at.is_not(None),
            Lead.lead_score.is_not(None),
            Lead.is_duplicate_of.is_(None),
        )
        .order_by(Lead.lead_id)
        .limit(n)
    ).all()

    injected = 0
    for lead in leads:
        # 1) real post-conversion evidence: an intent event AFTER the conversion
        act_time = lead.converted_at + timedelta(days=1)
        act_seq = (
            session.scalar(
                select(func.count()).select_from(Activity).where(Activity.lead_id == lead.lead_id)
            )
            or 0
        )
        activity = Activity(
            business_id=activity_bid(lead.business_id, int(act_seq) + 1),
            lead_id=lead.lead_id,
            contact_id=lead.contact_id,
            company_id=lead.company_id,
            activity_type="demo_request",
            channel="web",
            event_time=act_time,
            campaign_id=lead.campaign_id,
            metadata_json=None,
            created_at=at,
        )
        session.add(activity)

        # 2) a score explanation produced after conversion that incorporates it
        expl = LeadScoreExplanation(
            lead_id=lead.lead_id,
            scored_at=lead.converted_at + timedelta(days=2),  # after conversion AND after the event
            fit_score=lead.fit_score or 50,
            intent_score=lead.intent_score or 50,
            engagement_score=lead.engagement_score or 50,
            lead_score=lead.lead_score or 50,
            lead_category=lead.lead_category or "warm",
            weights_json=json.dumps({"fit": 0.4, "intent": 0.35, "engagement": 0.25}),
            rules_fired_json=json.dumps(
                [
                    {
                        "rule_code": "INTENT_DEMO_REQUEST",
                        "dimension": "intent",
                        "points": 50,
                    }
                ]
            ),
            activity_cutoff_id=None,
            created_at=at,
        )
        session.add(expl)
        session.flush()
        _log_injection(
            session,
            IssueType.score_uses_post_conversion_event.value,
            "lead_score_explanation",
            expl.explanation_id,
            f"temporal_leakage_expl_{expl.explanation_id}",
            at,
            related_lead_id=lead.lead_id,
            expected="Score excludes events after conversion/scoring cutoff",
            actual=(
                f"Explanation {expl.explanation_id} scored at {expl.scored_at} (after "
                f"conversion {lead.converted_at}) used post-conversion demo_request "
                f"activity {activity.business_id} at {act_time}"
            ),
            severity=Severity.critical.value,
            details={
                "activity_business_id": activity.business_id,
                "activity_event_time": act_time.isoformat(),
                "scored_at": expl.scored_at.isoformat(),
                "converted_at": lead.converted_at.isoformat(),
            },
        )
        injected += 1
    session.commit()
    return injected


def inject_territory_mismatch(session: Session, settings: Settings, at: datetime, n: int) -> int:
    """EX-03: reassign leads to reps outside their territory."""
    from yottaflex.engines.routing import territory_covers
    from yottaflex.db.models import SalesRep

    leads = session.scalars(
        select(Lead)
        .where(
            Lead.assigned_salesrep_id.is_not(None),
            Lead.is_duplicate_of.is_(None),
        )
        .order_by(Lead.lead_id)
    ).all()

    reps = session.scalars(
        select(SalesRep).where(SalesRep.is_active.is_(True)).order_by(SalesRep.salesrep_id)
    ).all()

    injected = 0
    for lead in leads:
        if injected >= n:
            break
        wrong_rep = None
        for rep in reps:
            if rep.salesrep_id == lead.assigned_salesrep_id:
                continue
            if not territory_covers(session, rep.salesrep_id, lead.territory_code):
                wrong_rep = rep
                break
        if wrong_rep is None:
            continue

        old_rep_id = lead.assigned_salesrep_id
        old_rep = session.get(SalesRep, old_rep_id) if old_rep_id else None
        if old_rep and old_rep.active_leads_count > 0:
            old_rep.active_leads_count -= 1
        lead.assigned_salesrep_id = wrong_rep.salesrep_id
        wrong_rep.active_leads_count += 1
        lead.updated_at = at

        _log_injection(
            session,
            IssueType.lead_assigned_outside_territory.value,
            "lead",
            lead.lead_id,
            f"territory_mismatch_lead_{lead.lead_id}",
            at,
            related_lead_id=lead.lead_id,
            expected="Lead assigned within territory coverage",
            actual=(
                f"Lead {lead.lead_id} ({lead.territory_code}) reassigned "
                f"from rep {old_rep_id} to rep {wrong_rep.salesrep_id}"
            ),
            severity=Severity.high.value,
            details={"wrong_rep": wrong_rep.salesrep_id},
        )
        injected += 1
    session.commit()
    return injected


def inject_duplicate_opportunity(session: Session, settings: Settings, at: datetime, n: int) -> int:
    """EX-04: create second opportunity for leads that already have one."""
    from sqlalchemy import func

    leads = session.scalars(
        select(Lead)
        .join(Opportunity, Opportunity.lead_id == Lead.lead_id)
        .group_by(Lead.lead_id)
        .where(Lead.is_duplicate_of.is_(None))
        .order_by(Lead.lead_id)
        .limit(n)
    ).all()

    # Need a simpler query for SQLite group by
    rows = session.execute(
        select(Opportunity.lead_id, func.count())
        .group_by(Opportunity.lead_id)
        .having(func.count() == 1)
        .order_by(Opportunity.lead_id)
        .limit(n)
    ).all()

    injected = 0
    for lead_id, _c in rows:
        primary = session.scalars(
            select(Opportunity).where(Opportunity.lead_id == lead_id).limit(1)
        ).first()
        if primary is None:
            continue
        from yottaflex.engines.deduplication import record_duplicate_gt
        from yottaflex.ids import opportunity_bid

        opp_seq = (
            session.scalar(
                select(func.count()).select_from(Opportunity)
            )
            or 0
        )
        dup = Opportunity(
            business_id=opportunity_bid(int(opp_seq) + 1, settings.business_id_year),
            lead_id=primary.lead_id,
            company_id=primary.company_id,
            contact_id=primary.contact_id,
            salesrep_id=primary.salesrep_id,
            name=f"[DUP] {primary.name}",
            product_line=primary.product_line,
            amount=primary.amount,
            currency=primary.currency,
            stage=OpportunityStage.new_lead.value,
            stage_entered_at=at,
            is_duplicate_flag=True,
            created_at=at,
            updated_at=at,
        )
        session.add(dup)
        session.flush()
        session.add(
            StageHistory(
                opportunity_id=dup.opportunity_id,
                from_stage=None,
                to_stage=OpportunityStage.new_lead.value,
                changed_at=at,
                reason="injected duplicate opportunity",
                actor_type="system",
                actor_id="anomaly_injector",
                created_at=at,
            )
        )
        record_duplicate_gt(
            session,
            "opportunity",
            primary.opportunity_id,
            dup.opportunity_id,
            "lead_id",
            str(lead_id),
            "injected",
            primary.business_id,
            dup.business_id,
        )
        _log_injection(
            session,
            IssueType.duplicate_creates_duplicate_opportunity.value,
            "opportunity",
            dup.opportunity_id,
            f"dup_opp_{dup.opportunity_id}",
            at,
            related_lead_id=lead_id,
            expected="One opportunity per lead",
            actual=f"Second opportunity {dup.opportunity_id} for lead {lead_id}",
            severity=Severity.high.value,
        )
        injected += 1
    session.commit()
    return injected


def inject_stage_history_gap(session: Session, settings: Settings, at: datetime, n: int) -> int:
    """EX-05: insert illegal skip transitions (e.g. new_lead -> proposal)."""
    # Find opportunities currently at demo or proposal with full history, then
    # inject a parallel bad history row that skips stages on selected opps.
    opps = session.scalars(
        select(Opportunity)
        .where(Opportunity.stage.in_([
            OpportunityStage.proposal.value,
            OpportunityStage.won.value,
            OpportunityStage.lost.value,
        ]))
        .order_by(Opportunity.opportunity_id)
        .limit(n)
    ).all()

    injected = 0
    for opp in opps:
        # Insert a fabricated gap row claiming skip from new_lead to proposal
        # with a later timestamp that breaks path validation
        bad = StageHistory(
            opportunity_id=opp.opportunity_id,
            from_stage=OpportunityStage.new_lead.value,
            to_stage=OpportunityStage.proposal.value,
            changed_at=opp.stage_entered_at + timedelta(hours=1),
            reason="injected illegal skip new_lead -> proposal without demo",
            actor_type="system",
            actor_id="anomaly_injector",
            created_at=at,
        )
        session.add(bad)
        session.flush()
        _log_injection(
            session,
            IssueType.stage_history_has_gaps.value,
            "opportunity",
            opp.opportunity_id,
            f"stage_gap_opp_{opp.opportunity_id}",
            at,
            related_lead_id=opp.lead_id,
            expected="Canonical transitions only; no skipped stages",
            actual=f"History row {bad.stage_history_id} skips stages for opp {opp.opportunity_id}",
            severity=Severity.medium.value,
        )
        injected += 1
    session.commit()
    return injected


def inject_all_anomalies(session: Session, settings: Settings) -> dict[str, int]:
    """Inject all 5 exception types with configured quotas (baseline remains pure until this runs)."""
    if not settings.anomaly_injection.enabled:
        log.info("anomaly injection disabled")
        return {}

    at = settings.base_dt().replace(
        hour=18, minute=0, second=0, microsecond=0
    ) + timedelta(days=65)

    clear_injections(session)
    quotas = settings.anomaly_injection.quotas
    results = {
        "opted_out_contacted": inject_opted_out_contacted(
            session, settings, at, quotas.opted_out_contacted
        ),
        "temporal_leakage": inject_temporal_leakage(
            session, settings, at, quotas.temporal_leakage
        ),
        "territory_mismatch": inject_territory_mismatch(
            session, settings, at, quotas.territory_mismatch
        ),
        "duplicate_opportunity": inject_duplicate_opportunity(
            session, settings, at, quotas.duplicate_opportunity
        ),
        "stage_history_gap": inject_stage_history_gap(
            session, settings, at, quotas.stage_history_gap
        ),
    }
    log.info("injected anomalies: %s", results)
    return results
