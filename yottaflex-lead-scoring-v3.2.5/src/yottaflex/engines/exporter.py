"""Complete data export engine (P0-C).

Writes, deterministically (same DB content ⇒ byte-identical output):
  - one CSV per table (business_id first; FK business_id companion columns)
  - ground_truth.json            (injections + exception GT + duplicate GT)
  - dataset_manifest.json        (seed, counts, targets, duplicate volumes)
  - validation_summary.json      (validation report + P0 checks)
  - checksums.json               (sha256 per exported file + per-table hash)
  - seed_data.sql                (CREATE TABLE + ordered INSERTs)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from yottaflex.config import Settings
from yottaflex.db.base import Base
from yottaflex.logging_setup import get_logger

log = get_logger("exporter")

# FK-safe export order covering every table in the metadata
EXPORT_ORDER: list[str] = [
    "territory",
    "product",
    "score_rule",
    "salesrep",
    "salesrep_territory",
    "salesrep_product",
    "campaign",
    "company",
    "contact",
    "lead",
    "lead_campaign",
    "lead_status_history",
    "consent",
    "activity",
    "task",
    "opportunity",
    "stage_history",
    "lead_score_explanation",
    "exception_record",
    "exception_resolution_history",
    "anomaly_injection_log",
    "ground_truth_exception",
    "duplicate_gt",
]

# SQL split files in dependency order (Phase 1 V3). Each file is self-contained:
# name -> table names (EXPORT_ORDER sublists preserve FK order).
SQL_SPLIT: dict[str, list[str]] = {
    "01_master_data": [
        "territory",
        "product",
        "score_rule",
        "salesrep",
        "salesrep_territory",
        "salesrep_product",
        "campaign",
        "company",
    ],
    "02_lead_data": ["contact", "lead", "lead_campaign", "lead_status_history", "consent"],
    "03_activity_data": ["activity", "task"],
    "04_workflow_data": ["stage_history", "lead_score_explanation"],
    "05_opportunity_data": ["opportunity"],
    "06_ground_truth": [
        "exception_record",
        "exception_resolution_history",
        "anomaly_injection_log",
        "ground_truth_exception",
        "duplicate_gt",
    ],
}


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (datetime, date)):
        value = value.isoformat()
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _bi_maps(session: Session) -> dict[str, dict[int, str]]:
    from yottaflex.db.models import Company, Contact, Lead, Opportunity

    maps: dict[str, dict[int, str]] = {}
    for label, model, pk in (
        ("company", Company, Company.company_id),
        ("contact", Contact, Contact.contact_id),
        ("lead", Lead, Lead.lead_id),
        ("opportunity", Opportunity, Opportunity.opportunity_id),
    ):
        maps[label] = {
            int(r[0]): str(r[1])
            for r in session.execute(select(pk, model.business_id)).all()
        }
    return maps


def _derived(table_name: str, row: dict[str, Any], maps: dict[str, dict[int, str]]) -> dict[str, Any]:
    """Companion business_id columns for FK references (exports/API parity)."""
    out: dict[str, Any] = {}

    def ref(entity: str, pk: Any) -> str | None:
        if pk is None:
            return None
        return maps.get(entity, {}).get(int(pk))

    if table_name == "contact":
        out["company_business_id"] = ref("company", row.get("company_id"))
    elif table_name == "lead":
        out["company_business_id"] = ref("company", row.get("company_id"))
        out["contact_business_id"] = ref("contact", row.get("contact_id"))
    elif table_name == "activity":
        out["lead_business_id"] = ref("lead", row.get("lead_id"))
        out["contact_business_id"] = ref("contact", row.get("contact_id"))
        out["company_business_id"] = ref("company", row.get("company_id"))
    elif table_name == "task":
        out["lead_business_id"] = ref("lead", row.get("lead_id"))
    elif table_name == "opportunity":
        out["lead_business_id"] = ref("lead", row.get("lead_id"))
        out["company_business_id"] = ref("company", row.get("company_id"))
        out["contact_business_id"] = ref("contact", row.get("contact_id"))
    elif table_name == "stage_history":
        out["opportunity_business_id"] = ref("opportunity", row.get("opportunity_id"))
    elif table_name == "lead_score_explanation":
        out["lead_business_id"] = ref("lead", row.get("lead_id"))
    elif table_name == "lead_campaign":
        out["lead_business_id"] = ref("lead", row.get("lead_id"))
    elif table_name == "lead_status_history":
        out["lead_business_id"] = ref("lead", row.get("lead_id"))
    elif table_name == "consent":
        subject_type = row.get("subject_type")
        subject_id = row.get("subject_id")
        entity = {"lead": "lead", "contact": "contact"}.get(str(subject_type))
        out["subject_business_id"] = ref(entity, subject_id) if entity else None
    elif table_name in ("anomaly_injection_log", "ground_truth_exception"):
        entity = str(row.get("affected_entity") or row.get("target_entity") or "")
        record_id = row.get("affected_record_id")
        if record_id is None:
            record_id = row.get("target_record_id")
        out["affected_business_id"] = ref(entity, record_id)
        lead_bid = ref("lead", row.get("related_lead_id"))
        out["related_lead_business_id"] = lead_bid
    elif table_name == "exception_record":
        entity = str(row.get("affected_entity") or "")
        out["affected_business_id"] = ref(entity, row.get("affected_record_id"))
        out["related_lead_business_id"] = ref("lead", row.get("related_lead_id"))
    return out


def _table_rows(session: Session, table_name: str, maps: dict[str, dict[int, str]]) -> list[dict[str, Any]]:
    table = Base.metadata.tables[table_name]
    pk_col = list(table.primary_key.columns)[0]
    rows = session.execute(select(table).order_by(pk_col)).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r._mapping)
        d.update(_derived(table_name, d, maps))
        out.append(d)
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    if not rows:
        # still write header-less empty file deterministically
        path.write_text("", encoding="utf-8", newline="\n")
        return ""
    # stable column order: business_id first, then original order, then derived
    cols = list(rows[0].keys())
    if "business_id" in cols:
        cols = ["business_id"] + [c for c in cols if c != "business_id"]
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(row.get(k)) for k in cols})
    text = buf.getvalue()
    path.write_text(text, encoding="utf-8", newline="\n")
    return text


def _real_columns(table_name: str) -> list[str]:
    """Actual schema columns (derived business_id companions are CSV-only)."""
    table = Base.metadata.tables[table_name]
    return [c.name for c in table.columns]


def _schema_ddl() -> str:
    """Full schema DDL via CreateTable/CreateIndex with dependency ordering."""
    dialect = sqlite.dialect()
    parts: list[str] = [
        "-- YottaFlex 00_schema.sql (V3 Phase 1) — CREATE TABLE + CREATE INDEX\n",
        "-- Restores schema into an empty SQLite database; data follows in 01..06.\n",
        "PRAGMA foreign_keys=OFF;\n",
        "BEGIN TRANSACTION;\n",
    ]
    # Tables first (EXPORT_ORDER is FK-safe), then indexes (sorted for determinism)
    for table_name in EXPORT_ORDER:
        table = Base.metadata.tables[table_name]
        ddl = str(CreateTable(table).compile(dialect=dialect))
        parts.append(f"\nDROP TABLE IF EXISTS {table_name};\n")
        parts.append(ddl.rstrip() + ";\n")
    indexes: list[tuple[str, Any]] = []
    for table_name in EXPORT_ORDER:
        table = Base.metadata.tables[table_name]
        indexes.extend((idx.name or "", idx) for idx in table.indexes)
    for name, idx in sorted(indexes, key=lambda t: t[0]):
        parts.append(f"\n{str(CreateIndex(idx).compile(dialect=dialect)).rstrip()};\n")
    parts.append("\nCOMMIT;\n")
    return "".join(parts)


def _sql_data_text(header: str, table_rows: dict[str, list[dict[str, Any]]], tables: list[str]) -> str:
    """INSERT statements for the given tables using real schema columns only."""
    parts: list[str] = [
        header + "\n",
        "PRAGMA foreign_keys=OFF;\n",
        "BEGIN TRANSACTION;\n",
    ]
    batch_size = 500
    for table_name in tables:
        rows = table_rows.get(table_name, [])
        if not rows:
            continue
        cols = _real_columns(table_name)
        col_list = ", ".join(f'"{c}"' for c in cols)
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            values = [
                "(" + ", ".join(_sql_value(r.get(c)) for c in cols) + ")" for r in batch
            ]
            parts.append(
                f"\nINSERT INTO {table_name} ({col_list}) VALUES\n"
                + ",\n".join(values)
                + ";\n"
            )
    parts.append("\nCOMMIT;\n")
    return "".join(parts)


def write_sql_splits(
    out_dir: Path,
    table_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, str]:
    """Write data/exports/sql/00_schema.sql .. 06_*.sql. Returns relpath -> sha256."""
    sql_dir = out_dir / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}

    schema_text = _schema_ddl()
    (sql_dir / "00_schema.sql").write_text(schema_text, encoding="utf-8", newline="\n")
    files["sql/00_schema.sql"] = _sha256_text(schema_text)

    for name, tables in SQL_SPLIT.items():
        header = f"-- YottaFlex {name}.sql (V3 Phase 1) — tables: {', '.join(tables)}"
        text = _sql_data_text(header, table_rows, tables)
        (sql_dir / f"{name}.sql").write_text(text, encoding="utf-8", newline="\n")
        files[f"sql/{name}.sql"] = _sha256_text(text)
    return files


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def export_all(
    session: Session,
    settings: Settings,
    out_dir: Path | str,
    validation_report: dict[str, Any] | None = None,
    pipeline_steps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export every table + GT/manifest/validation/checksums/seed SQL."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    maps = _bi_maps(session)
    table_rows: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, str] = {}  # filename -> sha256
    table_hashes: dict[str, str] = {}

    for table_name in EXPORT_ORDER:
        rows = _table_rows(session, table_name, maps)
        table_rows[table_name] = rows
        text = _write_csv(out / f"{table_name}.csv", rows)
        digest = _sha256_text(text)
        files[f"{table_name}.csv"] = digest
        table_hashes[table_name] = digest

    # ground_truth.json
    from yottaflex.db.models import (
        AnomalyInjectionLog,
        DuplicateGroundTruth,
        GroundTruthException,
    )

    inj_rows = session.execute(
        select(AnomalyInjectionLog).order_by(AnomalyInjectionLog.injection_id)
    ).scalars().all()
    gt_rows = session.execute(
        select(GroundTruthException).order_by(GroundTruthException.exception_gt_id)
    ).scalars().all()
    dup_rows = session.execute(
        select(DuplicateGroundTruth).order_by(DuplicateGroundTruth.duplicate_gt_id)
    ).scalars().all()

    def _entity_bi(entity: str, record_id: Any) -> str | None:
        if record_id is None:
            return None
        return maps.get(str(entity), {}).get(int(record_id))

    ground_truth = {
        "anomaly_injections": [
            {
                "injection_id": r.injection_id,
                "issue_type": r.issue_type,
                "target_entity": r.target_entity,
                "target_record_id": r.target_record_id,
                "target_business_id": _entity_bi(r.target_entity, r.target_record_id),
                "related_lead_id": r.related_lead_id,
                "related_lead_business_id": _entity_bi("lead", r.related_lead_id),
                "gt_label": r.gt_label,
                "injected_at": r.injected_at.isoformat(),
            }
            for r in inj_rows
        ],
        "ground_truth_exceptions": [
            {
                "exception_gt_id": r.exception_gt_id,
                "issue_type": r.issue_type,
                "affected_entity": r.affected_entity,
                "affected_record_id": r.affected_record_id,
                "affected_business_id": _entity_bi(r.affected_entity, r.affected_record_id),
                "related_lead_id": r.related_lead_id,
                "expected_behavior": r.expected_behavior,
                "actual_behavior": r.actual_behavior,
                "severity": r.severity,
                "injected_at": r.injected_at.isoformat(),
            }
            for r in gt_rows
        ],
        "duplicate_ground_truth": [
            {
                "duplicate_gt_id": r.duplicate_gt_id,
                "entity": r.entity,
                "primary_record_id": r.primary_record_id,
                "duplicate_record_id": r.duplicate_record_id,
                "primary_business_id": r.primary_business_id,
                "duplicate_business_id": r.duplicate_business_id,
                "match_key": r.match_key,
                "match_value": r.match_value,
                "origin": r.origin,
                "detected": r.detected,
            }
            for r in dup_rows
        ],
    }
    gt_text = json.dumps(ground_truth, indent=2, sort_keys=True, default=str) + "\n"
    (out / "ground_truth.json").write_text(gt_text, encoding="utf-8", newline="\n")
    files["ground_truth.json"] = _sha256_text(gt_text)

    # dataset_manifest.json
    counts: dict[str, int] = {}
    for table_name in EXPORT_ORDER:
        counts[table_name] = len(table_rows[table_name])
    manifest = {
        "seed": settings.seed,
        "base_datetime": settings.base_datetime,
        "business_id_year": settings.business_id_year,
        "counts": counts,
        "targets": {
            "companies": settings.counts.companies,
            "contacts": settings.counts.contacts,
            "leads": settings.counts.leads,
            "opportunities": settings.counts.opportunities,
        },
        "natural_duplicates": {
            "companies": settings.duplicates.natural_duplicate_companies,
            "contacts": settings.duplicates.natural_duplicate_contacts,
            "leads": settings.duplicates.natural_duplicate_leads,
            "opportunities": settings.duplicates.natural_duplicate_opportunities,
        },
        "heldout_fraction": settings.evaluation.heldout_fraction,
        "business_id_formats": {
            "company": "CO-000001",
            "contact": "CON-000001",
            "lead": "LEAD-2026-000001",
            "activity": "ACT-LEAD-2026-000001-001",
            "opportunity": "OPP-2026-000001",
            "task": "TASK-LEAD-2026-000001-001",
        },
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
    (out / "dataset_manifest.json").write_text(manifest_text, encoding="utf-8", newline="\n")
    files["dataset_manifest.json"] = _sha256_text(manifest_text)

    # validation_summary.json
    validation = {
        "validation_report": validation_report or {},
        "pipeline_steps": pipeline_steps or {},
        "checks": {
            "opportunity_count_exact": counts.get("opportunity")
            == settings.counts.opportunities,
            "company_count_exact": counts.get("company") == settings.counts.companies,
            "contact_count_exact": counts.get("contact") == settings.counts.contacts,
            "lead_count_exact": counts.get("lead") == settings.counts.leads,
        },
    }
    val_text = json.dumps(validation, indent=2, sort_keys=True, default=str) + "\n"
    (out / "validation_summary.json").write_text(val_text, encoding="utf-8", newline="\n")
    files["validation_summary.json"] = _sha256_text(val_text)

    # SQL splits (V3 Phase 1): schema + 6 data files for empty-DB restoration
    sql_files = write_sql_splits(out, table_rows)
    files.update(sql_files)

    # checksums.json (over all export files)
    checksums = {
        "algorithm": "sha256",
        "files": dict(sorted(files.items())),
        "tables": dict(sorted(table_hashes.items())),
    }
    (out / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    log.info("exported %d files to %s", len(files) + 1, out)
    return {
        "out_dir": str(out),
        "files": dict(sorted(files.items())),
        "tables": dict(sorted(table_hashes.items())),
    }
