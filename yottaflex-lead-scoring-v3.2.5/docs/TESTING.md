# Testing Documentation

## Strategy

```
        ┌──────────────┐
        │ Integration  │  pipeline slices + API TestClient + full exception flow
        ├──────────────┤
        │ Unit         │  formula, thresholds, consent, stage path, dedup, KPIs,
        │              │  determinism, GT isolation, validation, business IDs,
        │              │  duplicates, exports, SQL restoration, API safety
        └──────────────┘
```

## Commands

```bash
pytest -q                 # full suite (mini datasets, in-memory SQLite) — 102 tests
pytest -q -k scoring      # subset
python scripts/validate_data.py        # full-dataset validation on a generated DB
python scripts/compare_reproducibility.py --scale starter   # two-run determinism check
```

## Suite inventory (102 tests)

| File | Tests | Covers |
|------|------:|--------|
| `tests/unit/test_schema.py` | 4 | required tables exist, FK pragma on, append-only source guard |
| `tests/unit/test_data_generation.py` | 3 | exact counts, same-seed determinism, different-seed divergence |
| `tests/unit/test_scoring.py` | 6 | weighted formula, category boundaries, temporal cutoff, re-score determinism, explanation persisted, GT not imported |
| `tests/unit/test_validation.py` | 2 | clean data passes; bad status detected |
| `tests/unit/test_validation_complete.py` | 3 | full-record score range + weighted-formula identity (no sampling) |
| `tests/unit/test_engines.py` | 6 | assignment determinism, no baseline territory violations, consent gate, illegal stage rejected, history append-only, dedup mark-not-delete |
| `tests/unit/test_business_ids.py` | 5 | ID formats, uniqueness, zero-padding, FK parity, cross-run determinism |
| `tests/unit/test_natural_duplicates.py` | 3 | natural dupes generated, soft-marked, GT origins separated, volume exactness |
| `tests/unit/test_duplicate_reconciliation.py` | 1 | GT rows == email-group non-primaries (actual records) |
| `tests/unit/test_export_engine.py` | 5 | all-table CSV/JSON/SQL exports, business IDs, checksum determinism, GT JSON |
| `tests/unit/test_sql_restoration.py` | 5 | schema DDL integrity, restored counts, FK integrity, critical relationships |
| `tests/unit/test_restore_safety.py` | 5 | overwrite refusal (exit 3), incomplete-set refusal, count-mismatch failure, atomic replace, preservation on failure |
| `tests/unit/test_restore_manifest.py` | 2 | manifest-based truncation rejection + authentic-exports pass (V3.2.2) |
| `tests/unit/test_outcome_generation.py` | 6 | no score leakage (AST guard), selection ≠ top-score, open opps, per-step timestamps, held-out split |
| `tests/unit/test_p1_histories.py` | 7 | lead status timelines, consent typed FKs, converted-link FK, resolution history, coverage metrics |
| `tests/unit/test_ex02_independent_detection.py` | 4 | marker-free EX-02 detection, evidence requirement, pre-conversion no-FP, measured metrics (V3.2.2) |
| `tests/unit/test_export_protection.py` | 4 | export defaults to generated dir, overwrite permission, committed-exports protection (V3.2.2/V3.2.3) |
| `tests/unit/test_hashseed_determinism.py` | 2 | cross-process determinism across hash seeds; sorted bridge rows (V3.2.2) |
| `tests/unit/test_loss_reasons.py` | 3 | lost valid / won none / open none; deterministic across runs (V3.2.2/V3.2.3) |
| `tests/unit/test_api_safety.py` | 15 | run-all confirmation gate, live-DB protection, 7 path-equivalence refusals + junction alias, export defaults/permission API flows |
| `tests/integration/test_pipeline_exceptions.py` | 8 | baseline clean of injected types; injection → all 5 detected; blind P/R/F1; annotation post-eval; required fields; KPI ranges |
| `tests/integration/test_api.py` | 3 | health, meta, leads/metrics/score-rules/exceptions with seeded DB override |

## Results (latest)

```
102 passed in ~151s (clean venv, mini datasets; V3.2.3)
```

Evidence: `docs/evidence/v3_2_3_pytest_full.txt` (earlier: `v3_2_2_pytest_full.txt`, `v3_2_1_pytest_full.txt`).

No fake/placeholder tests. All assertions run against real engines and in-memory SQLite.

## Full-scale verification (not in default suite)

```bash
python scripts/generate_data.py --scale full      # 20K leads → data/yottaflex.db + data/exports
python scripts/validate_data.py                   # exit 0 + JSON evidence
python scripts/restore_sql_export.py --db data/restored.db   # SQL restoration, exit 0
python scripts/compare_reproducibility.py --scale full       # two-run five-way comparison
```

Results and evidence: see `VALIDATION_SUMMARY.md` and `FINAL_TEST_RESULTS.md`.

## What is intentionally not tested

- Streamlit UI rendering (manual run documented in README)
- Load/performance beyond one full pipeline run
- Concurrent multi-writer SQLite access
- Full-scale reproducibility in the default pytest suite (heavy; run explicitly via the script)
