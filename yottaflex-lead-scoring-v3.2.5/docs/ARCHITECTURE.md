# Architecture

## Goals

Modular, deterministic, explainable pipeline for lead scoring and opportunity management with explicit business rules, referential integrity, and auditable exceptions.

## Layered view

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION                                               │
│  • Streamlit — app/dashboard.py                             │
│  • FastAPI   — src/yottaflex/api/main.py  (/api/v1)         │
├─────────────────────────────────────────────────────────────┤
│  ORCHESTRATION                                              │
│  • src/yottaflex/pipeline.py  (steps A→L)                   │
│  • scripts/run_pipeline.py   (CLI entry)                    │
├─────────────────────────────────────────────────────────────┤
│  DOMAIN ENGINES (src/yottaflex/engines/)                    │
│  A data_generator      B validation       C scoring         │
│  D deduplication       E consent          F routing         │
│  G assignment          H task_management  I opportunity     │
│  J stage_history       K exceptions       L analytics       │
│  + anomaly_injection (post-baseline)                        │
├─────────────────────────────────────────────────────────────┤
│  DATA ACCESS                                                │
│  • SQLAlchemy models — src/yottaflex/db/models.py           │
│  • session/schema   — db/session.py, db/schema.py           │
│  • SQLite file      — data/yottaflex.db                     │
├─────────────────────────────────────────────────────────────┤
│  CONFIG / LOGGING                                           │
│  • config.py (Pydantic + YAML) · logging_setup.py           │
│  • config/settings.yaml · config/score_rules.yaml           │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline sequence

| Step | Engine | Input | Output |
|------|--------|-------|--------|
| A | data_generator | seed, counts | master rows + activities + consents |
| B | validation | tables | ValidationReport |
| B2 | deduplication | leads/contacts/companies | soft `is_duplicate_of` marks |
| C | scoring | activities ≤ scored_at, ScoreRules | scores + explanations |
| F/G | routing + assignment | territory/product maps | `assigned_salesrep_id` |
| E/H | consent + tasks | consents, categories | Task rows (consent-gated) |
| I/J | opportunity + stage_history | qualified leads | 3,000 opps + history |
| K | exceptions (baseline) | all artifacts | expected: 0 records |
| — | anomaly_injection | quotas | GT + injection log |
| K | exceptions (post) | artifacts | 75 detections |
| L | analytics | all | KPIs → JSON report |

## Dependency rules

1. Engines import models/config only — never API/dashboard.
2. `scoring.py` must not import `GroundTruthException` / `AnomalyInjectionLog` (tested).
3. `pipeline.py` is the sole orchestrator.
4. StageHistory is append-only; engines never UPDATE/DELETE history rows.

## Determinism

- `SeedSequence([seed, stream])` per entity stream (companies, contacts, leads, …) so refactors don't cascade randomness.
- Naive UTC timestamps derived from `settings.base_dt()` (never `datetime.now()` in generation path).
- Assignment order: `ORDER BY lead_id`, rep pick `min(active_leads_count, salesrep_id)`.

## Exception handling architecture

Five detectors implement a common `detect(session, detected_at) -> list[ExceptionRecord]` protocol. Detection:

1. Scans operational tables for rule violations.
2. Joins `anomaly_injection_log` / `ground_truth_exception` to attach `ground_truth_label`.
3. Writes `exception_record` rows (severity, expected vs actual, resolution_status).

Injection runs **after** a clean baseline so unrelated records are never corrupted.

## API surface

See `docs/API.md`. Auth is out of scope for local MVP (documented limitation).
