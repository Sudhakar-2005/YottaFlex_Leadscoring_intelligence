# V3.2.2 Test Results — actual execution evidence

Date: 2026-11-05 · Environment: `yottaflex-lead-scoring-v3.2.2` (clean venv via external interpreter path, `PYTHONPATH` pinned to this copy; cache-free runs)
All outputs below were produced by actual command execution; raw captures live in `docs/evidence/`.

## 1. Full test suite

```
pytest tests/ -q -p no:cacheprovider
96 passed, 1 warning in 111.76s (exit 0)
```
Evidence: `docs/evidence/v3_2_2_pytest_full.txt`

Inventory (22 files, 96 tests):

| File | Count | Notes |
|------|------:|-------|
| tests/integration/test_api.py | 3 | health/meta/list endpoints |
| tests/integration/test_pipeline_exceptions.py | 8 | 5-scenario flow + blind evaluation |
| tests/unit/test_api_safety.py | 12 | confirmation gate, **6 path-equivalence refusals**, export_dir API flows |
| tests/unit/test_business_ids.py | 5 | ID formats/uniqueness/parity |
| tests/unit/test_data_generation.py | 3 | volumes/determinism |
| tests/unit/test_duplicate_reconciliation.py | 1 | GT-vs-groups identity |
| tests/unit/test_engines.py | 6 | routing/consent/stage/dedup |
| tests/unit/test_ex02_independent_detection.py | 4 | **NEW** marker-free EX-02 detection |
| tests/unit/test_export_engine.py | 5 | CSV/JSON/SQL exports |
| tests/unit/test_export_protection.py | 2 | **NEW** export overwrite protection |
| tests/unit/test_hashseed_determinism.py | 2 | **NEW** cross-process determinism |
| tests/unit/test_loss_reasons.py | 2 | **NEW** lost/won loss_reason rules |
| tests/unit/test_natural_duplicates.py | 3 | natural dupes + GT origins |
| tests/unit/test_outcome_generation.py | 6 | no-leakage outcomes, timestamps, held-out |
| tests/unit/test_p1_histories.py | 7 | status history, FKs, resolution history, coverage |
| tests/unit/test_restore_manifest.py | 2 | **NEW** manifest verification + truncation rejection |
| tests/unit/test_restore_safety.py | 5 | overwrite refusal, atomic replace, preservation |
| tests/unit/test_schema.py | 4 | tables/FK pragma/append-only guard |
| tests/unit/test_scoring.py | 6 | formula/boundaries/temporal/isolation |
| tests/unit/test_sql_restoration.py | 5 | schema/rows/FK/relationship integrity |
| tests/unit/test_validation.py | 2 | clean pass + bad status detection |
| tests/unit/test_validation_complete.py | 3 | full-record score validation |
| **TOTAL** | **96** | (was 75 in V3.2.1; +21 V3.2.2) |

## 2. Defect reproduction (pre-fix) — Rule 2

Captured before any fix was applied (`v3_2_2_reproduction*.txt`):

| Defect | Reproduction result |
|--------|---------------------|
| EX-02 marker dependence | 15 detected WITH markers → **0 after stripping markers**; 0 real post-conversion activities existed |
| API path bypass | `sqlite:////...` equivalent path → **HTTP 500, not 400** (guard bypassed); other variants shown equal-to-live when canonicalized manually |
| Export overwrite | custom-DB run changed `checksums.json` (4dcacb30→9d78da8d) and `pipeline_result.json`; 30 files restored from HEAD |
| Manifest ignored | activities truncated 2,368→100 (FK-neutral) → **RESTORATION: PASS, exit 0** |
| Hash-seed determinism | separate processes seed 1 vs 2 → different `salesrep_territory.csv` hashes |
| Loss reasons | lost=10, with_reason=**0**, won_with_reason=0 |

## 3. Post-fix verification (full scale, seed 20261022)

| Check | Command | Actual result | Evidence |
|-------|---------|---------------|----------|
| Generation | `generate_data.py --scale full` | 3,000 opps (2975+15+10 exact); injections 20/15/15/10/15; blind P/R/F1 = 1.0/1.0/1.0 | `v3_2_2_full_generate.txt` |
| Validation | `validate_data.py` | exit 0; checks_run=24, critical=0; **378,475 IDs, 0 invalid**; 0 collapsed timestamps; 0 missing history; activities=320,971 | `v3_2_2_validate_data.txt` |
| Loss reasons (full) | query | `lost=1063 lost_with_reason=1063 won_with_reason=0` | in validation run output |
| SQL restoration | `restore_sql_export.py` | **PASS**: schema verified; `row counts match dataset_manifest.json for all 23 tables`; FK clean; 577,323 rows; atomic replace; re-run without `--force` → exit 3 | `v3_2_2_restore.txt` |
| Starter reproducibility | `compare_reproducibility.py --scale starter` | PASS 7/7 (58,115 rows; checksums identical; FK 0/0; validation byte-identical) | `v3_2_2_repro_starter.txt` |
| Full reproducibility | `compare_reproducibility.py --scale full` | PASS 7/7 (**577,323 rows**; 33 files; diffs=none; FK 0/0) | `v3_2_2_repro_full.txt` |
| Cross-process determinism | 3 separate processes, seeds 1/2/1 | `A == B: True`, `A == A2: True` → **fixed** | `v3_2_2_hashseed_fixed.txt` |

## 4. Regression test mapping

| Fix | Regression tests | Result |
|-----|------------------|--------|
| EX-02 independent detection | test_ex02_independent_detection.py (4) | 4 passed |
| Path-normalization guard | test_api_safety.py (canonical unit + 6 parametrized refusals) | 7 passed |
| Export overwrite protection | test_export_protection.py (2) + test_api_safety.py (2) | 4 passed |
| Manifest verification | test_restore_manifest.py (2) | 2 passed |
| Hash-seed determinism | test_hashseed_determinism.py (2) | 2 passed |
| Loss reasons | test_loss_reasons.py (2) | 2 passed |

## 5. Notes

- Full reproducibility was rerun because V3.2.2 **does** change generation (injected evidence activity + loss reasons + sorted bridge order) — per the V3.2.1 rule this required fresh evidence; it PASSED.
- Existing V3.2/V3.2.1 evidence files were preserved in `docs/evidence/`.
- One test bug was found and fixed during development (second-session fixture missing `generate_all`), and the restore script gained a Windows temp-handle close fix in V3.2.1 that remains covered.
