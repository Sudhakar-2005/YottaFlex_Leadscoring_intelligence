"""Lead status history engine (P1-1).

Append-only transitions: every lead timeline is reconstructable from records.
Lead timelines: new -> scored -> assigned -> working -> qualified -> converted
(could be disqualified/opted_out via agents/manual actions).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.db.models import ActorType, Lead, LeadStatusHistory
from yottaflex.logging_setup import get_logger

log = get_logger("lead_status_history")

ALLOWED: dict[str, set[str]] = {
    "new": {"scored", "disqualified", "opted_out"},
    "scored": {"assigned", "disqualified", "opted_out"},
    "assigned": {"working", "qualified", "disqualified", "opted_out"},
    "working": {"qualified", "disqualified", "opted_out"},
    "qualified": {"converted", "disqualified", "opted_out"},
    "converted": set(),
    "disqualified": set(),
    "opted_out": set(),
}


def append_status_change(
    session: Session,
    lead: Lead,
    to_status: str,
    changed_at: datetime,
    reason: str,
    actor_type: str = ActorType.system.value,
    actor_id: str | None = None,
    force: bool = False,
) -> LeadStatusHistory | None:
    """Append history row and transition lead.status. No-op if already there."""
    current = lead.status
    if to_status == current and not force:
        return None
    if not force and current is not None and to_status not in ALLOWED.get(current, set()):
        # unknown/custom paths permitted but logged (future workflow flexibility)
        log.debug("lead %s: non-standard transition %s -> %s", lead.lead_id, current, to_status)
    row = LeadStatusHistory(
        lead_id=lead.lead_id,
        from_status=current if current else None,
        to_status=to_status,
        changed_at=changed_at,
        reason=reason,
        actor_type=actor_type,
        actor_id=actor_id,
        created_at=changed_at,
    )
    session.add(row)
    lead.status = to_status
    lead.updated_at = changed_at
    return row


def record_initial_status(
    session: Session, lead: Lead, at: datetime, reason: str = "lead created"
) -> LeadStatusHistory:
    """Initial timeline row: None -> new."""
    row = LeadStatusHistory(
        lead_id=lead.lead_id,
        from_status=None,
        to_status=lead.status or "new",
        changed_at=at,
        reason=reason,
        actor_type=ActorType.system.value,
        actor_id="data_generator",
        created_at=at,
    )
    session.add(row)
    return row


def get_timeline(session: Session, lead_id: int) -> list[LeadStatusHistory]:
    return list(
        session.scalars(
            select(LeadStatusHistory)
            .where(LeadStatusHistory.lead_id == lead_id)
            .order_by(LeadStatusHistory.changed_at, LeadStatusHistory.history_id)
        ).all()
    )


def validate_timeline(session: Session, lead_id: int) -> list[str]:
    rows = get_timeline(session, lead_id)
    if not rows:
        return [f"lead {lead_id}: missing status history"]
    issues: list[str] = []
    for prev, nxt in zip(rows, rows[1:]):
        if nxt.changed_at < prev.changed_at:
            issues.append(f"non-monotonic time at history {nxt.history_id}")
        if nxt.from_status != prev.to_status:
            issues.append(
                f"from/to mismatch: expected {prev.to_status} got {nxt.from_status}"
            )
    return issues
