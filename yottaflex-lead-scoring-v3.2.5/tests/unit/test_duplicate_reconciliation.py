from __future__ import annotations

from sqlalchemy import select

from yottaflex.config import Settings
from yottaflex.db.models import DuplicateGroundTruth, Lead


def test_duplicate_reconciliation_from_actual_records(generated_session, mini_settings: Settings):
    """V3 Phase 2: duplicate_gt counts must reflect actual data, not config.

    In mini data (seed 42), configured lead dupes + shared-email groups together
    determine GT rows; the identity must hold: GT rows beyond configured copies
    are exactly extra shared-email groups from contact-derived emails.
    """
    from yottaflex.engines.deduplication import run_deduplication

    sess = generated_session
    run_deduplication(sess)

    from sqlalchemy import func

    # count actual duplicate rows from GT table (authoritative)
    gt_count = sess.scalar(
        select(func.count())
        .select_from(DuplicateGroundTruth)
        .where(DuplicateGroundTruth.entity == "lead", DuplicateGroundTruth.origin == "natural")
    ) or 0
    assert gt_count >= 1

    # email group identity: group non-primaries == GT rows
    from collections import defaultdict

    leads = sess.scalars(select(Lead)).all()
    by_email: dict[str, list[int]] = defaultdict(list)
    for lead in leads:
        by_email[lead.email_normalized].append(lead.lead_id)
    groups = [ids for ids in by_email.values() if len(ids) > 1]
    non_primaries = sum(len(ids) - 1 for ids in groups)
    assert gt_count == non_primaries, (
        f"lead GT rows {gt_count} != email-group non-primaries {non_primaries}"
    )
