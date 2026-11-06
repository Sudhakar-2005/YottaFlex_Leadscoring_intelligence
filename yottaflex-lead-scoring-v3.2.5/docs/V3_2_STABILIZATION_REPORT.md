# V3.2 Stabilization Report

Date: 2026-11-05 · Release candidate: `C:\Users\acer\yottaflex-lead-scoring-v3.2`
Seed: 20261022 · Submission deadline: 2026-11-06

## 0. Process rules honored

- Original project (`C:\Users\acer\yottaflex-lead-scoring`) untouched.
- Backup created before any V3.2 work: `C:\Users\acer\yottaflex-lead-scoring-submission-BACKUP-v3.2`.
- Dedicated V3.2 working copy created from the frozen submission copy (git history preserved).
- Scoring formula, DB architecture, challenge functionality, and ground-truth data unchanged.
- Nothing pushed; nothing submitted.

## 1. Fixes delivered

### 1.1 API safety — `POST /api/v1/pipeline/run-all`

**Defect:** the endpoint regenerated the whole live database with no confirmation, always
overwrote `data/exports`, and rebound the global engine — accidental destructive execution
was one request away (audit L14).

**Fix (`src/yottaflex/api/main.py`):**
- `confirm_destructive` (default false) required when the target is the live database —
  otherwise HTTP 400 and **nothing is modified**.
- `output_database_url` runs the pipeline into a separate database; live data untouched.
- `write_reports` flag (default true preserves legacy behavior; false protects the
  committed `data/exports` deliverables).
- Response now reports `destructive`, `ran_in_place`, `target_database`, `write_reports`.
- Engine rebinding only happens when the live DB was intentionally rebuilt.

### 1.2 SQL restoration safety — `scripts/restore_sql_export.py`

**Defect:** silently deleted an existing target database; no FK enforcement after load;
weak failure conditions.

**Fix:**
- Refuses to overwrite an existing target without `--force` (exit code 3, file untouched).
- Refuses incomplete export sets before any file work (exit code 2).
- Re-enables `PRAGMA foreign_keys=ON` after loading and runs `PRAGMA foreign_key_check`.
- Verifies all 23 expected tables exist, compares row counts against the source DB,
  enforces non-empty core tables; any failure exits 1 with explicit FAIL lines.
- Exit contract: 0 pass · 1 verification fail · 2 missing inputs · 3 overwrite refused.

### 1.3 Complete validation — `src/yottaflex/engines/validation.py`

**Defect:** score validation sampled `.limit(50)` leads (range + category only).

**Fix:**
- Score-range and category-domain checks now cover **all** scored leads (SQL aggregates;
  offender samples reported, full count in the issue).
- New weighted-formula identity check verifies **every** scored lead against
  `round(fit*0.40 + intent*0.35 + engagement*0.25)` using configured weights
  (`validate_dataset(..., settings=...)`; pipeline passes settings).
- Entity counts now include `score_rule` and `stage_history`.
- `scripts/validate_data.py` upgraded to full coverage with no sampling:
  business-ID format via exact SQL GLOB on every row (378,460 rows checked),
  collapsed stage timestamps across ALL opportunities (SQL aggregate),
  stage-history completeness (every opportunity has history).

### 1.4 Documentation reconciliation

Corrected to match the implementation: `README.md` (34-file exports, API safety examples,
73 tests), `docs/TESTING.md` (full rewrite: real inventory, 73 tests, evidence paths),
`docs/KNOWN_LIMITATIONS.md` (status column; L3/L12/L13/L14/L20 resolved, L16 mitigated,
L23 added), `docs/VALIDATION_SUMMARY.md` (V3.2 addendum with actual numbers),
`docs/ENGINEERING_AUDIT.md` (remediation status table), `docs/AI_PROMPT_HISTORY.md`
(P012-P016 entries), `docs/FINAL_SUBMISSION_CHECKLIST.md` (supersession banner).
No invented results — every number traces to an evidence file.

### 1.5 Full-scale reproducibility — `scripts/compare_reproducibility.py`

**Fix:** comparison upgraded from checksum-only to the required five-way comparison:
row counts (per table), file counts, checksums (per file + per table),
referential integrity (`PRAGMA foreign_key_check` on both generated DBs), and
validation reports (byte-identical JSON + both passed).

## 2. Files changed (V3.2)

| File | Change |
|------|--------|
| `src/yottaflex/api/main.py` | confirmation gate, separate-output DB, write_reports |
| `src/yottaflex/engines/validation.py` | full-record score checks, weighted-formula identity, extra counts |
| `src/yottaflex/pipeline.py` | pass settings into validation |
| `scripts/restore_sql_export.py` | overwrite protection, FK re-enable/check, fail-safe exit codes |
| `scripts/validate_data.py` | GLOB-based full ID checks, full stage checks, no sampling |
| `scripts/compare_reproducibility.py` | five-way comparison + exit codes |
| `tests/unit/test_api_safety.py` | NEW — 3 tests |
| `tests/unit/test_restore_safety.py` | NEW — 3 tests |
| `tests/unit/test_validation_complete.py` | NEW — 3 tests |
| docs (6 files) | reconciliation as listed in 1.4 |
| `docs/evidence/*` | raw command outputs (7 files) |
| data exports + reports | regenerated full scale (34 export files) |

## 3. Verification evidence (all commands actually run)

| Check | Command | Result | Evidence |
|-------|---------|--------|----------|
| Clean install | `python -m venv .venv; pip install -r requirements.txt; pip install -e .` | OK (editable → v3.2 src) | see §FINAL_TEST_RESULTS |
| Regression suite (baseline) | `pytest -q` | 64 passed | `evidence/v3_2_pytest_baseline.txt` |
| Final suite | `pytest -q` | **73 passed** | `evidence/v3_2_pytest_full.txt` |
| Full generation | `generate_data.py --scale full` | 3,000 opps exact; 90 detections; F1 1.0 | `evidence/v3_2_full_generate.txt` |
| Full validation | `validate_data.py` | passed=true, exit 0 | `evidence/v3_2_validate_data.txt` |
| SQL restoration | `restore_sql_export.py` ×3 | PASS / REFUSED(3) / PASS(force) | `evidence/v3_2_restore.txt` |
| Starter reproducibility | `compare_reproducibility.py --scale starter` | PASS 7/7 | `evidence/v3_2_repro_starter.txt` |
| Full reproducibility | `compare_reproducibility.py --scale full` | PASS 7/7 | `evidence/v3_2_repro_full.txt` |

## 4. Dataset statistics (full scale, seed 20261022)

5,000 companies · 10,000 contacts · 20,000 leads · 3,000 opportunities
(2,975 primary + 15 natural duplicates + 10 injected duplicates) · 320,956 activities ·
19,504 tasks · 13,218 stage-history rows · 57,033 consent rows · 23 tables / 577,308 total rows.

Duplicate ground truth: 741 natural + 10 injected = 751 (all detected, 100%).
See `DUPLICATE_RECONCILIATION.md` for the 516-vs-400 lead reconciliation.

## 5. Reproducibility results

- Starter (500/1000/2000/300): row counts 58,113 = 58,113; 33 files; checksums identical
  (files + tables); FK violations 0/0; validation reports byte-identical; both runs valid → **PASS**
- Full (5K/10K/20K/3K): row counts 577,308 = 577,308; 33 files; checksums identical;
  FK violations 0/0; validation reports byte-identical; both runs valid → **PASS**

## 6. Remaining limitations

See `KNOWN_LIMITATIONS.md` (L1-L11, L15, L17-L19, L21-L23 OPEN; L3/L12/L13/L14/L20 resolved;
L16 mitigated). Highlights: no API auth (local MVP), SQLite single-writer, full-scale
reproducibility verified by script rather than CI, wall-clock timestamps for manual
exception resolutions.

## 7. Commands to run the project

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt && pip install -e .
python scripts/generate_data.py --scale full
python scripts/validate_data.py
python scripts/restore_sql_export.py --db data/restored.db
python scripts/compare_reproducibility.py --scale starter
pytest -q
uvicorn yottaflex.api.main:app --port 8000        # API + /docs
streamlit run app/dashboard.py                    # dashboard
```
