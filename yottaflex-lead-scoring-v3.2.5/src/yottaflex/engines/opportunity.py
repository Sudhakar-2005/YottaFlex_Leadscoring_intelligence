from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yottaflex.config import Settings
from yottaflex.db.models import (
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    StageHistory,
    Task,
)
from yottaflex.engines.stage_history import append_stage_change
from yottaflex.ids import opportunity_bid
from yottaflex.logging_setup import get_logger

log = get_logger("opportunity")

ICP_INDUSTRIES = {"Technology", "Finance", "Healthcare", "Manufacturing", "Retail"}
BUDGET_BAND_VALUE = {
    None: 0.0,
    "<10M": 0.3,
    "10M-50M": 0.6,
    "50M-200M": 0.85,
    "200M+": 1.0,
}
INTENT_ACTIVITY_TYPES = ("demo_request", "pricing_inquiry", "form_submit", "content_download")

# Deterministic, business-meaningful loss reasons (V3.2.2)
LOSS_REASONS = (
    "no_decision_timing",
    "competitor_selected",
    "budget_frozen",
    "lost_contact",
    "requirements_mismatch",
)


def pick_loss_reason(opportunity_id: int) -> str:
    """Deterministic loss reason from the opportunity id (stable across runs)."""
    return LOSS_REASONS[int(_hash01("loss_reason", opportunity_id) * len(LOSS_REASONS)) % len(LOSS_REASONS)]


def _hash01(*parts: object) -> float:
    """Deterministic uniform in [0, 1) from parts (FNV-1a style)."""
    h = 2166136261
    for p in parts:
        for b in str(p).encode("utf-8"):
            h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h / 0x100000000


@dataclass
class _LeadSignals:
    activity_count: int = 0
    demo: bool = False
    pricing: bool = False
    form: bool = False
    content: bool = False
    has_task: bool = False


def _load_lead_signals(session: Session, lead_ids: list[int]) -> dict[int, _LeadSignals]:
    """Bulk activity/task signals used as documented selection/outcome factors."""
    from yottaflex.db.models import Activity

    signals: dict[int, _LeadSignals] = {lid: _LeadSignals() for lid in lead_ids}
    id_set = set(lead_ids)
    chunk = 800
    for start in range(0, len(lead_ids), chunk):
        part = lead_ids[start : start + chunk]
        rows = session.execute(
            select(Activity.lead_id, Activity.activity_type).where(Activity.lead_id.in_(part))
        ).all()
        for lid, atype in rows:
            sig = signals.get(lid)
            if sig is None:
                continue
            sig.activity_count += 1
            if atype == "demo_request":
                sig.demo = True
            elif atype == "pricing_inquiry":
                sig.pricing = True
            elif atype == "form_submit":
                sig.form = True
            elif atype == "content_download":
                sig.content = True
        task_rows = session.execute(select(Task.lead_id).where(Task.lead_id.in_(part))).all()
        for (lid,) in task_rows:
            sig = signals.get(lid)
            if sig is not None:
                sig.has_task = True
    # guard: signals only for requested ids
    return {k: v for k, v in signals.items() if k in id_set}


def _load_companies(session: Session, company_ids: set[int]) -> dict[int, object]:
    from yottaflex.db.models import Company

    out: dict[int, object] = {}
    ids = sorted(company_ids - set(out))
    chunk = 800
    for start in range(0, len(ids), chunk):
        part = ids[start : start + chunk]
        for c in session.scalars(select(Company).where(Company.company_id.in_(part))).all():
            out[c.company_id] = c
    return out


def _amount_for(product_line: str, rng_vals: tuple[int, int]) -> float:
    """Deterministic-ish amount from product line hash + range."""
    base = {
        "CRM": 45000,
        "Analytics": 38000,
        "Automation": 52000,
        "Service": 30000,
        "Data": 48000,
        "AI": 60000,
        "Integration": 35000,
        "Security": 42000,
        "Mobile": 28000,
        "Portal": 32000,
    }.get(product_line, 40000)
    spread = (rng_vals[1] - rng_vals[0]) / 1000.0
    return float(base + (rng_vals[0] % 1000) * spread * 0.1)


def conversion_propensity(
    lead: Lead,
    sig: _LeadSignals,
    company,
    settings: Settings,
) -> float:
    """Documented business factors for opportunity selection (P0-D).

    Uses actual buying intent, engagement volume, budget compatibility,
    product fit, follow-up presence and deterministic jitter.
    The final lead_score / lead_category are deliberately NOT inputs.
    """
    w = settings.opportunity_selection
    intent_hits = int(sig.demo) + int(sig.pricing) + int(sig.form) + int(sig.content)
    intent_c = min(1.0, intent_hits / 4.0)
    engage_c = min(1.0, sig.activity_count / 25.0)
    revenue_band = getattr(company, "annual_revenue_band", None) if company else None
    budget_c = BUDGET_BAND_VALUE.get(revenue_band, 0.3)
    if company is not None and company.industry in ICP_INDUSTRIES:
        fit_c = 1.0 if lead.product_line else 0.7
    else:
        fit_c = 0.35 if lead.product_line else 0.1
    if sig.has_task:
        followup_c = 1.0
    elif lead.assigned_salesrep_id is not None:
        followup_c = 0.5
    else:
        followup_c = 0.2
    jitter_c = _hash01("sel", lead.lead_id)
    return (
        w.intent_weight * intent_c
        + w.engagement_weight * engage_c
        + w.budget_weight * budget_c
        + w.fit_weight * fit_c
        + w.followup_weight * followup_c
        + w.jitter_weight * jitter_c
    )


def win_probability(lead: Lead, sig: _LeadSignals, company, settings: Settings) -> float:
    """Documented business factors for won/lost outcome (P0-D).

    Product fit, actual buying intent, budget compatibility, follow-up
    effectiveness and engagement drive the outcome. lead_score is NOT used.
    """
    oc = settings.opportunity_outcomes
    if company is not None and company.industry in ICP_INDUSTRIES:
        fit_c = 1.0
    else:
        fit_c = 0.2
    if lead.product_line:
        fit_c = min(1.0, fit_c + 0.2)
    intent_c = min(
        1.0,
        (0.5 if sig.demo else 0.0)
        + (0.3 if sig.pricing else 0.0)
        + (0.2 if sig.form else 0.0),
    )
    revenue_band = getattr(company, "annual_revenue_band", None) if company else None
    budget_c = BUDGET_BAND_VALUE.get(revenue_band, 0.3)
    followup_c = 1.0 if sig.has_task else 0.4
    engage_c = min(1.0, sig.activity_count / 25.0)
    p = (
        oc.base_win_p
        + oc.fit_max * fit_c
        + oc.intent_max * intent_c
        + oc.budget_max * budget_c
        + oc.followup_max * followup_c
        + oc.engagement_max * engage_c
    )
    return min(0.95, p)


def convert_qualified_leads(
    session: Session,
    settings: Settings,
    target_count: int | None = None,
    convert_at: datetime | None = None,
) -> dict[str, int]:
    """Opportunity Management Engine (I).

    Converts qualified leads to opportunities with valid initial StageHistory.

    Selection (P0-D): ranks eligible leads by conversion_propensity built
    from documented business factors + deterministic jitter — never by the
    final lead_score / lead_category.
    """
    target = target_count if target_count is not None else settings.counts.opportunities
    if convert_at is None:
        from datetime import timedelta

        convert_at = settings.base_dt().replace(hour=15, minute=0, second=0, microsecond=0)
        convert_at = convert_at + timedelta(days=63)

    existing = session.scalar(select(func.count()).select_from(Opportunity)) or 0
    if existing >= target:
        return {"created": 0, "existing": existing, "target": target}

    need = target - existing
    year = settings.business_id_year
    dupe_n = min(settings.duplicates.natural_duplicate_opportunities, need // 10)
    primary_need = max(0, need - dupe_n)

    # Eligible pool: assigned, not converted/dup, has company, has rep.
    # NOTE: no ORDER BY lead_score and no score predicates — selection is
    # propensity-based (P0-D); scored leads are the norm post-step C.
    eligible = session.scalars(
        select(Lead)
        .where(
            Lead.is_duplicate_of.is_(None),
            Lead.assigned_salesrep_id.is_not(None),
            Lead.company_id.is_not(None),
            Lead.status.not_in(
                [
                    LeadStatus.converted.value,
                    LeadStatus.disqualified.value,
                    LeadStatus.opted_out.value,
                ]
            ),
        )
        .order_by(Lead.lead_id.asc())
    ).all()

    # Skip leads that already hold an opportunity (primary or otherwise)
    leads_with_opp = set(
        session.execute(select(Opportunity.lead_id).distinct()).scalars().all()
    )
    eligible = [l for l in eligible if l.lead_id not in leads_with_opp]

    lead_ids = [l.lead_id for l in eligible]
    signals = _load_lead_signals(session, lead_ids)
    company_ids = {l.company_id for l in eligible if l.company_id is not None}
    companies = _load_companies(session, company_ids)

    ranked = sorted(
        eligible,
        key=lambda l: (
            -conversion_propensity(
                l,
                signals.get(l.lead_id, _LeadSignals()),
                companies.get(l.company_id) if l.company_id else None,
                settings,
            ),
            l.lead_id,
        ),
    )
    selected = ranked[:primary_need]

    created = 0
    opp_seq = existing
    primaries: list[Opportunity] = []
    for lead in selected:
        product_line = lead.product_line or "CRM"
        amount = _amount_for(product_line, (lead.lead_id * 37, lead.lead_id * 37 + 500))
        company = companies.get(lead.company_id) if lead.company_id else None
        opp_seq += 1
        opp = Opportunity(
            business_id=opportunity_bid(opp_seq, year),
            lead_id=lead.lead_id,
            company_id=lead.company_id,  # type: ignore[arg-type]
            contact_id=lead.contact_id,
            salesrep_id=lead.assigned_salesrep_id,  # type: ignore[arg-type]
            name=f"{getattr(company, 'name', 'Account')} — {product_line} #{opp_seq}",
            product_line=product_line,
            amount=amount,
            currency="USD",
            stage=OpportunityStage.new_lead.value,
            stage_entered_at=convert_at,
            is_duplicate_flag=False,
            created_at=convert_at,
            updated_at=convert_at,
        )
        session.add(opp)
        session.flush()
        primaries.append(opp)

        # Initial stage history (BR-H02)
        session.add(
            StageHistory(
                opportunity_id=opp.opportunity_id,
                from_stage=None,
                to_stage=OpportunityStage.new_lead.value,
                changed_at=convert_at,
                reason="opportunity created from qualified lead",
                actor_type="system",
                actor_id="pipeline",
                created_at=convert_at,
            )
        )

        from yottaflex.engines.lead_status_history import append_status_change

        append_status_change(
            session,
            lead,
            LeadStatus.converted.value,
            convert_at,
            reason=f"converted to opportunity {opp.business_id}",
            actor_id="opportunity",
        )
        lead.converted_opportunity_id = opp.opportunity_id
        lead.converted_at = convert_at
        created += 1

    # Natural baseline duplicate opportunities (P0-B): even-stride clones of
    # selected primaries, same lead_id, soft-marked, GT origin='natural'.
    from yottaflex.engines.deduplication import record_duplicate_gt

    natural_dupes = 0
    if dupe_n > 0 and primaries:
        clone_indices = sorted(
            {(k * len(primaries)) // dupe_n for k in range(dupe_n)}
        )
        for idx in clone_indices:
            src = primaries[idx]
            opp_seq += 1
            dup = Opportunity(
                business_id=opportunity_bid(opp_seq, year),
                lead_id=src.lead_id,
                company_id=src.company_id,
                contact_id=src.contact_id,
                salesrep_id=src.salesrep_id,
                name=f"[DUP] {src.name}",
                product_line=src.product_line,
                amount=src.amount,
                currency=src.currency,
                stage=OpportunityStage.new_lead.value,
                stage_entered_at=convert_at,
                is_duplicate_flag=True,
                created_at=convert_at,
                updated_at=convert_at,
            )
            session.add(dup)
            session.flush()
            session.add(
                StageHistory(
                    opportunity_id=dup.opportunity_id,
                    from_stage=None,
                    to_stage=OpportunityStage.new_lead.value,
                    changed_at=convert_at,
                    reason="natural duplicate opportunity (baseline)",
                    actor_type="system",
                    actor_id="pipeline",
                    created_at=convert_at,
                )
            )
            record_duplicate_gt(
                session,
                "opportunity",
                src.opportunity_id,
                dup.opportunity_id,
                "lead_id",
                str(src.lead_id),
                "natural",
                src.business_id,
                dup.business_id,
            )
            natural_dupes += 1

    session.commit()
    log.info(
        "opportunities created=%d (primary=%d natural_dupes=%d target remaining %d)",
        created,
        primary_need,
        natural_dupes,
        need,
    )
    return {
        "created": created,
        "natural_duplicate_opportunities": natural_dupes,
        "existing_after": existing + created + natural_dupes,
        "target": target,
    }


def advance_opportunities_realistic(
    session: Session,
    settings: Settings,
    start_at: datetime | None = None,
) -> dict[str, int]:
    """Advance opportunities through canonical stages with per-step history.

    Outcomes (P0-D): won/lost/open decided by documented business factors
    (product fit, actual intent, budget, follow-up effectiveness, engagement)
    via win_probability — never by lead_score. A configured fraction is left
    open at demo/proposal for realistic open-pipeline distribution.

    Stage history (P0-6): every path step carries its own timestamp.
    """
    if start_at is None:
        from datetime import timedelta

        start_at = settings.base_dt().replace(hour=16, minute=0, second=0, microsecond=0)
        start_at = start_at + timedelta(days=64)

    from datetime import timedelta

    # Only primary opportunities advance; duplicates stay at new_lead (open).
    opps = session.scalars(
        select(Opportunity)
        .where(
            Opportunity.stage == OpportunityStage.new_lead.value,
            Opportunity.is_duplicate_flag.is_(False),
        )
        .order_by(Opportunity.opportunity_id)
    ).all()

    lead_ids = sorted({o.lead_id for o in opps})
    signals = _load_lead_signals(session, lead_ids)
    company_ids = {o.company_id for o in opps}
    companies = _load_companies(session, company_ids)

    advanced = {
        "qualified": 0,
        "demo": 0,
        "proposal": 0,
        "won": 0,
        "lost": 0,
        "open": 0,
    }
    open_rate = settings.opportunity_outcomes.open_rate

    for opp in opps:
        lead = session.get(Lead, opp.lead_id)
        if lead is None:
            continue
        sig = signals.get(opp.lead_id, _LeadSignals())
        company = companies.get(opp.company_id)
        win_p = win_probability(lead, sig, company, settings)

        h_stage = _hash01("stage", opp.opportunity_id)
        h_open = _hash01("open", opp.opportunity_id)
        h_win = _hash01("win", opp.opportunity_id, int(win_p * 1000))

        # Build path as (stage, reason, timestamp) — one timestamp per step
        t = start_at
        steps: list[tuple[OpportunityStage, str, datetime]] = [
            (OpportunityStage.qualified, "lead qualified for opportunity", t)
        ]
        is_open = False
        if h_stage < 0.85:
            t = t + timedelta(days=3)
            steps.append((OpportunityStage.demo, "demo scheduled and held", t))
            if h_stage < 0.68:
                t = t + timedelta(days=5)
                steps.append((OpportunityStage.proposal, "proposal sent", t))
                if h_open < open_rate:
                    is_open = True  # deliberately left open at proposal
                elif h_win < win_p:
                    t = t + timedelta(days=7)
                    steps.append((OpportunityStage.won, "customer signed", t))
                else:
                    t = t + timedelta(days=7)
                    steps.append(
                        (
                            OpportunityStage.lost,
                            "lost to competitor or no decision",
                            t,
                        )
                    )
            elif h_open < open_rate:
                is_open = True  # deliberately left open at demo
            else:
                t = t + timedelta(days=4)
                steps.append((OpportunityStage.lost, "lost after demo", t))
        else:
            t = t + timedelta(days=4)
            steps.append((OpportunityStage.lost, "lost before demo", t))

        for stage, reason, ts in steps:
            try:
                append_stage_change(
                    session,
                    opp,
                    stage,
                    changed_at=ts,
                    reason=reason,
                    actor_type="system",
                )
                if stage == OpportunityStage.qualified.value:
                    advanced["qualified"] += 1
                elif stage == OpportunityStage.demo.value:
                    advanced["demo"] += 1
                elif stage == OpportunityStage.proposal.value:
                    advanced["proposal"] += 1
                elif stage == OpportunityStage.won.value:
                    advanced["won"] += 1
                elif stage == OpportunityStage.lost.value:
                    advanced["lost"] += 1
            except Exception as exc:  # noqa: BLE001 — log and continue
                log.warning("opp %s stage %s: %s", opp.opportunity_id, stage, exc)
                break
        # V3.2.2: populate a meaningful deterministic loss reason for lost
        # opportunities; won/open opportunities must never carry one.
        if opp.stage == OpportunityStage.lost.value and opp.loss_reason is None:
            opp.loss_reason = pick_loss_reason(opp.opportunity_id)
        if is_open:
            advanced["open"] += 1

    session.commit()
    return advanced


def timedelta_days(n: int):
    from datetime import timedelta

    return timedelta(days=n)
