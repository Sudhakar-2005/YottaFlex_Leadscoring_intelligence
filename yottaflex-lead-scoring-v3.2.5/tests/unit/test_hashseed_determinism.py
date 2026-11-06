"""V3.2.2 regression tests: cross-process (hash-seed) generation determinism.

Generation must be byte-identical across separate processes regardless of
PYTHONHASHSEED (previously set-iteration order changed salesrep_territory ids).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from yottaflex.db.models import SalesRepTerritory

PROJECT = Path(__file__).resolve().parents[2]

PROBE = """
import hashlib, sys
from pathlib import Path
sys.path.insert(0, {src!r})
from yottaflex.config import CountsConfig, Settings
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_engine
from yottaflex.engines.data_generator import generate_all
from yottaflex.engines.exporter import export_all

s = Settings(seed=20261022, counts=CountsConfig(
    companies=30, contacts=40, leads=50, opportunities=10, campaigns=3, sales_reps=8))
eng = make_engine("sqlite:///:memory:", s)
init_db(eng)
out = Path(sys.argv[1])
with open_session(eng) as sess:
    generate_all(sess, s)
    export_all(sess, s, out)
print("DONE")
"""


def _run_with_hashseed(hashseed: int, workdir: Path) -> dict[str, str]:
    workdir.mkdir(parents=True, exist_ok=True)
    probe = workdir / "probe.py"
    probe.write_text(PROBE.format(src=str(PROJECT / "src")), encoding="utf-8")
    exports = workdir / "exports"
    env = dict(os.environ, PYTHONHASHSEED=str(hashseed), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, str(probe), str(exports)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    checksums = json.loads((exports / "checksums.json").read_text(encoding="utf-8"))
    return checksums["files"]


def test_cross_process_hashseed_determinism(tmp_path):
    """Two separate processes with different PYTHONHASHSEED -> identical bytes."""
    a = _run_with_hashseed(1, tmp_path / "run_a")
    b = _run_with_hashseed(2, tmp_path / "run_b")
    assert a == b, "exports differ across hash seeds"
    # spot-check the previously affected file
    assert "salesrep_territory.csv" in a


def test_territory_rows_deterministically_sorted(generated_session, mini_settings):
    """Bridge rows per rep are inserted in sorted territory-code order."""
    sessions = generated_session
    rows = sessions.execute(
        select(
            SalesRepTerritory.salesrep_id,
            SalesRepTerritory.territory_code,
        ).order_by(SalesRepTerritory.id)
    ).all()
    per_rep: dict[int, list[str]] = {}
    for rep_id, code in rows:
        per_rep.setdefault(rep_id, []).append(code)
    assert per_rep
    for rep_id, codes in per_rep.items():
        assert codes == sorted(codes), f"rep {rep_id} territory order not sorted: {codes}"
