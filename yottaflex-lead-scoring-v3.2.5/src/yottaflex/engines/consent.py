from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.db.models import Consent, ConsentStatus, ConsentSubjectType, Lead, Task
from yottaflex.logging_setup import get_logger

log = get_logger("consent")


@dataclass
class ConsentDecision:
    allowed: bool
    status: str
    reason: str
    consent_id: int | None = None


def get_latest_consent(
    session: Session,
    subject_type: str,
    subject_id: int,
    channel: str,
    as_of: datetime | None = None,
) -> Consent | None:
    q = (
        select(Consent)
        .where(
            Consent.subject_type == subject_type,
            Consent.subject_id == subject_id,
            Consent.channel == channel,
        )
        .order_by(Consent.valid_from.desc(), Consent.consent_id.desc())
    )
    rows = session.scalars(q).all()
    if as_of is not None:
        for c in rows:
            if c.valid_from <= as_of and (c.valid_to is None or c.valid_to > as_of):
                return c
        return None
    return rows[0] if rows else None


def check_outreach_consent(
    session: Session,
    lead: Lead,
    channel: str = "email",
    as_of: datetime | None = None,
) -> ConsentDecision:
    """Consent validation engine (E). Lead-level consent required for outreach (BR-C01)."""
    consent = get_latest_consent(session, ConsentSubjectType.lead.value, lead.lead_id, channel, as_of)
    if consent is None:
        return ConsentDecision(False, "missing", "no consent record for channel")
    if consent.status == ConsentStatus.granted.value:
        return ConsentDecision(True, consent.status, "granted", consent.consent_id)
    if consent.status == ConsentStatus.revoked.value:
        return ConsentDecision(False, consent.status, "consent revoked", consent.consent_id)
    if consent.status == ConsentStatus.expired.value:
        return ConsentDecision(False, consent.status, "consent expired", consent.consent_id)
    return ConsentDecision(False, consent.status, f"status={consent.status}", consent.consent_id)


def is_opted_out(session: Session, lead_id: int) -> bool:
    lead = session.get(Lead, lead_id)
    if lead is None:
        return False
    if lead.status == "opted_out":
        return True
    d = check_outreach_consent(session, lead, "email")
    return not d.allowed and d.status in ("revoked", "missing")


def enforce_consent_on_tasks(session: Session) -> dict[str, int]:
    """Block pending outreach tasks whose lead lacks valid consent (BR-C02)."""
    blocked = 0
    tasks = session.scalars(
        select(Task).where(Task.status == "pending", Task.consent_checked.is_(False))
    ).all()
    for task in tasks:
        lead = session.get(Lead, task.lead_id)
        if lead is None:
            continue
        channel = "phone" if task.task_type == "call" else "email"
        decision = check_outreach_consent(session, lead, channel)
        task.consent_checked = True
        if not decision.allowed:
            task.status = "blocked"
            task.blocked_reason = f"consent_{decision.status}: {decision.reason}"
            blocked += 1
    session.commit()
    log.info("blocked tasks for consent: %d", blocked)
    return {"blocked": blocked, "checked": len(tasks)}
