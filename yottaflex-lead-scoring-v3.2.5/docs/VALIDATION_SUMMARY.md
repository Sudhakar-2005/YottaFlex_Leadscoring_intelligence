# Validation Summary - YottaFlex Lead Scoring Platform

Generated: 2026-11-04 (P0 complete) - seed 20261022, full scale. Updated: 2026-11-05 (V3.2 stabilization) - see addendum at the end.

## Dataset volumes (exact)

| Metric | Target | Actual |
|--------|--------|--------|
| Companies | 5,000 | 5,000 |
| Contacts | 10,000 | 10,000 |
| Leads | 20,000 | 20,000 |
| Opportunities | 3,000 | 3,000 |
| Campaigns | 30 | 30 |
| Sales Reps | 80 | 80 |

Opportunity composition: 2,975 primary + 15 natural duplicate + 10 injected duplicate = 3,000.

## P0 remediation status

### P0-A: Business IDs ✅
All entity business IDs deterministic, zero-padded, unique, FK-consistent across CSV/JSON/SQL exports:
CO-000001, CON-000001, LEAD-2026-000001, OPP-2026-000001, ACT-LEAD-2026-000001-001, TASK-LEAD-2026-000001-001.

### P0-B: Natural duplicates ✅
| Entity | Natural (config) | Soft-marked | GT origin |
|--------|------------------|-------------|-----------|
| Companies (domain) | 60 | 60 | natural |
| Contacts (email) | 150 | 150 | natural |
| Leads (email) | 400 | 400 | natural |
| Opportunities (lead group) | 15 | 15 | natural |
| Injected EX-04 | 10 | 10 | injected |
| **Total** | **741 natural + 10 injected** | | duplicate_gt |

Duplicate detection rate = 751/751 = 1.0.

### P0-C: Export engine ✅
25 files under `data/exports/`: 21 table CSVs + ground_truth.json + dataset_manifest.json + validation_summary.json + checksums.json + seed_data.sql. *(V3 replaced seed_data.sql with SQL splits; V3.2 exports = 34 files - see addendum.)*
Two-run reproducibility: **PASS** (starter scale, seed 20261022 — byte-identical checksums across 25 files).

### P0-D: Leakage-free opportunity/outcome generation ✅
- Selection: propensity from documented business factors (budget .25, jitter .25, follow-up .15, intent .15, engagement .10, fit .10) — **never lead_score** (AST-guarded pytest regression test).
- Outcome: win P from fit/intent/budget/follow-up/engagement; 12.3% open (367 demo/proposal).
- Low-score converters (<60): **129** (was 0 before)
- High-score non-converters (≥80): **6,016**
- Converted score range: 36–100 (was 90–100)
- Held-out: 5,907/19,484 scored leads (30.3%) in heldout split with separate conversion metrics.

### P0-5: Blind exception evaluation ✅
Method: key-based matching (detections ↔ GT by record/lead id); result labels attached post-evaluation only. Iterated semantics verified (sample first 500 opps → 0 collapsed timestamps).

| Scenario | GT | Detected | TP | FP | FN | P | R | F1 |
|----------|----|----|----|----|----|---|---|----|
| EX-01 opted-out contacted | 20 | 20 | 20 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| EX-02 temporal leakage | 15 | 15 | 15 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| EX-03 territory mismatch | 15 | 15 | 15 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| EX-04 dup opportunity | 25 | 25 | 25 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| EX-05 stage history gaps | 15 | 15 | 15 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| **Overall** | **90** | **90** | **90** | **0** | **0** | **1.0** | **1.0** | **1.0** |

2026-11-04 re-certified P0 GEN2 — these are measured blind-evaluation values, not defaults; null metrics are returned when undefined (no GT/detections).

### P0-6: Stage timestamps ✅
Every path step carries its own timestamp; 0/500 sampled opportunities collapsed (before: 1 distinct time per opp).

## KPI Definitions (raw data)

| KPI | Formula | Value |
|-----|---------|-------|
| lead_conversion_rate | converted / eligible (non-dup, not dq/opt-out) | 2,975 / 19,484 = **0.1527** |
| opportunity_win_rate | won / (won+lost) | 1,545 / 2,608 = **0.5924** |
| lead_qualification_rate | qualified+converted / total | 14,097 / 20,000 = 0.7049 |
| assignment_coverage | assigned / assignable | 19,484 / 19,484 = **1.0** |
| consent_compliance | compliant outreach / total outreach | 14,746 / 19,504 = **0.7561** |
| consent_coverage_rate | granted email consent / non-dup leads | 15,489 / 19,484 = **0.795** |
| opt_out_rate | revoked/expired consent leads / non-dup leads | 1,716 / 19,484 = **0.0881** |
| stale_lead_rate | open leads w/o activity since base+30d / open leads | 17 / 1,121 = **0.0152** |
| duplicate_detection_rate | detected GT / total duplicate GT | 751 / 751 = **1.0** |
| open_opportunities | demo+proposal+new_lead | **392** |

## Funnel (raw counts)

| Stage | Leads |
|-------|-------|
| total_leads | 20,000 |
| scored | 19,484 |
| assigned | 19,484 |
| working | 18,363 |
| qualified | 14,097 |
| converted | 2,975 |

## Category + Stage Distributions

**Lead categories:** cold 750, hot 8,175, nurture 4,766, warm 5,793

**Opportunity stages:** demo 80, lost 1,063, new_lead 25, proposal 287, won 1,545 (367 open at demo/proposal: 80 demo + 287 proposal; 25 dup ops at new_lead)

## P1 infrastructure (reproducibility, histories, FKs)

- Deterministic seed 20261022; `scripts/generate_data.py` (--scale), `validate_data.py`, `compare_reproducibility.py` (two-run checksum compare — starter scale PASS)
- LeadStatusHistory: 90,657 rows covering all 20,000 leads; initial `None→new` + all transitions (scored/assigned/working/qualified/converted) — timelines reconstructable, append-only
- ExceptionResolutionHistory: PATCH writes snapshotted transition rows; survives re-detection
- Consent typed FKs: 0 null lead/contact FKs (lead/contact subjects); CHECK constraints enforce
- Converted-link FK: 2,975 links resolve; `PRAGMA foreign_key_check` clean
- Coverage metrics: opt-out 8.8%, stale 1.5%, disqualified 0.0%, consent coverage 79.5%

## Baseline exception detection (pre-injection)

15 records — all EX-04 from natural duplicates (origin=natural). Zero EX-01/02/03/05. No injected anomalies in baseline. ✅

## Explainability spot checks

- Formula: Score = round(0.40*Fit + 0.35*Intent + 0.25*Engagement), caps 100 each
- lead_score_explanation rows persist weights_json + rules_fired_json for replay
- Temporal cutoff: future activities excluded (tested)

## Data quality findings

- 751 controlled duplicates (soft-marked, originals preserved)
- 0 hard violation active lead (injections only)
- 20 blocked attempted contacts counted as prevented (4,738 blocked consent tasks)
- 25 duplicate-opportunity groups detected (15 natural + 10 injected), all from duplicate_gt

## Commands to regenerate

```bash
python scripts/generate_data.py --scale full
python scripts/validate_data.py
python scripts/compare_reproducibility.py --scale starter
python -m pytest tests/ -q
```

## V3.2 addendum (2026-11-05, full scale, seed 20261022)

- Exports: **34 files** = 23 table CSVs + ground_truth.json + dataset_manifest.json + validation_summary.json + checksums.json + sql/00_schema.sql .. sql/06_ground_truth.sql
- Full-dataset validation (`scripts/validate_data.py`): **passed=true**, exit 0; engine checks_run=24, critical issues=0
- Business-ID format: ALL 378,460 rows validated via SQL GLOB patterns (company 5,000; contact 10,000; lead 20,000; opportunity 3,000; activity 320,956; task 19,504) - 0 invalid
- Score validation: ALL 19,484 scored leads checked (range 0-100 + weighted-formula identity; no sampling)
- Stage checks: 0 collapsed timestamps across ALL opportunities; 0 opportunities missing history
- SQL restoration: PASS (577,308 rows / 23 tables / 0 FK violations; refuses overwrite without --force)
- Reproducibility (starter): PASS on all 7 categories (row counts, file counts, checksums files+tables, referential integrity, validation reports identical, both runs valid)
- Reproducibility (full): PASS on all 7 categories (577,308 rows, 33 checksummed files + checksums.json)
- Tests: 73 passed in a clean venv; evidence in docs/evidence/

## Commands to regenerate (V3.2)

```bash
python scripts/generate_data.py --scale full
python scripts/validate_data.py
python scripts/restore_sql_export.py --db data/restored.db
python scripts/compare_reproducibility.py --scale starter
python scripts/compare_reproducibility.py --scale full
python -m pytest tests/ -q
```

## V3.2.2 addendum (2026-11-05, full scale, seed 20261022)

- Generation changed in V3.2.2 (real EX-02 post-conversion evidence activity, deterministic loss reasons, sorted bridge-row order); dataset and exports regenerated; full-scale reproducibility re-run.
- Total rows: **577,323** across 23 tables (activities 320,971, including 15 injected post-conversion evidence events).
- Lost opportunities: **1,063 / 1,063 carry a deterministic `loss_reason`**; 0 won opportunities carry one.
- Business IDs: **378,475 validated, 0 invalid** (GLOB, all rows).
- SQL restoration: **PASS with `dataset_manifest.json` verification** (all 23 tables), atomic replace, `--force` refusal semantics intact.
- Reproducibility: starter PASS 7/7 (58,115 rows); full PASS 7/7 (577,323 rows); checksums byte-identical.
- Cross-process determinism: identical exports across `PYTHONHASHSEED` 1 vs 2 (V3.2.2 fix; proof in evidence).
- Tests: **96 passed**; all V3.2.2 evidence under `docs/evidence/v3_2_2_*`.
