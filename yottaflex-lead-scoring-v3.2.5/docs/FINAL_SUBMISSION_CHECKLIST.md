> **V3.2 update (2026-11-05):** superseded by `FINAL_RELEASE_CHECKLIST.md`. Counts below (64 tests, 6+1 commits) reflect V3.1; V3.2 raises the suite to 73 tests and adds API/restoration safety. History and evidence remain valid.

# Final Submission Checklist — YottaFlex V3.1

Generated: 2026-11-04. Submission working copy:
`C:\Users\acer\yottaflex-lead-scoring-submission` (original project untouched at `C:\Users\acer\yottaflex-lead-scoring`).

## 1. Repository audit
- Existing `.git`: NO (no history anywhere — nothing to purge or reuse)
- `git` binary: NOT AVAILABLE on this host — init requires install (see §7)
- Tracked files: n/a (no repo yet)
- Large files in working copy: `data/yottaflex.db` (179 MB), `data/restored.db` (172 MB), legacy `data/exports/seed_data.sql` (121 MB) — all excluded from submission (not copied)

## 2. Files retained (submission copy)
- Source: `src/` (28 modules incl. exporter, lead_status_history, ids)
- App: `app/dashboard.py` (9-section Streamlit)
- Config: `config/settings.yaml`, `config/score_rules.yaml`
- Scripts: `generate_data.py`, `validate_data.py`, `compare_reproducibility.py`, `restore_sql_export.py`, `reconcile_duplicates.py`, `run_pipeline.py`
- Tests: `tests/` (64 tests, 8 test modules + conftest)
- Docs: `docs/` (13 files incl. AI_PROMPT_HISTORY.md, ARCHITECTURE, ERD, DATA_DICTIONARY, BUSINESS_RULES, TESTING, etc.)
- Root: `.gitignore`, `pyproject.toml`, `README.md`, `requirements.txt`
- Deliverables: `data/exports/*.csv` (21 tables), `*.json` (checksums/manifest/validation/ground_truth), **`data/exports/sql/00_schema.sql` .. `06_ground_truth.sql`**, `data/reports/pipeline_result.json`

## 3. Files excluded (not copied to submission)
| Excluded | Size | Reason |
|---|---|---|
| `data/yottaflex.db` | 179 MB | runtime DB (>100 MB); reproducible via generate_data.py |
| `data/restored.db` | 172 MB | restoration-test artifact |
| `data/exports/seed_data.sql` | 121 MB | **broken monolith** (empty DDL; V3 Phase 1 replaced by splits) |
| `.venv/` | — | runtime environment |
| `__pycache__/`, `*.egg-info/` | — | build noise |
| `.coverage`, `.pytest_cache/` | — | test artifacts |
| `scripts/_audit_secrets.py`, `scripts/_ddl_debug.py` | — | audit helpers (one-shot) |

## 4. Large-file audit (submission copy)
| File | Size | Under 100 MB? |
|---|---|---|
| `data/exports/sql/03_activity_data.sql` | 50.0 MB | ✅ |
| `data/exports/activity.csv` | 46.3 MB | ✅ |
| `data/exports/sql/02_lead_data.sql` | 33.0 MB | ✅ |
| `data/exports/lead_score_explanation.csv` | 18.5 MB | ✅ |
| `data/exports/sql/04_workflow_data.sql` | 18.2 MB | ✅ |
| All others | ≤ 10.5 MB | ✅ |

No individual file exceeds GitHub's 100 MB ordinary limit. Total files: 105.

## 5. Security audit
- Secret-pattern scan (API keys, AWS, PATs, private keys, hardcoded credentials): **NONE FOUND**
- `.env` files: none; no `.env.example` (no secrets in use — settings are YAML + env-var-free)
- All database URLs are local SQLite paths; no credentials anywhere in code/config/docs

## 6. Git repository status
- `git` binary: NOT INSTALLED on this host (no system change made without approval)
- Repository initialized with **dulwich** (standard git format, GitHub-compatible)
- 7 commits for the actual stabilization work: 6 thematic + 1 housekeeping (`.env.example`)
- Foundation · database & data generation · business logic · API & dashboard · testing & documentation · final stabilization & deliverables
- No historical timestamps fabricated — all commits carry their actual creation time
- Working tree clean; 106 files tracked; largest tracked object 50.02 MB

## 7. Publish instructions (after your approval)
1. Copy/upload `C:\Users\acer\yottaflex-lead-scoring-submission` or push from a machine with git:
   ```bash
   cd yottaflex-lead-scoring-submission
   git remote add origin <your-repo-url>
   git push -u origin master
   ```
2. Verify on GitHub: no `*.db`, no `.venv`, no `seed_data.sql`, all files < 100 MB.
3. Optional: add a LICENSE and repository description in GitHub settings.

## 8. Verification performed (submission copy)
- 64/64 tests pass inside the submission copy (same suite as original project)
- `restore_sql_export.py`: PASS (577,308 rows / 23 tables / 0 FK violations)
- `compare_reproducibility.py`: PASS (byte-identical checksums, starter scale)
- SQL exports: schema + 6 data files restore into empty SQLite with counts + FK integrity

## 9. Remaining issues
- `IMPORT` note from V3 Phase 1: restoring 03_activity_data.sql with `PRAGMA foreign_keys=OFF` around each file is required (already in files)
- `data/exports` (~150 MB) is large for a repo; consider Git LFS if CI prefers
- Dashboard/API import-time DB engine (L16) unchanged — local-only MVP note
