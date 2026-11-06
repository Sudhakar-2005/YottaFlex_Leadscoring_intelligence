from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    ALLOWED_STAGE_TRANSITIONS,
    ActorType,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    StageHistory,
)
from yottaflex.logging_setup import get_logger

log = get_logger("stage_history")


class StageTransitionError(Exception):
    pass


def append_stage_change(
    session: Session,
    opportunity: Opportunity,
    to_stage: OpportunityStage | str,
    changed_at: datetime,
    reason: str,
    actor_type: str = ActorType.system.value,
    actor_id: str | None = None,
    force: bool = False,
) -> StageHistory:
    """Stage History Engine (J). Append-only; validates canonical path (BR-H01..H03)."""
    to = to_stage.value if isinstance(to_stage, OpportunityStage) else to_stage
    current = opportunity.stage

    if to == current and not force:
        raise StageTransitionError(f"already in stage {to}")

    allowed = ALLOWED_STAGE_TRANSITIONS.get(OpportunityStage(current), set())
    allowed_vals = {s.value for s in allowed}
    if not force and to not in allowed_vals:
        raise StageTransitionError(f"illegal transition {current} -> {to}")

    history = StageHistory(
        opportunity_id=opportunity.opportunity_id,
        from_stage=current if current else None,
        to_stage=to,
        changed_at=changed_at,
        reason=reason,
        actor_type=actor_type,
        actor_id=actor_id,
        created_at=changed_at,
    )
    session.add(history)
    opportunity.stage = to
    opportunity.stage_entered_at = changed_at
    opportunity.updated_at = changed_at
    if to == OpportunityStage.won.value:
        opportunity.won_at = changed_at
    if to == OpportunityStage.lost.value:
        opportunity.lost_at = changed_at
    return history


def get_history(session: Session, opportunity_id: int) -> list[StageHistory]:
    return list(
        session.scalars(
            select(StageHistory)
            .where(StageHistory.opportunity_id == opportunity_id)
            .order_by(StageHistory.changed_at, StageHistory.stage_history_id)
        ).all()
    )


def validate_stage_path(session: Session, opportunity_id: int) -> list[str]:
    """Return list of gap/invalid issues for one opportunity (used by EX-05)."""
    issues: list[str] = []
    rows = get_history(session, opportunity_id)
    if not rows:
        issues.append("missing stage history")
        return issues

    from yottaflex.db.models import STAGE_ORDER

    order_index = {s.value: i for i, s in enumerate(STAGE_ORDER)}
    # first row should be initial new_lead
    if rows[0].from_stage is not None:
        issues.append(f"initial row has from_stage={rows[0].from_stage}")
    if rows[0].to_stage != OpportunityStage.new_lead.value:
        issues.append(f"initial to_stage={rows[0].to_stage} expected new_lead")

    for prev, nxt in zip(rows, rows[1:]):
        if nxt.changed_at < prev.changed_at:
            issues.append(f"non-monotonic time at stage_history {nxt.stage_history_id}")
        allowed = ALLOWED_STAGE_TRANSITIONS.get(OpportunityStage(prev.to_stage), set())
        if OpportunityStage(nxt.to_stage) not in allowed:
            # detect skip: next is more than +1 in branch order
            pi = order_index.get(prev.to_stage, -1)
            ni = order_index.get(nxt.to_stage, -1)
            if ni > pi + 1:
                issues.append(
                    f"stage gap: {prev.to_stage} -> {nxt.to_stage} (skipped intermediate)"
                )
            else:
                issues.append(f"illegal transition {prev.to_stage} -> {nxt.to_stage}")
        if nxt.from_stage != prev.to_stage:
            issues.append(
                f"from_stage mismatch: expected {prev.to_stage} got {nxt.from_stage}"
            )
    return issues
