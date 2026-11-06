"""V3.2.3 regression tests: pipeline export-overwrite protection and defaults.

Policy under test:
  - default export destination is data/generated/exports (never data/exports)
  - a starter/auxiliary run can never modify the committed full-scale exports
  - writing into an existing export set requires explicit overwrite permission
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from yottaflex.config import Settings
from yottaflex.pipeline import run_full_pipeline

PROJECT = Path(__file__).resolve().parents[2]
REPO_EXPORTS = PROJECT / "data" / "exports"
REPO_REPORTS = PROJECT / "data" / "reports"
GENERATED = PROJECT / "data" / "generated"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_default_run_writes_to_generated_dir_never_committed(tmp_path, mini_settings: Settings):
    """A run without export_dir writes to data/generated/exports; committed bytes intact."""
    committed_checksums = REPO_EXPORTS / "checksums.json"
    committed_reports = REPO_REPORTS / "pipeline_result.json"
    before_exports = _sha(committed_checksums)
    before_reports = _sha(committed_reports)

    try:
        run_full_pipeline(
            settings=mini_settings,
            database_url=f"sqlite:///{(tmp_path / 'run.db').as_posix()}",
            inject_anomalies=False,
            write_reports=True,  # no export_dir -> default generated dir
        )
        assert (GENERATED / "exports" / "checksums.json").exists()
        assert (GENERATED / "exports" / "sql" / "00_schema.sql").exists()
        assert (GENERATED / "reports" / "pipeline_result.json").exists()
    finally:
        shutil.rmtree(GENERATED, ignore_errors=True)

    # committed full-scale deliverables untouched, byte for byte
    assert _sha(committed_checksums) == before_exports
    assert _sha(committed_reports) == before_reports


def test_starter_run_with_overwrite_flag_still_never_touches_committed_exports(
    tmp_path, mini_settings: Settings
):
    """Even with overwrite permission, the default destination stays separate."""
    committed_checksums = REPO_EXPORTS / "checksums.json"
    before = _sha(committed_checksums)

    try:
        run_full_pipeline(
            settings=mini_settings,
            database_url=f"sqlite:///{(tmp_path / 'starter.db').as_posix()}",
            inject_anomalies=False,
            write_reports=True,
            overwrite_exports=True,  # permission alone must not redirect to data/exports
        )
        assert (GENERATED / "exports" / "checksums.json").exists()
    finally:
        shutil.rmtree(GENERATED, ignore_errors=True)

    assert _sha(committed_checksums) == before


def test_overwrite_requires_explicit_permission(tmp_path, mini_settings: Settings):
    """Second write into an existing export set requires overwrite_exports=True."""
    out = tmp_path / "exports_a"

    run_full_pipeline(
        settings=mini_settings,
        database_url=f"sqlite:///{(tmp_path / 'a.db').as_posix()}",
        inject_anomalies=False,
        write_reports=True,
        export_dir=out,
    )
    digest = _sha(out / "checksums.json")

    with pytest.raises(ValueError) as excinfo:
        run_full_pipeline(
            settings=mini_settings,
            database_url=f"sqlite:///{(tmp_path / 'b.db').as_posix()}",
            inject_anomalies=False,
            write_reports=True,
            export_dir=out,  # existing export set, no permission
        )
    assert "overwrite_exports" in str(excinfo.value)
    assert _sha(out / "checksums.json") == digest, "refusal must not modify the existing set"

    # explicit permission succeeds
    run_full_pipeline(
        settings=mini_settings,
        database_url=f"sqlite:///{(tmp_path / 'c.db').as_posix()}",
        inject_anomalies=False,
        write_reports=True,
        export_dir=out,
        overwrite_exports=True,
    )
    assert (out / "checksums.json").exists()


def test_explicit_committed_dir_requires_permission_and_preserves(tmp_path, mini_settings: Settings):
    """Pointing export_dir at data/exports without permission is refused, without writes."""
    before = _sha(REPO_EXPORTS / "checksums.json")
    with pytest.raises(ValueError) as excinfo:
        run_full_pipeline(
            settings=mini_settings,
            database_url=f"sqlite:///{(tmp_path / 'd.db').as_posix()}",
            inject_anomalies=False,
            write_reports=True,
            export_dir=REPO_EXPORTS,  # committed deliverables
        )
    assert "overwrite_exports" in str(excinfo.value)
    assert _sha(REPO_EXPORTS / "checksums.json") == before
