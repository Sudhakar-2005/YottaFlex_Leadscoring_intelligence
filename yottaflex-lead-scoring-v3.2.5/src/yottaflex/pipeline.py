from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from yottaflex.config import PROJECT_ROOT, Settings, load_settings
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_engine
from yottaflex.engines import anomaly_injection, analytics, assignment, consent
from yottaflex.engines.data_generator import generate_all
from yottaflex.engines.deduplication import run_deduplication
from yottaflex.engines.exceptions import run_exception_detection
from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
from yottaflex.engines.scoring import score_all_leads
from yottaflex.engines.task_management import create_followup_tasks
from yottaflex.engines.validation import validate_dataset
from yottaflex.logging_setup import get_logger, setup_logging

log = get_logger("pipeline")

REPORTS_DIR = PROJECT_ROOT / "data" / "reports"


@dataclass
class PipelineResult:
    steps: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)


def run_full_pipeline(
    settings: Settings | None = None,
    database_url: str | None = None,
    inject_anomalies: bool = True,
    write_reports: bool = True,
    export_dir: str | Path | None = None,
    overwrite_exports: bool = False,
) -> PipelineResult:
    """Orchestrate A→L baseline then optional anomaly injection + detection + analytics.

    Export policy (V3.2.3 — protects committed deliverables):
      - The default export destination is ``data/generated/exports`` — NEVER the
        committed ``data/exports``.
      - Writing into a directory that already contains an export set
        (``checksums.json`` present) requires explicit overwrite permission
        (``overwrite_exports=True``); otherwise a ValueError is raised BEFORE
        anything is written.
      - Reaching the committed full-scale exports therefore requires BOTH an
        explicit ``export_dir`` AND ``overwrite_exports=True``.
      - Reports mirror the export destination (default:
        ``data/generated/reports``).
    """
    setup_logging()
    settings = settings or load_settings()

    # Resolve the export destination up-front (fail fast, protect committed exports)
    resolved_export_dir: Path | None = None
    if write_reports:
        resolved_export_dir = (
            Path(export_dir)
            if export_dir is not None
            else PROJECT_ROOT / "data" / "generated" / "exports"
        )
        if (resolved_export_dir / "checksums.json").exists() and not overwrite_exports:
            raise ValueError(
                f"Refusing to overwrite an existing export set at {resolved_export_dir}. "
                "Pass overwrite_exports=True (API) / --overwrite-exports (CLI) to allow "
                "this destructive export operation. The committed full-scale deliverables "
                "in data/exports are protected by this check."
            )

    engine = make_engine(database_url, settings)
    init_db(engine)

    result = PipelineResult()

    with open_session(engine) as session:
        log.info("=== STEP A: data generation ===")
        gen = generate_all(session, settings)
        result.steps["generate"] = gen.manifest
        result.manifest = gen.manifest

        log.info("=== STEP B: validation ===")
        expected = {
            "company": settings.counts.companies,
            "contact": settings.counts.contacts,
            "lead": settings.counts.leads,
        }
        report = validate_dataset(session, expected=expected, settings=settings)
        result.steps["validation"] = report.to_dict()

        log.info("=== STEP B2: deduplication ===")
        dedup = run_deduplication(session)
        result.steps["deduplication"] = dedup.to_dict()

        log.info("=== STEP C: scoring ===")
        score_results = score_all_leads(session, settings)
        result.steps["scoring"] = {
            "scored": len(score_results),
            "avg_score": round(sum(r.lead_score for r in score_results) / len(score_results), 2)
            if score_results
            else 0,
        }

        log.info("=== STEP F/G: routing & assignment ===")
        assign_stats = assignment.assign_leads(session, settings)
        assign_cov = assignment.assignment_coverage(session, settings)
        result.steps["assignment"] = {**assign_stats, **assign_cov}

        log.info("=== STEP E/H: consent + follow-up tasks ===")
        # baseline tasks (consent gate applied inside)
        task_stats = create_followup_tasks(session, settings)
        consent_stats = consent.enforce_consent_on_tasks(session)
        result.steps["tasks"] = task_stats
        result.steps["consent_enforcement"] = consent_stats

        log.info("=== STEP I/J: opportunities & stage history ===")
        # Mark qualified: hot+warm that are assigned → qualified status for conversion pool
        from sqlalchemy import select

        from yottaflex.db.models import Lead, LeadStatus

        candidates = session.scalars(
            select(Lead).where(
                Lead.lead_category.in_(["hot", "warm"]),
                Lead.assigned_salesrep_id.is_not(None),
                Lead.is_duplicate_of.is_(None),
                Lead.status.not_in(
                    ["converted", "disqualified", "opted_out"]
                ),
            )
        ).all()
        qualified_at = settings.base_dt().replace(hour=15, minute=0, second=0, microsecond=0)
        from datetime import timedelta

        qualified_at = qualified_at + timedelta(days=62)
        for lead in candidates:
            if lead.status in (LeadStatus.assigned.value, LeadStatus.working.value, LeadStatus.scored.value):
                from yottaflex.engines.lead_status_history import append_status_change

                append_status_change(
                    session,
                    lead,
                    LeadStatus.qualified.value,
                    qualified_at,
                    reason="hot/warm assigned lead qualified for conversion pool",
                    actor_id="pipeline",
                )
        session.commit()

        # Final dataset must contain exactly settings.counts.opportunities rows:
        # baseline creates the remainder, injected EX-04 duplicates add the quota.
        dup_quota = (
            settings.anomaly_injection.quotas.duplicate_opportunity
            if (inject_anomalies and settings.anomaly_injection.enabled)
            else 0
        )
        baseline_opp_target = settings.counts.opportunities - dup_quota
        conv = convert_qualified_leads(session, settings, target_count=baseline_opp_target)
        advance = advance_opportunities_realistic(session, settings)
        result.steps["opportunities"] = {**conv, "advancement": advance}

        # Baseline exception detection (natural duplicates may raise EX-04;
        # injected anomaly types must be absent before injection)
        log.info("=== STEP K: baseline exception detection ===")
        baseline_ex = run_exception_detection(session)
        result.steps["baseline_exceptions"] = {
            "count": len(baseline_ex),
            "by_type": _count_by_type(baseline_ex),
        }

        # Analytics baseline
        result.steps["baseline_analytics"] = analytics.summary_metrics(session, settings)

        if inject_anomalies and settings.anomaly_injection.enabled:
            log.info("=== ANOMALY INJECTION ===")
            injected = anomaly_injection.inject_all_anomalies(session, settings)
            result.steps["injected"] = injected

            log.info("=== STEP K: post-injection exception detection ===")
            detected = run_exception_detection(session)
            result.steps["exceptions"] = {
                "count": len(detected),
                "by_type": _count_by_type(detected),
            }
            # Blind evaluation first (P0-5), then annotate labels for display
            evaluation = analytics.summary_metrics(session, settings)["exception_evaluation"]
            from yottaflex.engines.exceptions import annotate_detection_labels

            annotated = annotate_detection_labels(session)
            evaluation["labels_annotated_post_evaluation"] = annotated
            result.steps["exception_evaluation"] = evaluation

        log.info("=== STEP L: final analytics ===")
        result.steps["analytics"] = analytics.summary_metrics(session, settings)

    if write_reports and resolved_export_dir is not None:
        # P0-C: complete export engine (CSV/JSON/SQL + manifest/checksums)
        from yottaflex.engines.exporter import export_all

        with open_session(engine) as session:
            export_result = export_all(
                session,
                settings,
                resolved_export_dir,
                validation_report=result.steps.get("validation"),
                pipeline_steps=result.steps,
            )
        result.steps["export"] = export_result
        result.steps["export_dir"] = str(resolved_export_dir)
        log.info("exported %d files to %s", len(export_result.get("files", {})), resolved_export_dir)

        # Reports mirror the export destination (default: data/exports -> data/reports),
        # so custom export destinations never overwrite the committed reports either.
        reports_dir = resolved_export_dir.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        out = reports_dir / "pipeline_result.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result.steps, f, indent=2, default=str)
        log.info("wrote %s", out)

    return result


def _count_by_type(records) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        out[r.issue_type] = out.get(r.issue_type, 0) + 1
    return out


if __name__ == "__main__":
    run_full_pipeline()
