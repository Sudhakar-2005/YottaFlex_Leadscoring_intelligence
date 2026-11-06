from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import Lead, LeadStatus, SalesRep
from yottaflex.engines.routing import eligible_reps_for_lead
from yottaflex.logging_setup import get_logger

log = get_logger("assignment")


def _pick_rep(eligible: list[SalesRep], strategy: str) -> SalesRep | None:
    if not eligible:
        return None
    if strategy == "round_robin_id":
        return eligible[0]
    # least_loaded_then_id (default): min load, then lowest id (already sorted by id)
    return min(eligible, key=lambda r: (r.active_leads_count, r.salesrep_id))


def assign_leads(
    session: Session,
    settings: Settings,
    assigned_at: datetime | None = None,
    categories: set[str] | None = None,
) -> dict[str, int]:
    """Sales Assignment Engine (G). Deterministic least-loaded assignment."""
    if assigned_at is None:
        from datetime import timedelta

        assigned_at = settings.base_dt().replace(hour=13, minute=0, second=0, microsecond=0)
        assigned_at = assigned_at + timedelta(days=61)

    strategy = settings.routing.assignment_strategy
    from yottaflex.engines.routing import _coverage_maps

    maps = _coverage_maps(session)
    q = (
        select(Lead)
        .where(
            Lead.assigned_salesrep_id.is_(None),
            Lead.is_duplicate_of.is_(None),
            Lead.status.in_([LeadStatus.scored.value, LeadStatus.new.value]),
        )
        .order_by(Lead.lead_id)
    )
    if categories:
        q = q.where(Lead.lead_category.in_(list(categories)))

    leads = session.scalars(q).all()
    assigned = 0
    unassignable = 0

    for lead in leads:
        eligible = eligible_reps_for_lead(
            session, lead, require_capacity=True, _maps=maps
        )
        rep = _pick_rep(eligible, strategy)
        if rep is None:
            unassignable += 1
            continue
        lead.assigned_salesrep_id = rep.salesrep_id
        lead.assigned_at = assigned_at
        if lead.status in (LeadStatus.scored.value, LeadStatus.new.value):
            from yottaflex.engines.lead_status_history import append_status_change

            append_status_change(
                session,
                lead,
                LeadStatus.assigned.value,
                assigned_at,
                reason=f"assigned to rep {rep.salesrep_id}",
                actor_id="assignment",
            )
        else:
            lead.updated_at = assigned_at
        rep.active_leads_count += 1
        assigned += 1

    session.commit()
    log.info("assigned=%d unassignable=%d", assigned, unassignable)
    return {"assigned": assigned, "unassignable": unassignable, "considered": len(leads)}


def assignment_coverage(session: Session, settings: Settings) -> dict[str, float]:
    # count assignable baseline = non-dup leads not excluded
    from sqlalchemy import func

    base = session.scalar(
        select(func.count()).select_from(Lead).where(
            Lead.is_duplicate_of.is_(None),
            Lead.status.not_in(["disqualified", "opted_out"]),
        )
    ) or 0
    with_rep = session.scalar(
        select(func.count()).select_from(Lead).where(
            Lead.is_duplicate_of.is_(None),
            Lead.assigned_salesrep_id.is_not(None),
        )
    ) or 0
    coverage = (with_rep / base) if base else 0.0
    return {"assignable": base, "assigned": with_rep, "coverage": round(coverage, 4)}
