from __future__ import annotations

import inspect

from sqlalchemy import func, select

from yottaflex.config import Settings
from yottaflex.db.models import Lead, Opportunity, StageHistory
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
from yottaflex.engines.scoring import score_all_leads


def _prepare(session, settings: Settings, target: int = 20):
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


def test_no_lead_score_in_selection_or_outcome():
    """P0-D regression: opportunity code must not read the final score/category."""
    import ast
    import inspect

    from yottaflex.engines import opportunity

    tree = ast.parse(inspect.getsource(opportunity))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("lead_score", "lead_category"), (
                f"opportunity.py reads {node.attr} — score leakage (P0-D)"
            )


def test_selection_not_top_score(generated_session, mini_settings: Settings):
    """Converted set must differ from the top-N by final lead_score."""
    sess = generated_session
    _prepare(sess, mini_settings, target=15)

    converted_ids = set(
        sess.execute(
            select(Lead.lead_id).where(Lead.status == "converted")
        ).scalars().all()
    )
    assert converted_ids

    top_scores = set(
        sess.execute(
            select(Lead.lead_id)
            .where(Lead.is_duplicate_of.is_(None), Lead.lead_score.is_not(None))
            .order_by(Lead.lead_score.desc(), Lead.lead_id.asc())
            .limit(len(converted_ids))
        ).scalars().all()
    )
    assert converted_ids != top_scores, (
        "converted leads are exactly the top-scored leads — score leakage"
    )

    # high-score non-converters exist
    hot_not_converted = sess.scalar(
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.is_duplicate_of.is_(None),
            Lead.lead_score.is_not(None),
            Lead.lead_score >= 80,
            Lead.status != "converted",
        )
    ) or 0
    assert hot_not_converted > 0, "no high-score non-converters — selection mirrors score"


def test_exact_opportunity_count(generated_session, mini_settings: Settings):
    sess = generated_session
    _prepare(sess, mini_settings, target=15)
    total = sess.scalar(select(func.count()).select_from(Opportunity)) or 0
    assert total == 15


def test_open_opportunities_exist(generated_session, mini_settings: Settings):
    """P0-D: realistic open pipeline (demo/proposal) in stage distribution."""
    sess = generated_session
    _prepare(sess, mini_settings, target=30)
    from yottaflex.db.models import OpportunityStage

    open_count = sess.scalar(
        select(func.count())
        .select_from(Opportunity)
        .where(Opportunity.stage.in_([OpportunityStage.demo.value, OpportunityStage.proposal.value]))
    ) or 0
    assert open_count > 0
    winners = sess.scalar(
        select(func.count())
        .select_from(Opportunity)
        .where(Opportunity.stage == OpportunityStage.won.value)
    ) or 0
    losers = sess.scalar(
        select(func.count())
        .select_from(Opportunity)
        .where(Opportunity.stage == OpportunityStage.lost.value)
    ) or 0
    assert winners > 0 and losers > 0


def test_stage_history_timestamps_are_per_step(generated_session, mini_settings: Settings):
    """P0-6: each stage-history row carries its own increasing timestamp."""
    sess = generated_session
    _prepare(sess, mini_settings, target=20)

    opps = sess.scalars(select(Opportunity).limit(10)).all()
    multi_step = 0
    for opp in opps:
        rows = sess.execute(
            select(StageHistory.to_stage, StageHistory.changed_at)
            .where(StageHistory.opportunity_id == opp.opportunity_id)
            .order_by(StageHistory.stage_history_id)
        ).all()
        if len(rows) < 3:
            continue
        multi_step += 1
        times = [r[1] for r in rows]
        assert len(set(times)) > 1, f"opp {opp.opportunity_id}: collapsed stage timestamps"
        assert times == sorted(times), f"opp {opp.opportunity_id}: non-monotonic stage times"
        # canonical path order
        stages = [r[0] for r in rows]
        assert stages[0] == "new_lead"
        assert stages[1] == "qualified"
    assert multi_step >= 3


def test_heldout_split_populated_and_analytic(generated_session, mini_settings: Settings):
    """P0-D: held-out split assigned at generation; metrics report both splits."""
    from yottaflex.engines import analytics

    sess = generated_session
    _prepare(sess, mini_settings)
    split_counts = {
        row[0]: row[1]
        for row in sess.execute(
            select(Lead.eval_split, func.count()).group_by(Lead.eval_split)
        ).all()
    }
    assert split_counts.get("dev", 0) > 0
    assert split_counts.get("heldout", 0) > 0

    he = analytics.heldout_evaluation(sess)
    assert he["split_sizes"]["dev"] > 0
    assert he["split_sizes"]["heldout"] > 0

    checks = analytics.opportunity_selection_checks(sess)
    assert checks["high_score_non_converters_gte80"] > 0
