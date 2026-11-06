# Engineering Audit — Consolidated Report

**Status: CURRENT as of V3.2.1 (2026-11-05).**
This single document replaces the original V3 audit and all its addenda. It contains exactly two kinds of content:

1. **Current state** — verified as of this revision (Sections 1–4, 6).
2. **Historical record** — the original V3 audit findings, clearly labelled and retained only for traceability (Section 5). Every historical finding listed there has since been remediated or superseded; nothing in Section 5 describes the current implementation.

No contradictory claims are permitted: any number in the "current" sections traces to a command output saved under `docs/evidence/`.

---

## 1. Scope and method

- System: YottaFlex Lead Scoring & Opportunity Management (FastAPI + Streamlit + SQLAlchemy/SQLite, seed 20261022).
- Method: source inspection, live command execution, and evidence capture. Test runs use a clean virtual environment; audits run read-only.
- Release candidate audited: `C:\Users\acer\yottaflex-lead-scoring-v3.2.1` (git history inherited and verified clean).

## 2. Current implementation status (verified)

| Area | Current state | Evidence |
|------|---------------|----------|
| Test suite | **75 passed** (clean venv, cache-free) | `docs/evidence/v3_2_1_pytest_full.txt` |
| Dataset volumes | 5,000 / 10,000 / 20,000 / 3,000 exact (companies/contacts/leads/opportunities) | `v3_2_1_full_generate.txt` |
| Full validation | exit 0; 24 checks, 0 critical; 378,460 business IDs GLOB-checked, 0 invalid; 0 collapsed stage timestamps; 0 opportunities without history | `v3_2_1_validate_data.txt` |
| Exports | 34 deliverables: 23 table CSVs + 4 JSONs + 7 SQL splits; largest 50.02 MB (<100 MB) | `v3_2_1_repo_audit.txt` |
| SQL restoration | **Atomic**: temp DB → schema/count/FK verification → `os.replace`; refuses overwrite without `--force` (exit 3); failure preserves original (exit 1) | `v3_2_1_pytest_full.txt`, `test_restore_safety.py` |
| Foreign keys | Re-enabled after load; `PRAGMA foreign_key_check` clean; violating inserts rejected | `v3_2_pytest_full.txt` (FK proof), script source |
| API safety | `POST /pipeline/run-all` requires `confirm_destructive` for live DB (HTTP 400 otherwise); separate `output_database_url`; `write_reports` guard | `tests/unit/test_api_safety.py` |
| Blind evaluation | Key-based P/R/F1 (no label circularity), null when undefined | `tests/integration/test_pipeline_exceptions.py` |
| Reproducibility | Two-run five-way comparison PASS (starter + full, seed 20261022) per the V3.2 methodology (single-process runs) | `v3_2_repro_starter.txt`, `v3_2_repro_full.txt` |
| Security | No secrets (101 files scanned); `.env.example` placeholders only; no auth (documented L1) | `v3_2_1_secret_scan.txt` |
| Repository | 121 tracked files before this revision; no `.db`, `.venv`, caches, or `seed_data.sql` in ANY commit; max object 50.02 MB | `v3_2_1_repo_audit.txt` |

## 3. Remediation ledger (findings → status)

| Finding (origin) | Status | Where fixed / verified |
|------------------|--------|------------------------|
| P0-1 no business IDs | FIXED | `ids.py`; `test_business_ids.py`; GLOB full-coverage check |
| P0-2 baseline had no natural duplicates | FIXED | `duplicate_gt` natural 741 + injected 10; `test_natural_duplicates.py` |
| P0-3 no export engine | FIXED | exporter writes 34 files; `test_export_engine.py` |
| P0-4 score leakage into opportunity selection/outcome | FIXED | propensity + factor outcomes; AST guard test; 129 low-score converters / 6,016 high-score non-converters |
| P0-5 circular P/R evaluation | FIXED | blind key-based evaluation; `test_pipeline_exceptions.py` |
| P0-6 collapsed stage timestamps | FIXED | per-step timestamps; full-coverage check reports 0 |
| P1 seed/history/FK/coverage/exactness items | FIXED | seed 20261022; `lead_status_history`; resolution history; typed consent FKs; converted-link FK; coverage metrics |
| P2 dashboard/dead code/perf/docs | FIXED | 9-section dashboard; dead code removed; consent metric 0.086 s; docs regenerated |
| L14 destructive `run-all` API | FIXED (V3.2) | confirmation gate + separate output DB; `test_api_safety.py` |
| L20 sampled stage-timestamp validation | FIXED (V3.2) | full SQL aggregate in `validate_data.py` |
| Restore could delete an existing target | FIXED (V3.2.1) | `--force` refusal + atomic temp-restore/replace; `test_restore_safety.py` (5 tests) |
| Validation sampled `.limit(50)` | FIXED (V3.2) | full-record range + weighted-formula identity; `test_validation_complete.py` |

## 4. Verification evidence index

| Evidence file | Content |
|---------------|---------|
| `docs/evidence/v3_2_1_pytest_full.txt` | 75 passed (current suite) |
| `docs/evidence/v3_2_1_full_generate.txt` | full-scale generation output |
| `docs/evidence/v3_2_1_validate_data.txt` | full validation JSON (exit 0) |
| `docs/evidence/v3_2_1_repo_audit.txt` | large-file + tracked-file audit |
| `docs/evidence/v3_2_1_secret_scan.txt` | secret scan (no hits) |
| `docs/evidence/v3_2_1_hashseed_finding.txt` | cross-process determinism finding |
| `docs/evidence/v3_2_*.txt` | V3.2 baseline evidence (preserved): generation, validation, restore, reproducibility (starter+full), pytest baseline/full |

## 5. Historical record — original V3 audit findings (HISTORICAL ONLY)

> The following describes the system **as it was at the V3 audit (2026-11-04)**. It is retained for traceability. None of these statements describes the current implementation; see Sections 2–3 for current status.

- No business IDs existed (integer PKs only) — remediated (P0-1).
- Baseline had zero natural duplicates; `baseline_natural_dupes` flag was dead config — remediated (P0-2).
- No export engine existed; only `pipeline_result.json` was written — remediated (P0-3).
- Opportunity selection ordered by `lead_score` desc and outcomes used score-based win probability — score leakage, remediated (P0-4).
- Exception evaluation matched detections via labels attached from the injection log (circular); F1 never computed; docs claimed P=R=1.0 — remediated (P0-5).
- Stage-history rows shared one final timestamp per opportunity — remediated (P0-6).
- Suite had 29 tests; later V3.1 release reported 64; V3.2 73; current 75.
- Known-limitation IDs L1–L22 were introduced across the original audit and subsequent releases; current statuses live in `KNOWN_LIMITATIONS.md`.

## 6. Open findings (current)

| Item | Details | Disposition |
|------|---------|-------------|
| Cross-process determinism (`salesrep_territory` row order) | Hash-seed-dependent set iteration in `generate_reference_data` changes bridge-row ids across processes; content sets identical; affects 4 files byte-wise | Documented; NOT fixed (out of V3.2.1 scope — touches data generation). See `v3_2_1_hashseed_finding.txt` and L24. Recommended fix: `sorted(covered)` + regenerate exports + full-scale rerun, pending owner approval |
| L1–L11, L15, L17–L19, L21–L23 | Accepted release limitations with mitigations | `KNOWN_LIMITATIONS.md` release disposition (V3.2) |

## 7. Components preserved (not to be rewritten)

Scoring formula and explainability, consent gate, routing/assignment determinism, stage-history append-only engine, baseline-clean-then-inject architecture, API route set, engine boundaries, and the fixed technology stack — all unchanged through V3.2.1.

---

*Consolidated 2026-11-05 (V3.2.1). Supersedes all previous revisions of this document.*
