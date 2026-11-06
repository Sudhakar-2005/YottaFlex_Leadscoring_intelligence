from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    Activity,
    Campaign,
    Company,
    Consent,
    Contact,
    Lead,
    Opportunity,
    SalesRep,
    ScoreRule,
    StageHistory,
    Task,
)


@dataclass
class ValidationIssue:
    check: str
    entity: str
    record_id: int | None
    severity: str  # critical | high | medium | low
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    checks_run: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def passed(self) -> bool:
        return self.critical_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "critical_count": self.critical_count,
            "total_issues": len(self.issues),
            "counts": self.counts,
            "issues": [i.__dict__ for i in self.issues[:100]],
        }


def validate_dataset(
    session: Session,
    expected: dict[str, int] | None = None,
    settings: Settings | None = None,
) -> ValidationReport:
    """Data validation engine (B): counts, nulls, referential integrity, domain rules.

    V3.2: scoring checks validate ALL scored leads (no sampling). When
    ``settings`` is provided the persisted score is re-verified against the
    weighted formula for every scored record.
    """
    report = ValidationReport()

    def count(model) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    entity_models = {
        "company": Company,
        "contact": Contact,
        "lead": Lead,
        "campaign": Campaign,
        "activity": Activity,
        "consent": Consent,
        "salesrep": SalesRep,
        "task": Task,
        "opportunity": Opportunity,
        "score_rule": ScoreRule,
        "stage_history": StageHistory,
    }
    for name, model in entity_models.items():
        report.counts[name] = count(model)
        report.checks_run += 1

    # Expected counts (when provided)
    if expected:
        for key, want in expected.items():
            got = report.counts.get(key, 0)
            report.checks_run += 1
            if got != want:
                report.issues.append(
                    ValidationIssue(
                        check="row_count",
                        entity=key,
                        record_id=None,
                        severity="critical",
                        message=f"expected {want} rows, found {got}",
                    )
                )

    # Leads must have territory FK populated (non-null already) and email
    bad_email = session.scalars(
        select(Lead.lead_id).where((Lead.email_normalized.is_(None)) | (Lead.email_normalized == ""))
    ).all()
    for lid in bad_email:
        report.issues.append(
            ValidationIssue("lead_email_present", "lead", lid, "critical", "lead missing normalized email")
        )
    report.checks_run += 1

    # Activities must reference at least one subject (CHECK enforced; verify)
    orphan_acts = session.scalars(
        select(Activity.activity_id).where(
            Activity.lead_id.is_(None),
            Activity.contact_id.is_(None),
            Activity.company_id.is_(None),
        )
    ).all()
    for aid in orphan_acts:
        report.issues.append(
            ValidationIssue("activity_subject", "activity", aid, "critical", "activity has no subject")
        )
    report.checks_run += 1

    # Orphan FKs via left join (lead.company_id not in company)
    orphan_leads = session.scalars(
        select(Lead.lead_id)
        .outerjoin(Company, Lead.company_id == Company.company_id)
        .where(Lead.company_id.is_not(None), Company.company_id.is_(None))
    ).all()
    for lid in orphan_leads:
        report.issues.append(
            ValidationIssue("lead_company_fk", "lead", lid, "critical", "lead.company_id missing")
        )
    report.checks_run += 1

    orphan_tasks = session.scalars(
        select(Task.task_id)
        .outerjoin(Lead, Task.lead_id == Lead.lead_id)
        .where(Lead.lead_id.is_(None))
    ).all()
    for tid in orphan_tasks:
        report.issues.append(
            ValidationIssue("task_lead_fk", "task", tid, "critical", "task.lead_id missing")
        )
    report.checks_run += 1

    # Domain: lead status in known set
    valid_statuses = {
        "new", "scored", "assigned", "working", "qualified",
        "converted", "disqualified", "opted_out",
    }
    bad_status = session.scalars(
        select(Lead.lead_id).where(Lead.status.not_in(valid_statuses))
    ).all()
    for lid in bad_status:
        report.issues.append(
            ValidationIssue("lead_status_domain", "lead", lid, "high", "invalid lead status")
        )
    report.checks_run += 1

    # Scoring validation (V3.2): ALL scored records, not a sample
    scored_total = int(
        session.scalar(
            select(func.count()).select_from(Lead).where(Lead.lead_score.is_not(None))
        )
        or 0
    )
    bad_score_filter = (Lead.lead_score < 0) | (Lead.lead_score > 100)
    bad_range = int(
        session.scalar(
            select(func.count()).select_from(Lead).where(
                Lead.lead_score.is_not(None), bad_score_filter
            )
        )
        or 0
    )
    if bad_range:
        sample_ids = session.scalars(
            select(Lead.lead_id)
            .where(Lead.lead_score.is_not(None), bad_score_filter)
            .order_by(Lead.lead_id)
            .limit(10)
        ).all()
        report.issues.append(
            ValidationIssue(
                "lead_score_range",
                "lead",
                sample_ids[0] if sample_ids else None,
                "critical",
                f"{bad_range} of {scored_total} scored leads outside 0-100 "
                f"(first ids: {sample_ids})",
            )
        )
    report.checks_run += 1

    bad_cat = int(
        session.scalar(
            select(func.count()).select_from(Lead).where(
                Lead.lead_category.is_not(None),
                Lead.lead_category.not_in(("hot", "warm", "nurture", "cold")),
            )
        )
        or 0
    )
    if bad_cat:
        sample_ids = session.scalars(
            select(Lead.lead_id)
            .where(
                Lead.lead_category.is_not(None),
                Lead.lead_category.not_in(("hot", "warm", "nurture", "cold")),
            )
            .order_by(Lead.lead_id)
            .limit(10)
        ).all()
        report.issues.append(
            ValidationIssue(
                "lead_category_domain",
                "lead",
                sample_ids[0] if sample_ids else None,
                "high",
                f"{bad_cat} leads have invalid category (first ids: {sample_ids})",
            )
        )
    report.checks_run += 1

    # Arithmetic identity: persisted score == weighted formula, ALL scored leads
    if settings is not None and scored_total:
        w = settings.scoring.weights
        rows = session.execute(
            select(
                Lead.lead_id,
                Lead.fit_score,
                Lead.intent_score,
                Lead.engagement_score,
                Lead.lead_score,
            ).where(Lead.lead_score.is_not(None))
        ).all()
        mismatched: list[tuple[int, int, int]] = []
        missing_components = 0
        for lid, fit, intent, engage, score in rows:
            if fit is None or intent is None or engage is None:
                missing_components += 1
                continue
            expected_score = round(
                fit * w.fit + intent * w.intent + engage * w.engagement
            )
            if score != expected_score:
                mismatched.append((lid, score, expected_score))
        if missing_components:
            report.issues.append(
                ValidationIssue(
                    "lead_score_components_missing",
                    "lead",
                    None,
                    "critical",
                    f"{missing_components} scored leads missing component scores",
                )
            )
        if mismatched:
            report.issues.append(
                ValidationIssue(
                    "lead_score_arithmetic",
                    "lead",
                    mismatched[0][0],
                    "critical",
                    f"{len(mismatched)} of {scored_total} scores fail the weighted "
                    f"formula (lead_id, actual, expected): {mismatched[:5]}",
                )
            )
        report.checks_run += 1

    # Stage history monotonic changed_at per opportunity
    rows = session.execute(
        select(StageHistory.opportunity_id, StageHistory.changed_at, StageHistory.stage_history_id)
        .order_by(StageHistory.opportunity_id, StageHistory.changed_at, StageHistory.stage_history_id)
    ).all()
    prev: dict[int, Any] = {}
    for opp_id, changed_at, sh_id in rows:
        if opp_id in prev and changed_at < prev[opp_id]:
            report.issues.append(
                ValidationIssue(
                    "stage_history_time_monotonic",
                    "stage_history",
                    sh_id,
                    "high",
                    f"changed_at went backwards for opportunity {opp_id}",
                )
            )
        prev[opp_id] = changed_at
    report.checks_run += 1

    # Duplicate open opportunities per lead (baseline should be 0)
    dup_opps = session.execute(
        select(Opportunity.lead_id, func.count().label("c"))
        .group_by(Opportunity.lead_id)
        .having(func.count() > 1)
    ).all()
    for lead_id, c in dup_opps:
        report.issues.append(
            ValidationIssue(
                "single_open_opportunity",
                "opportunity",
                lead_id,
                "high",
                f"lead {lead_id} has {c} opportunities",
            )
        )
    report.checks_run += 1

    return report
