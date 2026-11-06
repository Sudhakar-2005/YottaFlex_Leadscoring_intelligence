# V3.2.2 Fix Report — Critical Defect Resolution

Date: 2026-11-05 · Working copy: `C:\Users\acer\yottaflex-lead-scoring-v3.2.2` (from V3.2.1, git history preserved)
Process: reproduce before fixing, regression test per fix, full suite after. No framework/architecture changes. Nothing pushed.

Reproduction evidence (pre-fix): `docs/evidence/v3_2_2_reproduction.txt`, `v3_2_2_reproduction_round2.txt`, `v3_2_2_reproduction_round3.txt`

---

## P0-1 — EX-02 marker leakage (GT-dependent detection)

- **Original defect:** `TemporalLeakageDetector` flagged explanations containing the injected marker `INJECTED_POST_CONVERSION_EVENT` / `post_conversion: true`; the injected scenario contained no real post-conversion evidence, so detection was circular (detector read what the injector wrote).
- **Root cause:** detection logic keyed on ground-truth-ish rule payload fields in `rules_fired_json`; injection planted only a magic marker.
- **Reproduced:** with markers present → 15 detections; after stripping all marker fields (timestamps/data untouched) → **0 detections**; post-conversion activities in data → **0**. (`v3_2_2_reproduction.txt`, DEFECT 1)
- **Changed files:** `src/yottaflex/engines/anomaly_injection.py`, `src/yottaflex/engines/exceptions.py`
- **Implementation:**
  - Injection now creates the *actual* violation: a real post-conversion intent activity (`demo_request` at `converted_at + 1d`, with a proper `ACT-...` business ID) plus a stale score explanation (`scored_at = converted_at + 2d`) carrying only a normal `INTENT_DEMO_REQUEST` rule — **no marker fields anywhere**.
  - Detector rewritten to independent evidence only: candidates = explanations joined to leads where `scored_at > converted_at`; confirmed when an intent activity exists with `event_time` in `(converted_at, scored_at]`. Evidence JSON cites the activity id/type/timestamps. Ground truth stays in `anomaly_injection_log`/`ground_truth_exception` (evaluation remains blind).
- **Regression tests:** `tests/unit/test_ex02_independent_detection.py` (4): no-marker data still fully detected with real activity evidence per detection; deleting post-conversion activities removes detections (no marker crutch); legitimate pre-conversion events → zero false positives; blind P/R/F1 recomputed from measured TP/FP/FN.
- **Actual result:** all 4 pass; full-suite EX-02 still 15 detected post-injection, baseline 0.
- **Remaining limitations:** the independent rule treats only the four intent event types as evidence (documented, conservative); scoring-cutoff semantics beyond conversion (e.g., re-scores of non-converted leads) are out of scope of the injected scenario.

## P0-2 — API path-normalization bypass

- **Original defect:** the live-DB guard compared **URL strings**; a four-slash absolute URL (`sqlite:////C:/.../data/yottaflex.db`) passed the guard and reached execution (**HTTP 500** instead of 400) — on platforms where SQLite accepts that form it targets the live file.
- **Root cause:** `Settings.resolved_database_url()` does not normalize four-slash/case/percent-encoded forms; the endpoint compared raw strings.
- **Reproduced:** `four-slash-abs → HTTP 500 (400 = correctly refused)`; resolution table in `v3_2_2_reproduction.txt` (DEFECT 2).
- **Changed files:** `src/yottaflex/config.py` (new `canonical_sqlite_path()`), `src/yottaflex/api/main.py` (guard compares canonical paths)
- **Implementation:** canonicalization handles scheme case, URL-encoding, `./`/`../`, backslashes, three-slash relative, three-slash drive-absolute, four-slash absolute, Windows case-insensitivity (`normcase`) and trailing dot/space aliasing. In-place detection = canonical equality; `:memory:`/non-SQLite fall back to string comparison (still treated as non-live).
- **Regression tests:** `tests/unit/test_api_safety.py`: `test_canonical_sqlite_path_normalizes_equivalents` + 6 parametrized refusal cases (dot, parent, backslashes, four-slash, upper-case, trailing-dot) — each must return **400** without `confirm_destructive`.
- **Actual result:** 7/7 pass; the previously bypassing four-slash now returns 400; separate DB still runs without confirmation.
- **Remaining limitations:** canonicalization relies on Python/OS path semantics; exotic aliases (8.3 short names, junctions) are not enumerated — path equality for those would still differ, but any representation that SQLite accepts as the live file is caught for the forms above (tested).

## P0-3 — Export overwrite protection

- **Original defect:** any pipeline run with `write_reports=True` (the API default) exported to the committed `data/exports` — a custom-DB run overwrote committed deliverables.
- **Root cause:** export destination hardcoded to `PROJECT_ROOT/data/exports` regardless of target DB.
- **Reproduced:** custom-DB mini run changed `checksums.json` and `pipeline_result.json` hashes; **29 export files + 1 report restored from HEAD** (`v3_2_2_reproduction_round2.txt`, DEFECT 3).
- **Changed files:** `src/yottaflex/pipeline.py`, `src/yottaflex/api/main.py`, `scripts/generate_data.py` (optional `--export-dir`)
- **Implementation:** `run_full_pipeline(..., export_dir=None)`; exports allowed only when (a) target = default DB (current behavior) or (b) explicit `export_dir`. Non-default target without `export_dir` → `ValueError` **before any DB/export write** (fail-fast). Reports mirror the destination (`<export_dir>/../reports/pipeline_result.json`, i.e., `data/reports` by default). API adds `export_dir` and maps `ValueError` → HTTP 400.
- **Regression tests:** `tests/unit/test_export_protection.py` (2) + API tests (`test_run_all_custom_db_write_reports_requires_export_dir` 400 with no artifacts created; `test_run_all_custom_db_with_export_dir` 200 + repo exports byte-identical).
- **Actual result:** all pass; committed exports untouched by custom runs.
- **Remaining limitations:** explicit `export_dir` pointed at the committed folder is the caller's deliberate choice (allowed); docs state the contract.

## P1-4 — SQL manifest verification

- **Original defect:** restoration ignored `dataset_manifest.json`; FK-neutral truncation (activities) of exports **passed** with exit 0 when no source DB was shipped.
- **Root cause:** verification only used a source DB (when available) + core-non-empty check; far more permissive than the deliverable contract.
- **Reproduced:** activities truncated 2,368 → 100 rows (valid SQL): `RESTORATION: PASS`, exit 0 (`v3_2_2_reproduction_round3.txt`). (Lead/opportunity truncations were already caught by FK checks — noted in evidence.)
- **Changed files:** `scripts/restore_sql_export.py`
- **Implementation:** new `load_manifest_counts()` (reads `dataset_manifest.json` next to `sql/`); `verify_restoration` verifies every manifest table exists and matches expected row counts exactly; runs before FK/source checks; target DB still replaced only after all checks (atomic flow unchanged from V3.2.1). Manifest absence → explicit NOTE + fallback to source-DB checks.
- **Regression tests:** `tests/unit/test_restore_manifest.py` (2): truncated activities rejected (exit 1, "manifest row-count mismatches", existing target preserved byte-identical); authentic exports show `OK: row counts match dataset_manifest.json`.
- **Actual result:** both pass; full-scale restoration against real exports: `OK: row counts match dataset_manifest.json for all 23 tables` (577,323 rows).
- **Remaining limitations:** fallback path when a manifest is absent is necessarily weaker (source DB or core checks only); exports produced by this release always include the manifest.

## P1-5 — Deterministic generation (hash-seed)

- **Original defect:** `generate_reference_data` iterated a Python `set` of territory codes; `salesrep_territory` bridge-row ids changed across processes (L24).
- **Root cause:** hash-seed-dependent set iteration order.
- **Reproduced:** separate processes with `PYTHONHASHSEED=1` vs `2` → different `salesrep_territory.csv` hashes (`v3_2_2_reproduction.txt`, DEFECT 5).
- **Changed files:** `src/yottaflex/engines/data_generator.py` — `for tc in sorted(covered):`
- **Regression tests:** `tests/unit/test_hashseed_determinism.py` (2): two separate subprocess runs with different hash seeds → **identical full checksum sets**; bridge rows per rep are in sorted territory-code order.
- **Actual result:** post-fix proof `A(seed=1) == B(seed=2): True` (`v3_2_2_hashseed_fixed.txt`). L24 resolved.
- **Remaining limitations:** none for the fixed path; any future set iteration over string values must keep the same discipline (noted in code review guidance).

## P1-6 — Opportunity loss reasons

- **Original defect:** `Opportunity.loss_reason` was never populated (1,063/1,063 lost had NULL at full scale).
- **Root cause:** advancement never set the column.
- **Reproduced:** mini run `lost=10; with loss_reason=0` (`v3_2_2_reproduction.txt`, DEFECT 6).
- **Changed files:** `src/yottaflex/engines/opportunity.py`
- **Implementation:** deterministic `pick_loss_reason(opportunity_id)` (FNV-1a hash over a 5-value business vocabulary: no_decision_timing, competitor_selected, budget_frozen, lost_contact, requirements_mismatch) applied when an opportunity finishes at `lost`; won/open/duplicate rows never receive one.
- **Regression tests:** `tests/unit/test_loss_reasons.py` (2): every lost has a valid reason and every won has none; identical `(lead, stage, reason)` mapping across two independent same-seed runs.
- **Actual result:** full scale now `lost=1063 lost_with_reason=1063 won_with_reason=0`; both tests pass.
- **Remaining limitations:** reasons are synthetic-but-plausible assignments (no CRM narrative source); vocabulary configurable later via settings if desired.

---

## Verification summary (actual command outcomes)

| Check | Result | Evidence |
|-------|--------|----------|
| Full suite | **96 passed** (exit 0) | `v3_2_2_pytest_full.txt` |
| Full generation | 3,000 opps exact; 90 detections; F1 1.0 | `v3_2_2_full_generate.txt` |
| Full validation | exit 0; 24 checks; 0 critical; 378,475 IDs valid | `v3_2_2_validate_data.txt` |
| SQL restoration | PASS incl. manifest; refusal exit 3 intact | `v3_2_2_restore.txt` |
| Starter reproducibility | PASS 7/7 | `v3_2_2_repro_starter.txt` |
| Full reproducibility | PASS 7/7 (577,323 rows) | `v3_2_2_repro_full.txt` |
| Cross-process determinism | PASS (identical across hash seeds) | `v3_2_2_hashseed_fixed.txt` |

## Exact changed-file list (V3.2.2)

| File | Change |
|------|--------|
| `src/yottaflex/config.py` | `canonical_sqlite_path()` |
| `src/yottaflex/api/main.py` | canonical guard, `export_dir` field, ValueError→400 |
| `src/yottaflex/pipeline.py` | export protection + explicit destination + fail-fast, reports mirror destination |
| `src/yottaflex/engines/anomaly_injection.py` | real EX-02 evidence (activity + stale score), no markers |
| `src/yottaflex/engines/exceptions.py` | EX-02 detector rewritten (timestamps + activity evidence only) |
| `src/yottaflex/engines/data_generator.py` | `sorted(covered)` deterministic bridge rows |
| `src/yottaflex/engines/opportunity.py` | deterministic loss reasons |
| `scripts/restore_sql_export.py` | manifest verification section |
| `scripts/generate_data.py` | optional `--export-dir` |
| tests | +5 new files, +21 tests (total 96) |
| data exports/reports | regenerated for the changed generation (committed) |
| docs | README, TESTING, VALIDATION_SUMMARY, KNOWN_LIMITATIONS + 2 new reports + 9 evidence files |

## Remaining limitations

- L24 (hash-seed determinism): **RESOLVED** in V3.2.2 (evidence above).
- Manifest fallback weakness when `dataset_manifest.json` is absent (documented, L25).
- EX-02 evidence limited to the four intent event types (documented, L26).
- All previously accepted limitations (L1–L11, L15, L17–L19, L21–L23) remain as documented in `KNOWN_LIMITATIONS.md`.
