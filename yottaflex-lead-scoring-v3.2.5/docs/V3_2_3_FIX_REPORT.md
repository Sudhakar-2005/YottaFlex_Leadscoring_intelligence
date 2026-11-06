# V3.2.3 Fix Report — Release Stabilization

Date: 2026-11-05 · Working copy: `C:\Users\acer\yottaflex-lead-scoring-v3.2.3`
Backup before edits: `C:\Users\acer\yottaflex-lead-scoring-v3.2.2-BACKUP-v3.2.3` (full copy of the V3.2.2 release, untouched)
Base: V3.2.2 (git history preserved) · Nothing pushed · Original project and committed exports untouched.

Scope note (honest accounting): items **1 (EX-02), 4 (restore integrity) and the core of 2/5 were already fixed in V3.2.2** and are *verified here against this task's refined checklist*. The genuine V3.2.3 gaps were: export runs defaulting to the committed directory (item 3's "default to a separate generated-output directory" + explicit overwrite permission), `//`-form and symlink/junction path regressions (item 2's extended list), an explicit open-opportunity loss test (item 5), and the prompt-history/report deliverables.

---

## 1. EX-02 ground-truth leakage — CRITICAL → VERIFIED FIXED (V3.2.2), re-verified

- **Defect:** detector read the injected marker `INJECTED_POST_CONVERSION_EVENT`/`post_conversion`; stripping markers removed all 15 detections (proved pre-fix in `docs/evidence/v3_2_2_reproduction.txt`, DEFECT 1).
- **Files changed (V3.2.2):** `src/yottaflex/engines/exceptions.py`, `src/yottaflex/engines/anomaly_injection.py`; tests `tests/unit/test_ex02_independent_detection.py`.
- **Implementation:** injection creates the real violation (post-conversion `demo_request` activity + stale score, no marker fields); detector uses only `activity.event_time` vs `lead.converted_at` vs `explanation.scored_at`; evidence JSON cites the actual activity; ground truth stays in `anomaly_injection_log`/`ground_truth_exception` (blind evaluation untouched).
- **Tests:** 4 — marker-free detection of all injected cases; deleting the post-conversion activities → 0 detections (no marker crutch); pre-conversion events → 0 false positives; P/R/F1 recomputed from measured TP/FP/FN.
- **Verification evidence:** `docs/evidence/v3_2_2_reproduction.txt` (defect), `v3_2_2_pytest_full.txt` + full-scale run (`v3_2_2_full_generate.txt`: EX-02 = 15 detected post-injection, baseline 0, blind F1 = 1.0).

## 2. API destructive-path protection — CRITICAL → VERIFIED FIXED + EXTENDED

- **Defect:** string comparison let `sqlite:////C:/...` (four-slash) reach execution — HTTP 500 instead of 400 (`v3_2_2_reproduction.txt`, DEFECT 2).
- **Files changed (V3.2.2):** `src/yottaflex/config.py` (`canonical_sqlite_path`), `src/yottaflex/api/main.py` (canonical guard). **V3.2.3 additions:** `tests/unit/test_api_safety.py` (double-slash variant + junction-alias test).
- **Implementation:** canonicalization resolves traversal (`./`, `../`), duplicate separators (`//`), backslashes, three/four-slash forms, URL-encoding, scheme case, Windows case-insensitivity and trailing dot/space aliasing; existing symlinks/junctions are resolved by `Path.resolve()`. In-place detection = canonical equality before any execution.
- **Tests now:** canonical unit + **7 parametrized refusals** (`dot_segment`, `parent_segment`, `double_slash_mid`, `backslashes`, `four_slash_absolute`, `case_variant`, `trailing_dot`) + **junction alias** (directory junction through the project; skips only if `mklink /J` unavailable — it ran and passed) + live-DB-untouched assertions.
- **Verification evidence:** `docs/evidence/v3_2_2_reproduction.txt` (defect), `docs/evidence/v3_2_3_pytest_full.txt` (all refusals; junction ran, 0 skips).

## 3. Prevent accidental export overwrites — CRITICAL → FIXED IN V3.2.3 (gap closed)

- **Defect (V3.2.2 residual):** a run against the default database still wrote to the committed `data/exports` — a **starter-scale run could overwrite the committed full-scale exports**; repeat runs offered no permission gate.
- **Root cause:** default export destination was the committed deliverable folder and no overwrite-permission concept existed.
- **Files changed (V3.2.3):** `src/yottaflex/pipeline.py` (default destination now `data/generated/exports`; ValueError before any write when an existing export set — `checksums.json` — would be overwritten without `overwrite_exports=True`), `src/yottaflex/api/main.py` (`overwrite_exports` field + passthrough), `scripts/generate_data.py` (`--overwrite-exports`), `.gitignore` (`data/generated/`), tests `tests/unit/test_export_protection.py` (rewritten, 4 tests), `tests/unit/test_api_safety.py` (defaults + permission flows).
- **Behavior contract now:** committed `data/exports` can only be reached with **explicit `export_dir` AND `overwrite_exports=True`**; auxiliary/starter/API runs default to `data/generated/exports`; a refused run modifies nothing (fail-fast before engine creation).
- **Tests:** default-run to generated dir with committed hashes before/after (byte-identical); starter run with `overwrite_exports=True` still never touches committed exports; second write into an existing set → ValueError then succeeds with permission; explicit `data/exports` without permission → refused with hashes unchanged; API: default → generated dir + committed untouched, repeated run → 400 then 200 with permission.
- **Verification evidence:** `docs/evidence/v3_2_3_pytest_full.txt`.

## 4. SQL restoration integrity → VERIFIED (V3.2.2), unchanged

- **Defect:** manifest ignored; FK-neutral truncation passed (`v3_2_2_reproduction_round3.txt`).
- **Files changed (V3.2.2):** `scripts/restore_sql_export.py` (`load_manifest_counts`, manifest section in `verify_restoration`; atomic temp-restore flow from V3.2.1 preserved).
- **Contract:** every manifest table must exist with exact counts; FK re-enabled + `foreign_key_check`; `RESTORATION: PASS` prints only when all checks pass; failure preserves the target byte-for-byte (tests assert marker DB unchanged and `*.tmp-restore.*` cleanup).
- **Tests:** `tests/unit/test_restore_manifest.py` (2) + `tests/unit/test_restore_safety.py` (5).
- **Evidence:** `docs/evidence/v3_2_2_restore.txt` (full-scale PASS with manifest, 577,323 rows, refusal exit 3), `v3_2_3_pytest_full.txt`.

## 5. Opportunity loss reasons → VERIFIED + EXTENDED (open case)

- **Defect:** 0/1,063 lost opportunities had a reason (`v3_2_2_reproduction.txt`, DEFECT 6).
- **Files changed (V3.2.2):** `src/yottaflex/engines/opportunity.py` (deterministic `pick_loss_reason` over a documented 5-value vocabulary; applied on terminal `lost`). **V3.2.3 addition:** explicit open-opportunity test.
- **Tests now (3):** every lost has a valid reason; every won has none; **every open (new_lead/qualified/demo/proposal) has none and `lost_at` is null**; deterministic mapping across two independent same-seed runs.
- **Evidence:** full scale `lost=1063 lost_with_reason=1063 won_with_reason=0` (`v3_2_2_validate_data.txt`); suite output `v3_2_3_pytest_full.txt`.

---

## Full test suite (exact command and result)

Command (from `yottaflex-lead-scoring-v3.2.3`; venv interpreter with `PYTHONPATH` pinned to this copy; cache-free):

```
set PYTHONPATH=<v3.2.3>\src
set PYTHONDONTWRITEBYTECODE=1
python -m pytest tests/ -q -p no:cacheprovider
```

Result: **102 passed, 0 skipped, 1 warning in 151.17s — exit code 0.**
Failures: **none.** Raw output: `docs/evidence/v3_2_3_pytest_full.txt`.
(Previous release baselines preserved: `v3_2_2_pytest_full.txt` 96 passed; `v3_2_1_pytest_full.txt` 75 passed.)

## Tests added/changed in V3.2.3 (+6 items, 96 → 102)

| Test | Type | Purpose |
|------|------|---------|
| `test_export_protection.py::test_default_run_writes_to_generated_dir_never_committed` | new | default destination is separate; committed hashes unchanged |
| `test_export_protection.py::test_starter_run_with_overwrite_flag_still_never_touches_committed_exports` | new | permission alone never redirects to committed dir |
| `test_export_protection.py::test_overwrite_requires_explicit_permission` | new | refusal then success-with-permission (hashes checked) |
| `test_export_protection.py::test_explicit_committed_dir_requires_permission_and_preserves` | new | committed dir refused without permission |
| `test_api_safety.py::test_junction_alias_refused_without_confirmation` | new | junction/symlink-like alias cannot bypass (ran; skipped only if mklink unavailable) |
| `test_api_safety.py::test_equivalent_live_paths_refused_without_confirmation[double_slash_mid]` | new param | `//` form added to the refusal matrix |
| `test_api_safety.py::test_run_all_defaults_to_generated_dir_not_committed` | replaces V3.2.2 raise-test | new default semantics |
| `test_api_safety.py::test_run_all_second_run_requires_overwrite_permission` | new | 200 → 400 → 200 permission flow |
| `test_loss_reasons.py::test_open_opportunities_have_no_reason_and_are_not_lost` | new | open-opportunity coverage |

## Verification evidence index (V3.2.3)

| File | Content |
|------|---------|
| `docs/evidence/v3_2_3_pytest_full.txt` | 102 passed, 0 skipped, exit 0 (full suite) |
| `docs/evidence/v3_2_2_*.txt` | defect reproductions + V3.2.2 verification (referenced above) |

Committed exports were hashed before and after every test run in this task and remained byte-identical (asserted in tests; also verified via git status before commit).

## Remaining unresolved / open items

1. **Manifest-absent fallback (L25):** if a foreign export set ships without `dataset_manifest.json`, restore verification is weaker (source-DB/core checks only). Exports produced by this line always include the manifest.
2. **EX-02 evidence vocabulary (L26):** detection treats only the four intent event types as post-conversion evidence (conservative, documented).
3. **Full-scale reproducibility was not re-run in V3.2.3:** data generation is unchanged since V3.2.2 (this task changed only export destination semantics and tests/docs), so the V3.2.2 evidence (`v3_2_2_repro_starter/full.txt`) remains valid for the current generation code.
4. Accepted limitations from earlier releases (L1–L11, L15, L17–L19, L21–L23) unchanged.
5. Nothing pushed to GitHub; no submission performed — awaiting coordinator/owner review.
