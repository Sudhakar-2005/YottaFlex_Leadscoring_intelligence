from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy import func, select

from yottaflex.config import Settings
from yottaflex.db.models import (
    Activity,
    Company,
    Contact,
    Lead,
    Opportunity,
    StageHistory,
)
from yottaflex.engines.exporter import export_all


def _prepare_full(session, settings: Settings):
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.opportunity import advance_opportunities_realistic, convert_qualified_leads
    from yottaflex.engines.scoring import score_all_leads
    from yottaflex.engines.task_management import create_followup_tasks

    score_all_leads(session, settings)
    assign_leads(session, settings)
    for lead in session.scalars(
        select(Lead).where(
            Lead.assigned_salesrep_id.is_not(None),
            Lead.lead_category.in_(["hot", "warm"]),
        )
    ).all():
        lead.status = "qualified"
    session.commit()
    convert_qualified_leads(session, settings, target_count=10)
    advance_opportunities_realistic(session, settings)
    create_followup_tasks(session, settings)


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_export_all_tables_and_files(generated_session, mini_settings: Settings, tmp_path):
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    result = export_all(
        generated_session, mini_settings, out,
        validation_report={"passed": True}, pipeline_steps={},
    )
    files = result["files"]
    # every table has a CSV
    for table in [
        "territory", "product", "company", "contact", "lead",
        "activity", "task", "opportunity", "stage_history", "consent",
        "duplicate_gt", "exception_record", "anomaly_injection_log",
        "ground_truth_exception",
    ]:
        assert f"{table}.csv" in files
        assert (out / f"{table}.csv").exists()
    for name in ["ground_truth.json", "dataset_manifest.json", "validation_summary.json", "checksums.json"]:
        assert (out / name).exists()
    for name in [
        "00_schema.sql",
        "01_master_data.sql",
        "02_lead_data.sql",
        "03_activity_data.sql",
        "04_workflow_data.sql",
        "05_opportunity_data.sql",
        "06_ground_truth.sql",
    ]:
        assert (out / "sql" / name).exists()


def test_export_row_counts_and_business_ids(generated_session, mini_settings: Settings, tmp_path):
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)

    companies = _read_csv(out / "company.csv")
    assert len(companies) == mini_settings.counts.companies
    assert companies[0]["business_id"] == "CO-000001"

    leads = _read_csv(out / "lead.csv")
    assert len(leads) == mini_settings.counts.leads
    assert leads[0]["business_id"] == "LEAD-2026-000001"

    opps = _read_csv(out / "opportunity.csv")
    assert len(opps) == 10
    assert opps[0]["business_id"] == "OPP-2026-000001"
    # FK business ids present and consistent
    lead_bids = {r["business_id"] for r in leads}
    for o in opps:
        assert o["lead_business_id"] in lead_bids

    activities = _read_csv(out / "activity.csv")
    n_activities = generated_session.scalar(select(func.count()).select_from(Activity)) or 0
    assert len(activities) == n_activities
    for a in activities[:3]:
        assert a["business_id"].startswith("ACT-LEAD-2026-")
        assert a["lead_business_id"].startswith("LEAD-2026-")


def test_export_checksums_deterministic(generated_session, mini_settings: Settings, tmp_path):
    _prepare_full(generated_session, mini_settings)
    out1 = tmp_path / "e1"
    out2 = tmp_path / "e2"
    r1 = export_all(generated_session, mini_settings, out1)
    r2 = export_all(generated_session, mini_settings, out2)
    assert r1["files"] == r2["files"]
    assert r1["tables"] == r2["tables"]
    c1 = json.loads((out1 / "checksums.json").read_text(encoding="utf-8"))
    c2 = json.loads((out2 / "checksums.json").read_text(encoding="utf-8"))
    assert c1 == c2


def test_export_ground_truth_json(generated_session, mini_settings: Settings, tmp_path):
    from yottaflex.engines import anomaly_injection

    _prepare_full(generated_session, mini_settings)
    anomaly_injection.inject_all_anomalies(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)

    gt = json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))
    assert "anomaly_injections" in gt
    assert "ground_truth_exceptions" in gt
    assert "duplicate_ground_truth" in gt
    assert len(gt["anomaly_injections"]) > 0
    assert len(gt["duplicate_ground_truth"]) > 0
    origins = {r["origin"] for r in gt["duplicate_ground_truth"]}
    assert origins == {"natural", "injected"}
    # business ids resolved for injected targets
    assert any(
        r.get("target_business_id") for r in gt["anomaly_injections"]
    )
    manifest = json.loads((out / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == mini_settings.seed
    assert manifest["business_id_year"] == 2026
    assert manifest["counts"]["lead"] == mini_settings.counts.leads


def test_seed_sql_contains_business_ids(generated_session, mini_settings: Settings, tmp_path):
    """V3 Phase 1: split SQL files carry schema + data with business IDs."""
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)

    schema = (out / "sql" / "00_schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE lead" in schema
    assert "CREATE INDEX" in schema
    assert "FOREIGN KEY" in schema

    lead_sql = (out / "sql" / "02_lead_data.sql").read_text(encoding="utf-8")
    assert "INSERT INTO lead" in lead_sql
    assert "LEAD-2026-000001" in lead_sql

    opp_sql = (out / "sql" / "05_opportunity_data.sql").read_text(encoding="utf-8")
    assert "INSERT INTO opportunity" in opp_sql
    assert "OPP-2026-000001" in opp_sql

    act_sql = (out / "sql" / "03_activity_data.sql").read_text(encoding="utf-8")
    assert "INSERT INTO activity" in act_sql

    assert "BEGIN TRANSACTION" in schema
    assert "COMMIT" in schema
