from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.config import Settings, canonical_sqlite_path, load_settings
from yottaflex.db.models import (
    ExceptionRecord,
    ExceptionResolutionHistory,
    Lead,
    LeadStatusHistory,
    Opportunity,
    ResolutionStatus,
    SalesRep,
    ScoreRule,
    StageHistory,
    Task,
)
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_engine
from yottaflex.engines import analytics
from yottaflex.pipeline import run_full_pipeline

settings: Settings = load_settings()
engine = init_db(make_engine(settings=settings))

app = FastAPI(
    title="YottaFlex Lead Scoring API",
    version="0.1.0",
    description="Lead Scoring & Opportunity Management System API",
)


def _session_factory():
    from yottaflex.db.session import make_session_factory

    return make_session_factory(engine)


def get_session():
    factory = _session_factory()
    with factory() as session:
        yield session


class ExceptionPatch(BaseModel):
    resolution_status: ResolutionStatus
    note: str | None = None
    actor_id: str | None = None


class PipelineRunRequest(BaseModel):
    inject_anomalies: bool = True
    mini: bool = False
    # V3.2 safety: destructive runs must be explicitly confirmed
    confirm_destructive: bool = False
    # V3.2 safety: optional separate target DB (leaves live data untouched)
    output_database_url: str | None = None
    # V3.2 safety: set False to skip reports/exports entirely
    write_reports: bool = True
    # V3.2.2/V3.2.3: explicit export destination; defaults to data/generated/exports
    export_dir: str | None = None
    # V3.2.3: explicit permission required to overwrite an existing export set
    overwrite_exports: bool = False


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/meta/seed")
def meta_seed() -> dict[str, Any]:
    return {
        "seed": settings.seed,
        "base_datetime": settings.base_datetime,
        "counts": settings.counts.model_dump(),
        "weights": settings.scoring.weights.model_dump(),
        "thresholds": settings.scoring.category_thresholds.model_dump(),
    }


@app.post("/api/v1/pipeline/run-all")
def pipeline_run_all(body: PipelineRunRequest) -> dict[str, Any]:
    """Run the full pipeline (DESTRUCTIVE — regenerates every table in the target DB).

    Safety contract:
      - Running against the live database requires ``confirm_destructive=true``;
        otherwise the request is rejected with HTTP 400 and nothing is touched.
      - ``output_database_url`` runs the pipeline into a separate database and
        leaves the live database untouched (no confirmation needed).
      - Path-equivalence hardening (V3.2.2): live-DB detection compares CANONICAL
        filesystem paths, so equivalent representations (``/./``, ``/../``,
        backslashes, four-slash absolute, case variants, trailing dots) cannot
        bypass the confirmation gate.
      - ``write_reports=true`` with a non-default database requires an explicit
        ``export_dir`` (protects the committed data/exports deliverables).
    """
    s = load_settings()
    if body.mini:
        s.counts.companies = 80
        s.counts.contacts = 120
        s.counts.leads = 200
        s.counts.opportunities = 40
        s.counts.campaigns = 8
        s.counts.sales_reps = 16

    live_url = settings.resolved_database_url()
    live_canon = canonical_sqlite_path(live_url) or live_url

    if body.output_database_url:
        target_url = body.output_database_url
        run_settings = s.model_copy(update={"database_url": target_url})
        resolved_target = run_settings.resolved_database_url()
        target_canon = (
            canonical_sqlite_path(target_url)
            or canonical_sqlite_path(resolved_target)
            or resolved_target
        )
    else:
        resolved_target = live_url
        target_canon = live_canon
        run_settings = s

    runs_in_place = target_canon == live_canon
    if runs_in_place and not body.confirm_destructive:
        raise HTTPException(
            status_code=400,
            detail=(
                "Refusing destructive run: this regenerates the live database "
                f"({live_url}). Re-send with confirm_destructive=true, or pass "
                "output_database_url to generate into a separate database."
            ),
        )

    try:
        result = run_full_pipeline(
            settings=run_settings,
            database_url=body.output_database_url,
            inject_anomalies=body.inject_anomalies,
            write_reports=body.write_reports,
            export_dir=body.export_dir,
            overwrite_exports=body.overwrite_exports,
        )
    except ValueError as exc:
        # export overwrite protection (V3.2.2/V3.2.3)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Only rebind the API engine when the live database was intentionally rebuilt
    global engine
    if runs_in_place:
        engine = init_db(make_engine(settings=run_settings))
    return {
        "destructive": True,
        "ran_in_place": runs_in_place,
        "target_database": resolved_target,
        "write_reports": body.write_reports,
        "export_dir": body.export_dir,
        "overwrite_exports": body.overwrite_exports,
        "steps": {k: v for k, v in result.steps.items() if k != "deduplication"},
    }


@app.get("/api/v1/leads")
def list_leads(
    category: str | None = None,
    status: str | None = None,
    territory: str | None = None,
    score_min: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    q = select(Lead).where(Lead.is_duplicate_of.is_(None))
    if category:
        q = q.where(Lead.lead_category == category)
    if status:
        q = q.where(Lead.status == status)
    if territory:
        q = q.where(Lead.territory_code == territory)
    if score_min is not None:
        q = q.where(Lead.lead_score >= score_min)
    q = q.order_by(Lead.lead_id).offset(offset).limit(limit)
    rows = session.scalars(q).all()
    return {
        "count": len(rows),
        "items": [
            {
                "lead_id": r.lead_id,
                "business_id": r.business_id,
                "email": r.email_normalized,
                "name": f"{r.first_name} {r.last_name}",
                "status": r.status,
                "category": r.lead_category,
                "score": r.lead_score,
                "territory": r.territory_code,
                "assigned_salesrep_id": r.assigned_salesrep_id,
            }
            for r in rows
        ],
    }


@app.get("/api/v1/leads/{lead_id}")
def get_lead(lead_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    from yottaflex.db.models import LeadScoreExplanation

    expl = session.scalars(
        select(LeadScoreExplanation)
        .where(LeadScoreExplanation.lead_id == lead_id)
        .order_by(LeadScoreExplanation.scored_at.desc())
    ).first()
    return {
        "lead_id": lead.lead_id,
        "business_id": lead.business_id,
        "email": lead.email_normalized,
        "name": f"{lead.first_name} {lead.last_name}",
        "status": lead.status,
        "category": lead.lead_category,
        "score": lead.lead_score,
        "fit": lead.fit_score,
        "intent": lead.intent_score,
        "engagement": lead.engagement_score,
        "territory": lead.territory_code,
        "eval_split": lead.eval_split,
        "assigned_salesrep_id": lead.assigned_salesrep_id,
        "converted_opportunity_id": lead.converted_opportunity_id,
        "explanation": None
        if expl is None
        else {
            "scored_at": expl.scored_at.isoformat(),
            "weights": expl.weights_json,
            "rules_fired": expl.rules_fired_json,
            "lead_score": expl.lead_score,
        },
    }


@app.get("/api/v1/opportunities")
def list_opportunities(
    stage: str | None = None,
    salesrep_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    q = select(Opportunity)
    if stage:
        q = q.where(Opportunity.stage == stage)
    if salesrep_id is not None:
        q = q.where(Opportunity.salesrep_id == salesrep_id)
    q = q.order_by(Opportunity.opportunity_id).offset(offset).limit(limit)
    rows = session.scalars(q).all()
    return {
        "count": len(rows),
        "items": [
            {
                "opportunity_id": r.opportunity_id,
                "business_id": r.business_id,
                "lead_id": r.lead_id,
                "name": r.name,
                "stage": r.stage,
                "amount": r.amount,
                "product_line": r.product_line,
                "salesrep_id": r.salesrep_id,
                "is_duplicate_flag": r.is_duplicate_flag,
            }
            for r in rows
        ],
    }


@app.get("/api/v1/leads/{lead_id}/status-history")
def lead_status_history(lead_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    rows = session.scalars(
        select(LeadStatusHistory)
        .where(LeadStatusHistory.lead_id == lead_id)
        .order_by(LeadStatusHistory.changed_at, LeadStatusHistory.history_id)
    ).all()
    return {
        "lead_id": lead_id,
        "current_status": lead.status,
        "history": [
            {
                "history_id": h.history_id,
                "from_status": h.from_status,
                "to_status": h.to_status,
                "changed_at": h.changed_at.isoformat(),
                "reason": h.reason,
                "actor_type": h.actor_type,
                "actor_id": h.actor_id,
            }
            for h in rows
        ],
    }


@app.get("/api/v1/opportunities/{opp_id}/history")
def opp_history(opp_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    opp = session.get(Opportunity, opp_id)
    if opp is None:
        raise HTTPException(404, "opportunity not found")
    rows = session.scalars(
        select(StageHistory)
        .where(StageHistory.opportunity_id == opp_id)
        .order_by(StageHistory.changed_at, StageHistory.stage_history_id)
    ).all()
    return {
        "opportunity_id": opp_id,
        "business_id": opp.business_id,
        "current_stage": opp.stage,
        "history": [
            {
                "stage_history_id": h.stage_history_id,
                "from_stage": h.from_stage,
                "to_stage": h.to_stage,
                "changed_at": h.changed_at.isoformat(),
                "reason": h.reason,
                "actor_type": h.actor_type,
            }
            for h in rows
        ],
    }


@app.get("/api/v1/tasks")
def list_tasks(
    status: str | None = None,
    salesrep_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    q = select(Task)
    if status:
        q = q.where(Task.status == status)
    if salesrep_id is not None:
        q = q.where(Task.salesrep_id == salesrep_id)
    q = q.order_by(Task.task_id).offset(offset).limit(limit)
    rows = session.scalars(q).all()
    return {
        "count": len(rows),
        "items": [
            {
                "task_id": r.task_id,
                "business_id": r.business_id,
                "lead_id": r.lead_id,
                "salesrep_id": r.salesrep_id,
                "type": r.task_type,
                "status": r.status,
                "due_date": r.due_date.isoformat(),
                "priority": r.priority,
                "blocked_reason": r.blocked_reason,
            }
            for r in rows
        ],
    }


@app.get("/api/v1/sales-reps")
def list_sales_reps(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(select(SalesRep).order_by(SalesRep.salesrep_id)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "salesrep_id": r.salesrep_id,
                "employee_code": r.employee_code,
                "name": f"{r.first_name} {r.last_name}",
                "home_territory": r.home_territory_code,
                "active_leads": r.active_leads_count,
                "capacity": r.capacity_max_open_leads,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@app.get("/api/v1/exceptions")
def list_exceptions(
    issue_type: str | None = None,
    severity: str | None = None,
    resolution_status: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    q = select(ExceptionRecord)
    if issue_type:
        q = q.where(ExceptionRecord.issue_type == issue_type)
    if severity:
        q = q.where(ExceptionRecord.severity == severity)
    if resolution_status:
        q = q.where(ExceptionRecord.resolution_status == resolution_status)
    q = q.order_by(ExceptionRecord.exception_id).offset(offset).limit(limit)
    rows = session.scalars(q).all()
    return {
        "count": len(rows),
        "items": [
            {
                "exception_id": r.exception_id,
                "issue_type": r.issue_type,
                "affected_entity": r.affected_entity,
                "affected_record_id": r.affected_record_id,
                "detection_timestamp": r.detection_timestamp.isoformat(),
                "severity": r.severity,
                "resolution_status": r.resolution_status,
                "ground_truth_label": r.ground_truth_label,
                "expected_behavior": r.expected_behavior,
                "actual_behavior": r.actual_behavior,
                "related_lead_id": r.related_lead_id,
            }
            for r in rows
        ],
    }


@app.patch("/api/v1/exceptions/{exception_id}")
def patch_exception(
    exception_id: int,
    body: ExceptionPatch,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rec = session.get(ExceptionRecord, exception_id)
    if rec is None:
        raise HTTPException(404, "exception not found")
    from_status = rec.resolution_status
    to_status = body.resolution_status.value
    rec.resolution_status = to_status
    # P1-4: append resolution history (survives later re-detection)
    resolved_at = datetime.now(tz=None).replace(microsecond=0)
    session.add(
        ExceptionResolutionHistory(
            exception_id=rec.exception_id,
            issue_type=rec.issue_type,
            affected_entity=rec.affected_entity,
            affected_record_id=rec.affected_record_id,
            from_status=from_status,
            to_status=to_status,
            reason=body.note,
            actor_id=body.actor_id,
            resolved_at=resolved_at,
            created_at=resolved_at,
        )
    )
    session.commit()
    return {"exception_id": rec.exception_id, "resolution_status": rec.resolution_status}


@app.get("/api/v1/exceptions/{exception_id}/resolutions")
def exception_resolutions(exception_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(
        select(ExceptionResolutionHistory)
        .where(ExceptionResolutionHistory.exception_id == exception_id)
        .order_by(ExceptionResolutionHistory.resolution_id)
    ).all()
    return {
        "exception_id": exception_id,
        "count": len(rows),
        "resolutions": [
            {
                "resolution_id": r.resolution_id,
                "issue_type": r.issue_type,
                "from_status": r.from_status,
                "to_status": r.to_status,
                "reason": r.reason,
                "actor_id": r.actor_id,
                "resolved_at": r.resolved_at.isoformat(),
            }
            for r in rows
        ],
    }


@app.get("/api/v1/metrics/summary")
def metrics_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    return analytics.summary_metrics(session, settings)


@app.get("/api/v1/metrics/funnel")
def metrics_funnel(session: Session = Depends(get_session)) -> dict[str, Any]:
    return analytics.conversion_funnel(session)


@app.get("/api/v1/score-rules")
def list_score_rules(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(
        select(ScoreRule).where(ScoreRule.is_active.is_(True)).order_by(ScoreRule.priority)
    ).all()
    return {
        "count": len(rows),
        "items": [
            {
                "score_rule_id": r.score_rule_id,
                "rule_code": r.rule_code,
                "dimension": r.dimension,
                "name": r.name,
                "points": r.points,
                "priority": r.priority,
            }
            for r in rows
        ],
    }
