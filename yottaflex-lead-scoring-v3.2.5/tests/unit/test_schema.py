from __future__ import annotations

from yottaflex.db.base import Base
from yottaflex.db.schema import init_db


def test_all_core_tables_exist(engine):
    names = set(Base.metadata.tables)
    required = {
        "company",
        "contact",
        "lead",
        "campaign",
        "activity",
        "consent",
        "score_rule",
        "salesrep",
        "task",
        "opportunity",
        "stage_history",
    }
    assert required.issubset(names), f"missing: {required - names}"


def test_bridge_and_support_tables_exist(engine):
    names = set(Base.metadata.tables)
    for t in [
        "territory",
        "product",
        "lead_campaign",
        "salesrep_territory",
        "salesrep_product",
        "lead_score_explanation",
        "exception_record",
        "ground_truth_exception",
        "anomaly_injection_log",
    ]:
        assert t in names


def test_foreign_keys_enabled(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            val = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert val == 1


def test_stage_history_append_only_api(engine, session):
    """Service-level guard: stage history rows are never updated by engines."""
    from yottaflex.db.models import Opportunity, StageHistory

    # No update helper exists — ensure model has no soft-update pattern in engines
    import inspect

    from yottaflex.engines import stage_history as sh

    src = inspect.getsource(sh)
    assert "StageHistory(" in src  # creates via constructor
    assert ".update(" not in src  # no bulk update of history
