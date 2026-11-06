from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tmp_leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.glob("*.tmp-restore.*"))


def _make_marker_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE audit_marker (value INTEGER)")
    con.execute("INSERT INTO audit_marker VALUES (42)")
    con.commit()
    con.close()


def _build_small_exports(tmp_path: Path, settings):
    """Create a small but complete SQL export set + source DB for restore tests."""
    from sqlalchemy import select

    from yottaflex.db.models import Lead
    from yottaflex.db.schema import init_db, open_session
    from yottaflex.db.session import make_engine
    from yottaflex.engines.assignment import assign_leads
    from yottaflex.engines.data_generator import generate_all
    from yottaflex.engines.deduplication import run_deduplication
    from yottaflex.engines.exporter import export_all
    from yottaflex.engines.opportunity import (
        advance_opportunities_realistic,
        convert_qualified_leads,
    )
    from yottaflex.engines.scoring import score_all_leads
    from yottaflex.engines.task_management import create_followup_tasks

    src_db = tmp_path / "src.db"
    url = f"sqlite:///{src_db.as_posix()}"
    engine = make_engine(url, settings)
    init_db(engine)
    with open_session(engine) as session:
        generate_all(session, settings)
        run_deduplication(session)
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
        exports = tmp_path / "exports"
        export_all(session, settings, exports)
    engine.dispose()
    return src_db, exports / "sql"


def _run_restore(sql_dir: Path, target: Path, source_db: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "restore_sql_export.py"),
            "--src", str(sql_dir),
            "--db", str(target),
            "--source-db", str(source_db),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


def test_restore_refuses_to_overwrite_without_force(tmp_path, mini_settings):
    """V3.2.1: an existing target database is never silently deleted."""
    src_db, sql_dir = _build_small_exports(tmp_path, mini_settings)
    target = tmp_path / "restored.db"

    r1 = _run_restore(sql_dir, target, src_db)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "RESTORATION: PASS" in r1.stdout
    assert "foreign_key_check clean" in r1.stdout
    assert "schema verified" in r1.stdout
    assert "replaced atomically" in r1.stdout
    assert _tmp_leftovers(tmp_path) == []
    digest_before = _sha256(target)

    r2 = _run_restore(sql_dir, target, src_db)
    assert r2.returncode == 3, r2.stdout
    assert "REFUSED" in r2.stdout
    assert _sha256(target) == digest_before  # untouched
    assert _tmp_leftovers(tmp_path) == []

    r3 = _run_restore(sql_dir, target, src_db, "--force")
    assert r3.returncode == 0, r3.stdout
    assert "RESTORATION: PASS" in r3.stdout
    assert _tmp_leftovers(tmp_path) == []


def test_failed_restoration_preserves_existing_target(tmp_path, mini_settings):
    """V3.2.1 regression: a failed restore must NOT touch an existing target."""
    src_db, sql_dir = _build_small_exports(tmp_path, mini_settings)

    # corrupt the export set so loading fails mid-way
    broken_dir = tmp_path / "broken_sql"
    broken_dir.mkdir()
    for f in sorted(sql_dir.glob("*.sql")):
        text = f.read_text(encoding="utf-8")
        if f.name == "03_activity_data.sql":
            text = "THIS IS NOT VALID SQL;\n"
        (broken_dir / f.name).write_text(text, encoding="utf-8")

    target = tmp_path / "existing.db"
    _make_marker_db(target)
    digest_before = _sha256(target)

    r = _run_restore(broken_dir, target, src_db, "--force")
    assert r.returncode == 1, r.stdout
    assert "RESTORATION: FAIL" in r.stdout
    assert "SQL load error" in r.stdout
    assert "original preserved" in r.stdout

    # target byte-identical and still the marker DB
    assert _sha256(target) == digest_before
    con = sqlite3.connect(str(target))
    marker = con.execute("SELECT value FROM audit_marker").fetchone()
    con.close()
    assert marker == (42,)
    assert _tmp_leftovers(tmp_path) == []


def test_successful_restore_replaces_target_atomically(tmp_path, mini_settings):
    """V3.2.1: with --force the target is replaced only after checks pass."""
    src_db, sql_dir = _build_small_exports(tmp_path, mini_settings)
    target = tmp_path / "existing.db"
    _make_marker_db(target)

    r = _run_restore(sql_dir, target, src_db, "--force")
    assert r.returncode == 0, r.stdout
    assert "replaced atomically" in r.stdout

    con = sqlite3.connect(str(target))
    tables = {
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "audit_marker" not in tables  # old content fully replaced
    leads = int(con.execute("SELECT COUNT(*) FROM lead").fetchone()[0])
    con.close()
    assert leads > 0
    assert _tmp_leftovers(tmp_path) == []


def test_restore_fails_on_incomplete_export_set(tmp_path, mini_settings):
    """V3.2.1: partial export sets fail safely before touching the target."""
    src_db, sql_dir = _build_small_exports(tmp_path, mini_settings)
    incomplete = tmp_path / "incomplete_sql"
    incomplete.mkdir()
    (incomplete / "00_schema.sql").write_text(
        (sql_dir / "00_schema.sql").read_text(encoding="utf-8"), encoding="utf-8"
    )
    target = tmp_path / "should_not_exist.db"
    r = _run_restore(incomplete, target, src_db)
    assert r.returncode == 2, r.stdout
    assert "incomplete export set" in r.stdout
    assert not target.exists()
    assert _tmp_leftovers(tmp_path) == []


def test_restore_reports_count_mismatch_as_failure(tmp_path, mini_settings):
    """V3.2.1: verification failure leaves NO target behind and exits 1."""
    src_db, sql_dir = _build_small_exports(tmp_path, mini_settings)

    # Craft a bogus source DB with wrong counts for a compared table
    wrong = tmp_path / "wrong_source.db"
    con = sqlite3.connect(str(wrong))
    src = sqlite3.connect(str(src_db))
    src.backup(con)
    src.close()
    con.execute("DELETE FROM lead WHERE lead_id > 5")
    con.commit()
    con.close()

    target = tmp_path / "restored2.db"
    r = _run_restore(sql_dir, target, wrong)
    assert r.returncode == 1, r.stdout
    assert "RESTORATION: FAIL" in r.stdout
    assert "row-count mismatches" in r.stdout
    assert "original preserved" in r.stdout
    # no partial target, no temp leftovers
    assert not target.exists()
    assert _tmp_leftovers(tmp_path) == []
