# Final Release Checklist — YottaFlex V3.2.1

Date: 2026-11-05 · Deadline: 2026-11-06 · Release candidate: `C:\Users\acer\yottaflex-lead-scoring-v3.2.1`
Supersedes the V3.2 checklist. No push, no submission — owner approval granted (2026-11-05); publication handed to the project owner.

## A. Release gates

- [x] Original project + V3.2 release preserved untouched; V3.2.1 is a separate copy
- [x] Backup chain intact: `...-submission-BACKUP-v3.2`, `yottaflex-lead-scoring-v3.2`
- [x] No business-logic redesign; scoring formula, DB schema, challenge functionality unchanged
- [x] Git history verified safe (12 inherited commits; zero banned artifacts in any commit)
- [x] Nothing pushed; nothing submitted

## B. V3.2.1 review items

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Repository cleanup (`.venv`, `.pytest_cache`, DBs, caches removed; deliverables preserved) | DONE | `v3_2_1_repo_audit.txt` |
| 2 | ENGINEERING_AUDIT consolidated rewrite (history labelled) | DONE | `docs/ENGINEERING_AUDIT.md` |
| 3 | SQL restoration atomicity (temp DB → verify → atomic replace; preserve on failure) | DONE | script + 5 restore tests |
| 4 | Final verification (pytest, restore safety, validation, large files, secrets, git audit) | DONE | `docs/evidence/v3_2_1_*.txt` |
| 5 | Deliverables (V3.2.1 release report + this checklist) | DONE | `docs/V3_2_1_RELEASE_REPORT.md` |

## C. Verification results (actual outputs)

- [x] `pytest tests/ -q -p no:cacheprovider` → **75 passed** (exit 0)
- [x] `pytest tests/unit/test_restore_safety.py` → **5 passed**
- [x] Full validation (temp DB) → exit 0; 24 checks, 0 critical; 378,460 IDs checked, 0 invalid
- [x] Large-file audit → largest 50.02 MB; none ≥ 100 MB
- [x] Secret scan → NONE (101 files); `.env.example` placeholders only
- [x] Git tracked audit → 121 files; no `.db`/`.venv`/caches/`seed_data.sql` anywhere in history

Full-scale reproducibility: V3.2 evidence preserved (no generation/export changes in V3.2.1).

## D. Data deliverables present (tracked)

- [x] 23 table CSVs · 4 JSONs (ground_truth, dataset_manifest, validation_summary, checksums)
- [x] 7 split SQL files (`sql/00_schema.sql` … `06_ground_truth.sql`)
- [x] Ground-truth data (duplicate_gt.csv, ground_truth.json)
- [x] Test suite (18 test files, 75 tests) and evidence (`docs/evidence/`)
- [x] Documentation incl. AI prompt history; no runtime DBs shipped

## E. Open items (documented, accepted for release)

- Limitations L1–L11, L15, L17–L19, L21–L23 (see release disposition in `KNOWN_LIMITATIONS.md`)
- **L24 (new)**: cross-process hash-seed ordering in `salesrep_territory` — content identical,
  4 files differ byte-wise across processes; recommended one-line fix deferred pending owner
  approval (changes generated ids); owner decided 2026-11-05 to keep it deferred. Evidence: `docs/evidence/v3_2_1_hashseed_finding.txt`

## F. Publication (after owner approval; not performed)

1. Use `C:\Users\acer\yottaflex-lead-scoring-v3.2.1` as the release copy.
2. On a machine with git:
   ```bash
   cd yottaflex-lead-scoring-v3.2.1
   git remote add origin <your-repo-url>
   git push -u origin master
   ```
3. Create the GitHub repository empty (no README/license) to avoid a first-push conflict.
4. Verify on GitHub: no `*.db`, no `.venv`, no `seed_data.sql`; max file ≈ 50 MB.

**Owner approval: GRANTED (2026-11-05). Publication handed to the project owner** (self-push); no push or submission was performed by this session.
