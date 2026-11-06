from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yottaflex.db.models import (
    ExceptionRecord,
    GroundTruthException,
    IssueType,
    Lead,
    LeadScoreExplanation,
    Opportunity,
    ResolutionStatus,
    SalesRep,
    Severity,
    StageHistory,
    Task,
    AnomalyInjectionLog,
)
from yottaflex.engines.consent import check_outreach_consent
from yottaflex.engines.stage_history import validate_stage_path
from yottaflex.logging_setup import get_logger

log = get_logger("exceptions")


class Detector(Protocol):
    issue_type: str

    def detect(self, session: Session, detected_at: datetime) -> list[ExceptionRecord]: ...


# NOTE (P0-5): detectors are deliberately blind — they never attach ground
# truth labels during detection. Evaluation matches detections to GT by keys
# afterwards (see exception_evaluation / _blind_match). This removes the
# previous circular "label attached from injection log ⇒ matched" logic.


class ConsentViolationDetector:
    """EX-01: outreach task/activity on lead without valid consent."""

    issue_type = IssueType.opted_out_lead_contacted.value

    def detect(self, session: Session, detected_at: datetime) -> list[ExceptionRecord]:
        results: list[ExceptionRecord] = []
        tasks = session.scalars(
            select(Task).where(Task.status.in_(["pending", "in_progress", "completed"]))
        ).all()
        for task in tasks:
            lead = session.get(Lead, task.lead_id)
            if lead is None:
                continue
            channel = "phone" if task.task_type == "call" else "email"
            decision = check_outreach_consent(session, lead, channel, as_of=task.created_at)
            if decision.allowed:
                continue
            # Only flag if task is an outreach attempt (not blocked)
            if task.status == "blocked":
                continue
            results.append(
                ExceptionRecord(
                    issue_type=self.issue_type,
                    affected_entity="task",
                    affected_record_id=task.task_id,
                    detection_timestamp=detected_at,
                    expected_behavior="No outreach for lead without valid consent",
                    actual_behavior=(
                        f"Task {task.task_id} type={task.task_type} status={task.status} "
                        f"for lead {lead.lead_id} consent={decision.status}"
                    ),
                    ground_truth_label=None,  # blind detection (P0-5)
                    severity=Severity.critical.value,
                    resolution_status=ResolutionStatus.open.value,
                    related_lead_id=lead.lead_id,
                    evidence_json=json.dumps(
                        {"consent_status": decision.status, "reason": decision.reason}
                    ),
                    created_at=detected_at,
                )
            )
        return results


class TemporalLeakageDetector:
    """EX-02 (V3.2.2): detects scores produced AFTER conversion that incorporated
    post-conversion intent activity.

    Independent detection only: uses actual event timestamps (activity.event_time),
    scoring timestamps (explanation.scored_at) and conversion timestamps
    (lead.converted_at). It never reads injected markers, rule payload flags, or
    any ground-truth fields.
    """

    issue_type = IssueType.score_uses_post_conversion_event.value

    INTENT_EVENT_TYPES = ("demo_request", "pricing_inquiry", "form_submit", "content_download")

    def detect(self, session: Session, detected_at: datetime) -> list[ExceptionRecord]:
        from yottaflex.db.models import Activity

        results: list[ExceptionRecord] = []

        # Candidates: explanations whose score timestamp is AFTER the lead conversion
        candidates = session.execute(
            select(LeadScoreExplanation, Lead)
            .join(Lead, Lead.lead_id == LeadScoreExplanation.lead_id)
            .where(
                Lead.converted_at.is_not(None),
                LeadScoreExplanation.scored_at > Lead.converted_at,
            )
            .order_by(LeadScoreExplanation.explanation_id)
        ).all()

        for expl, lead in candidates:
            # Independent evidence: an intent activity in (converted_at, scored_at]
            evidence = session.execute(
                select(
                    Activity.activity_id,
                    Activity.activity_type,
                    Activity.event_time,
                )
                .where(
                    Activity.lead_id == lead.lead_id,
                    Activity.event_time > lead.converted_at,
                    Activity.event_time <= expl.scored_at,
                    Activity.activity_type.in_(self.INTENT_EVENT_TYPES),
                )
                .order_by(Activity.activity_id)
                .limit(1)
            ).first()
            if evidence is None:
                continue  # scored late but no post-conversion evidence was used

            results.append(
                ExceptionRecord(
                    issue_type=self.issue_type,
                    affected_entity="lead_score_explanation",
                    affected_record_id=expl.explanation_id,
                    detection_timestamp=detected_at,
                    expected_behavior=(
                        "Scores must not incorporate activity events after the "
                        "conversion/scoring cutoff"
                    ),
                    actual_behavior=(
                        f"Score explanation {expl.explanation_id} scored at "
                        f"{expl.scored_at} (after conversion {lead.converted_at}) "
                        f"incorporates post-conversion {evidence.activity_type} "
                        f"activity {evidence.activity_id} at {evidence.event_time}"
                    ),
                    ground_truth_label=None,  # blind detection (P0-5)
                    severity=Severity.critical.value,
                    resolution_status=ResolutionStatus.open.value,
                    related_lead_id=lead.lead_id,
                    evidence_json=json.dumps(
                        {
                            "activity_id": evidence.activity_id,
                            "activity_type": evidence.activity_type,
                            "event_time": evidence.event_time.isoformat(),
                            "scored_at": expl.scored_at.isoformat(),
                            "converted_at": lead.converted_at.isoformat(),
                        }
                    ),
                    created_at=detected_at,
                )
            )
        return results


class TerritoryMismatchDetector:
    """EX-03: lead assigned to rep not covering lead territory."""

    issue_type = IssueType.lead_assigned_outside_territory.value

    def detect(self, session: Session, detected_at: datetime) -> list[ExceptionRecord]:
        from yottaflex.engines.routing import territory_covers

        results: list[ExceptionRecord] = []
        leads = session.scalars(
            select(Lead).where(Lead.assigned_salesrep_id.is_not(None)).order_by(Lead.lead_id)
        ).all()
        for lead in leads:
            rep_id = lead.assigned_salesrep_id
            if rep_id is None:
                continue
            if territory_covers(session, rep_id, lead.territory_code):
                continue
            rep = session.get(SalesRep, rep_id)
            results.append(
                ExceptionRecord(
                    issue_type=self.issue_type,
                    affected_entity="lead",
                    affected_record_id=lead.lead_id,
                    detection_timestamp=detected_at,
                    expected_behavior="Lead assigned only to reps covering lead territory",
                    actual_behavior=(
                        f"Lead {lead.lead_id} territory={lead.territory_code} "
                        f"assigned to rep {rep_id} "
                        f"(home={rep.home_territory_code if rep else '?'})"
                    ),
                    ground_truth_label=None,  # blind detection (P0-5)
                    severity=Severity.high.value,
                    resolution_status=ResolutionStatus.open.value,
                    related_lead_id=lead.lead_id,
                    evidence_json=json.dumps(
                        {
                            "lead_territory": lead.territory_code,
                            "rep_id": rep_id,
                            "rep_home": rep.home_territory_code if rep else None,
                        }
                    ),
                    created_at=detected_at,
                )
            )
        return results


class DuplicateOpportunityDetector:
    """EX-04: same lead results in multiple opportunities."""

    issue_type = IssueType.duplicate_creates_duplicate_opportunity.value

    def detect(self, session: Session, detected_at: datetime) -> list[ExceptionRecord]:
        from sqlalchemy import func

        results: list[ExceptionRecord] = []
        rows = session.execute(
            select(Opportunity.lead_id, func.count().label("c"), func.group_concat(Opportunity.opportunity_id))
            .group_by(Opportunity.lead_id)
            .having(func.count() > 1)
        ).all()
        for lead_id, c, opp_ids in rows:
            first_opp = int(str(opp_ids).split(",")[0])
            results.append(
                ExceptionRecord(
                    issue_type=self.issue_type,
                    affected_entity="opportunity",
                    affected_record_id=first_opp,
                    detection_timestamp=detected_at,
                    expected_behavior="At most one opportunity per lead",
                    actual_behavior=f"Lead {lead_id} has {c} opportunities: {opp_ids}",
                    ground_truth_label=None,  # blind detection (P0-5)
                    severity=Severity.high.value,
                    resolution_status=ResolutionStatus.open.value,
                    related_lead_id=lead_id,
                    evidence_json=json.dumps({"opportunity_ids": str(opp_ids), "count": c}),
                    created_at=detected_at,
                )
            )
        return results


class StageGapDetector:
    """EX-05: missing or invalid stage transitions."""

    issue_type = IssueType.stage_history_has_gaps.value

    def detect(self, session: Session, detected_at: datetime) -> list[ExceptionRecord]:
        results: list[ExceptionRecord] = []
        opp_ids = session.scalars(select(Opportunity.opportunity_id).order_by(Opportunity.opportunity_id)).all()
        for opp_id in opp_ids:
            issues = validate_stage_path(session, opp_id)
            if not issues:
                continue
            # Distinguish gaps/invalid vs missing (missing also flagged)
            results.append(
                ExceptionRecord(
                    issue_type=self.issue_type,
                    affected_entity="stage_history",
                    affected_record_id=opp_id,
                    detection_timestamp=detected_at,
                    expected_behavior="Complete canonical stage path with monotonic history",
                    actual_behavior="; ".join(issues),
                    ground_truth_label=None,  # blind detection (P0-5)
                    severity=Severity.medium.value,
                    resolution_status=ResolutionStatus.open.value,
                    related_lead_id=None,
                    evidence_json=json.dumps({"issues": issues}),
                    created_at=detected_at,
                )
            )
        return results


DEFAULT_DETECTORS: list[Detector] = [
    ConsentViolationDetector(),
    TemporalLeakageDetector(),
    TerritoryMismatchDetector(),
    DuplicateOpportunityDetector(),
    StageGapDetector(),
]


def run_exception_detection(
    session: Session,
    detected_at: datetime | None = None,
    detectors: list[Detector] | None = None,
    replace_existing: bool = True,
) -> list[ExceptionRecord]:
    """Exception Detection Engine (K)."""
    if detected_at is None:
        detected_at = datetime.fromisoformat("2025-04-01T00:00:00+00:00").replace(tzinfo=None)
    detectors = detectors or DEFAULT_DETECTORS

    if replace_existing:
        from sqlalchemy import delete

        session.execute(delete(ExceptionRecord))
        session.commit()

    all_records: list[ExceptionRecord] = []
    for det in detectors:
        found = det.detect(session, detected_at)
        for rec in found:
            session.add(rec)
        all_records.extend(found)
        log.info("detector %s -> %d", det.issue_type, len(found))
    session.commit()
    return all_records


def _gt_key_sets(session: Session, issue_type: str) -> tuple[set, set]:
    """Return (gt_keys) for an issue type from independent ground truth.

    Blind evaluation: keys are read from GT tables only — never from
    ExceptionRecord.ground_truth_label.

    Matching keys:
      EX-04 (duplicate opportunity): related_lead_id (one detection per lead
        group; GT rows come from duplicate_gt natural+injected and injections)
      all others: affected_record_id
    """
    if issue_type == IssueType.duplicate_creates_duplicate_opportunity.value:
        from yottaflex.db.models import DuplicateGroundTruth, Opportunity

        keys: set = set()
        # duplicate_gt rows (natural + injected) → resolve to lead ids
        dup_rows = session.execute(
            select(
                DuplicateGroundTruth.duplicate_record_id,
                DuplicateGroundTruth.primary_record_id,
            ).where(DuplicateGroundTruth.entity == "opportunity")
        ).all()
        opp_ids: list[int] = []
        for dup_id, prim_id in dup_rows:
            opp_ids.extend([dup_id, prim_id])
        opp_ids = sorted(set(opp_ids))
        for start in range(0, len(opp_ids), 800):
            part = opp_ids[start : start + 800]
            for lead_id in session.execute(
                select(Opportunity.lead_id).where(Opportunity.opportunity_id.in_(part))
            ).scalars():
                if lead_id is not None:
                    keys.add(int(lead_id))
        # also include injected GT rows keyed by related_lead_id
        for (lid,) in session.execute(
            select(AnomalyInjectionLog.related_lead_id).where(
                AnomalyInjectionLog.issue_type == issue_type,
                AnomalyInjectionLog.related_lead_id.is_not(None),
            )
        ).all():
            keys.add(int(lid))
        return keys

    keys = set()
    for (rid,) in session.execute(
        select(AnomalyInjectionLog.target_record_id).where(
            AnomalyInjectionLog.issue_type == issue_type,
            AnomalyInjectionLog.target_entity.in_(
                [
                    "task",
                    "lead",
                    "lead_score_explanation",
                    "opportunity",
                    "stage_history",
                ]
            ),
        )
    ).all():
        keys.add(int(rid))
    for (rid,) in session.execute(
        select(GroundTruthException.affected_record_id).where(
            GroundTruthException.issue_type == issue_type
        )
    ).all():
        keys.add(int(rid))
    return keys


def _detection_key_sets(session: Session, issue_type: str) -> set:
    if issue_type == IssueType.duplicate_creates_duplicate_opportunity.value:
        return {
            int(r[0])
            for r in session.execute(
                select(ExceptionRecord.related_lead_id).where(
                    ExceptionRecord.issue_type == issue_type,
                    ExceptionRecord.related_lead_id.is_not(None),
                )
            ).all()
        }
    return {
        int(r[0])
        for r in session.execute(
            select(ExceptionRecord.affected_record_id).where(
                ExceptionRecord.issue_type == issue_type
            )
        ).all()
    }


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | int | None]:
    precision = (tp / (tp + fp)) if (tp + fp) else None
    recall = (tp / (tp + fn)) if (tp + fn) else None
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def exception_evaluation(session: Session) -> dict[str, Any]:
    """Blind precision/recall/F1 of detectors vs independent ground truth (P0-5).

    Detections are matched to GT by business keys only (record id or lead id),
    never by labels attached during detection. Undefined metrics (no GT or no
    detections) are reported as null — never defaulted to 1.0.
    """
    det_count = session.scalar(select(func.count()).select_from(ExceptionRecord)) or 0
    inj_count = session.scalar(select(func.count()).select_from(AnomalyInjectionLog)) or 0

    by_type: dict[str, dict[str, Any]] = {}
    total_tp = total_fp = total_fn = 0
    for issue in IssueType:
        gt_keys = _gt_key_sets(session, issue.value)
        det_keys = _detection_key_sets(session, issue.value)
        tp = len(gt_keys & det_keys)
        fp = len(det_keys - gt_keys)
        fn = len(gt_keys - det_keys)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        stats = _prf(tp, fp, fn)
        stats["ground_truth"] = len(gt_keys)
        stats["detected"] = len(det_keys)
        by_type[issue.value] = stats

    overall = _prf(total_tp, total_fp, total_fn)
    return {
        "methodology": (
            "blind key-based matching (detections ↔ GT by record/lead id); "
            "null metrics mean undefined (no GT or no detections)"
        ),
        "injections": inj_count,
        "detections": det_count,
        "matched_to_gt": total_tp,
        "overall_precision": overall["precision"],
        "overall_recall": overall["recall"],
        "overall_f1": overall["f1"],
        "by_type": by_type,
    }


def annotate_detection_labels(session: Session) -> int:
    """Post-evaluation annotation: attach GT labels to matched detections.

    Called only AFTER blind exception_evaluation so labels never influence
    matching. Returns number of records annotated.
    """
    annotated = 0
    for issue in IssueType:
        gt_keys = _gt_key_sets(session, issue.value)
        if issue == IssueType.duplicate_creates_duplicate_opportunity.value:
            det_rows = session.scalars(
                select(ExceptionRecord).where(ExceptionRecord.issue_type == issue.value)
            ).all()
            for rec in det_rows:
                if rec.related_lead_id is not None and int(rec.related_lead_id) in gt_keys:
                    rec.ground_truth_label = f"gt:{issue.value}"
                    annotated += 1
        else:
            det_rows = session.scalars(
                select(ExceptionRecord).where(ExceptionRecord.issue_type == issue.value)
            ).all()
            for rec in det_rows:
                if int(rec.affected_record_id) in gt_keys:
                    rec.ground_truth_label = f"gt:{issue.value}"
                    annotated += 1
    session.commit()
    return annotated
