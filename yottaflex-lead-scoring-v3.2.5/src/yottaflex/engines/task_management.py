from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    Lead,
    LeadStatus,
    Priority,
    Task,
    TaskStatus,
    TaskType,
)
from yottaflex.engines.consent import check_outreach_consent
from yottaflex.ids import task_bid
from yottaflex.logging_setup import get_logger

log = get_logger("tasks")

CATEGORY_PRIORITY = {
    "hot": Priority.high.value,
    "warm": Priority.medium.value,
    "nurture": Priority.medium.value,
    "cold": Priority.low.value,
}


def _task_type_for_category(category: str, settings: Settings) -> str:
    mapping = {
        "hot": settings.tasks.hot_task_type,
        "warm": settings.tasks.warm_task_type,
        "nurture": settings.tasks.nurture_task_type,
        "cold": settings.tasks.cold_task_type,
    }
    return mapping.get(category, "follow_up")


def _due_days(category: str, settings: Settings) -> int:
    return settings.tasks.due_days.get(category, 7)


def create_followup_tasks(
    session: Session,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, int]:
    """Follow-up Task Management Engine (H). Consent-gated (BR-C01/BR-T01..T03)."""
    if now is None:
        from datetime import timedelta

        now = settings.base_dt().replace(hour=14, minute=0, second=0, microsecond=0)
        now = now + timedelta(days=62)

    leads = session.scalars(
        select(Lead)
        .where(
            Lead.assigned_salesrep_id.is_not(None),
            Lead.is_duplicate_of.is_(None),
            Lead.status.in_(
                [
                    LeadStatus.assigned.value,
                    LeadStatus.scored.value,
                    LeadStatus.working.value,
                ]
            ),
            Lead.lead_category.is_not(None),
        )
        .order_by(Lead.lead_id)
    ).all()

    created = 0
    blocked = 0
    skipped_cold = 0
    skipped_exists = 0

    for lead in leads:
        category = lead.lead_category or "cold"
        if category == "cold" and not settings.tasks.cold_create_task:
            skipped_cold += 1
            continue

        existing = session.scalars(
            select(Task).where(
                Task.lead_id == lead.lead_id,
                Task.status.in_([TaskStatus.pending.value, TaskStatus.in_progress.value]),
            )
        ).first()
        if existing is not None:
            skipped_exists += 1
            continue

        ttype = _task_type_for_category(category, settings)
        channel = "phone" if ttype == "call" else "email"
        decision = check_outreach_consent(session, lead, channel, as_of=now)

        due = now + timedelta(days=_due_days(category, settings))
        existing_task_count = (
            session.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.lead_id == lead.lead_id)
            )
            or 0
        )
        task = Task(
            business_id=task_bid(lead.business_id, int(existing_task_count) + 1),
            lead_id=lead.lead_id,
            salesrep_id=lead.assigned_salesrep_id,  # type: ignore[arg-type]
            task_type=ttype,
            title=f"{ttype.title()} — {lead.first_name} {lead.last_name} ({category})",
            description=f"Auto follow-up for {category} lead {lead.lead_id}",
            due_date=due,
            status=TaskStatus.pending.value,
            priority=CATEGORY_PRIORITY.get(category, Priority.medium.value),
            consent_checked=True,
            blocked_reason=None,
            created_at=now,
            updated_at=now,
        )
        if not decision.allowed:
            task.status = TaskStatus.blocked.value
            task.blocked_reason = f"consent_{decision.status}: {decision.reason}"
            blocked += 1
        else:
            created += 1
            if lead.status == LeadStatus.assigned.value:
                from yottaflex.engines.lead_status_history import append_status_change

                append_status_change(
                    session,
                    lead,
                    LeadStatus.working.value,
                    now,
                    reason="follow-up task created",
                    actor_id="tasks",
                )
        session.add(task)

    session.commit()
    log.info(
        "tasks created=%d blocked=%d skipped_cold=%d skipped_exists=%d",
        created,
        blocked,
        skipped_cold,
        skipped_exists,
    )
    return {
        "created": created,
        "blocked_consent": blocked,
        "skipped_cold": skipped_cold,
        "skipped_exists": skipped_exists,
        "considered": len(leads),
    }
