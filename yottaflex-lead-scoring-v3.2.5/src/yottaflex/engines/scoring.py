from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    Activity,
    Company,
    Lead,
    LeadCategory,
    LeadScoreExplanation,
    LeadStatus,
    ScoreRule,
)
from yottaflex.logging_setup import get_logger

log = get_logger("scoring")


@dataclass
class ScoreResult:
    lead_id: int
    fit: int
    intent: int
    engagement: int
    lead_score: int
    category: str
    rules_fired: list[dict[str, Any]]
    scored_at: datetime


def categorize(score: int, thresholds: dict[str, int]) -> str:
    if score >= thresholds["hot"]:
        return LeadCategory.hot.value
    if score >= thresholds["warm"]:
        return LeadCategory.warm.value
    if score >= thresholds["nurture"]:
        return LeadCategory.nurture.value
    return LeadCategory.cold.value


def weighted_score(fit: int, intent: int, engagement: int, weights: dict[str, float]) -> float:
    raw = (
        fit * weights["fit"]
        + intent * weights["intent"]
        + engagement * weights["engagement"]
    )
    return round(raw)


def _eval_condition(cond: dict[str, Any], ctx: dict[str, Any]) -> int:
    """Return points contribution for a rule given evaluation context."""
    ctype = cond.get("type")
    if ctype == "employee_band_in":
        return cond["points"] if ctx.get("employee_band") in cond["values"] else 0
    if ctype == "employee_band_not_in":
        return cond["points"] if ctx.get("employee_band") not in cond["values"] else 0
    if ctype == "industry_in":
        return cond["points"] if ctx.get("industry") in cond["values"] else 0
    if ctype == "industry_not_in":
        return cond["points"] if ctx.get("industry") not in cond["values"] else 0
    if ctype == "revenue_band_in":
        return cond["points"] if ctx.get("revenue_band") in cond["values"] else 0
    if ctype == "activity_count_at_least":
        counts: dict[str, int] = ctx.get("activity_counts") or {}
        total = sum(counts.get(t, 0) for t in cond["activity_types"])
        return cond["points"] if total >= cond.get("min_count", 1) else 0
    if ctype == "activity_count_scaled":
        counts = ctx.get("activity_counts") or {}
        total = sum(counts.get(t, 0) for t in cond["activity_types"])
        pts = total * int(cond.get("per_count", 1))
        return min(pts, int(cond.get("max_points", 100)))
    return 0


def build_lead_context(session: Session, lead: Lead, scored_at: datetime) -> dict[str, Any]:
    """Assemble scoring context with temporal cutoff (BR-S04)."""
    company = session.get(Company, lead.company_id) if lead.company_id else None

    activities = session.scalars(
        select(Activity).where(
            Activity.lead_id == lead.lead_id,
            Activity.event_time <= scored_at,
        )
    ).all()

    activity_counts: dict[str, int] = {}
    for a in activities:
        activity_counts[a.activity_type] = activity_counts.get(a.activity_type, 0) + 1

    return {
        "employee_band": company.employee_band if company else None,
        "industry": company.industry if company else None,
        "revenue_band": company.annual_revenue_band if company else None,
        "size_score": company.size_score if company else (lead.fit_raw or 50),
        "activity_counts": activity_counts,
        "activity_cutoff": scored_at,
        "max_activity_id": max((a.activity_id for a in activities), default=None),
    }


def score_lead(
    session: Session,
    lead: Lead,
    settings: Settings,
    rules: list[ScoreRule],
    scored_at: datetime,
) -> ScoreResult:
    """Compute explainable Fit/Intent/Engagement scores for one lead."""
    ctx = build_lead_context(session, lead, scored_at)

    # Fit baseline from company size_score (0-100), then rule bonuses capped
    fit_base = int(ctx.get("size_score") or 50)
    rules_fired: list[dict[str, Any]] = []
    dim_points: dict[str, int] = {"fit": fit_base, "intent": 0, "engagement": 0}

    active_rules = sorted(
        [r for r in rules if r.is_active],
        key=lambda r: (r.dimension, r.priority, r.score_rule_id),
    )

    for rule in active_rules:
        cond = json.loads(rule.condition_json)
        # attach points into cond for scaled/absolute helpers
        cond.setdefault("points", rule.points)
        contribution = _eval_condition(cond, ctx)
        if contribution > 0:
            dim_points[rule.dimension] = dim_points.get(rule.dimension, 0) + contribution
            rules_fired.append(
                {
                    "rule_code": rule.rule_code,
                    "dimension": rule.dimension,
                    "points": contribution,
                    "priority": rule.priority,
                }
            )

    caps = settings.scoring.dimension_caps
    fit = max(0, min(int(dim_points.get("fit", 0)), caps.get("fit", 100)))
    intent = max(0, min(int(dim_points.get("intent", 0)), caps.get("intent", 100)))
    engagement = max(0, min(int(dim_points.get("engagement", 0)), caps.get("engagement", 100)))

    weights = {
        "fit": settings.scoring.weights.fit,
        "intent": settings.scoring.weights.intent,
        "engagement": settings.scoring.weights.engagement,
    }
    score = int(weighted_score(fit, intent, engagement, weights))
    score = max(0, min(score, 100))
    category = categorize(score, settings.scoring.category_thresholds.model_dump())

    return ScoreResult(
        lead_id=lead.lead_id,
        fit=fit,
        intent=intent,
        engagement=engagement,
        lead_score=score,
        category=category,
        rules_fired=rules_fired,
        scored_at=scored_at,
    )


def score_all_leads(
    session: Session,
    settings: Settings,
    scored_at: datetime | None = None,
) -> list[ScoreResult]:
    """Score all non-converted leads. Persist lead fields + explanation rows (BR-S05/S06)."""
    from yottaflex.db.base import Base  # noqa: F401

    if scored_at is None:
        # Score after the synthetic activity window (base + 60 days) so
        # pre-conversion events are in scope without future leakage.
        scored_at = settings.base_dt().replace(hour=12, minute=0, second=0, microsecond=0)
        from datetime import timedelta

        scored_at = scored_at + timedelta(days=61)

    rules = list(session.scalars(select(ScoreRule).where(ScoreRule.is_active.is_(True))).all())
    leads = list(
        session.scalars(
            select(Lead)
            .where(Lead.is_duplicate_of.is_(None))
            .order_by(Lead.lead_id)
        ).all()
    )

    weights = {
        "fit": settings.scoring.weights.fit,
        "intent": settings.scoring.weights.intent,
        "engagement": settings.scoring.weights.engagement,
    }
    results: list[ScoreResult] = []

    for lead in leads:
        # Temporal leakage guard: never use post-conversion events
        effective_at = scored_at
        if lead.converted_at is not None and lead.converted_at < effective_at:
            effective_at = lead.converted_at

        result = score_lead(session, lead, settings, rules, effective_at)
        lead.fit_score = result.fit
        lead.intent_score = result.intent
        lead.engagement_score = result.engagement
        lead.lead_score = result.lead_score
        lead.lead_category = result.category
        lead.scored_at = result.scored_at
        if lead.status == LeadStatus.new.value:
            from yottaflex.engines.lead_status_history import append_status_change

            append_status_change(
                session,
                lead,
                LeadStatus.scored.value,
                result.scored_at,
                reason="lead scored",
                actor_id="scoring",
            )
        else:
            lead.updated_at = result.scored_at

        session.add(
            LeadScoreExplanation(
                lead_id=lead.lead_id,
                scored_at=result.scored_at,
                fit_score=result.fit,
                intent_score=result.intent,
                engagement_score=result.engagement,
                lead_score=result.lead_score,
                lead_category=result.category,
                weights_json=json.dumps(weights),
                rules_fired_json=json.dumps(result.rules_fired),
                activity_cutoff_id=None,
                created_at=result.scored_at,
            )
        )
        results.append(result)

    session.commit()
    log.info("scored %d leads at %s", len(results), scored_at.isoformat())
    return results
