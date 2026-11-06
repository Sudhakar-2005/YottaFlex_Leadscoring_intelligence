# Technical Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| TD-01 | **Stack unchanged** (Python 3.12, FastAPI, SQLAlchemy 2, Pydantic, SQLite, Streamlit, Pandas/NumPy, Plotly, Pytest) | Matches problem statement; no paid/extra infra. |
| TD-02 | **SQLite + StaticPool for :memory:** | Zero-ops file DB; StaticPool required so all sessions share one in-memory DB (fixes "no such table" under FastAPI/TestClient). |
| TD-03 | **Naive UTC datetimes everywhere** | Avoids aware/naive comparison errors; `Settings.base_dt()` strips tz from YAML. |
| TD-04 | **SeedSequence([seed, stream]) per generator** | Independent RNG streams: changing company logic doesn't shift lead draws. |
| TD-05 | **No DB FK Lead.converted_opportunity_id → Opportunity** | Prevents cyclic FK (lead↔opportunity) that breaks SQLite `create_all`; logical link + unique constraint only. Opportunity.lead_id remains the enforced FK. |
| TD-06 | **Soft dedup (mark, don't delete)** | Preserves traceability; satisfies "never silently overwrite". |
| TD-07 | **Explainability as `lead_score_explanation` rows** | Replayable audit without re-running engines; weights + rules_fired JSON. |
| TD-08 | **Temporal cutoff at scoring time** | `event_time <= scored_at`; converted leads additionally capped at `converted_at` (BR-S04). |
| TD-09 | **Assignment: territory+product preferred, territory-only fallback (BR-R02b)** | Product-only dead-ends would tank coverage; fallback keeps ≥96% coverage while preferring skill match. |
| TD-10 | **Least-loaded then lowest ID** | Deterministic, simple, fair; no global RNG in assignment path. |
| TD-11 | **Injection after clean baseline** (P0-B refinement: baseline has zero INJECTED-type exceptions; EX-04 natural dupes may fire) | Baseline detectors must return 0 for injected types; anomalies only touch targeted rows. |
| TD-12 | **Superseded by P0-5: blind key-based evaluation** (`exception_evaluation` matches detections↔GT by record/lead id; labels attached post-evaluation only) | Previous label-attached matching was circular; blind matching is an honest measurement. |
| TD-13 | **Stage lost allowed from qualified/demo/proposal** | Early-loss is realistic; skips still illegal — EX-05 only fires on true gaps. |
| TD-14 | **Superseded by P0-D: propensity selection** (documented business factors + jitter; score never an input) | Score-ranked selection guaranteed exact target but created direct leakage; propensity keeps exactness without circularity. |
| TD-15 | **N+1 avoidance: preload territory/product maps during assignment** | Full run assignment dropped ~6.5min → ~1.5min. |
| TD-16 | **Capacity 200–350 open leads/rep** | 80 reps A- ~275 avg — ~22K slots — ~96% coverage at 20K leads. |
| TD-17 | **Dependency injection override in API tests** | Clean FastAPI testing without monkeypatching engine internals. |
| TD-18 | **Pipeline writes `data/reports/pipeline_result.json`** | Machine-readable validation artifact for submission. |
| TD-19 | **Business ID helpers in `yottaflex.ids`** (zero-padded, immutable, deterministic) | Single source for formats; validated by regex in tests + validate_data.py. |
| TD-20 | **`duplicate_gt` table separates natural vs injected duplicates** (origin column) | Required separation between deliberate anomalies and realistic duplicates (P0-B). |
| TD-21 | **Natural dupes generated inside fixed volumes** (copies of earlier records; soft-dedup marks; originals preserved) | Row counts stay exact; dedup + GT give detection-rate metrics. |
| TD-22 | **Exporter writes all tables as CSV + GT/manifest/validation/checksums/seed SQL** | Complete offline handoff; checksums prove reproducibility. |
| TD-23 | **Per-step stage timestamps** (path built as (stage, reason, time) triples) | Fixes collapsed-timestamp bug (P0-6). |
| TD-24 | **FNV-1a hash streams for outcome randomness** (per-opportunity stage/open/win draws) | Global RNG shifts avoided; fully reproducible. |
| TD-25 | **Lead status history = explicit table + transition helper** (`lead_status_history` append-only; all 5 status-write sites route through `append_status_change`) | Every lead timeline reconstructable; single choke point for future workflow changes (P1-1). |
| TD-26 | **Lead.converted_opportunity_id is a real FK (SET NULL)** | Cycle is safe in SQLite (FKs checked at DML time, not DDL); enforced at P1-2 after verifying create_all + clear order work. |
| TD-27 | **Consent typed FKs (`lead_id`/`contact_id`) alongside subject triple** | Polymorphic subjects gain enforcement without breaking the (type,id) contract (P1-3). |
| TD-28 | **Exception resolution history snapshots identity** (survives re-detection deletes) | Re-detection hard-deletes exception_record (pre-existing design); resolutions live on (P1-4). `resolved_at` uses wall clock (manual action, not pipeline data — exports stay deterministic while the table is empty). |
| TD-29 | **Coverage metrics from consent/activity (not just status)** | opt-out/stale/consent-coverage are data-derived; disqualified=0 is an honest report (status never set by baseline) (P1-5). |

## Rejected alternatives

| Alternative | Why rejected |
|-------------|--------------|
| PostgreSQL / Docker | Unnecessary infrastructure per §8 |
| ML model for scoring | Rules must be explainable; problem states weighted formula |
| Hard-delete duplicates | Violates traceability / no-silent-overwrite |
| SQLite triggers for append-only | App-level guard + tests sufficient for MVP (TD-11/A11) |
| Auth (JWT/API keys) | Out of scope local MVP (A12) |
