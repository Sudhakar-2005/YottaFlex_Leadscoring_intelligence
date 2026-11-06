"""Validate a generated database (V3.2: full coverage, no sampling).

Checks run against EVERY applicable record:
  - engine validation report (counts, FKs, domains, full score arithmetic)
  - business-ID format compliance via exact SQL GLOB patterns (all rows)
  - opportunity volume exactness
  - duplicate ground truth by origin
  - collapsed stage timestamps across ALL opportunities (SQL aggregate)
  - stage-history completeness: every opportunity has >= 1 history row

Usage:
    python scripts/validate_data.py
    python scripts/validate_data.py --database-url sqlite:///data/yottaflex.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, select, text  # noqa: E402

from yottaflex.config import load_settings  # noqa: E402
from yottaflex.db.schema import init_db, open_session  # noqa: E402
from yottaflex.db.session import make_engine  # noqa: E402
from yottaflex.engines.validation import validate_dataset  # noqa: E402

# Exact business-ID patterns as SQLite GLOB (character classes = full coverage,
# no per-row Python sampling)
BID_GLOBS = {
    "company": "CO-[0-9][0-9][0-9][0-9][0-9][0-9]",
    "contact": "CON-[0-9][0-9][0-9][0-9][0-9][0-9]",
    "lead": "LEAD-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]",
    "opportunity": "OPP-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]",
    "activity": "ACT-LEAD-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9]",
    "task": "TASK-LEAD-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9]",
}


def _bid_format_check(session, table: str, glob: str) -> dict:
    total = int(session.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
    invalid = int(
        session.execute(
            text(f'SELECT COUNT(*) FROM "{table}" WHERE business_id NOT GLOB :pat'),
            {"pat": glob},
        ).scalar()
        or 0
    )
    sample = session.execute(
        text(f'SELECT business_id FROM "{table}" WHERE business_id NOT GLOB :pat LIMIT 5'),
        {"pat": glob},
    ).scalars().all()
    return {"total": total, "invalid": invalid, "samples": list(sample)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    settings = load_settings()
    engine = make_engine(args.database_url, settings)
    init_db(engine)

    from yottaflex.db.models import DuplicateGroundTruth, Opportunity

    with open_session(engine) as session:
        expected = {
            "company": settings.counts.companies,
            "contact": settings.counts.contacts,
            "lead": settings.counts.leads,
        }
        report = validate_dataset(session, expected=expected, settings=settings)

        checks: dict[str, object] = {}
        # opportunity volume exact
        opp_total = int(
            session.scalar(select(func.count()).select_from(Opportunity)) or 0
        )
        checks["opportunity_count_exact"] = opp_total == settings.counts.opportunities
        checks["opportunity_count"] = opp_total

        # business-ID format — ALL rows via GLOB
        checks["bid_format"] = {
            entity: _bid_format_check(session, entity, glob)
            for entity, glob in BID_GLOBS.items()
        }
        checks["bid_format_all_valid"] = all(
            v["invalid"] == 0 for v in checks["bid_format"].values()
        )

        # duplicate ground truth by origin
        checks["duplicate_gt_by_origin"] = {
            origin: c
            for origin, c in session.execute(
                select(DuplicateGroundTruth.origin, func.count()).group_by(
                    DuplicateGroundTruth.origin
                )
            ).all()
        }

        # collapsed stage timestamps — ALL opportunities (SQL aggregate)
        collapsed = int(
            session.execute(
                text(
                    "SELECT COUNT(*) FROM ("
                    "  SELECT opportunity_id FROM stage_history"
                    "  GROUP BY opportunity_id"
                    "  HAVING COUNT(*) >= 2 AND COUNT(DISTINCT changed_at) = 1"
                    ")"
                )
            ).scalar()
            or 0
        )
        checks["stage_timestamps_collapsed"] = collapsed

        # stage-history completeness — every opportunity has >= 1 history row
        missing_history = int(
            session.execute(
                text(
                    "SELECT COUNT(*) FROM opportunity o "
                    "LEFT JOIN (SELECT DISTINCT opportunity_id FROM stage_history) s "
                    "  ON s.opportunity_id = o.opportunity_id "
                    "WHERE s.opportunity_id IS NULL"
                )
            ).scalar()
            or 0
        )
        checks["opportunities_without_history"] = missing_history

        passed = (
            report.passed
            and checks["opportunity_count_exact"]
            and checks["bid_format_all_valid"]
            and collapsed == 0
            and missing_history == 0
        )

    summary = {
        "passed": passed,
        "validation_report": report.to_dict(),
        "checks": checks,
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
