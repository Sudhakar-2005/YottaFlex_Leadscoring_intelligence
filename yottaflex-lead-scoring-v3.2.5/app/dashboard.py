"""YottaFlex AI — Intelligence-Led Sales Execution (premium UI, V3.2.5).

Design language: dark enterprise (see app/ui.py design system).
Navigation: sidebar sections + top header (global chrome). All nine sections
preserved. Every displayed value is computed from the existing database or
existing report artifacts — no fabricated analytics.

AI panel signals are deterministic, rule-based derivations of current records
(clearly labelled), never model predictions and never ground-truth inputs.

Backend untouched: same schema, engines, settings and artifacts as V3.2.x.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd
import plotly.express as px
import streamlit as st

from yottaflex.config import PROJECT_ROOT, load_settings
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_engine
from yottaflex.engines import analytics

import ui

st.set_page_config(page_title="YottaFlex AI", page_icon="YF", layout="wide", initial_sidebar_state="collapsed")
if not __import__("os").environ.get("DISABLE_YF_CSS"):
    ui.inject_css()

settings = load_settings()
engine = init_db(make_engine(settings=settings))
TASK_AS_OF = settings.base_dt() + timedelta(days=90)  # same reference as exception timestamps

SECTIONS = [
    "Executive Overview",
    "Lead Explorer",
    "Scoring Intelligence",
    "Sales Assignment",
    "Task Management",
    "Opportunity Pipeline",
    "Exception Intelligence",
    "Data Quality",
    "Configuration & Audit",
]
SUBTITLES = {
    "Executive Overview": "Revenue & lead intelligence workspace",
    "Lead Explorer": "Search, inspect and export the lead universe",
    "Scoring Intelligence": "Explainable Fit / Intent / Engagement scoring",
    "Sales Assignment": "Workload, territory coverage and routing exceptions",
    "Task Management": "Follow-up execution, blockers and overdue work",
    "Opportunity Pipeline": "Stages, value, outcomes and loss analysis",
    "Exception Intelligence": "Detected anomalies, evidence and blind evaluation",
    "Data Quality": "Validation, duplicates and integrity indicators",
    "Configuration & Audit": "Runtime configuration and export audit trail",
}

EXCHANGE_GREEN = ui.SUCCESS


# ---------------------------------------------------------------------------
# Data access (read-only; existing tables/artifacts only)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_metrics() -> dict:
    with open_session(engine) as session:
        return analytics.summary_metrics(session, settings)


@st.cache_data(show_spinner=False)
def load_exec_kpis(rep_id: int | None) -> dict:
    from sqlalchemy import func, select

    from yottaflex.db.models import Lead, LeadStatus, Opportunity, OpportunityStage

    with open_session(engine) as session:
        total_leads = session.scalar(select(func.count()).select_from(Lead)) or 0
        active_leads = (
            session.scalar(
                select(func.count())
                .select_from(Lead)
                .where(Lead.status.not_in([LeadStatus.disqualified.value, LeadStatus.opted_out.value]))
            )
            or 0
        )
        qualified_leads = (
            session.scalar(
                select(func.count())
                .select_from(Lead)
                .where(Lead.status.in_([LeadStatus.qualified.value, LeadStatus.converted.value]))
            )
            or 0
        )
        opp_q = select(Opportunity)
        if rep_id is not None:
            opp_q = opp_q.where(Opportunity.salesrep_id == rep_id)
        opps = session.scalars(opp_q).all()
        open_stages = {
            OpportunityStage.new_lead.value, OpportunityStage.demo.value,
            OpportunityStage.proposal.value, OpportunityStage.qualified.value,
        }
        open_opps = [o for o in opps if o.stage in open_stages]
        open_value = float(sum(o.amount or 0.0 for o in open_opps))
        won = [o for o in opps if o.stage == OpportunityStage.won.value]
        lost = [o for o in opps if o.stage == OpportunityStage.lost.value]
        win_rate = (len(won) / (len(won) + len(lost))) if (won or lost) else None
        cycles = [
            (o.won_at - o.created_at).total_seconds() / 86400.0
            for o in won
            if o.won_at is not None
        ]
        avg_cycle = (sum(cycles) / len(cycles)) if cycles else None
    return {
        "total_leads": int(total_leads),
        "active_leads": int(active_leads),
        "qualified_leads": int(qualified_leads),
        "total_opportunities": len(opps),
        "active_deals": len(open_opps),
        "open_pipeline_value": open_value,
        "won": len(won),
        "lost": len(lost),
        "closed": len(won) + len(lost),
        "win_rate": win_rate,
        "avg_cycle_days": avg_cycle,
        "won_with_dates": len(cycles),
    }


BOARD_COLUMNS = [
    ("new_lead", "New", ui.MUTED),
    ("qualified", "Qualified", ui.ACCENT),
    ("demo", "Demo", ui.ACCENT_2),
    ("proposal", "Proposal", ui.AI),
]
BOARD_STEP = {"new_lead": 1, "qualified": 2, "demo": 3, "proposal": 4, "won": 5, "lost": 5}


@st.cache_data(show_spinner=False)
def load_deal_board(rep_id: int | None, per_column: int = 3) -> dict:
    """Open-pipeline kanban data: real opportunities grouped by stage."""
    from sqlalchemy import select

    from yottaflex.db.models import Opportunity, SalesRep

    with open_session(engine) as session:
        q = select(Opportunity).where(
            Opportunity.stage.in_(["new_lead", "qualified", "demo", "proposal"])
        )
        if rep_id is not None:
            q = q.where(Opportunity.salesrep_id == rep_id)
        opps = session.scalars(q).all()
        codes = dict(session.execute(select(SalesRep.salesrep_id, SalesRep.employee_code)).all())
    board: dict[str, dict] = {
        key: {"title": title, "accent": accent, "cards": [], "count": 0, "value": 0.0}
        for key, title, accent in BOARD_COLUMNS
    }
    for o in opps:
        if o.stage not in board:
            continue
        board[o.stage]["count"] += 1
        board[o.stage]["value"] += float(o.amount or 0.0)
    for key in board:
        rows = sorted(
            (o for o in opps if o.stage == key), key=lambda o: float(o.amount or 0.0), reverse=True
        )
        for o in rows[:per_column]:
            board[key]["cards"].append(
                {
                    "name": o.name,
                    "amount": float(o.amount or 0.0),
                    "rep": codes.get(o.salesrep_id, str(o.salesrep_id)),
                    "product_line": o.product_line,
                    "stage_since": o.stage_entered_at,
                }
            )
        board[key]["more"] = (
            f"+{board[key]['count'] - len(board[key]['cards'])} more"
            if board[key]["count"] > len(board[key]["cards"])
            else ""
        )
    return board


@st.cache_data(show_spinner=False)
def load_rep_options() -> dict:
    from sqlalchemy import select

    from yottaflex.db.models import SalesRep

    with open_session(engine) as session:
        rows = session.execute(
            select(SalesRep.salesrep_id, SalesRep.employee_code).order_by(SalesRep.employee_code)
        ).all()
    return {code: rid for rid, code in rows}


@st.cache_data(show_spinner=False)
def load_recent_stage_events(limit: int = 6) -> list[dict]:
    from sqlalchemy import select

    from yottaflex.db.models import Opportunity, StageHistory

    with open_session(engine) as session:
        rows = session.execute(
            select(StageHistory.to_stage, StageHistory.changed_at, StageHistory.reason,
                   Opportunity.business_id, Opportunity.name)
            .join(Opportunity, Opportunity.opportunity_id == StageHistory.opportunity_id)
            .where(StageHistory.to_stage.in_(["qualified", "demo", "proposal", "won", "lost"]))
            .order_by(StageHistory.changed_at.desc(), StageHistory.stage_history_id.desc())
            .limit(limit)
        ).all()
    return [
        {
            "title": f"{name} → {stage} · {reason}",
            "date": f"{changed_at:%d %b %Y} · {business_id}",
        }
        for stage, changed_at, reason, business_id, name in rows
    ]


@st.cache_data(show_spinner=False)
def load_lead_scores() -> pd.DataFrame:
    from sqlalchemy import select

    from yottaflex.db.models import Lead

    with open_session(engine) as session:
        rows = session.execute(
            select(
                Lead.lead_id, Lead.business_id, Lead.fit_score, Lead.intent_score,
                Lead.engagement_score, Lead.lead_score, Lead.lead_category, Lead.eval_split,
            ).where(Lead.lead_score.is_not(None), Lead.is_duplicate_of.is_(None))
        ).all()
    return pd.DataFrame(
        rows,
        columns=["lead_id", "business_id", "fit", "intent", "engagement", "score", "category", "split"],
    )


@st.cache_data(show_spinner=False)
def load_lead_explorer(
    categories: tuple, statuses: tuple, min_score: int, split: str, search: str, limit: int = 2000
) -> pd.DataFrame:
    from sqlalchemy import or_, select

    from yottaflex.db.models import Lead

    q = select(Lead).where(Lead.is_duplicate_of.is_(None), Lead.lead_score.is_not(None))
    if categories:
        q = q.where(Lead.lead_category.in_(list(categories)))
    if statuses:
        q = q.where(Lead.status.in_(list(statuses)))
    if min_score > 0:
        q = q.where(Lead.lead_score >= min_score)
    if split != "all":
        q = q.where(Lead.eval_split == split)
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.where(
            or_(
                Lead.business_id.ilike(like),
                Lead.email_normalized.ilike(like),
                (Lead.first_name + " " + Lead.last_name).ilike(like),
            )
        )
    q = q.order_by(Lead.lead_score.desc(), Lead.lead_id.asc()).limit(limit)
    with open_session(engine) as session:
        rows = session.scalars(q).all()
    return pd.DataFrame(
        [
            {
                "business_id": r.business_id,
                "name": f"{r.first_name} {r.last_name}",
                "email": r.email_normalized,
                "score": r.lead_score,
                "category": r.lead_category,
                "status": r.status,
                "territory": r.territory_code,
                "rep": r.assigned_salesrep_id,
                "split": r.eval_split,
            }
            for r in rows
        ]
    )


@st.cache_data(show_spinner=False)
def load_lead_detail(business_id: str) -> dict | None:
    from sqlalchemy import func, select

    from yottaflex.db.models import Activity, Lead, LeadScoreExplanation, Task

    with open_session(engine) as session:
        lead = session.scalars(select(Lead).where(Lead.business_id == business_id)).first()
        if lead is None:
            return None
        expl = session.scalars(
            select(LeadScoreExplanation)
            .where(LeadScoreExplanation.lead_id == lead.lead_id)
            .order_by(LeadScoreExplanation.scored_at.desc())
            .limit(1)
        ).first()
        activity_count = (
            session.scalar(select(func.count()).select_from(Activity).where(Activity.lead_id == lead.lead_id)) or 0
        )
        last_activity = session.scalars(
            select(Activity).where(Activity.lead_id == lead.lead_id).order_by(Activity.event_time.desc()).limit(1)
        ).first()
        tasks = session.execute(
            select(Task.business_id, Task.task_type, Task.status, Task.priority, Task.due_date)
            .where(Task.lead_id == lead.lead_id)
            .order_by(Task.task_id)
        ).all()
        return {
            "lead": {
                "business_id": lead.business_id,
                "name": f"{lead.first_name} {lead.last_name}",
                "email": lead.email_normalized,
                "company_id": lead.company_id,
                "territory": lead.territory_code,
                "source": lead.source,
                "status": lead.status,
                "category": lead.lead_category,
                "score": lead.lead_score,
                "fit": lead.fit_score,
                "intent": lead.intent_score,
                "engagement": lead.engagement_score,
                "split": lead.eval_split,
                "rep": lead.assigned_salesrep_id,
                "converted_opportunity_id": lead.converted_opportunity_id,
            },
            "explanation": None
            if expl is None
            else {
                "scored_at": expl.scored_at.isoformat(),
                "weights": json.loads(expl.weights_json or "{}"),
                "rules": json.loads(expl.rules_fired_json or "[]"),
            },
            "activity_count": int(activity_count),
            "last_activity": None
            if last_activity is None
            else {
                "type": last_activity.activity_type,
                "time": last_activity.event_time.isoformat(),
            },
            "tasks": [
                {
                    "task": t_bid,
                    "type": ttype,
                    "status": tstatus,
                    "priority": tprio,
                    "due": tdue.isoformat(),
                }
                for t_bid, ttype, tstatus, tprio, tdue in tasks
            ],
        }


@st.cache_data(show_spinner=False)
def load_assignment_section() -> dict:
    from sqlalchemy import case, func, select

    from yottaflex.db.models import ExceptionRecord, Lead, SalesRep, Territory

    with open_session(engine) as session:
        rep_rows = session.execute(
            select(
                SalesRep.salesrep_id, SalesRep.employee_code, SalesRep.role,
                SalesRep.home_territory_code, SalesRep.capacity_max_open_leads,
                func.count(Lead.lead_id).label("assigned_leads"),
            )
            .join(
                Lead,
                (Lead.assigned_salesrep_id == SalesRep.salesrep_id) & (Lead.is_duplicate_of.is_(None)),
                isouter=True,
            )
            .group_by(SalesRep.salesrep_id)
            .order_by(func.count(Lead.lead_id).desc(), SalesRep.salesrep_id)
        ).all()
        rep_df = pd.DataFrame(
            [
                {
                    "rep_id": rid,
                    "rep": code,
                    "role": role,
                    "home_territory": home,
                    "assigned_leads": int(assigned or 0),
                    "capacity": capacity,
                    "utilization": round((assigned or 0) / capacity, 3) if capacity else None,
                }
                for rid, code, role, home, capacity, assigned in rep_rows
            ]
        )
        terr_rows = session.execute(
            select(
                Territory.territory_code, Territory.region,
                func.count(Lead.lead_id).label("leads"),
                func.sum(case((Lead.assigned_salesrep_id.is_not(None), 1), else_=0)).label("assigned"),
            )
            .join(Lead, (Lead.territory_code == Territory.territory_code) & (Lead.is_duplicate_of.is_(None)))
            .group_by(Territory.territory_code, Territory.region)
            .order_by(func.count(Lead.lead_id).desc())
        ).all()
        terr_df = pd.DataFrame(
            [
                {"territory": code, "region": region, "leads": int(leads),
                 "assigned": int(assigned or 0), "unassigned": int(leads) - int(assigned or 0)}
                for code, region, leads, assigned in terr_rows
            ]
        )
        unassigned_total = session.scalar(
            select(func.count()).select_from(Lead).where(
                Lead.is_duplicate_of.is_(None),
                Lead.assigned_salesrep_id.is_(None),
                Lead.status.not_in(["disqualified", "opted_out"]),
            )
        ) or 0
        exc_total = session.scalar(
            select(func.count()).select_from(ExceptionRecord).where(
                ExceptionRecord.issue_type == "lead_assigned_outside_territory"
            )
        ) or 0
        exc_rows = session.scalars(
            select(ExceptionRecord)
            .where(ExceptionRecord.issue_type == "lead_assigned_outside_territory")
            .order_by(ExceptionRecord.exception_id)
            .limit(200)
        ).all()
        exc_df = pd.DataFrame(
            [
                {"exception_id": r.exception_id, "lead_id": r.related_lead_id,
                 "severity": r.severity, "status": r.resolution_status,
                 "detected_at": r.detection_timestamp.isoformat()}
                for r in exc_rows
            ]
        )
    return {
        "rep_df": rep_df,
        "terr_df": terr_df,
        "unassigned_total": int(unassigned_total),
        "assignment_exceptions_total": int(exc_total),
        "assignment_exceptions_df": exc_df,
    }


@st.cache_data(show_spinner=False)
def load_task_section(reference_iso: str) -> dict:
    from sqlalchemy import case, func, select

    from yottaflex.db.models import SalesRep, Task

    ref = datetime.fromisoformat(reference_iso)
    with open_session(engine) as session:
        status_rows = session.execute(select(Task.status, func.count()).group_by(Task.status)).all()
        status_df = pd.DataFrame(status_rows, columns=["status", "count"]).sort_values("count", ascending=False)
        priority_rows = session.execute(select(Task.priority, func.count()).group_by(Task.priority)).all()
        priority_df = pd.DataFrame(priority_rows, columns=["priority", "count"])
        overdue_total = session.scalar(
            select(func.count()).select_from(Task).where(
                Task.status.in_(["pending", "in_progress"]), Task.due_date < ref
            )
        ) or 0
        overdue_rows = session.execute(
            select(Task.business_id, Task.lead_id, SalesRep.employee_code, Task.task_type,
                   Task.priority, Task.due_date, Task.status)
            .join(SalesRep, SalesRep.salesrep_id == Task.salesrep_id)
            .where(Task.status.in_(["pending", "in_progress"]), Task.due_date < ref)
            .order_by(Task.due_date, Task.task_id)
            .limit(200)
        ).all()
        overdue_df = pd.DataFrame(
            overdue_rows, columns=["task", "lead_id", "rep", "type", "priority", "due_date", "status"]
        )
        rep_rows = session.execute(
            select(
                SalesRep.employee_code,
                func.count(Task.task_id).label("tasks"),
                func.sum(case((Task.status == "pending", 1), else_=0)).label("pending"),
                func.sum(case((Task.status == "blocked", 1), else_=0)).label("blocked"),
            )
            .join(Task, Task.salesrep_id == SalesRep.salesrep_id)
            .group_by(SalesRep.employee_code)
            .order_by(func.count(Task.task_id).desc())
        ).all()
        rep_df = pd.DataFrame(
            rep_rows,
            columns=["rep", "tasks", "pending", "blocked"],
        )
        blocked_rows = session.execute(
            select(Task.blocked_reason, func.count())
            .where(Task.status == "blocked")
            .group_by(Task.blocked_reason)
            .order_by(func.count().desc())
        ).all()
        blocked_df = pd.DataFrame(blocked_rows, columns=["blocked_reason", "count"])
        pivot_rows = session.execute(
            select(Task.priority, Task.status, func.count()).group_by(Task.priority, Task.status)
        ).all()
        pivot = pd.DataFrame(pivot_rows, columns=["priority", "status", "count"])
        pivot_df = pivot.pivot_table(index="priority", columns="status", values="count", fill_value=0).reset_index()
        total_tasks = session.scalar(select(func.count()).select_from(Task)) or 0
    return {
        "total": int(total_tasks),
        "status_df": status_df,
        "priority_df": priority_df,
        "overdue_total": int(overdue_total),
        "overdue_df": overdue_df,
        "rep_df": rep_df,
        "blocked_df": blocked_df,
        "pivot_df": pivot_df,
        "reference": ref.isoformat(),
    }


@st.cache_data(show_spinner=False)
def load_opportunity_section() -> dict:
    from sqlalchemy import func, select

    from yottaflex.db.models import Opportunity, OpportunityStage

    with open_session(engine) as session:
        rows = session.execute(
            select(
                Opportunity.business_id, Opportunity.stage, Opportunity.amount,
                Opportunity.product_line, Opportunity.loss_reason, Opportunity.salesrep_id,
                Opportunity.stage_entered_at, Opportunity.name,
            )
        ).all()
        df = pd.DataFrame(
            rows,
            columns=["opp", "stage", "amount", "product_line", "loss_reason", "rep", "stage_entered_at", "name"],
        )
        won_value = float(df.loc[df["stage"] == "won", "amount"].sum())
        lost_value = float(df.loc[df["stage"] == "lost", "amount"].sum())
        open_df = df[df["stage"].isin(["new_lead", "qualified", "demo", "proposal"])]
        open_value = float(open_df["amount"].sum())
    return {
        "df": df,
        "won_value": won_value,
        "lost_value": lost_value,
        "open_value": open_value,
        "open_count": int(len(open_df)),
    }


@st.cache_data(show_spinner=False)
def load_rep_performance() -> pd.DataFrame:
    from sqlalchemy import func, select

    from yottaflex.db.models import Opportunity, SalesRep

    with open_session(engine) as session:
        rows = session.execute(
            select(
                SalesRep.employee_code,
                func.count(Opportunity.opportunity_id).label("opportunities"),
            )
            .join(Opportunity, Opportunity.salesrep_id == SalesRep.salesrep_id)
            .group_by(SalesRep.employee_code)
        ).all()
        won_rows = session.execute(
            select(Opportunity.salesrep_id, func.count(), func.sum(Opportunity.amount))
            .where(Opportunity.stage == "won")
            .group_by(Opportunity.salesrep_id)
        ).all()
        lost_rows = session.execute(
            select(Opportunity.salesrep_id, func.count())
            .where(Opportunity.stage == "lost")
            .group_by(Opportunity.salesrep_id)
        ).all()
    reps = {r[0]: {"opps": int(r[1])} for r in rows}
    for rep_id, count, amount in won_rows:
        reps.setdefault(rep_id, {"opps": 0})
        reps[rep_id]["won"] = int(count)
        reps[rep_id]["won_value"] = float(amount or 0.0)
    for rep_id, count in lost_rows:
        reps.setdefault(rep_id, {"opps": 0})
        reps[rep_id]["lost"] = int(count)
    code_map = {}
    from yottaflex.db.models import SalesRep as _SR

    with open_session(engine) as session:
        for rid, code in session.execute(select(_SR.salesrep_id, _SR.employee_code)).all():
            code_map[rid] = code
    out = []
    for rid, vals in reps.items():
        out.append(
            {
                "rep": code_map.get(rid, str(rid)),
                "opps": vals.get("opps", 0),
                "won": vals.get("won", 0),
                "lost": vals.get("lost", 0),
                "won_value": vals.get("won_value", 0.0),
            }
        )
    return pd.DataFrame(out).sort_values("won", ascending=False).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_product_performance() -> pd.DataFrame:
    from sqlalchemy import case, func, select

    from yottaflex.db.models import Opportunity, OpportunityStage

    with open_session(engine) as session:
        rows = session.execute(
            select(
                Opportunity.product_line,
                func.sum(case((Opportunity.stage == "won", Opportunity.amount), else_=0.0)).label("won_value"),
                func.sum(case((Opportunity.stage == "lost", Opportunity.amount), else_=0.0)).label("lost_value"),
                func.count().label("total"),
            )
            .where(Opportunity.stage.in_([OpportunityStage.won.value, OpportunityStage.lost.value]))
            .group_by(Opportunity.product_line)
        ).all()
    return pd.DataFrame(rows, columns=["product_line", "won_value", "lost_value", "closed"])


@st.cache_data(show_spinner=False)
def load_exceptions() -> pd.DataFrame:
    from sqlalchemy import select

    from yottaflex.db.models import ExceptionRecord

    with open_session(engine) as session:
        rows = session.scalars(select(ExceptionRecord).order_by(ExceptionRecord.exception_id)).all()
    return pd.DataFrame(
        [
            {
                "id": r.exception_id,
                "type": r.issue_type,
                "severity": r.severity,
                "status": r.resolution_status,
                "entity": r.affected_entity,
                "record_id": r.affected_record_id,
                "gt": r.ground_truth_label,
                "detected_at": r.detection_timestamp.isoformat(),
                "evidence": r.evidence_json,
                "actual": r.actual_behavior,
            }
            for r in rows
        ]
    )


@st.cache_data(show_spinner=False)
def load_exception_section() -> dict:
    from sqlalchemy import func, select

    from yottaflex.db.models import ExceptionResolutionHistory

    with open_session(engine) as session:
        resolutions = session.execute(
            select(
                ExceptionResolutionHistory.resolution_id,
                ExceptionResolutionHistory.exception_id,
                ExceptionResolutionHistory.issue_type,
                ExceptionResolutionHistory.from_status,
                ExceptionResolutionHistory.to_status,
                ExceptionResolutionHistory.resolved_at,
            ).order_by(ExceptionResolutionHistory.resolution_id)
        ).all()
    res_df = pd.DataFrame(
        resolutions, columns=["resolution_id", "exception_id", "issue_type", "from_status", "to_status", "resolved_at"]
    )
    return {"resolutions": res_df}


@st.cache_data(show_spinner="Running full validation on the live database…")
def load_validation_live() -> dict:
    from yottaflex.engines.validation import validate_dataset

    with open_session(engine) as session:
        report = validate_dataset(
            session,
            expected={
                "company": settings.counts.companies,
                "contact": settings.counts.contacts,
                "lead": settings.counts.leads,
            },
            settings=settings,
        )
        return report.to_dict()


@st.cache_data(show_spinner=False)
def load_data_quality_section() -> dict:
    from sqlalchemy import func, select

    from yottaflex.db.models import (
        AnomalyInjectionLog, DuplicateGroundTruth, ExceptionRecord, GroundTruthException,
    )

    with open_session(engine) as session:
        exc_rows = session.execute(
            select(ExceptionRecord.issue_type, ExceptionRecord.severity, func.count())
            .group_by(ExceptionRecord.issue_type, ExceptionRecord.severity)
            .order_by(func.count().desc())
        ).all()
        exc_df = pd.DataFrame(exc_rows, columns=["issue_type", "severity", "detections"])
        dup_rows = session.execute(
            select(
                DuplicateGroundTruth.entity, DuplicateGroundTruth.origin,
                DuplicateGroundTruth.primary_business_id, DuplicateGroundTruth.duplicate_business_id,
                DuplicateGroundTruth.match_key, DuplicateGroundTruth.detected,
            ).order_by(DuplicateGroundTruth.duplicate_gt_id).limit(200)
        ).all()
        dup_df = pd.DataFrame(
            dup_rows,
            columns=["entity", "origin", "primary_business_id", "duplicate_business_id", "match_key", "detected"],
        )
        gt_dups = dict(
            session.execute(
                select(DuplicateGroundTruth.origin, func.count()).group_by(DuplicateGroundTruth.origin)
            ).all()
        )
        gt_exc = session.scalar(select(func.count()).select_from(GroundTruthException)) or 0
        injections = session.scalar(select(func.count()).select_from(AnomalyInjectionLog)) or 0
    return {
        "operational_exc_df": exc_df,
        "dup_df": dup_df,
        "gt_dup_counts": gt_dups,
        "gt_exceptions": int(gt_exc),
        "gt_injections": int(injections),
    }


@st.cache_data(show_spinner=False)
def load_audit_section() -> dict:
    """Export manifest + pipeline result artifacts (read-only)."""
    out: dict = {"manifest": None, "checksums_files": 0, "pipeline": None, "export_dir": None}
    for candidate in (PROJECT_ROOT / "data" / "exports", PROJECT_ROOT / "data" / "generated" / "exports"):
        manifest_path = candidate / "dataset_manifest.json"
        if manifest_path.exists():
            out["export_dir"] = str(candidate)
            out["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
            checksums = candidate / "checksums.json"
            if checksums.exists():
                out["checksums_files"] = len(json.loads(checksums.read_text(encoding="utf-8")).get("files", {}))
            break
    pipeline_path = PROJECT_ROOT / "data" / "reports" / "pipeline_result.json"
    if pipeline_path.exists():
        data = json.loads(pipeline_path.read_text(encoding="utf-8"))
        out["pipeline"] = {
            "validation_passed": data.get("validation", {}).get("passed"),
            "baseline_exceptions": data.get("baseline_exceptions", {}).get("count"),
            "detections": data.get("exceptions", {}).get("count"),
            "injections": data.get("injected"),
        }
    return out


@st.cache_data(show_spinner=False)
def load_stage_history(business_id: str) -> pd.DataFrame:
    from sqlalchemy import select

    from yottaflex.db.models import Opportunity, StageHistory

    with open_session(engine) as session:
        opp = session.scalars(select(Opportunity).where(Opportunity.business_id == business_id)).first()
        if opp is None:
            return pd.DataFrame()
        rows = session.execute(
            select(StageHistory.from_stage, StageHistory.to_stage, StageHistory.changed_at,
                   StageHistory.reason, StageHistory.actor_id)
            .where(StageHistory.opportunity_id == opp.opportunity_id)
            .order_by(StageHistory.stage_history_id)
        ).all()
    return pd.DataFrame(rows, columns=["from_stage", "to_stage", "changed_at", "reason", "actor"])


# ---------------------------------------------------------------------------
# Global chrome: brand, pill navigation, search, alerts, filter chips
# ---------------------------------------------------------------------------
metrics = load_metrics()
alerts_df = load_exceptions()
open_alerts = int((alerts_df["status"] == "open").sum()) if not alerts_df.empty else 0
crit_alerts = int(((alerts_df["status"] == "open") & (alerts_df["severity"] == "critical")).sum()) if not alerts_df.empty else 0
rep_options = load_rep_options()

head_brand, head_right = st.columns([3.4, 3])
with head_brand:
    st.markdown(
        '<div class="yf-brand" style="padding-top:0.2rem;">'
        '<div class="logo">YF</div><div><div class="name">YottaFlex AI</div>'
        '<div class="tag">Lead Intelligence Platform</div></div></div>',
        unsafe_allow_html=True,
    )
with head_right:
    search_col, alert_col = st.columns([3, 1.4])
    with search_col:
        global_search = st.text_input(
            "Global search", placeholder="Search leads…", label_visibility="collapsed", key="gsearch"
        )
    with alert_col:
        with st.popover(f"Alerts {open_alerts}", use_container_width=True):
            if alerts_df.empty:
                st.write("No exception records.")
            else:
                sev = (
                    alerts_df[alerts_df["status"] == "open"]
                    .groupby(["severity", "type"], as_index=False)
                    .size()
                    .rename(columns={"size": "count"})
                    .sort_values("count", ascending=False)
                )
                st.dataframe(sev, width="stretch", hide_index=True, height=220)
                st.caption("Operational detections only (ExceptionRecord); ground truth stays separate.")

# Full-width top navigation row (always visible; wraps cleanly)
section = (
    st.segmented_control(
        "Navigation", SECTIONS, selection_mode="single",
        default="Executive Overview", label_visibility="collapsed", key="nav",
    )
    or "Executive Overview"
)

st.write("")
chrome = st.columns([1.15, 1.5, 1.5, 1.0, 1.15, 0.75])
f_categories = chrome[0].multiselect("Category", ["hot", "warm", "nurture", "cold"], key="f_cat", placeholder="All")
f_statuses = chrome[1].multiselect(
    "Status", ["new", "scored", "assigned", "working", "qualified", "converted", "disqualified", "opted_out"],
    key="f_status", placeholder="All",
)
f_min_score = chrome[2].slider("Minimum score", 0, 100, 0, key="f_score")
f_split = chrome[3].selectbox("Eval split", ["all", "dev", "heldout"], key="f_split")
f_rep = chrome[4].selectbox("Owner (pipeline)", ["All reps"] + list(rep_options.keys()), key="f_rep")
with chrome[5]:
    st.write("")
    if st.button("Refresh", use_container_width=True, help="Recompute all cached queries from the database"):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# 1. Executive Overview
# ---------------------------------------------------------------------------
if section == "Executive Overview":
    rep_id = None if f_rep == "All reps" else rep_options[f_rep]
    k = load_exec_kpis(rep_id)
    cat_color = ui.CATEGORY_COLOR
    win_rate_pct = (k["win_rate"] or 0.0) * 100

    ui.kpi_grid(
        [
            ui.kpi_card("Active deals", f"{k['active_deals']:,}", f"{k['total_opportunities']:,} total · open stages", accent=ui.ACCENT),
            ui.kpi_card("Pipeline value", f"${k['open_pipeline_value']:,.0f}", "open opportunity value", accent=ui.ACCENT_2),
            ui.kpi_card("Win rate", f"{k['win_rate']:.1%}" if k["win_rate"] is not None else "n/a",
                        f"{k['won']:,} won / {k['closed']:,} closed", accent=ui.SUCCESS),
            ui.kpi_card("Avg deal cycle", f"{k['avg_cycle_days']:.1f} days" if k["avg_cycle_days"] else "n/a",
                        f"{k['won_with_dates']:,} closed-won with timestamps", accent=ui.AI),
        ]
    )
    ui.kpi_grid(
        [
            ui.kpi_card("Total leads", f"{k['total_leads']:,}", "all records", accent=ui.ACCENT),
            ui.kpi_card("Active leads", f"{k['active_leads']:,}", "excl. disqualified / opted-out", accent=ui.ACCENT_2),
            ui.kpi_card("Qualified leads", f"{k['qualified_leads']:,}", "qualified or converted", accent=ui.AI),
            ui.kpi_card("Lead conversion", f"{metrics['lead_conversion_rate']['value']:.1%}",
                        f"{metrics['lead_conversion_rate']['converted_leads']:,} of {metrics['lead_conversion_rate']['eligible_leads']:,} eligible", accent=ui.SUCCESS),
        ]
    )

    st.write("")
    left, right = st.columns([3, 1.15])

    with left:
        ui.section("Revenue pipeline", "open opportunities by stage · step bar = factual stage position")
        board = load_deal_board(rep_id, per_column=3)
        bands = ((50000, "High Value", ui.ACCENT), (35000, "Core", ui.AI), (0, "Standard", ui.MUTED))
        board_cols = []
        for key, title, accent in BOARD_COLUMNS:
            col = board[key]
            cards_html = []
            for c in col["cards"]:
                tag, tag_color = next((lbl, colr) for thr, lbl, colr in bands if c["amount"] >= thr)
                days = (TASK_AS_OF - c["stage_since"]).days
                cards_html.append(
                    ui.deal_card(
                        c["name"],
                        c["product_line"],
                        c["amount"],
                        BOARD_STEP[key],
                        5,
                        f"Owner {c['rep']}",
                        f"{days}d in stage",
                        tag=tag,
                        tag_color=tag_color,
                    )
                )
            board_cols.append(
                {"title": title, "total": f"${col['value']:,.0f}", "cards": cards_html, "more": col["more"]}
            )
        ui.kanban_board(board_cols)
        st.caption(
            "Top 3 open deals per stage by value; '+N more' is the real remaining count. Value tags are display "
            "bands over actual amounts (≥$50k High Value, ≥$35k Core); the step bar shows stage position, not a forecast."
        )

        funnel = pd.DataFrame(metrics["funnel"]["stages"])
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(funnel, x="stage", y="count", title="Conversion funnel (leads)", color="stage",
                         color_discrete_map=ui.STAGE_COLOR)
            ui.chart_style(fig, height=300).update_layout(showlegend=False)
            st.plotly_chart(fig, width="stretch")
        with c2:
            cats = pd.DataFrame(list(metrics["category_distribution"].items()), columns=["category", "count"])
            fig = px.pie(cats, names="category", values="count", title="Lead categories (score bands)",
                         color="category", color_discrete_map=cat_color, hole=0.55)
            ui.chart_style(fig, height=300)
            st.plotly_chart(fig, width="stretch")
        c3, c4 = st.columns(2)
        with c3:
            rep_perf = load_rep_performance().head(12)
            fig = px.bar(rep_perf, x="rep", y=["won", "lost"], title="Sales performance — top 12 reps",
                         barmode="group", color_discrete_sequence=[ui.SUCCESS, ui.DANGER])
            ui.chart_style(fig, height=300)
            st.plotly_chart(fig, width="stretch")
        with c4:
            prod = load_product_performance()
            fig = px.bar(prod, x="product_line", y=["won_value", "lost_value"],
                         title="Won vs lost value by product line ($)",
                         barmode="group", color_discrete_sequence=[ui.SUCCESS, ui.DANGER])
            ui.chart_style(fig, height=300)
            st.plotly_chart(fig, width="stretch")
        st.caption("The synthetic dataset spans a single quarter — multi-period revenue trends are not available; "
                   "value splits above are computed from actual opportunity records.")

    with right:
        ui.section("Deal intelligence", "rule-based signals · current records")
        intel_tab = (
            st.segmented_control(
                "Intel view", ["Insights", "Activity"], selection_mode="single",
                default="Insights", label_visibility="collapsed", key="intel_tab",
            )
            or "Insights"
        )
        if intel_tab == "Insights":
            sev_counts = (
                alerts_df[alerts_df["status"] == "open"].groupby("severity").size().to_dict()
                if not alerts_df.empty
                else {}
            )
            ui.insight_card(
                "Anomaly alerts",
                f"{open_alerts} open detection(s), {crit_alerts} critical",
                " · ".join(f"{s}: {c}" for s, c in sorted(sev_counts.items())) or "No open detections.",
                "Source: ExceptionRecord (detector output). Not ground truth.",
            )
            hot_leads = load_lead_explorer(("hot",), ("qualified", "working"), 90, "all", "", limit=5)
            if hot_leads.empty:
                ui.insight_card("High-priority leads", "No hot leads currently awaiting action",
                                "All hot leads are converted or excluded.", "Source: lead records.")
            else:
                rows_html = "<br>".join(
                    f"• {ui.esc(r.business_id)} — score {r.score} — {ui.esc(r.status)}"
                    for r in hot_leads.itertuples()
                )
                ui.insight_card(
                    "High-priority leads",
                    f"{len(hot_leads)} hot lead(s) awaiting conversion",
                    rows_html,
                    "Why: score ≥ 90 with hot category. Source: lead records (rule-based).",
                )
            tasks = load_task_section(TASK_AS_OF.isoformat())
            ui.insight_card(
                "Follow-up pressure",
                f"{tasks['overdue_total']:,} overdue follow-ups",
                "Top reps by volume: "
                + ", ".join(f"{r.rep} ({r.tasks})" for r in tasks["rep_df"].head(3).itertuples()),
                f"Overdue = pending tasks with due date < {tasks['reference'][:10]}.",
            )
            opps = load_opportunity_section()
            open_prop = opps["df"][opps["df"]["stage"] == "proposal"]
            if not open_prop.empty:
                oldest_days = int((TASK_AS_OF - open_prop["stage_entered_at"].min()).days)
                ui.insight_card(
                    "Pipeline risk",
                    f"{len(open_prop):,} proposals open — ${float(open_prop['amount'].sum()):,.0f}",
                    f"Oldest proposal has been in stage {oldest_days} days (as-of window).",
                    "Signal: stage duration heuristic, not a forecast.",
                )
        else:
            ui.timeline(load_recent_stage_events(7))
            st.caption("Latest recorded stage transitions from stage_history (most recent first).")

        ui.section("Performance engine", "closed-opportunity win rate")
        ui.gauge(
            win_rate_pct,
            "Win rate",
            f"{k['won']:,} won / {k['closed']:,} closed — computed from real records, no forecast.",
            color=ui.SUCCESS if win_rate_pct >= 50 else ui.WARNING,
        )

# ---------------------------------------------------------------------------
# 2. Lead Explorer
# ---------------------------------------------------------------------------
elif section == "Lead Explorer":
    leads = load_lead_explorer(tuple(f_categories), tuple(f_statuses), f_min_score, f_split, global_search)
    ui.section("Lead explorer", f"{len(leads):,} lead(s) match the top filters (display cap 2,000)")
    if leads.empty:
        ui.empty_state("No leads match the current filters.", "Adjust filters or clear the global search.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Matches", f"{len(leads):,}")
        c2.metric("Avg score", f"{leads['score'].mean():.1f}")
        c3.metric("Hot share", f"{(leads['category'] == 'hot').mean():.1%}")
        st.dataframe(leads, width="stretch", hide_index=True, height=340)
        st.download_button(
            "Export filtered leads (CSV, max 2,000)",
            data=leads.to_csv(index=False).encode("utf-8"),
            file_name="yottaflex_leads_filtered.csv",
            mime="text/csv",
        )
        st.divider()
        ui.section("Lead inspector", "score breakdown, explanation trail and follow-up tasks")
        pick = st.selectbox("Lead (business ID)", leads["business_id"].head(200).tolist(), key="explorer_pick")
        detail = load_lead_detail(pick)
        if detail:
            lead = detail["lead"]
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Score", lead["score"], help=f"category {lead['category']}")
            col_b.metric("Fit", lead["fit"])
            col_c.metric("Intent", lead["intent"])
            col_d.metric("Engagement", lead["engagement"])
            st.write(
                ui.badge(lead["status"], ui.ACCENT)
                + ui.badge(lead["category"], ui.CATEGORY_COLOR.get(lead["category"], ui.MUTED))
                + ui.badge(f"split: {lead['split']}", ui.AI)
                + ui.badge(f"territory {lead['territory']}", ui.ACCENT_2),
                unsafe_allow_html=True,
            )
            st.caption(
                f"{lead['name']} · {lead['email']} · source {lead['source']} · "
                f"rep {lead['rep']} · activities {detail['activity_count']:,}"
                + (f" · last activity {detail['last_activity']['type']} @ {detail['last_activity']['time'][:16]}"
                   if detail["last_activity"] else "")
            )
            ex = detail["explanation"]
            if ex:
                st.caption(f"Scoring explanation (scored at {ex['scored_at'][:16]})")
                rules_rows = []
                for r in ex["rules"]:
                    if isinstance(r, dict):
                        rules_rows.append(
                            {
                                "rule": r.get("rule_code"),
                                "dimension": r.get("dimension"),
                                "points": r.get("points"),
                            }
                        )
                if rules_rows:
                    st.dataframe(pd.DataFrame(rules_rows), width="stretch", hide_index=True, height=180)
                st.json(ex["weights"], expanded=False)
            if detail["tasks"]:
                st.dataframe(pd.DataFrame(detail["tasks"]), width="stretch", hide_index=True, height=160)
            else:
                ui.empty_state("No follow-up tasks recorded for this lead.")

# ---------------------------------------------------------------------------
# 3. Scoring Intelligence
# ---------------------------------------------------------------------------
elif section == "Scoring Intelligence":
    scores = load_lead_scores()
    ui.section("Scoring intelligence", f"{len(scores):,} scored leads · weights Fit 0.40 / Intent 0.35 / Engagement 0.25")
    c1, c2 = st.columns(2)
    with c1:
        fig = px.histogram(scores, x="score", nbins=40, title="Final score distribution",
                           color_discrete_sequence=[ui.ACCENT])
        ui.chart_style(fig, height=300)
        st.plotly_chart(fig, width="stretch")
    with c2:
        sample = scores.sample(min(len(scores), 3000), random_state=settings.seed)
        fig = px.scatter(sample, x="fit", y="intent", color="category", title="Fit vs Intent (sample 3,000)",
                         color_discrete_map=ui.CATEGORY_COLOR, opacity=0.6)
        ui.chart_style(fig, height=300)
        st.plotly_chart(fig, width="stretch")
    c3, c4 = st.columns(2)
    comps = scores.melt(
        id_vars=["lead_id"], value_vars=["fit", "intent", "engagement"], var_name="component", value_name="value"
    )
    with c3:
        fig = px.histogram(comps, x="value", color="component", barmode="overlay", histnorm="percent",
                           title="Score components (all scored leads)", opacity=0.55,
                           color_discrete_sequence=[ui.ACCENT, ui.AI, ui.SUCCESS])
        ui.chart_style(fig, height=300)
        st.plotly_chart(fig, width="stretch")
    with c4:
        he = metrics["heldout_evaluation"]
        rows = []
        for split, buckets in he["by_split_and_bucket"].items():
            for bucket, data in buckets.items():
                rows.append({"split": split, "bucket": bucket, **data})
        st.write("**Held-out evaluation** — conversion rate by score bucket")
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=260)
    st.caption("Explanation trails per lead (weights + fired rules) are viewable in Lead Explorer → Lead inspector.")

# ---------------------------------------------------------------------------
# 4. Sales Assignment
# ---------------------------------------------------------------------------
elif section == "Sales Assignment":
    asg = load_assignment_section()
    ac = metrics["assignment_coverage"]
    ui.section("Sales assignment", "least-loaded routing across territories with capacity awareness")
    ui.kpi_grid(
        [
            ui.kpi_card("Coverage", f"{ac['value']:.1%}", f"{ac['assigned_leads']:,} / {ac['assignable_leads']:,} assignable", accent=ui.SUCCESS),
            ui.kpi_card("Unassigned (active)", f"{asg['unassigned_total']:,}", "assignable leads without a rep", accent=ui.WARNING),
            ui.kpi_card("Routing exceptions (EX-03)", f"{asg['assignment_exceptions_total']:,}", "outside-territory assignments", accent=ui.DANGER),
            ui.kpi_card("Active reps", f"{int((asg['rep_df']['assigned_leads'] > 0).sum())}", f"of {len(asg['rep_df'])}", accent=ui.ACCENT_2),
        ]
    )
    c1, c2 = st.columns(2)
    with c1:
        rep_top = asg["rep_df"].head(20).sort_values("assigned_leads")
        fig = px.bar(rep_top, x="assigned_leads", y="rep", orientation="h",
                     title="Representative-wise assignment distribution (top 20)",
                     color_discrete_sequence=[ui.ACCENT])
        ui.chart_style(fig, height=430).update_layout(yaxis_title="", xaxis_title="assigned leads")
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = px.bar(asg["terr_df"].sort_values("leads"), x="leads", y="territory", orientation="h",
                     title="Territory-wise workload", color_discrete_sequence=[ui.ACCENT_2])
        ui.chart_style(fig, height=430).update_layout(yaxis_title="", xaxis_title="leads")
        st.plotly_chart(fig, width="stretch")
    ui.section("Capacity utilization — top 10 reps", "assigned leads / max open capacity")
    for row in asg["rep_df"].head(10).itertuples():
        col1, col2, col3 = st.columns([2, 5, 1])
        col1.write(f"**{row.rep}** · {row.role} · {row.home_territory}")
        col2.markdown(ui.progress_bar(row.utilization or 0, ui.ACCENT if (row.utilization or 0) < 0.75 else ui.WARNING),
                      unsafe_allow_html=True)
        col3.caption(f"{row.assigned_leads}/{row.capacity} ({(row.utilization or 0):.0%})")
    with st.expander("All representatives (workload & capacity)", expanded=False):
        st.dataframe(asg["rep_df"], width="stretch", hide_index=True, height=300)
    with st.expander("Territory detail", expanded=False):
        st.dataframe(asg["terr_df"], width="stretch", hide_index=True, height=280)
    ui.section("Assignment exceptions (operational records)")
    if asg["assignment_exceptions_df"].empty:
        ui.empty_state("No lead_assigned_outside_territory exception records.")
    else:
        st.dataframe(asg["assignment_exceptions_df"], width="stretch", hide_index=True, height=240)
        st.caption("Detector output (ExceptionRecord). Ground-truth labels are separate and never detector input.")

# ---------------------------------------------------------------------------
# 5. Task Management
# ---------------------------------------------------------------------------
elif section == "Task Management":
    tasks = load_task_section(TASK_AS_OF.isoformat())
    status_map = dict(zip(tasks["status_df"]["status"], tasks["status_df"]["count"]))
    ui.section("Task management", f"as-of {tasks['reference'][:10]} (base + 90 days reference)")
    ui.kpi_grid(
        [
            ui.kpi_card("Total tasks", f"{tasks['total']:,}", "task table records", accent=ui.ACCENT),
            ui.kpi_card("Pending", f"{int(status_map.get('pending', 0)):,}", "awaiting execution", accent=ui.WARNING),
            ui.kpi_card("Blocked", f"{int(status_map.get('blocked', 0)):,}", "consent-gated outreach", accent=ui.DANGER),
            ui.kpi_card("Overdue", f"{tasks['overdue_total']:,}", f"pending with due < {tasks['reference'][:10]}", accent=ui.DANGER),
            ui.kpi_card("Completed in dataset", f"{int(status_map.get('completed', 0)):,}", "dataset contains pending/blocked only", accent=ui.MUTED),
        ]
    )
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(tasks["status_df"], x="status", y="count", title="Tasks by status", color="status",
                     color_discrete_map=ui.STATUS_COLOR)
        ui.chart_style(fig, height=300).update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = px.bar(tasks["priority_df"], x="priority", y="count", title="Tasks by priority",
                     color="priority",
                     color_discrete_map={"high": ui.DANGER, "medium": ui.WARNING, "low": ui.MUTED})
        ui.chart_style(fig, height=300).update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch")
    c3, c4 = st.columns(2)
    with c3:
        fig = px.bar(tasks["rep_df"].head(20).sort_values("tasks"), x="tasks", y="rep", orientation="h",
                     title="Representative-wise task workload (top 20)", color_discrete_sequence=[ui.ACCENT_2])
        ui.chart_style(fig, height=420).update_layout(yaxis_title="", xaxis_title="tasks")
        st.plotly_chart(fig, width="stretch")
    with c4:
        st.write("**Priority × status matrix**")
        st.dataframe(tasks["pivot_df"], width="stretch", hide_index=True, height=180)
        st.write("**Consent blockers**")
        st.dataframe(tasks["blocked_df"], width="stretch", hide_index=True, height=180)
    with st.expander(f"Overdue task detail (first 200 of {tasks['overdue_total']:,})", expanded=False):
        st.dataframe(tasks["overdue_df"], width="stretch", hide_index=True, height=300)
    st.caption(
        "Overdue uses the same base+90d reference as exception timestamps. 'Completed' is 0 because the "
        "generated dataset only produces pending/consent-blocked tasks — a data fact, not a display error."
    )

# ---------------------------------------------------------------------------
# 6. Opportunity Pipeline
# ---------------------------------------------------------------------------
elif section == "Opportunity Pipeline":
    opps = load_opportunity_section()
    wr = metrics["opportunity_win_rate"]
    ui.section("Opportunity pipeline", "stages, value and outcome analysis")
    ui.kpi_grid(
        [
            ui.kpi_card("Open opportunities", f"{opps['open_count']:,}", "new_lead + demo + proposal", accent=ui.ACCENT),
            ui.kpi_card("Open value", f"${opps['open_value']:,.0f}", "sum of open amounts", accent=ui.ACCENT_2),
            ui.kpi_card("Won value", f"${opps['won_value']:,.0f}", f"{wr['won']:,} opportunities", accent=ui.SUCCESS),
            ui.kpi_card("Lost value", f"${opps['lost_value']:,.0f}", f"{wr['lost']:,} opportunities", accent=ui.DANGER),
            ui.kpi_card("Win rate", f"{wr['value']:.1%}", f"closed {wr['closed']:,}", accent=ui.SUCCESS),
        ]
    )
    c1, c2 = st.columns(2)
    with c1:
        stages = pd.DataFrame(list(metrics["stage_distribution"].items()), columns=["stage", "count"])
        fig = px.bar(stages, x="stage", y="count", title="Stage distribution", color="stage",
                     color_discrete_map=ui.STAGE_COLOR)
        ui.chart_style(fig, height=300).update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with c2:
        lost_df = opps["df"][opps["df"]["loss_reason"].notna()]
        by_reason = lost_df.groupby("loss_reason", as_index=False).size().rename(columns={"size": "count"})
        fig = px.bar(by_reason, x="loss_reason", y="count", title="Lost opportunities by reason",
                     color_discrete_sequence=[ui.DANGER])
        ui.chart_style(fig, height=300)
        st.plotly_chart(fig, width="stretch")
    ui.section("Stage history inspector", "append-only transition trail per opportunity")
    sample_ids = opps["df"][opps["df"]["stage"].isin(["won", "lost", "proposal", "demo"])]["opp"].head(500).tolist()
    pick_opp = st.selectbox("Opportunity (business ID)", sample_ids, key="opp_pick")
    hist = load_stage_history(pick_opp)
    if hist.empty:
        ui.empty_state("No stage history for this opportunity.")
    else:
        left_h, right_h = st.columns([3, 1])
        with left_h:
            st.dataframe(hist, width="stretch", hide_index=True, height=260)
        with right_h:
            row = opps["df"][opps["df"]["opp"] == pick_opp].iloc[0]
            st.metric("Stage", row["stage"])
            st.caption(f"Entered {str(row['stage_entered_at'])[:16]}")
            if row["loss_reason"]:
                st.markdown(ui.badge(f"lost: {row['loss_reason']}", ui.DANGER), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 7. Exception Intelligence
# ---------------------------------------------------------------------------
elif section == "Exception Intelligence":
    ev = metrics["exception_evaluation"]
    sev_open = (
        alerts_df[alerts_df["status"] == "open"].groupby("severity").size().to_dict()
        if not alerts_df.empty
        else {}
    )
    ui.section("Exception intelligence", "blind key-matched evaluation · operational detections")
    ui.kpi_grid(
        [
            ui.kpi_card("Open — critical", f"{int(sev_open.get('critical', 0))}", "consent & temporal leakage", accent=ui.DANGER),
            ui.kpi_card("Open — high", f"{int(sev_open.get('high', 0))}", "territory & duplicates", accent=ui.WARNING),
            ui.kpi_card("Open — medium", f"{int(sev_open.get('medium', 0))}", "stage-history gaps", accent=ui.ACCENT),
            ui.kpi_card("Precision / Recall / F1", f"{ev['overall_precision']} / {ev['overall_recall']} / {ev['overall_f1']}",
                        f"detections {ev['detections']} vs injections {ev['injections']}", accent=ui.AI),
        ]
    )
    c1, c2 = st.columns([2, 1])
    with c1:
        by_type = pd.DataFrame(ev["by_type"]).T.reset_index().rename(columns={"index": "issue_type"})
        st.dataframe(by_type, width="stretch", hide_index=True, height=240)
    with c2:
        res = load_exception_section()["resolutions"]
        st.write("**Resolution history**")
        if res.empty:
            ui.empty_state("No manual resolutions recorded.", "PATCH /api/v1/exceptions/{id} appends history.")
        else:
            st.dataframe(res, width="stretch", hide_index=True, height=200)
    ui.section("Detection catalog", "operational records with evidence")
    if alerts_df.empty:
        ui.empty_state("No exception records.")
    else:
        types = (
            alerts_df.groupby(["type", "severity"], as_index=False)
            .size()
            .rename(columns={"size": "detections"})
            .sort_values("detections", ascending=False)
        )
        st.dataframe(types, width="stretch", hide_index=True, height=220)
        pick_exc = st.selectbox("Inspect detection evidence", alerts_df["id"].head(200).tolist(), key="exc_pick")
        row = alerts_df[alerts_df["id"] == pick_exc].iloc[0]
        st.markdown(
            ui.badge(row["type"], ui.SEVERITY_COLOR.get(row["severity"], ui.ACCENT))
            + ui.badge(row["severity"], ui.SEVERITY_COLOR.get(row["severity"], ui.ACCENT))
            + ui.badge(row["status"], ui.SUCCESS if row["status"] == "resolved" else ui.MUTED),
            unsafe_allow_html=True,
        )
        st.caption(row["actual"])
        try:
            st.json(json.loads(row["evidence"] or "{}"), expanded=True)
        except (TypeError, json.JSONDecodeError):
            st.write(row["evidence"])
        st.caption(
            "Ground truth (anomaly_injection_log, ground_truth_exception, duplicate_gt) is used only for the "
            "P/R/F1 evaluation above — never as detector input. Labels shown on records are attached after "
            "evaluation for display only."
        )

# ---------------------------------------------------------------------------
# 8. Data Quality
# ---------------------------------------------------------------------------
elif section == "Data Quality":
    validation = load_validation_live()
    dq = load_data_quality_section()
    ui.section("Data quality", "full-coverage validation of the live database")
    ui.kpi_grid(
        [
            ui.kpi_card("Validation passed", "yes" if validation["passed"] else "no",
                        f"{validation['checks_run']} checks run", accent=ui.SUCCESS if validation["passed"] else ui.DANGER),
            ui.kpi_card("Critical issues", f"{validation['critical_count']}", "must be zero", accent=ui.DANGER),
            ui.kpi_card("Total issues", f"{validation['total_issues']}", "all severities", accent=ui.WARNING),
            ui.kpi_card("Duplicate detection", f"{metrics['duplicate_detection_rate']['value']:.1%}",
                        f"{metrics['duplicate_detection_rate']['detected_duplicates']:,} / {metrics['duplicate_detection_rate']['ground_truth_duplicates']:,} GT", accent=ui.AI),
        ]
    )
    issues_df = pd.DataFrame(validation["issues"])
    c1, c2 = st.columns([1, 2])
    with c1:
        if issues_df.empty:
            ui.empty_state("No validation issues recorded.")
        else:
            sev = issues_df.groupby("severity", as_index=False).size().rename(columns={"size": "issues"})
            fig = px.bar(sev, x="severity", y="issues", title="Issues by severity", color="severity",
                         color_discrete_map=ui.SEVERITY_COLOR)
            ui.chart_style(fig, height=280).update_layout(showlegend=False)
            st.plotly_chart(fig, width="stretch")
    with c2:
        if not issues_df.empty:
            chk = (
                issues_df.groupby(["check", "severity"], as_index=False)
                .size()
                .rename(columns={"size": "issues"})
                .sort_values("issues", ascending=False)
            )
            st.dataframe(chk, width="stretch", hide_index=True, height=280)
    if not issues_df.empty:
        st.dataframe(issues_df, width="stretch", hide_index=True, height=220)
        if validation["total_issues"] > len(issues_df):
            st.caption(f"Showing first {len(issues_df)} of {validation['total_issues']} issues (stored report truncation).")

    ui.section("Operational detections vs ground-truth labels", "strict separation (GT is evaluation-only)")
    c3, c4 = st.columns(2)
    with c3:
        st.write("**Operational detections (ExceptionRecord)**")
        st.dataframe(dq["operational_exc_df"], width="stretch", hide_index=True, height=240)
    with c4:
        st.write("**Ground-truth labels (never detector input)**")
        gt_rows = pd.DataFrame(
            [
                {"table": "duplicate_gt", "labels": dq["gt_dup_counts"].get("natural", 0) + dq["gt_dup_counts"].get("injected", 0)},
                {"table": "ground_truth_exception", "labels": dq["gt_exceptions"]},
                {"table": "anomaly_injection_log", "labels": dq["gt_injections"]},
            ]
        )
        st.dataframe(gt_rows, width="stretch", hide_index=True, height=140)
        st.caption(f"duplicate_gt origins: {dq['gt_dup_counts']}")
    ui.section("Duplicate records (ground-truth sample)")
    st.dataframe(dq["dup_df"], width="stretch", hide_index=True, height=260)

# ---------------------------------------------------------------------------
# 9. Configuration & Audit
# ---------------------------------------------------------------------------
elif section == "Configuration & Audit":
    audit = load_audit_section()
    ui.section("Configuration", "runtime settings driving generation, scoring and policy")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("**Dataset**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"key": "seed", "value": str(settings.seed)},
                    {"key": "base datetime", "value": settings.base_datetime},
                    {"key": "business ID year", "value": str(settings.business_id_year)},
                    {"key": "database", "value": settings.database_url},
                ]
            ),
            width="stretch", hide_index=True,
        )
    with c2:
        st.write("**Scoring weights & thresholds**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"key": "fit weight", "value": str(settings.scoring.weights.fit)},
                    {"key": "intent weight", "value": str(settings.scoring.weights.intent)},
                    {"key": "engagement weight", "value": str(settings.scoring.weights.engagement)},
                    {"key": "hot threshold", "value": str(settings.scoring.category_thresholds.hot)},
                    {"key": "warm threshold", "value": str(settings.scoring.category_thresholds.warm)},
                    {"key": "nurture threshold", "value": str(settings.scoring.category_thresholds.nurture)},
                ]
            ),
            width="stretch", hide_index=True,
        )
    with c3:
        st.write("**Injection quotas**")
        q = settings.anomaly_injection.quotas
        st.dataframe(
            pd.DataFrame(
                [
                    {"scenario": "opted-out contacted", "quota": q.opted_out_contacted},
                    {"scenario": "temporal leakage", "quota": q.temporal_leakage},
                    {"scenario": "territory mismatch", "quota": q.territory_mismatch},
                    {"scenario": "duplicate opportunity", "quota": q.duplicate_opportunity},
                    {"scenario": "stage-history gap", "quota": q.stage_history_gap},
                ]
            ),
            width="stretch", hide_index=True,
        )
    ui.section("Export audit", "dataset manifest and checksums (artifacts, read-only)")
    if audit["manifest"]:
        m = audit["manifest"]
        st.caption(f"manifest: {audit['export_dir']} · checksummed files: {audit['checksums_files']}")
        counts_df = pd.DataFrame(
            [{"table": t, "rows": c} for t, c in sorted(m.get("counts", {}).items())]
        )
        st.dataframe(counts_df, width="stretch", hide_index=True, height=280)
    else:
        ui.empty_state("No dataset manifest found.", "Run: python scripts/generate_data.py --scale full")
    ui.section("Pipeline audit", "last recorded pipeline execution")
    if audit["pipeline"]:
        p = audit["pipeline"]
        st.dataframe(
            pd.DataFrame(
                [
                    {"key": "validation passed", "value": str(p["validation_passed"])},
                    {"key": "baseline exceptions", "value": str(p["baseline_exceptions"])},
                    {"key": "post-injection detections", "value": str(p["detections"])},
                    {"key": "injections (per scenario)", "value": json.dumps(p["injections"])},
                ]
            ),
            width="stretch", hide_index=True,
        )
    else:
        ui.empty_state("No pipeline result artifact found.", "Run: python scripts/generate_data.py --scale full")

# ---------------------------------------------------------------------------
st.caption(
    f"YottaFlex AI · seed {settings.seed} · deterministic pipeline · all metrics computed live from SQLite — "
    "no fabricated analytics. AI panel signals are rule-based derivations of current records."
)
