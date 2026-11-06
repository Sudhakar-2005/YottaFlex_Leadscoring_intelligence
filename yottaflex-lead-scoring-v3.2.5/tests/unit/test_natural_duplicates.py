from __future__ import annotations

from sqlalchemy import func, select

from yottaflex.config import Settings
from yottaflex.db.models import (
    Company,
    Contact,
    DuplicateGroundTruth,
    Lead,
    Opportunity,
)
from yottaflex.engines.deduplication import run_deduplication


def test_natural_duplicates_exist_in_baseline(generated_session, mini_settings: Settings):
    """P0-B: baseline contains controlled natural duplicates of all four kinds."""
    sess = generated_session

    dup_companies = sess.scalar(
        select(func.count()).select_from(Company).where(Company.is_duplicate_of.is_not(None))
    )
    assert dup_companies == 0  # not marked until dedup runs

    report = run_deduplication(sess)
    assert report.count > 0

    marked_companies = sess.scalar(
        select(func.count()).select_from(Company).where(Company.is_duplicate_of.is_not(None))
    ) or 0
    marked_contacts = sess.scalar(
        select(func.count()).select_from(Contact).where(Contact.is_duplicate_of.is_not(None))
    ) or 0
    marked_leads = sess.scalar(
        select(func.count()).select_from(Lead).where(Lead.is_duplicate_of.is_not(None))
    ) or 0
    # natural dupe config caps at 10% of each pool; mini pools are tiny
    assert marked_companies >= 1
    assert marked_contacts >= 1
    assert marked_leads >= 1

    # duplicate_gt records all natural copies with origin='natural'
    gt_origins = {
        origin: c
        for origin, c in sess.execute(
            select(DuplicateGroundTruth.origin, func.count()).group_by(
                DuplicateGroundTruth.origin
            )
        ).all()
    }
    assert gt_origins.get("natural", 0) >= 3  # companies + contacts + leads
    assert gt_origins.get("injected", 0) == 0

    entities = {
        row[0]
        for row in sess.execute(select(DuplicateGroundTruth.entity).distinct()).all()
    }
    assert {"company", "contact", "lead"}.issubset(entities)

    # originals preserved: primary rows still exist with is_duplicate_of None
    primaries = sess.scalars(
        select(Lead).where(Lead.is_duplicate_of.is_(None)).limit(1)
    ).first()
    assert primaries is not None
    total_leads = sess.scalar(select(func.count()).select_from(Lead)) or 0
    assert total_leads == mini_settings.counts.leads

    # every duplicate_gt row carries business IDs
    for r in sess.scalars(select(DuplicateGroundTruth)).all():
        assert r.primary_business_id and r.duplicate_business_id
        assert r.detected is True


def test_natural_duplicate_opportunities(generated_session, mini_settings: Settings):
    """P0-B/P0-D: baseline holds natural dup opportunities, GT origin='natural'."""
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.opportunity import convert_qualified_leads
    from yottaflex.engines.scoring import score_all_leads

    sess = generated_session
    score_all_leads(sess, mini_settings)
    assign_leads(sess, mini_settings)
    convert_qualified_leads(sess, mini_settings, target_count=20)

    dup_opps = sess.scalar(
        select(func.count()).select_from(Opportunity).where(Opportunity.is_duplicate_flag.is_(True))
    ) or 0
    assert dup_opps >= 1

    gt = sess.execute(
        select(DuplicateGroundTruth)
        .where(
            DuplicateGroundTruth.entity == "opportunity",
            DuplicateGroundTruth.origin == "natural",
        )
        .limit(1)
    ).first()
    assert gt is not None
    assert gt[0].primary_business_id.startswith("OPP-2026-")
    assert gt[0].duplicate_business_id.startswith("OPP-2026-")

    # lead.converted_opportunity_id points to a primary only (unique constraint)
    converted = sess.scalars(
        select(Opportunity).where(
            Opportunity.opportunity_id.in_(
                select(Lead.converted_opportunity_id).where(
                    Lead.converted_opportunity_id.is_not(None)
                )
            )
        )
    ).all()
    assert all(o.is_duplicate_flag is False for o in converted)


def test_injected_duplicates_are_separate_from_natural(generated_session, mini_settings: Settings):
    """Deliberately injected EX-04 duplicates keep origin='injected' GT."""
    from yottaflex.engines import anomaly_injection
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
    from yottaflex.engines.scoring import score_all_leads

    sess = generated_session
    score_all_leads(sess, mini_settings)
    assign_leads(sess, mini_settings)
    # reserve quota room so final volume lands exactly on 20 (mirrors pipeline)
    convert_qualified_leads(sess, mini_settings, target_count=10)
    advance_opportunities_realistic(sess, mini_settings)
    anomaly_injection.inject_all_anomalies(sess, mini_settings)

    natural = sess.scalar(
        select(func.count())
        .select_from(DuplicateGroundTruth)
        .where(DuplicateGroundTruth.entity == "opportunity", DuplicateGroundTruth.origin == "natural")
    ) or 0
    injected = sess.scalar(
        select(func.count())
        .select_from(DuplicateGroundTruth)
        .where(DuplicateGroundTruth.entity == "opportunity", DuplicateGroundTruth.origin == "injected")
    ) or 0
    assert natural >= 1
    assert injected >= 1
    assert natural + injected >= 2

    # total = baseline rows (target 10) + injected secondaries (mini pool may be < quota)
    total = sess.scalar(select(func.count()).select_from(Opportunity)) or 0
    assert total == 10 + injected, f"total {total} != 10 baseline + {injected} injected"
