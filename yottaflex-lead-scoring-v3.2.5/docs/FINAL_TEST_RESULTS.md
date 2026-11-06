# Final Test Results - V3.2 (actual execution evidence)

Date: 2026-11-05 · Environment: clean venv (`yottaflex-lead-scoring-v3.2\.venv`, Python 3.12.10)
Raw outputs: `docs/evidence/` (files listed per section)

## 1. Clean environment installation

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   -> OK (no errors)
.venv\Scripts\python.exe -m pip install -e .                  -> OK
import check: yottaflex from C:\Users\acer\yottaflex-lead-scoring-v3.2\src\yottaflex
```

## 2. Pytest suite

| Run | Command | Result | Evidence |
|-----|---------|--------|----------|
| Baseline (pre-V3.2 changes) | `pytest tests/ -q` | **64 passed** in 84.57s | `evidence/v3_2_pytest_baseline.txt` |
| Final (post-V3.2 changes) | `pytest tests/ -q` | **73 passed** | `evidence/v3_2_pytest_full.txt` |

New tests added in V3.2 (9 total):
- `tests/unit/test_api_safety.py` (3): refusal without confirm (400, DB untouched),
  refusal when output == live without confirm, safe separate-DB run (live untouched,
  separate DB populated).
- `tests/unit/test_restore_safety.py` (3): overwrite refusal exit 3 (bytes unchanged),
  incomplete export set exit 2 (target never created), count-mismatch exit 1.
- `tests/unit/test_validation_complete.py` (3): clean full validation passes; score-range
  violation on a high lead_id detected (regression for the removed `.limit(50)`);
  one-point weighted-formula drift detected.

## 3. Full-scale generation

`python scripts/generate_data.py --scale full` (evidence: `v3_2_full_generate.txt`)

```
opportunities created=2975 + 15 natural dupes; baseline target 2990; +10 injected = 3000 rows
injected: opted_out_contacted=20, temporal_leakage=15, territory_mismatch=15,
          duplicate_opportunity=10, stage_history_gap=15
baseline exceptions: 15 (all natural EX-04)
post-injection detections: 90 (20/15/15/25/15)
blind evaluation P/R/F1: 1.0 / 1.0 / 1.0
exports written: 33 files (+ checksums.json = 34 on disk)
```

## 4. Full-dataset validation

`python scripts/validate_data.py` -> exit 0 (evidence: `v3_2_validate_data.txt`)

```
passed: True · engine checks_run: 24 · critical issues: 0
opportunity_count: 3000 (exact)
business-ID GLOB checks (ALL rows): company 5000/0 invalid · contact 10000/0 ·
  lead 20000/0 · opportunity 3000/0 · activity 320956/0 · task 19504/0
stage_timestamps_collapsed: 0 (ALL opportunities) · opportunities_without_history: 0
duplicate_gt: natural 741 + injected 10
counts: activity 320,956 · consent 57,033 · task 19,504 · stage_history 13,218
```

## 5. SQL restoration + foreign keys

`python scripts/restore_sql_export.py --db data/restored.db` (evidence: `v3_2_restore.txt`)

```
run 1 (fresh):     exit 0 — all 23 tables present; foreign_key_check clean;
                   row counts match source; 577,308 rows; RESTORATION: PASS
run 2 (no force):  exit 3 — REFUSED: target exists (171.9 MB); nothing modified
run 3 (--force):   exit 0 — RESTORATION: PASS
```

## 6. Reproducibility (five-way comparison)

Starter — `--scale starter` (evidence: `v3_2_repro_starter.txt`), exit 0:

```
[PASS] row counts: 58,113 = 58,113 (23 tables)
[PASS] file counts: 33 = 33
[PASS] checksums (files): 33 files; diffs=none
[PASS] checksums (tables): 23 tables
[PASS] referential integrity: violations 0 / 0
[PASS] validation reports identical: byte-identical JSON
[PASS] validation passed (both runs)
REPRODUCIBILITY: PASS
```

Full — `--scale full` (evidence: `v3_2_repro_full.txt`), exit 0:

```
[PASS] row counts: 577,308 = 577,308 (23 tables)
[PASS] file counts: 33 = 33
[PASS] checksums (files): diffs=none
[PASS] checksums (tables)
[PASS] referential integrity: violations 0 / 0
[PASS] validation reports identical: byte-identical JSON
[PASS] validation passed (both runs)
REPRODUCIBILITY: PASS
```

## 7. Export integrity

- `checksums.json` covers all 33 exported artifacts (files) + 23 per-table hashes.
- Byte-identical across independent runs (both scales) — proof of export integrity.
- SQL splits restore into an empty SQLite DB with exact counts and 0 FK violations.

## 8. Summary

| Check | Status |
|-------|--------|
| Clean environment installation | PASS |
| Pytest suite (73) | PASS |
| Starter-scale reproducibility | PASS (7/7) |
| Full-scale reproducibility | PASS (7/7) |
| SQL restoration | PASS (with refusal + force semantics) |
| Foreign-key validation | PASS (0 violations) |
| API safety tests | PASS (3/3) |
| Data validation (full coverage) | PASS (exit 0, 0 critical) |
| Export integrity | PASS (byte-identical checksums) |
