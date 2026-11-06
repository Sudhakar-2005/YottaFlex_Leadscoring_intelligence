"""Two-run reproducibility check (V3.2: full five-way comparison).

Generates the same scale twice from scratch, exports both, and compares:
  1. row counts              (dataset_manifest counts per table)
  2. file counts             (checksums.json file entries)
  3. checksums               (sha256 per file + per table)
  4. referential integrity   (PRAGMA foreign_key_check on each generated DB)
  5. validation reports      (validation_summary.json + engine validation)

Exits non-zero on any mismatch. Nothing is pushed or published.

Usage:
    python scripts/compare_reproducibility.py --scale starter
    python scripts/compare_reproducibility.py --scale full
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from yottaflex.db.schema import init_db  # noqa: E402
from yottaflex.engines.exporter import export_all  # noqa: E402
from yottaflex.pipeline import run_full_pipeline  # noqa: E402

from generate_data import build_settings  # noqa: E402


def _fk_check(db_path: Path) -> list:
    con = sqlite3.connect(str(db_path))
    try:
        return con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()


def _generate_and_export(scale: str, seed: int, workdir: Path) -> dict:
    db_path = workdir / "yottaflex.db"
    url = f"sqlite:///{db_path.as_posix()}"
    settings = build_settings(scale, seed, url)
    result = run_full_pipeline(
        settings=settings, database_url=url, inject_anomalies=True, write_reports=False
    )

    engine = create_engine(url)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    out_dir = workdir / "exports"
    with factory() as session:
        export_all(
            session,
            settings,
            out_dir,
            validation_report=result.steps.get("validation"),
            pipeline_steps=result.steps,
        )
    engine.dispose()

    fk_violations = _fk_check(db_path)
    checksums = json.loads((out_dir / "checksums.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((out_dir / "validation_summary.json").read_text(encoding="utf-8"))
    return {
        "checksums": checksums,
        "manifest": manifest,
        "validation": validation,
        "validation_passed": bool(result.steps.get("validation", {}).get("passed")),
        "fk_violations": len(fk_violations),
        "file_count": len(checksums["files"]),
        "row_counts": manifest["counts"],
        "total_rows": sum(manifest["counts"].values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=["starter", "full"], default="starter")
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        d1, d2 = Path(tmp) / "run1", Path(tmp) / "run2"
        d1.mkdir()
        d2.mkdir()
        print(f"[run 1/2] scale={args.scale} seed={args.seed}")
        a = _generate_and_export(args.scale, args.seed, d1)
        print(f"[run 2/2] scale={args.scale} seed={args.seed}")
        b = _generate_and_export(args.scale, args.seed, d2)

        results: list[tuple[str, bool, str]] = []

        # 1) row counts (per table)
        rc_ok = a["row_counts"] == b["row_counts"]
        results.append(
            ("row counts", rc_ok, f"total_rows={a['total_rows']} vs {b['total_rows']}, "
             f"tables={len(a['row_counts'])}")
        )

        # 2) file counts
        fc_ok = a["file_count"] == b["file_count"]
        results.append(("file counts", fc_ok, f"{a['file_count']} vs {b['file_count']}"))

        # 3) checksums (per file + per table)
        files_ok = a["checksums"]["files"] == b["checksums"]["files"]
        tables_ok = a["checksums"]["tables"] == b["checksums"]["tables"]
        diff_files = [
            n for n in sorted(set(a["checksums"]["files"]) | set(b["checksums"]["files"]))
            if a["checksums"]["files"].get(n) != b["checksums"]["files"].get(n)
        ]
        results.append(
            ("checksums (files)", files_ok, f"{len(a['checksums']['files'])} files; diffs={diff_files or 'none'}")
        )
        results.append(
            ("checksums (tables)", tables_ok, f"{len(a['checksums']['tables'])} tables")
        )

        # 4) referential integrity in BOTH generated databases
        fk_ok = a["fk_violations"] == 0 and b["fk_violations"] == 0
        results.append(
            ("referential integrity", fk_ok, f"violations run1={a['fk_violations']} run2={b['fk_violations']}")
        )

        # 5) validation reports (engine checks + manifest-driven checks)
        val_ok = a["validation"] == b["validation"]
        passed_ok = a["validation_passed"] and b["validation_passed"]
        results.append(
            ("validation reports identical", val_ok, "byte-identical JSON" if val_ok else "DIFFER")
        )
        results.append(
            ("validation passed (both runs)", passed_ok,
             f"run1={a['validation_passed']} run2={b['validation_passed']}")
        )

        print(f"\nscale={args.scale} seed={args.seed} - comparison results:")
        all_ok = True
        for name, ok, detail in results:
            status = "PASS" if ok else "FAIL"
            all_ok = all_ok and ok
            print(f"  [{status}] {name}: {detail}")

        if all_ok:
            print("\nREPRODUCIBILITY: PASS")
            return 0
        print("\nREPRODUCIBILITY: FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
