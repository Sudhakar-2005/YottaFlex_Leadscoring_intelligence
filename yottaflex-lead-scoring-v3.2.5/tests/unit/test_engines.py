from __future__ import annotations

from yottaflex.config import Settings
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.consent import check_outreach_consent
from yottaflex.engines.deduplication import run_deduplication
from yottaflex.engines.scoring import score_all_leads
from yottaflex.engines.stage_history import StageTransitionError, append_stage_change
from yottaflex.db.models import (
    ALLOWED_STAGE_TRANSITIONS,
    Lead,
    Opportunity,
    OpportunityStage,
    StageHistory,
    Task,
    Consent,
)
from sqlalchemy import select


def test_assignment_deterministic(generated_session, mini_settings: Settings):
    from yottaflex.db.models import SalesRep

    score_all_leads(generated_session, mini_settings)
    s1 = assign_leads(generated_session, mini_settings)
    # reset leads + rep counters for second pass
    for lead in generated_session.scalars(select(Lead)).all():
        lead.assigned_salesrep_id = None
        lead.assigned_at = None
        if lead.status == "assigned":
            lead.status = "scored"
    for rep in generated_session.scalars(select(SalesRep)).all():
        rep.active_leads_count = 0
    generated_session.commit()
    s2 = assign_leads(generated_session, mini_settings)
    assert s1["assigned"] == s2["assigned"]


def test_assignment_outside_territory_forbidden_in_baseline(generated_session, mini_settings: Settings):
    from yottaflex.engines.routing import territory_covers

    score_all_leads(generated_session, mini_settings)
    assign_leads(generated_session, mini_settings)
    leads = generated_session.scalars(
        select(Lead).where(Lead.assigned_salesrep_id.is_not(None))
    ).all()
    for lead in leads:
        assert territory_covers(
            generated_session, lead.assigned_salesrep_id, lead.territory_code
        ), f"lead {lead.lead_id} assigned outside territory"


def test_consent_gate_blocks_revoked(generated_session, mini_settings: Settings):
    lead = generated_session.scalars(
        select(Lead).where(Lead.assigned_salesrep_id.is_not(None)).limit(1)
    ).first()
    if lead is None:
        # assign first
        score_all_leads(generated_session, mini_settings)
        assign_leads(generated_session, mini_settings)
        lead = generated_session.scalars(
            select(Lead).where(Lead.assigned_salesrep_id.is_not(None)).limit(1)
        ).first()
    assert lead is not None

    # force revoke
    consent = generated_session.scalars(
        select(Consent).where(
            Consent.subject_type == "lead",
            Consent.subject_id == lead.lead_id,
            Consent.channel == "email",
        )
    ).first()
    consent.status = "revoked"
    generated_session.commit()

    d = check_outreach_consent(generated_session, lead, "email")
    assert d.allowed is False
    assert d.status == "revoked"


def test_illegal_stage_transition_rejected(generated_session, mini_settings: Settings):
    # create minimal opportunity via pipeline pieces
    from yottaflex.engines.opportunity import convert_qualified_leads
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.scoring import score_all_leads
    from sqlalchemy import func

    score_all_leads(generated_session, mini_settings)
    # qualify some
    for lead in generated_session.scalars(select(Lead)).all():
        if lead.assigned_salesrep_id is None:
            pass
    assign_leads(generated_session, mini_settings)
    for lead in generated_session.scalars(
        select(Lead).where(Lead.assigned_salesrep_id.is_not(None), Lead.lead_category.in_(["hot", "warm"]))
    ).all():
        lead.status = "qualified"
    generated_session.commit()
    convert_qualified_leads(generated_session, mini_settings, target_count=5)

    opp = generated_session.scalars(select(Opportunity).limit(1)).first()
    assert opp is not None
    # new_lead -> proposal is illegal
    try:
        append_stage_change(
            generated_session,
            opp,
            OpportunityStage.proposal,
            changed_at=opp.stage_entered_at,
            reason="illegal skip",
        )
        raised = False
    except StageTransitionError:
        raised = True
    assert raised


def test_stage_history_append_only(generated_session, mini_settings: Settings):
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.opportunity import convert_qualified_leads
    from yottaflex.engines.scoring import score_all_leads
    from datetime import datetime

    score_all_leads(generated_session, mini_settings)
    assign_leads(generated_session, mini_settings)
    for lead in generated_session.scalars(
        select(Lead)
        .where(Lead.assigned_salesrep_id.is_not(None))
        .limit(20)
    ).all():
        lead.status = "qualified"
    generated_session.commit()
    convert_qualified_leads(generated_session, mini_settings, target_count=5)
    opp = generated_session.scalars(select(Opportunity).limit(1)).first()
    before = generated_session.scalars(
        select(StageHistory).where(StageHistory.opportunity_id == opp.opportunity_id)
    ).all()
    assert len(before) >= 1
    # append qualified
    append_stage_change(
        generated_session,
        opp,
        OpportunityStage.qualified,
        changed_at=datetime(2025, 6, 1),
        reason="ok",
    )
    generated_session.commit()
    after = generated_session.scalars(
        select(StageHistory)
        .where(StageHistory.opportunity_id == opp.opportunity_id)
        .order_by(StageHistory.stage_history_id)
    ).all()
    assert len(after) == len(before) + 1
    # original rows unchanged (first row still initial)
    assert after[0].stage_history_id == before[0].stage_history_id
    assert after[0].to_stage == before[0].to_stage


def test_dedup_marks_not_deletes(generated_session, mini_settings: Settings):
    # inject a natural dupe email
    leads = generated_session.scalars(select(Lead).limit(2)).all()
    if len(leads) >= 2:
        leads[1].email_normalized = leads[0].email_normalized
        leads[1].email = leads[0].email
        generated_session.commit()
    from sqlalchemy import func

    before = generated_session.scalar(select(func.count()).select_from(Lead))
    run_deduplication(generated_session)
    after = generated_session.scalar(select(func.count()).select_from(Lead))
    assert before == after
    marked = generated_session.scalar(
        select(func.count()).select_from(Lead).where(Lead.is_duplicate_of.is_not(None))
    )
    assert marked and marked >= 1
