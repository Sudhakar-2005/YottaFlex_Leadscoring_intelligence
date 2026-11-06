"""Restore YottaFlex SQL exports into a SQLite database (V3.2.1 atomic restore).

Safety contract:
  - Never silently deletes an existing database target — requires --force.
  - Restores into a TEMPORARY database file first (same directory as the target,
    so the final replacement is an atomic os.replace on one volume).
  - Verifies schema (all expected tables + exact column sets), enables foreign
    keys, runs PRAGMA foreign_key_check, and compares row counts before the
    target is touched.
  - The target database is REPLACED only after every check passes; on any
    failure the original target is preserved unchanged and the temp file is
    removed.
  - Fails safely with explicit exit codes instead of partial "success".

Exit codes:
  0 = restoration verified PASS (target replaced atomically)
  1 = restoration/verification FAILED (target preserved, temp cleaned)
  2 = missing inputs (SQL files / bad paths)
  3 = target exists and --force was not given (refused, nothing modified)

Usage:
    python scripts/restore_sql_export.py --db data/restored.db
    python scripts/restore_sql_export.py --db data/restored.db --force
    python scripts/restore_sql_export.py --src data/exports/sql --db /tmp/check.db --source-db data/yottaflex.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from yottaflex.engines.exporter import EXPORT_ORDER  # noqa: E402

SQL_FILES = [
    "00_schema.sql",
    "01_master_data.sql",
    "02_lead_data.sql",
    "03_activity_data.sql",
    "04_workflow_data.sql",
    "05_opportunity_data.sql",
    "06_ground_truth.sql",
]


def restore_sql_dir(sql_dir: Path, tmp_db: Path) -> sqlite3.Connection:
    """Load all SQL split files into a freshly created TEMP database file.

    The caller owns cleanup of ``tmp_db``; the real target is never touched here.
    On load failure the connection is closed before the error propagates so the
    temp file handle is released (required for cleanup on Windows).
    """
    if tmp_db.exists():
        tmp_db.unlink()
    con = sqlite3.connect(str(tmp_db))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        for name in SQL_FILES:
            script = (sql_dir / name).read_text(encoding="utf-8")
            con.executescript(script)
        con.commit()
    except BaseException:
        con.close()
        raise
    return con


def table_counts(con: sqlite3.Connection) -> dict[str, int]:
    names = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    return {n: int(con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]) for n in names}


def verify_schema(con: sqlite3.Connection, log=print) -> bool:
    """Verify all expected tables exist with exactly the expected column sets."""
    import yottaflex.db.models  # noqa: F401  (populate metadata)
    from yottaflex.db.base import Base

    ok = True
    present = {
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing = [t for t in EXPORT_ORDER if t not in present]
    if missing:
        ok = False
        log(f"FAIL: missing tables after restore: {missing}")

    mismatches = []
    for table in EXPORT_ORDER:
        if table not in present:
            continue
        expected_cols = [c.name for c in Base.metadata.tables[table].columns]
        got_cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]
        if expected_cols != got_cols:
            mismatches.append(
                f"{table}: expected {len(expected_cols)} cols, got {len(got_cols)}"
            )
    if mismatches:
        ok = False
        log(f"FAIL: schema column mismatches: {mismatches[:10]}")
    if ok:
        log(f"OK: schema verified ({len(EXPORT_ORDER)} tables, column sets match)")
    return ok


def load_manifest_counts(sql_dir: Path) -> dict[str, int] | None:
    """Read expected per-table row counts from dataset_manifest.json (V3.2.2).

    The manifest sits next to the sql/ directory in the exports folder. When
    present, it is the authoritative expectation set that catches incomplete or
    truncated exports (including FK-neutral truncations the other checks miss).
    """
    manifest_path = sql_dir.parent / "dataset_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    counts = data.get("counts")
    if isinstance(counts, dict) and counts:
        return {str(k): int(v) for k, v in counts.items()}
    return None


def verify_restoration(
    con: sqlite3.Connection,
    source_db: Path | None,
    manifest_counts: dict[str, int] | None = None,
    log=print,
) -> bool:
    """Full integrity verification. Returns True only if everything passes."""
    ok = True

    # 1) schema + all expected tables
    if not verify_schema(con, log=log):
        ok = False

    counts = table_counts(con)

    # 2) manifest row counts (V3.2.2): every expected table, exact counts
    if manifest_counts:
        missing = [t for t in manifest_counts if t not in counts]
        mismatches = [
            f"{t}: manifest expects {expected}, got {counts.get(t, 'missing')}"
            for t, expected in manifest_counts.items()
            if t in counts and counts[t] != expected
        ]
        if missing:
            ok = False
            log(f"FAIL: tables present in manifest but missing after restore: {missing}")
        if mismatches:
            ok = False
            log(f"FAIL: {len(mismatches)} manifest row-count mismatches")
            for m in mismatches[:20]:
                log(f"  {m}")
        if not missing and not mismatches:
            log(f"OK: row counts match dataset_manifest.json for all {len(manifest_counts)} tables")
    else:
        log("NOTE: dataset_manifest.json unavailable — manifest verification skipped")

    # 3) foreign keys enforced + integrity check
    con.execute("PRAGMA foreign_keys=ON")
    fk_enabled = con.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_enabled != 1:
        ok = False
        log("FAIL: could not enable PRAGMA foreign_keys")
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        ok = False
        log(f"FAIL: {len(violations)} foreign key violations")
        for v in violations[:10]:
            log(f"  violation: {v}")
    else:
        log("OK: PRAGMA foreign_key_check clean")

    # 4) row counts vs source database (when available)
    if source_db is not None and source_db.exists():
        src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
        mismatches = []
        for table in EXPORT_ORDER:
            if table not in counts:
                mismatches.append(f"{table}: missing in restored db")
                continue
            expected = int(src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            if expected != counts[table]:
                mismatches.append(f"{table}: expected {expected}, got {counts[table]}")
        src.close()
        if mismatches:
            ok = False
            log(f"FAIL: {len(mismatches)} row-count mismatches")
            for m in mismatches[:20]:
                log(f"  {m}")
        else:
            log("OK: row counts match source for all tables")
    else:
        log("NOTE: source database unavailable — count comparison skipped")

    # 5) completeness: restored row total must be > 0; core baseline tables
    #    must be non-empty (GT/exception/opportunity tables may legitimately
    #    be empty depending on which pipeline stages produced the export)
    CORE_NON_EMPTY = {
        "territory", "product", "score_rule", "salesrep",
        "campaign", "company", "contact", "lead", "consent", "activity",
        "lead_status_history",
    }
    total = sum(counts.values())
    empty = [t for t in CORE_NON_EMPTY if counts.get(t, 0) == 0]
    if total == 0:
        ok = False
        log("FAIL: restored database is empty")
    if empty:
        ok = False
        log(f"FAIL: expected non-empty core tables are empty: {sorted(empty)}")
    log(f"OK: {total} rows restored across {len(counts)} tables")

    return ok


def atomic_restore(
    sql_dir: Path,
    target_db: Path,
    source_db: Path | None,
    force: bool,
    log=print,
) -> int:
    """Atomic restore flow. Returns the process exit code (0/1/2/3)."""
    # input checks
    if not (sql_dir / "00_schema.sql").exists():
        log(f"ERROR: SQL exports not found under {sql_dir} (expected 00_schema.sql)")
        return 2
    missing_files = [f for f in SQL_FILES if not (sql_dir / f).exists()]
    if missing_files:
        log(f"ERROR: incomplete export set — missing: {missing_files}")
        log("Refusing to start a partial restore.")
        return 2

    # overwrite permission
    if target_db.exists() and not force:
        size_mb = target_db.stat().st_size / 1024 / 1024
        log(
            f"REFUSED: target database already exists ({target_db}, {size_mb:.1f} MB).\n"
            "Refusing to overwrite without explicit permission.\n"
            "Re-run with --force to allow overwrite, or choose a different --db path."
        )
        return 3

    target_db.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = target_db.parent / f"{target_db.name}.tmp-restore.{os.getpid()}.db"

    con: sqlite3.Connection | None = None
    try:
        log(f"restoring {len(SQL_FILES)} files from {sql_dir} into temp database {tmp_db}")
        try:
            con = restore_sql_dir(sql_dir, tmp_db)
        except sqlite3.Error as exc:
            log(f"FAIL: SQL load error: {exc}")
            log("NOT replacing target: original preserved.")
            return 1

        source = source_db if (source_db is not None and source_db.exists()) else None
        manifest_counts = load_manifest_counts(sql_dir)
        ok = verify_restoration(con, source, manifest_counts=manifest_counts, log=log)
        con.close()
        con = None

        if not ok:
            log("NOT replacing target: verification failed, original preserved.")
            return 1

        # all checks passed — atomically replace the target (same volume)
        try:
            os.replace(tmp_db, target_db)
        except OSError as exc:
            log(f"FAIL: could not replace target ({exc}); original preserved.")
            return 1
        log(f"OK: target database replaced atomically: {target_db}")
        log("RESTORATION: PASS")
        return 0
    finally:
        if con is not None:
            con.close()
        if tmp_db.exists():
            try:
                tmp_db.unlink()
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=PROJECT_ROOT / "data" / "exports" / "sql")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "restored.db")
    parser.add_argument("--source-db", type=Path, default=PROJECT_ROOT / "data" / "yottaflex.db")
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow replacing an existing target database (required if it exists)",
    )
    args = parser.parse_args()

    code = atomic_restore(args.src, args.db, args.source_db, args.force)
    if code == 1:
        print("RESTORATION: FAIL")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
