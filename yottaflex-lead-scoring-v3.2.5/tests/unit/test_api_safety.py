from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yottaflex.api.main import app
from yottaflex.config import canonical_sqlite_path, load_settings


def _live_url() -> str:
    return load_settings().resolved_database_url()


def _live_abs_posix() -> str:
    return Path(_live_url().removeprefix("sqlite:///")).as_posix()


def _equivalent_variants() -> dict[str, str]:
    """Path representations that all target the SAME live database file."""
    abs_posix = _live_abs_posix()
    return {
        "dot_segment": "sqlite:///data/./yottaflex.db",
        "parent_segment": "sqlite:///data/tmp/../yottaflex.db",
        "double_slash_mid": "sqlite:///data//yottaflex.db",
        "backslashes": "sqlite:///data\\yottaflex.db",
        "four_slash_absolute": "sqlite:////" + abs_posix.lstrip("/"),
        "case_variant": "sqlite:///" + abs_posix.upper(),
        "trailing_dot": "sqlite:///data/yottaflex.db.",
    }


def test_canonical_sqlite_path_normalizes_equivalents():
    """V3.2.2/V3.2.3: every equivalent representation canonicalizes to the live path."""
    live_canon = canonical_sqlite_path(_live_url())
    assert live_canon is not None
    for label, url in _equivalent_variants().items():
        canon = canonical_sqlite_path(url)
        assert canon == live_canon, f"{label} not canonicalized: {canon} != {live_canon}"


@pytest.mark.parametrize(
    "label", ["dot_segment", "parent_segment", "double_slash_mid", "backslashes",
              "four_slash_absolute", "case_variant", "trailing_dot"]
)
def test_equivalent_live_paths_refused_without_confirmation(label: str):
    """V3.2.2/V3.2.3 regression: path-equivalent live targets must require confirmation."""
    client = TestClient(app)
    url = _equivalent_variants()[label]
    r = client.post(
        "/api/v1/pipeline/run-all",
        json={"output_database_url": url, "write_reports": False},
    )
    assert r.status_code == 400, f"{label} bypassed the gate: HTTP {r.status_code}"
    assert "confirm_destructive" in r.json()["detail"]


def test_junction_alias_refused_without_confirmation(tmp_path):
    """V3.2.3: a directory junction (symlink-like alias) to the project must not bypass.

    Junctions are used because file symlinks need admin rights on Windows; a
    junction through the project data directory points at the same live file.
    """
    link = tmp_path / "project_alias"
    project = Path(__file__).resolve().parents[2]
    proc = __import__("subprocess").run(
        ["cmd", "/c", "mklink", "/J", str(link), str(project)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"junction creation unavailable: {proc.stdout.strip()} {proc.stderr.strip()}")

    url = f"sqlite:///{(link / 'data' / 'yottaflex.db').as_posix()}"
    canon = canonical_sqlite_path(url)
    live_canon = canonical_sqlite_path(_live_url())
    assert canon == live_canon, f"junction alias not canonicalized: {canon} != {live_canon}"

    client = TestClient(app)
    r = client.post(
        "/api/v1/pipeline/run-all",
        json={"output_database_url": url, "write_reports": False},
    )
    assert r.status_code == 400, f"junction alias bypassed the gate: HTTP {r.status_code}"
    assert "confirm_destructive" in r.json()["detail"]


def test_run_all_defaults_to_generated_dir_not_committed(tmp_path):
    """V3.2.3: API run without export_dir writes to data/generated; committed bytes intact."""
    import shutil

    project = Path(__file__).resolve().parents[2]
    generated = project / "data" / "generated"
    repo_checksums = project / "data" / "exports" / "checksums.json"
    before = repo_checksums.read_bytes()

    client = TestClient(app)
    target = tmp_path / "api_default.db"
    try:
        r = client.post(
            "/api/v1/pipeline/run-all",
            json={
                "mini": True,
                "output_database_url": f"sqlite:///{target.as_posix()}",
                "write_reports": True,  # no export_dir -> generated default
            },
        )
        assert r.status_code == 200, r.text
        assert (generated / "exports" / "checksums.json").exists()
    finally:
        shutil.rmtree(generated, ignore_errors=True)

    assert repo_checksums.read_bytes() == before, "committed exports were modified"


def test_run_all_second_run_requires_overwrite_permission(tmp_path):
    """V3.2.3: repeated API runs into an existing export set need explicit permission."""
    client = TestClient(app)
    target = tmp_path / "api_twice.db"
    out = tmp_path / "api_exports_twice"
    body = {
        "mini": True,
        "output_database_url": f"sqlite:///{target.as_posix()}",
        "write_reports": True,
        "export_dir": str(out),
    }
    r1 = client.post("/api/v1/pipeline/run-all", json=body)
    assert r1.status_code == 200, r1.text

    r2 = client.post("/api/v1/pipeline/run-all", json=body)
    assert r2.status_code == 400, r2.text
    assert "overwrite_exports" in r2.json()["detail"]

    body_with_permission = dict(body, overwrite_exports=True)
    r3 = client.post("/api/v1/pipeline/run-all", json=body_with_permission)
    assert r3.status_code == 200, r3.text


def test_run_all_custom_db_with_export_dir(tmp_path):
    """V3.2.2: explicit export_dir allows a custom-DB API run; repo exports untouched."""
    client = TestClient(app)
    repo_checksums = Path(__file__).resolve().parents[2] / "data" / "exports" / "checksums.json"
    before = repo_checksums.read_bytes()
    target = tmp_path / "api_custom2.db"
    out = tmp_path / "api_exports"
    r = client.post(
        "/api/v1/pipeline/run-all",
        json={
            "mini": True,
            "output_database_url": f"sqlite:///{target.as_posix()}",
            "write_reports": True,
            "export_dir": str(out),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ran_in_place"] is False
    assert body["export_dir"] == str(out)
    assert (out / "checksums.json").exists()
    assert (out / "sql" / "00_schema.sql").exists()
    assert repo_checksums.read_bytes() == before, "committed exports were modified"


def _live_db_path() -> Path:
    url = load_settings().resolved_database_url()
    assert url.startswith("sqlite:///")
    return Path(url.removeprefix("sqlite:///"))


def _live_count() -> int:
    path = _live_db_path()
    if not path.exists():
        return 0
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lead'"
        ).fetchone()
        if row is None:
            return 0
        return int(con.execute("SELECT COUNT(*) FROM lead").fetchone()[0])
    finally:
        con.close()


def test_run_all_refused_without_confirmation():
    """V3.2: destructive run-all is rejected unless explicitly confirmed."""
    client = TestClient(app)
    before = _live_count()
    r = client.post("/api/v1/pipeline/run-all", json={})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "confirm_destructive" in detail
    assert "live database" in detail
    # live database untouched
    assert _live_count() == before


def test_run_all_refused_when_output_equals_live_without_confirmation():
    """Pointing output at the live DB is still destructive — must be confirmed."""
    client = TestClient(app)
    live = load_settings().resolved_database_url()
    r = client.post(
        "/api/v1/pipeline/run-all",
        json={"output_database_url": live},
    )
    assert r.status_code == 400, r.text


def test_run_all_into_separate_database_is_safe(tmp_path):
    """V3.2: separate output DB runs without touching live data or exports."""
    client = TestClient(app)
    before = _live_count()
    target = tmp_path / "separate_run.db"
    url = f"sqlite:///{target.as_posix()}"

    r = client.post(
        "/api/v1/pipeline/run-all",
        json={
            "mini": True,
            "output_database_url": url,
            "write_reports": False,  # do not clobber data/exports deliverables
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["destructive"] is True
    assert body["ran_in_place"] is False
    assert body["write_reports"] is False

    # separate database was populated
    assert target.exists()
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    try:
        leads = int(con.execute("SELECT COUNT(*) FROM lead").fetchone()[0])
        opps = int(con.execute("SELECT COUNT(*) FROM opportunity").fetchone()[0])
    finally:
        con.close()
    assert leads > 0
    assert opps > 0

    # live database untouched
    assert _live_count() == before
