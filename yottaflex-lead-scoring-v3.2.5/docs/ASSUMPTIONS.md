# Assumptions

Approved defaults from Phase-0 analysis (A01–A22). Deviations must be documented here.

| ID | Assumption |
|----|------------|
| A01 | Territory and Product are **supporting** tables (not among the 11 required entities); bridges implement M:N. |
| A02 | Campaigns=30, SalesReps=80, Activities≈320K at full scale (tunable in settings.yaml). |
| A03 | Conversion := lead.status='converted' with linked Opportunity. |
| A04 | Eligible leads := not disqualified, not opted_out, not duplicate-marked. |
| A05 | **Superseded by P0-B.** Baseline contains controlled natural duplicates (A25); injected duplicates remain separate (origin label). |
| A06 | Dedup soft-marks `is_duplicate_of`; never hard-deletes. |
| A07 | ~50% of leads link to an existing Contact; each contact links to at most one lead. |
| A08 | Single batch scoring pass at base+61d; activities span base+0..60d. |
| A09 | MVP: one score per lead per run; explanation rows support future versioning. |
| A10 | **Superseded by P0-D.** Exactly 3,000 opportunities via propensity selection on documented business factors (A27) — never by final score. |
| A11 | StageHistory append-only enforced at application layer + tests (no SQLite triggers). |
| A12 | Authentication/authorization out of scope for local MVP. |
| A13 | Baseline scorer is correct (no leakage); EX-02 detects **injected** bad explanations. |
| A14 | EX-01 injected as non-blocked outreach tasks on revoked-consent leads. |
| A15 | Injection quotas: consent 20, temporal 15, territory 15, dup-opp 10, stage-gap 15. |
| A16 | GT tables isolated: scoring module must not import them (pytest guard). |
| A17 | Dimension normalization uses fixed caps (100) after rule points; fit base = company size_score. |
| A18 | Lead status history is not a separate table; status + updated_at only. |
| A19 | FastAPI is the programmatic contract; Streamlit is the analyst UX — both required by stack. |
| A20 | Project path: `C:\Users\acer\yottaflex-lead-scoring\`. |
| A21 | Opportunity amounts are synthetic (product-line base A¬ lead_id hash); win rate is not amount-weighted. |
| A22 | "Remove duplicates" in workflow = soft-mark + report (aligns with never-delete). |
| A23 | Business IDs are deterministic external keys (CO/CON/LEAD/OPP/ACT/TASK); integer PKs stay as internal surrogates. ID year=2026 per spec (independent of base_datetime 2025). |
| A24 | Natural key uniques (company.domain, contact.email_normalized) are non-unique indexes so natural duplicates are representable (soft-dedup marks them). |
| A25 | Natural duplicate volumes: companies 60/5000, contacts 150/10000, leads 400/20000, opportunities 15/3000 (configurable; capped at 10% of each pool at small scales). Total row counts stay exact — dupes live inside the volumes. |
| A26 | Final dataset holds exactly 3,000 opportunities: baseline creates target−injected dup quota, injection adds quota. Natural dup opportunities are 15 of the baseline rows. |
| A27 | Opportunity selection propensity = intent .15 + engagement .10 + budget .25 + fit .10 + follow-up .15 + jitter .25 (weights in settings.yaml). Won/lost/open outcomes use documented business factors with open_rate 0.15. lead_score/lead_category are never inputs (AST-guarded test). |
| A28 | Held-out split: 30% of leads flagged `eval_split='heldout'` at generation; conversion-rate-by-score-bucket metrics report dev and held-out separately. |
| A29 | Exception evaluation is blind (key-based TP/FP/FN, P/R/F1). Labels are attached post-evaluation only for display. |
| A30 | Deterministic seed is 20261022; reproducibility = byte-identical export checksums across two fresh runs. |
| A31 | Lead status history starts at lead creation (initial `None -> new` row); task/assignment/scoring/pipeline/convert transitions all append via one helper. |
| A32 | Re-detection of exceptions hard-deletes prior exception_record rows (locked-in design); resolution history snapshots identity so it survives re-detection. |
| A33 | Stale-lead definition: open status (new/scored/assigned) with no activity since base_datetime+30d. |
| A34 | Consent typed FK columns mirror (subject_type, subject_id); consistency enforced by CHECK constraint + generation-time population. |

## Contradictions resolved (with rationale)

| # | Contradiction | Resolution |
|---|---------------|------------|
| C1 | Remove duplicates vs never overwrite/delete | Soft-mark + validation report (A06/A22) |
| C2 | EX-02 implies buggy scores vs prevent leakage | Baseline correct; inject bad scores (A13) |
| C3 | 11 entities vs Territory/Product need | Supporting tables (A01) |
| C4 | Exact 3K opps vs organic funnel | Score-rank constructive selection (A10) |

## Configurable, not hard-coded

- Scoring weights, category thresholds → `settings.yaml`
- Score rules → `score_rules.yaml`
- Task due days, consent rates, injection quotas → `settings.yaml`
