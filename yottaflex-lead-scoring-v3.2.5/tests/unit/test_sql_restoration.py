from __future__ import annotations

import sqlite3

from sqlalchemy import func, select

from yottaflex.db.models import (
    Activity,
    Company,
    Contact,
    Lead,
    Opportunity,
    Task,
)
from yottaflex.engines.exporter import EXPORT_ORDER, export_all, write_sql_splits


def _prepare_full(session, settings):
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


def _restore_from_sql_dir(sql_dir) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys=OFF")
    for name in sorted(sql_dir.glob("*.sql")):
        con.executescript(name.read_text(encoding="utf-8"))
    con.commit()
    return con


def test_sql_splits_written(generated_session, mini_settings, tmp_path):
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)

    for name in [
        "00_schema.sql",
        "01_master_data.sql",
        "02_lead_data.sql",
        "03_activity_data.sql",
        "04_workflow_data.sql",
        "05_opportunity_data.sql",
        "06_ground_truth.sql",
    ]:
        assert (out / "sql" / name).exists(), f"missing {name}"
        assert (out / "sql" / name).stat().st_size > 0


def test_schema_ddl_uses_createtable_and_indexes(generated_session, mini_settings, tmp_path):
    """Schema SQL must carry real CREATE TABLE with constraints + CREATE INDEX."""
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)
    schema = (out / "sql" / "00_schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE lead" in schema
    assert "FOREIGN KEY" in schema
    assert "CONSTRAINT" in schema
    assert "CREATE INDEX" in schema
    assert "business_id" in schema
    assert "DROP TABLE IF EXISTS lead" in schema
    # no derived-only columns leak into DDL column lists
    assert "company_business_id" not in schema.split("CREATE INDEX")[0]
    assert "subject_business_id" not in schema


def test_sql_inserts_use_only_real_columns(generated_session, mini_settings, tmp_path):
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)
    for sql_file in ["01_master_data.sql", "02_lead_data.sql", "06_ground_truth.sql"]:
        text = (out / "sql" / sql_file).read_text(encoding="utf-8")
        for forbidden in ["company_business_id", "lead_business_id", "subject_business_id",
                          "affected_business_id", "related_lead_business_id", "opportunity_business_id"]:
            assert forbidden not in text, f"{forbidden} leaked into {sql_file}"


def test_sql_restoration_into_empty_db(generated_session, mini_settings, tmp_path):
    """V3 Phase 1 mandatory test: empty DB ← SQL splits; counts + FKs verified."""
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)

    restored = _restore_from_sql_dir(out / "sql")

    # 1) row counts match source for every table
    def _expected_count(table_name: str) -> int:
        from yottaflex.db.base import Base

        t = Base.metadata.tables[table_name]
        return int(generated_session.execute(select(func.count()).select_from(t)).scalar() or 0)

    for table in EXPORT_ORDER:
        got = int(restored.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        assert got == _expected_count(table), f"{table}: restored {got} != {_expected_count(table)}"

    # 2) foreign keys valid
    violations = restored.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == []

    # 3) business IDs preserved
    src_bids = generated_session.execute(select(Lead.business_id).order_by(Lead.business_id).limit(1)).scalar()
    restored_bids = restored.execute("SELECT business_id FROM lead ORDER BY business_id LIMIT 1").fetchone()[0]
    assert src_bids == restored_bids


def test_sql_restoration_critical_relationships(generated_session, mini_settings, tmp_path):
    _prepare_full(generated_session, mini_settings)
    out = tmp_path / "exports"
    export_all(generated_session, mini_settings, out)
    restored = _restore_from_sql_dir(out / "sql")

    # converted lead -> opportunity resolution
    dangling = restored.execute(
        "SELECT COUNT(*) FROM lead l LEFT JOIN opportunity o "
        "ON o.opportunity_id = l.converted_opportunity_id "
        "WHERE l.converted_opportunity_id IS NOT NULL AND o.opportunity_id IS NULL"
    ).fetchone()[0]
    assert dangling == 0

    # activity -> lead resolution
    dangling_act = restored.execute(
        "SELECT COUNT(*) FROM activity a LEFT JOIN lead l ON l.lead_id = a.lead_id "
        "WHERE a.lead_id IS NOT NULL AND l.lead_id IS NULL"
    ).fetchone()[0]
    assert dangling_act == 0

    # consent typed FKs
    dangling_consent = restored.execute(
        "SELECT COUNT(*) FROM consent c LEFT JOIN lead l ON l.lead_id = c.lead_id "
        "WHERE c.subject_type='lead' AND l.lead_id IS NULL"
    ).fetchone()[0]
    assert dangling_consent == 0

    # company/contact volumes present
    assert restored.execute("SELECT COUNT(*) FROM company WHERE business_id LIKE 'CO-%'").fetchone()[0] > 0
    assert restored.execute("SELECT COUNT(*) FROM lead WHERE business_id LIKE 'LEAD-%'").fetchone()[0] > 0
