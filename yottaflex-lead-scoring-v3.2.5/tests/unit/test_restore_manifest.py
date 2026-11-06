"""V3.2.2 regression tests: restore verification against dataset_manifest.json.

Catches incomplete/truncated exports that older checks miss (FK-neutral
truncation of tables without dependents), while preserving the target DB on
failure.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import test_restore_safety as trs  # noqa: E402  (helper module in the same dir)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _truncate_activities(sql_dir: Path, keep_rows: int = 100) -> None:
    """Valid-syntax, FK-neutral truncation: keep only the first N activity rows."""
    act_sql = sql_dir / "03_activity_data.sql"
    text = act_sql.read_text(encoding="utf-8")
    before_values, marker, after_values = text.partition("VALUES\n")
    rows = after_values.split("),\n")
    reconstructed = "),\n".join(rows[:keep_rows]) + ")\n;"
    act_sql.write_text(before_values + marker + reconstructed + "\nCOMMIT;\n", encoding="utf-8")


def test_truncated_exports_rejected_via_manifest(tmp_path, mini_settings):
    """Manifest counts catch FK-neutral truncation; target stays preserved."""
    src_db, sql_dir = trs._build_small_exports(tmp_path, mini_settings)
    _truncate_activities(sql_dir)

    target = tmp_path / "existing.db"
    trs._make_marker_db(target)
    digest_before = _sha(target)

    r = trs._run_restore(sql_dir, target, tmp_path / "absent_source.db", "--force")
    assert r.returncode == 1, r.stdout
    assert "RESTORATION: FAIL" in r.stdout
    assert "manifest row-count mismatches" in r.stdout
    assert "original preserved" in r.stdout
    assert _sha(target) == digest_before
    con = sqlite3.connect(str(target))
    marker = con.execute("SELECT value FROM audit_marker").fetchone()
    con.close()
    assert marker == (42,)


def test_authentic_exports_pass_manifest_check(tmp_path, mini_settings):
    src_db, sql_dir = trs._build_small_exports(tmp_path, mini_settings)
    target = tmp_path / "restored.db"
    r = trs._run_restore(sql_dir, target, src_db)
    assert r.returncode == 0, r.stdout
    assert "row counts match dataset_manifest.json" in r.stdout
    assert "RESTORATION: PASS" in r.stdout
