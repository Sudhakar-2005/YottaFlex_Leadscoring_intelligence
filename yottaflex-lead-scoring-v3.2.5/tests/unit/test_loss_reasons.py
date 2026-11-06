"""V3.2.2 regression tests: opportunity loss reasons."""
from __future__ import annotations

from sqlalchemy import select

from yottaflex.config import Settings
from yottaflex.db.models import Lead, Opportunity, OpportunityStage
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.opportunity import LOSS_REASONS, advance_opportunities_realistic, convert_qualified_leads
from yottaflex.engines.scoring import score_all_leads


def _prep(session, settings: Settings, target: int = 30):
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


def test_lost_opportunities_have_valid_reasons_won_have_none(generated_session, mini_settings: Settings):
    sess = generated_session
    _prep(sess, mini_settings)

    lost = sess.scalars(
        select(Opportunity).where(Opportunity.stage == OpportunityStage.lost.value)
    ).all()
    won = sess.scalars(
        select(Opportunity).where(Opportunity.stage == OpportunityStage.won.value)
    ).all()
    assert lost, "fixture must produce lost opportunities"
    assert won, "fixture must produce won opportunities"

    for opp in lost:
        assert opp.loss_reason is not None, f"lost opp {opp.opportunity_id} missing loss_reason"
        assert opp.loss_reason in LOSS_REASONS
    for opp in won:
        assert opp.loss_reason is None, f"won opp {opp.opportunity_id} must not have loss_reason"


def test_open_opportunities_have_no_reason_and_are_not_lost(generated_session, mini_settings: Settings):
    """V3.2.3: open opportunities (demo/proposal/new_lead) never carry a loss reason."""
    sess = generated_session
    _prep(sess, mini_settings)

    open_stages = (
        OpportunityStage.new_lead.value,
        OpportunityStage.qualified.value,
        OpportunityStage.demo.value,
        OpportunityStage.proposal.value,
    )
    open_opps = sess.scalars(
        select(Opportunity).where(Opportunity.stage.in_(open_stages))
    ).all()
    assert open_opps, "fixture must produce open opportunities"
    for opp in open_opps:
        assert opp.loss_reason is None, (
            f"open opp {opp.opportunity_id} (stage={opp.stage}) must not have loss_reason"
        )
        assert opp.lost_at is None


def test_loss_reasons_deterministic_across_runs(generated_session, mini_settings: Settings):
    """Same seed -> identical (lead, stage, loss_reason) mapping, stable pick function."""
    sess = generated_session
    _prep(sess, mini_settings, target=20)
    mapping_a = {
        (o.lead_id, o.stage): o.loss_reason
        for o in sess.scalars(select(Opportunity)).all()
    }

    # second, independent database with the same seed
    from yottaflex.db.schema import init_db, open_session
    from yottaflex.db.session import make_engine
    from yottaflex.engines.data_generator import generate_all

    engine = make_engine("sqlite:///:memory:", mini_settings)
    init_db(engine)
    with open_session(engine) as sess2:
        generate_all(sess2, mini_settings)
        _prep(sess2, mini_settings, target=20)
        mapping_b = {
            (o.lead_id, o.stage): o.loss_reason
            for o in sess2.scalars(select(Opportunity)).all()
        }
    engine.dispose()

    assert mapping_a == mapping_b
