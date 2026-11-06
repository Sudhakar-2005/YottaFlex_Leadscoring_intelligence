from __future__ import annotations

from fastapi.testclient import TestClient

from yottaflex.api.main import app
from yottaflex.config import Settings
from yottaflex.db.schema import init_db, open_session
from yottaflex.db.session import make_session_factory
from yottaflex.engines.data_generator import generate_all
from yottaflex.engines.assignment import assign_leads
from yottaflex.engines.scoring import score_all_leads
from yottaflex.engines.validation import validate_dataset


def test_health():
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_meta_seed():
    client = TestClient(app)
    r = client.get("/api/v1/meta/seed")
    assert r.status_code == 200
    body = r.json()
    assert "seed" in body
    assert "weights" in body


def test_leads_and_metrics_endpoints_with_mini_data(mini_settings: Settings):
    """Seed a separate engine and override API session dependency."""
    from yottaflex.api import main as api_main
    from yottaflex.db.session import make_engine, make_session_factory

    eng = make_engine("sqlite:///:memory:", mini_settings)
    init_db(eng)
    with open_session(eng) as session:
        generate_all(session, mini_settings)
        score_all_leads(session, mini_settings)
        assign_leads(session, mini_settings)

    factory = make_session_factory(eng)

    def override_session():
        with factory() as s:
            yield s

    api_main.app.dependency_overrides[api_main.get_session] = override_session
    try:
        client = TestClient(api_main.app)
        r = client.get("/api/v1/leads", params={"limit": 5})
        assert r.status_code == 200, r.text
        assert "items" in r.json()

        r = client.get("/api/v1/metrics/summary")
        assert r.status_code == 200
        assert "lead_conversion_rate" in r.json()

        r = client.get("/api/v1/score-rules")
        assert r.status_code == 200
        assert r.json()["count"] > 0

        r = client.get("/api/v1/exceptions")
        assert r.status_code == 200
    finally:
        api_main.app.dependency_overrides.clear()
