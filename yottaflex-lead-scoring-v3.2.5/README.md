# YottaFlex AI — Lead Scoring & Opportunity Management System

End-to-end system that scores leads on **Fit / Intent / Engagement**, routes and assigns sales reps, manages follow-up tasks, tracks opportunities with append-only stage history, detects five classes of business exceptions, and reports measurable KPIs.

## Dataset (reproducible, seed=20261022)

| Entity | Count |
|--------|------:|
| Leads | 20,000 |
| Contacts | 10,000 |
| Companies | 5,000 |
| Opportunities | 3,000 |
| (+ Campaigns 30, SalesReps 80, Territories 16, Products 10) | |

Business IDs (P0-A): `CO-000001`, `CON-000001`, `LEAD-2026-000001`, `OPP-2026-000001`, `ACT-LEAD-2026-000001-001`, `TASK-LEAD-2026-000001-001`.

Baseline includes controlled natural duplicates (60 companies, 150 contacts, 400 leads, 15 opportunities) — soft-marked with ground-truth separation from injected anomalies.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
pip install -e .

# Full pipeline (exports default to data/generated/exports - committed exports stay safe)
python scripts/generate_data.py --scale full

# Refresh the committed full-scale deliverables (explicit destination + permission)
python scripts/generate_data.py --scale full --export-dir data/exports --overwrite-exports

# Mini smoke run
python scripts/generate_data.py --scale starter --no-inject

# Validate + two-run reproducibility (five-way comparison: counts, files, checksums, FKs, validation)
python scripts/validate_data.py
python scripts/compare_reproducibility.py --scale starter
python scripts/compare_reproducibility.py --scale full

# SQL restoration (refuses to overwrite without --force; re-enables and checks FKs)
python scripts/restore_sql_export.py --db data/restored.db

# Tests (102 — see docs/evidence/v3_2_5_pytest_full.txt)
pytest -q

# API
uvicorn yottaflex.api.main:app --reload
# OpenAPI docs: http://127.0.0.1:8000/docs

# Dashboard
streamlit run app/dashboard.py
```

Outputs land in `data/yottaflex.db`. The committed deliverables live in `data/exports/` (23 table CSVs + ground_truth.json + dataset_manifest.json + validation_summary.json + checksums.json + `sql/00_schema.sql` .. `sql/06_ground_truth.sql`) and `data/reports/pipeline_result.json`; auxiliary runs write to `data/generated/` instead (V3.2.3 policy).

## API safety (V3.2)

`POST /api/v1/pipeline/run-all` is destructive (regenerates every table). It now:

- **requires `confirm_destructive=true`** to run against the live database — otherwise HTTP 400 and nothing is touched;
- detects the live database by **canonical filesystem path** (V3.2.2/V3.2.3): `./`, `../`, `//`, backslash, four-slash-absolute, case, trailing-dot and junction (symlink-like) representations cannot bypass the gate;
- supports **`output_database_url`** to generate into a separate database, leaving live data untouched;
- **export policy (V3.2.3):** runs default to a separate `data/generated/exports` directory; overwriting any existing export set requires explicit permission (`overwrite_exports=true` in the API / `--overwrite-exports` in the CLI); the committed `data/exports` deliverables can only be reached with an explicit `export_dir` **and** that permission.

```bash
# refused (protects live data)
curl -X POST localhost:8000/api/v1/pipeline/run-all -H "Content-Type: application/json" -d '{}'

# safe: separate database, no report overwrite
curl -X POST localhost:8000/api/v1/pipeline/run-all -H "Content-Type: application/json" \
  -d '{"mini": true, "output_database_url": "sqlite:///data/api_run.db", "write_reports": false}'
```

## Architecture (summary)

```
Presentation   Streamlit dashboard · FastAPI (/api/v1/...)
Application    pipeline.py orchestrates engines A→L
Domain engines DataGen · Validation · Scoring · Dedup · Consent
               Routing · Assignment · Tasks · Opportunity
               StageHistory · Exceptions · Analytics
Data           SQLAlchemy 2 · SQLite · Pydantic config
```

See `docs/ARCHITECTURE.md`, `docs/ERD.md`, `docs/DATA_DICTIONARY.md`.

## Lead scoring

```
lead_score = Fit×0.40 + Intent×0.35 + Engagement×0.25   (each dim 0–100)
Hot ≥80 · Warm ≥60 · Nurture ≥40 · Cold <40   (configurable in config/settings.yaml)
```

- Every score stores an explainable rules-fired trail (`lead_score_explanation`).
- Temporal cutoff: only `activity.event_time <= scored_at` contributes (no leakage).
- Ground-truth labels are **never** imported by the scoring module (enforced by test).

## Exception scenarios (all 5)

| Issue type | Severity | Detection |
|------------|----------|-----------|
| opted_out_lead_contacted | critical | outreach task without valid consent |
| score_uses_post_conversion_event | critical | explanation scored after conversion that used post-conversion intent activity (independent timestamps/evidence — no injected markers, V3.2.2) |
| lead_assigned_outside_territory | high | rep does not cover lead territory |
| duplicate_creates_duplicate_opportunity | high | >1 opportunity per lead |
| stage_history_has_gaps | medium | illegal/skipped stage transitions |

Baseline data is generated **clean of the five injected anomaly types** (natural baseline duplicates, EX-04 origin='natural', may be detected pre-injection). Anomalies are injected afterwards with quotas; blind key-based evaluation achieves **precision=1.0, recall=1.0, F1=1.0** against ground truth on the full run (methodology documented, undefined metrics reported as null — never defaulted to 1.0).

## Release hardening (V3.2.2/V3.2.3)

- Express the API guard, restore flow and exports in canonical paths/destinations (see API safety above).
- `scripts/restore_sql_export.py` verifies restored rows against **`dataset_manifest.json`** (every table, exact counts), catches truncated exports, re-enables + checks foreign keys, and replaces the target atomically only after all checks pass (`--force` required to overwrite).
- Generation is **cross-process deterministic** (sorted bridge-row ordering): identical exports across separate processes and hash seeds.
- Lost opportunities carry meaningful deterministic **`loss_reason`** values; won/open opportunities never do.
- Export overwrite policy (V3.2.3): auxiliary/starter/API runs default to `data/generated/exports`; committed exports require explicit destination + `overwrite_exports` permission.

## Core KPIs (full run, seed 20261022)

| Metric | Value |
|--------|------:|
| Lead conversion rate | 15.3% |
| Opportunity win rate | 59.2% |
| Assignment coverage | 100% |
| Consent compliance | 75.6% |
| Consent coverage | 79.5% |
| Opt-out rate (revoked) | 8.8% |
| Duplicate detection rate | 100% |
| Low-score converters (<60) | 129 |
| High-score non-converters (≥80) | 6,016 |
| Baseline exceptions (natural EX-04) | 15 |

Exact numbers: `data/reports/pipeline_result.json`.

## Documentation index

| Doc | Path |
|-----|------|
| Architecture | `docs/ARCHITECTURE.md` |
| ERD | `docs/ERD.md` |
| Data dictionary | `docs/DATA_DICTIONARY.md` |
| Business rules | `docs/BUSINESS_RULES.md` |
| API | `docs/API.md` |
| Assumptions | `docs/ASSUMPTIONS.md` |
| Technical decisions | `docs/TECHNICAL_DECISIONS.md` |
| Testing | `docs/TESTING.md` |
| Validation summary | `docs/VALIDATION_SUMMARY.md` |
| V3.2 stabilization report | `docs/V3_2_STABILIZATION_REPORT.md` |
| V3.2.2 fix report | `docs/V3_2_2_FIX_REPORT.md` |
| V3.2.2 test results | `docs/V3_2_2_TEST_RESULTS.md` |
| Final test results | `docs/FINAL_TEST_RESULTS.md` |
| Final release checklist | `docs/FINAL_RELEASE_CHECKLIST.md` |
| AI prompt history | `docs/AI_PROMPT_HISTORY.md` |
| Known limitations | `docs/KNOWN_LIMITATIONS.md` |

## Configuration

- `config/settings.yaml` — seed, counts, weights, thresholds, injection quotas
- `config/score_rules.yaml` — Fit/Intent/Engagement rule definitions

Changing weights or thresholds does not require code changes.

## License

See the repository-level `LICENSE` file. Confirm the intended licensing terms before publishing; this project README previously described the deliverable as internal use.
