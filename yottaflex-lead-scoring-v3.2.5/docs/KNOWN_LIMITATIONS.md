# Known Limitations

Status legend: OPEN · RESOLVED (kept for traceability, marked with the release that fixed it)

| # | Limitation | Impact | Mitigation / future work | Status |
|---|------------|--------|---------------------------|--------|
| L1 | No authentication/authorization on API | Local trusted use only | Add API key/JWT before any shared deployment | OPEN |
| L2 | SQLite single-writer | Not for concurrent production load | Postgres when multi-user needed | OPEN |
| L3 | Lead status history not a separate audit table | Status changes only on `updated_at` | LeadStatusHistory table added with full timeline + API endpoint | RESOLVED (P1) |
| L4 | StageHistory append-only is app-enforced, not DB triggers | Raw SQL could violate | Add SQLite triggers or CHECK constraints later | OPEN |
| L5 | One scoring pass per pipeline run | No incremental re-score API | Score versioning schema already supports N explanations | OPEN |
| L6 | Consent model is latest-row-wins per channel | Complex multi-consent histories simplified | Full consent ledger query API | OPEN |
| L7 | Dedup uses exact email/domain only | No fuzzy name+company matching | Add phonetic/fuzzy keys if needed | OPEN |
| L8 | Opportunity amounts synthetic; win rate not revenue-weighted | KPIs are count-based | Weighted win rate if finance data exists | OPEN |
| L9 | Streamlit dashboard not covered by automated tests | UI regressions possible | Playwright/screenshot tests later | OPEN |
| L10 | Re-running injection without full baseline regen can double-count | Prefer full pipeline run | Idempotent injection clears GT/injection log first | OPEN |
| L11 | Assignment capacity reloaded once per run | Concurrent assignment not considered | Transactional capacity reservation | OPEN |
| L12 | 0 unassignable leads at full scale | none | — | RESOLVED (V3: coverage 100%) |
| L13 | Natural duplicates suppressed in baseline | Real-world dupe rate not exercised | Natural dupes generated in baseline (60/150/400/15) with GT separation | RESOLVED (P0-B) |
| L14 | `pipeline/run-all` API rewrites the same DB file | Destructive without warning | Confirmation gate + separate `output_database_url` + `write_reports` flag | RESOLVED (V3.2) |
| L15 | No PII masking in exports | Emails/names in cleartext (synthetic data) | Masking layer if real data introduced | OPEN |
| L16 | Git binary not installed on host | No direct git CLI | Repo initialized with dulwich (standard format); push from a machine with git | MITIGATED (V3.1) |
| L17 | Natural duplicate counts are fixed config (60/150/400/15) | Baseline duplicates are controlled, not measured from real systems | Estimate volumes from data profiling for production parity | OPEN |
| L18 | Held-out split is a reporting split only | Rule-based scorer has no fitting step | Add fit/predict split if a learned model is introduced | OPEN |
| L19 | EX-04 natural vs injected dup groups detected identically | Separation relies on duplicate_gt origin labels | Detector could classify origin heuristically | OPEN |
| L20 | validate_data.py sampled stage timestamps (first 500 opps) | Sampling could miss collapse elsewhere | Full SQL aggregate over ALL opportunities | RESOLVED (V3.2) |
| L21 | resolved_at in exception resolutions uses wall clock (manual PATCH) | Non-deterministic timestamps for post-generation manual actions | Clock injection for analytic use | OPEN |
| L22 | Disqualified/opted_out lead statuses never occur in generated baseline | No lifecycle process generates them | Add lifecycle injector if demo needs those states | OPEN |
| L23 | Full-scale reproducibility (~10 min, two 20K runs) not in default CI suite | Determinism is verified only when the script is run | CI job invoking `compare_reproducibility.py --scale full` | OPEN |
| L24 | Cross-process determinism: hash-seed-dependent set iteration changed `salesrep_territory` bridge-row ids across processes | none (fixed) | Iterate `sorted(covered)` in `generate_reference_data`; cross-process proof: identical checksums across hash seeds (`docs/evidence/v3_2_2_hashseed_fixed.txt`) | RESOLVED (V3.2.2) |
| L25 | Restore verification falls back to source-DB/core checks when `dataset_manifest.json` is absent from an export set | Weaker truncation detection for foreign/legacy export sets | Exports produced by this release always include the manifest; keep manifests alongside `sql/` when transporting exports | OPEN |
| L26 | EX-02 detector treats only the four intent event types (demo_request, pricing_inquiry, form_submit, content_download) as post-conversion evidence | Non-intent post-conversion activity (e.g. plain page_view) is not flagged | Conservative by design; extend the evidence vocabulary if the scoring model starts consuming other event types | OPEN |

---

## Release disposition (V3.2, 2026-11-05)

Decision: **all OPEN limitations are formally accepted for the 2026-11-06 submission.**
None of them blocks the challenge requirements; each is documented with its mitigation
path and carried as post-release backlog. Grouped rationale:

| Group | Items | Rationale |
|-------|-------|-----------|
| Security & privacy | L1, L15 | Local-only MVP with synthetic data; authentication and PII masking are required only before any shared deployment with real data |
| Infrastructure | L2, L11 | SQLite is the assigned stack; batch pipeline does not require concurrent writers or transactional capacity reservation |
| Model & reporting | L5, L6, L7, L8, L9, L17, L18, L19, L21, L22 | Rule-based MVP scope is complete; each item is an enhancement (incremental scoring, consent ledger, fuzzy dedup, weighted KPIs, UI tests, lifecycle states) tracked for future releases |
| Process & CI | L10, L23 | Mitigated by the documented full-run procedure (`generate_data.py` performs a complete baseline regeneration); CI gating of full-scale reproducibility is planned work |
| Resolved/mitigated | L3, L12, L13, L14, L16, L20 | Fixed in P0-B/P1/V3/V3.2 or mitigated (git via dulwich); retained in the table for traceability |

V3.2.2 update: L24 resolved (sorted bridge-row generation + cross-process proof); L25/L26 added as new accepted items.

Post-release backlog priority order: L1 (API auth) -> L23 (CI reproducibility job) ->
L9 (dashboard tests) -> L15 (PII masking) -> remaining enhancements.
