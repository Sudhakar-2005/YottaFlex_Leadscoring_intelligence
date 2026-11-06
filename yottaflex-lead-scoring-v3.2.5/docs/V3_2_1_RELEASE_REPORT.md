# V3.2.1 Release Report

Date: 2026-11-05 · Release candidate: `C:\Users\acer\yottaflex-lead-scoring-v3.2.1`
Base: verified V3.2 release (git history inherited, 12 commits at copy time).
Scope: **only** the four V3.2.1 review items. No business-logic changes. Nothing pushed; nothing submitted.

## 1. Repository cleanup (item 1)

Performed at copy time (robocopy with exclusions), so the release copy never contained runtime artifacts:

| Removed from release copy | Note |
|---------------------------|------|
| `.venv/` | development environment (recreated via `pip install -r requirements.txt && pip install -e .`) |
| `.pytest_cache/` | test cache (audits/tests run with `-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`) |
| `data/restored.db` | restoration artifact (reproducible via `scripts/restore_sql_export.py`) |
| `data/yottaflex.db` | runtime database (~179 MB; reproducible via `scripts/generate_data.py --scale full`) |
| `__pycache__/` (all) | bytecode caches |

Preserved and verified tracked: all source, all tests, 23 CSV exports, 4 JSON exports, 7 SQL splits,
ground-truth data (`duplicate_gt.csv`, `ground_truth.json`), test evidence (`docs/evidence/`),
architecture/business docs, AI prompt history. Git history verified safe: 12 commits scanned —
**no `.db`, `.venv`, `seed_data.sql`, caches, or `.coverage` in ANY commit** (`docs/evidence/v3_2_1_repo_audit.txt`).

Copy command: `robocopy <src> <dst> /E /XD .venv .pytest_cache __pycache__ /XF yottaflex.db restored.db`
→ `robocopy exit: 1 (0-7 = success)`; leftover scan: none.

## 2. Engineering audit rewrite (item 2)

`docs/ENGINEERING_AUDIT.md` rewritten as one consolidated current report:
- Sections 1–4 + 6 = current state, every number tied to an evidence file.
- Section 5 = original V3 findings, explicitly labelled **HISTORICAL ONLY**, with the remediation pointer.
- No contradictory claims; single canonical description of the current implementation.

## 3. SQL restoration atomicity (item 3)

`scripts/restore_sql_export.py` rewritten:

```
flow: input checks --> overwrite permission (exit 3 without --force)
      --> restore into <target>.tmp-restore.<pid>.db (same directory => same volume)
      --> verify schema (all 23 tables + exact column sets vs ORM metadata)
      --> PRAGMA foreign_keys=ON + PRAGMA foreign_key_check
      --> row counts vs source DB + non-empty core tables
      --> ONLY THEN os.replace(tmp, target)  [atomic]
      --> on ANY failure: target preserved unchanged, temp removed (exit 1)
exit codes: 0 pass · 1 fail/verify fail (target preserved) · 2 missing inputs · 3 overwrite refused
```

Regression tests (`tests/unit/test_restore_safety.py`, 5 tests — 2 new):
1. refuse overwrite without `--force` (target byte-identical; no temp leftovers)
2. **failed restore preserves an existing target** (corrupted SQL load → exit 1 → marker DB byte-identical)
3. **successful restore replaces the target only via atomic swap** (old content fully gone, new data present)
4. incomplete export set refused before any work (exit 2; no target created)
5. count-mismatch verification failure (exit 1; no partial target; no temp leftovers)

Testing caught and fixed a real Windows defect during development: the load-error path leaked an
open temp-DB handle, preventing cleanup — the connection is now closed before the error propagates.

Command: `pytest tests/unit/test_restore_safety.py -v -p no:cacheprovider` → **5 passed**.

## 4. Final verification (item 4)

| Check | Command | Actual result | Evidence |
|-------|---------|---------------|----------|
| Full suite | `pytest tests/ -q -p no:cacheprovider` | **75 passed**, exit 0 | `docs/evidence/v3_2_1_pytest_full.txt` |
| SQL restoration safety | `pytest tests/unit/test_restore_safety.py -v` | **5 passed** | included above |
| Full validation | `generate_data.py --scale full --database-url <temp>` then `validate_data.py --database-url <temp>` | exit 0; 24 checks, 0 critical; 378,460 IDs (0 invalid); 0 collapsed timestamps; 0 missing history; dup GT 741 natural + 10 injected | `v3_2_1_full_generate.txt`, `v3_2_1_validate_data.txt` |
| Large-file audit | working-tree + tracked scan | 1 file >50 MB (`03_activity_data.sql`, 50.02 MB); **none ≥100 MB** | `v3_2_1_repo_audit.txt` |
| Secret scan | 101 files, 7 patterns | **NONE**; `.env.example` placeholders only | `v3_2_1_secret_scan.txt` |
| Git tracked-file audit | dulwich tree walk + history scan | 121 tracked; banned categories all "none"; history clean | `v3_2_1_repo_audit.txt` |

Full-scale reproducibility was **not** rerun (no data-generation/export changes), per instruction;
all V3.2 evidence is preserved under `docs/evidence/v3_2_*.txt`.

## 5. New finding surfaced during verification (owner decision requested)

While running the mandated full validation, the regeneration produced 4 modified export files.
Investigation proved a **cross-process determinism gap**: `generate_reference_data` iterates a
Python `set` of territory codes, so `salesrep_territory` bridge-row ids depend on the process
hash seed. Content sets are identical; only row order/ids differ; other 29 export files are
cross-process deterministic.

Controlled experiment (separate processes):
`PYTHONHASHSEED=1` vs `=2` → different file hashes; `=1` twice → identical.
Full evidence: `docs/evidence/v3_2_1_hashseed_finding.txt`; added as **L24** in `KNOWN_LIMITATIONS.md`.

Action taken: exports were restored to the committed V3.2 versions (via HEAD blobs) so the release
stays byte-consistent with the published V3.2 evidence. The finding is **not fixed** (fixing touches
data generation and changes generated ids — outside the V3.2.1 scope per the review rules).
Recommended patch (pending owner approval): iterate `sorted(covered)` in `generate_reference_data`,
regenerate exports, rerun full-scale reproducibility.

## 6. Exact changed-file list (V3.2.1)

| File | Change |
|------|--------|
| `scripts/restore_sql_export.py` | atomic restore flow (temp DB → verify → os.replace; exit codes; handle close fix) |
| `tests/unit/test_restore_safety.py` | 5 tests (2 new regressions; atomicity assertions) |
| `docs/ENGINEERING_AUDIT.md` | consolidated current report (history labelled) |
| `docs/KNOWN_LIMITATIONS.md` | L24 added (hash-seed finding) |
| `docs/FINAL_RELEASE_CHECKLIST.md` | rewritten for V3.2.1 |
| `docs/V3_2_1_RELEASE_REPORT.md` | this report (new) |
| `docs/evidence/v3_2_1_*.txt` | 6 new evidence files (pytest, generate, validate, repo audit, secret scan, hashseed finding) |

Cleanup-only (no git impact): removal of `.venv`, `.pytest_cache`, `data/yottaflex.db`,
`data/restored.db`, `__pycache__` from the release copy (excluded at copy time).

## 7. Remaining limitations

Open: L1–L11, L15, L17–L19, L21–L23 (release disposition in `KNOWN_LIMITATIONS.md`) + **L24 (new)**.
Resolved/mitigated: L3, L12, L13, L14, L16, L20.

## 8. Approval status

**Awaiting project-owner approval.** No GitHub push, no submission. Repository tree is clean
after commits; verification commands reproduced above with saved evidence.
