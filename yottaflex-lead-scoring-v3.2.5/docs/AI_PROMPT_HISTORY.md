# AI Prompt History

All significant AI prompts used during development of this project, in order.

---

### P001 — Master meta-prompt (initial)
**Role:** Autonomous senior engineering team (architect, backend, data, DB, ML, QA, DevOps, docs).  
**Task:** Study YottaFlex problem statement + workflow image; produce Phase-0 analysis only (13 deliverables); no code until approval.  
**Output:** Requirement breakdown, workflow, architecture, module deps, ER design, API proposal, business rules, exception architecture, data-gen strategy, testing strategy, 72h roadmap, 22 ambiguities/4 contradictions.  
**Decision:** Presented plan; requested approval on A01/A05/A10/A13/A20.

---

### P002 — Approval
**User:** "Approve"  
**Action:** Begin implementation from Phase 3 (Database Design) per roadmap.

---

### P003 — Schema bootstrap
**Prompt (internal):** Create project scaffold, Pydantic settings, SQLAlchemy models for 11 entities + Territory/Product/bridges/GT/exception tables; verify `create_all` on SQLite.  
**Issues found:** `CHECK` import wrong (use CheckConstraint); duplicate index on Lead; circular FK lead↔opportunity breaking SQLite DDL.  
**Resolution:** CheckConstraint; removed dup Index; dropped DB FK on `converted_opportunity_id` (logical link only) — TD-05.

---

### P004 — Data generation engine
**Prompt (internal):** Deterministic generators for territories, products, score rules, reps (coverage bridges), companies, contacts, campaigns, leads (~50% contact-linked), consents, pre-scoring activities with latent intent/engagement. SeedSequence streams.  
**Issues:** LeadCampaign flushed before lead_id assigned; contact double-linking created natural dupes; naive/aware datetime mix.  
**Resolution:** Deferred bridge flush; one-lead-per-contact; `Settings.base_dt()` naive UTC.

---

### P005 — Engine suite
**Prompt (internal):** Implement validation, scoring (explainable + temporal cutoff), dedup soft-mark, consent gate, routing (territory+product), assignment (least-loaded), tasks, opportunities (exact 3K), stage history (append-only, canonical path), 5 detectors, analytics KPIs, anomaly injection with GT logs.  
**Decisions:** Lost allowed early from qualified/demo (TD-13); BR-R02b territory-only fallback; injection after clean baseline.

---

### P006 — Pipeline smoke (mini)
**Prompt (internal):** Run mini pipeline; fix failures iteratively.  
**Fixes:** Timezone compare error → naive UTC; illegal demo→lost transitions → allow early lost; GT miss on dup-opp → match by related_lead_id; scoring cutoff before activities → scored_at = base+61d; category skew → boost activity generation; assignment coverage → broader rep coverage + capacity.

---

### P007 — Full-scale run #1
**Observation:** Coverage 22% (capacity 40–80 × 80 reps ≈ 4K slots); assignment 6.5 min (N+1).  
**Fix:** Capacity 200–350; preload territory/product maps in assignment (TD-15/TD-16).

---

### P008 — Test suite
**Prompt (internal):** Write unit+integration tests: schema, determinism, scoring boundaries, temporal, GT isolation, consent, stage path, dedup, baseline=0 exceptions, injection P/R=1.0, API endpoints.  
**Fixes:** `:memory:` StaticPool (TD-02); API dependency override for tests; assignment reset must clear rep counters.

---

### P009 — Full-scale validation (final)
**Result:** 20K/10K/5K/3K exact · baseline exceptions 0 · injected 75/75 detected P=R=1.0 · coverage 96.45% · win rate 66.9% · 29 tests passed.

---

### P010 — Documentation pack
**Prompt (internal):** Write README, ARCHITECTURE, ERD, DATA_DICTIONARY, BUSINESS_RULES, API, ASSUMPTIONS, TECHNICAL_DECISIONS, TESTING, VALIDATION_SUMMARY, AI_PROMPT_HISTORY, KNOWN_LIMITATIONS.

---

### P011 — Environment constraint (Git)
**Observation:** `git` binary not installed on the host.  
**Action:** Documented as L16 in KNOWN_LIMITATIONS; `.gitignore` ready for `git init` where Git is available.

---

---

### P012 - V3 engineering audit + P0 remediation
**Prompt (internal):** Audit whole codebase; fix P0 defects before P1: deterministic business IDs, natural baseline duplicates with GT separation, complete export engine, score-leakage-free outcome generation + held-out split, honest blind P/R/F1, per-step stage timestamps.
**Result:** Business IDs (CO/CON/LEAD/OPP/ACT/TASK), duplicate_gt (natural 741 + injected 10), 7-file SQL export design, propensity-based selection (low-score converters exist), blind key-based evaluation with F1, stage timelines fixed. Tests 29 -> 51.

---

### P013 - P1/P2 infrastructure
**Prompt (internal):** Add LeadStatusHistory + exception resolution history, consent typed FKs, converted-link FK, coverage metrics; rebuild dashboard into 9 sections; remove dead code; fix consent metric performance.
**Result:** lead_status_history (90,657 rows full scale), resolution history survives re-detection, `PRAGMA foreign_key_check` clean, coverage metrics (opt-out 8.8%, stale 1.5%), dashboard 9 sections, 58 tests, coverage 88.8%.

---

### P014 - V3: SQL export repair + duplicate reconciliation
**Prompt (internal):** Split broken 121 MB seed_data.sql into schema + 6 data files with real DDL; build restoration tool; reconcile 400 configured vs 516 actual duplicate leads.
**Result:** CreateTable/CreateIndex schema, restore PASS (577,308 rows, 0 FK violations), reconciliation report: 516 = 400 configured + 116 contact-derived shared-email groups. Tests 58 -> 64.

---

### P015 - V3.1: submission preparation
**Prompt (internal):** Clean GitHub-ready copy, security audit, large-file audit, repository initialization (git binary absent), submission checklist.
**Result:** 107 tracked files, max file 50.02 MB, no secrets, repo created with dulwich (7 commits), `FINAL_SUBMISSION_CHECKLIST.md`.

---

### P016 - V3.2: final stabilization
**Prompt (internal):** Fix five issues: API destructive-run protection, SQL restore overwrite safety, remove validation sampling, reconcile docs, full-scale reproducibility. Run everything with evidence.
**Result:** API confirmation gate + separate output DB; restore refuses to overwrite without `--force` (exit 3) and re-enables/checks FKs; validation covers ALL scored records (range + weighted-formula identity, checks_run 24); docs reconciled; starter + full reproducibility PASS (five-way comparison); 73 tests pass in a clean venv. Evidence in `docs/evidence/`; reports `V3_2_STABILIZATION_REPORT.md`, `FINAL_TEST_RESULTS.md`, `FINAL_RELEASE_CHECKLIST.md`.

---

### P017 - V3.2.3: release-stabilization verification + export overwrite policy

**Prompt (verbatim, project coordinator):**

> We are working on the YottaFlex AI coding challenge. This is a release-stabilization task, NOT a redesign.
>
> Work on a separate branch or clean working copy. Back up the current project before editing. Do not delete or overwrite the original dataset, committed exports, or existing working database.
>
> Fix these issues in order:
>
> 1. EX-02 ground-truth leakage - CRITICAL
> - Inspect "exceptions.py", "anomaly_injection.py", scoring logic, and EX-02 tests.
> - Remove all dependence on injected marker strings/tags as the detector's evidence.
> - Detect post-conversion activity using actual timestamps and conversion events.
> - Ensure the detector works when all injected marker labels are removed.
> - Ensure ground-truth labels are stored separately and never used as detector input.
> - Add tests proving that removing markers does not change detection results.
> - Recalculate precision, recall and F1 using independently detected records.
>
> 2. API destructive-path protection - CRITICAL
> - Inspect API pipeline execution and database path configuration.
> - Normalize and resolve paths before comparing them with protected paths.
> - Reject traversal, alternate separators, symlinks, and equivalent path representations.
> - Add regression tests for "/./", "/../", "//", and equivalent Windows path forms.
> - Verify that no request can clear or modify the live database unexpectedly.
>
> 3. Prevent accidental export overwrites - CRITICAL
> - Inspect pipeline report/export generation.
> - Never overwrite committed full-scale exports during a starter run or ordinary API request.
> - Require an explicit output directory and explicit overwrite permission for destructive export operations.
> - Default to a separate generated-output directory.
> - Add tests that hash protected exports before and after pipeline execution.
>
> 4. SQL restoration integrity
> - Verify the restored database against "dataset_manifest.json".
> - Check expected tables, row counts, and foreign-key integrity.
> - Reject truncated or incomplete exports.
> - Do not print RESTORATION PASS unless every required check passes.
> - Preserve the existing target database if restoration fails.
>
> 5. Opportunity loss reasons
> - Populate "loss_reason" through a documented, deterministic outcome-generation rule.
> - Ensure every lost opportunity has a valid reason.
> - Add tests for won, lost, and open opportunities.
>
> Rules
> - Do not redesign the architecture or change the scoring formula.
> - Do not fabricate test results or documentation evidence.
> - Do not hide, delete, or relabel anomalies to improve metrics.
> - Keep ground truth separate from detection.
> - Preserve all AI prompts and add the actual prompts used in this task to the prompt history.
> - Run the full test suite and report the exact command, result, and failures.
> - Produce "docs/V3_2_3_FIX_REPORT.md" containing each defect, files changed, tests added, and verification evidence.
>
> Do not push to GitHub. Stop after implementation and report what remains unresolved.

**Actions:** backed up the V3.2.2 release (`yottaflex-lead-scoring-v3.2.2-BACKUP-v3.2.3`) and created the dedicated `yottaflex-lead-scoring-v3.2.3` working copy. Verified items 1/2/4/5 were already fixed in V3.2.2 (EX-02 independent detection, canonical path guard, manifest-verified atomic restore, deterministic loss reasons) and closed the real gaps: export runs now DEFAULT to `data/generated/exports`; overwriting any existing export set requires explicit permission (`overwrite_exports` / `--overwrite-exports`); added `//`-form and junction-alias path regressions; added the open-opportunity loss-reason test.

**Result:** 102 tests passed (0 skipped, exit 0; evidence `docs/evidence/v3_2_3_pytest_full.txt`); committed exports byte-identical across every test run (hashed before/after); junction alias and all seven path-equivalence forms refused with HTTP 400; report in `docs/V3_2_3_FIX_REPORT.md`. No push, no submission.

---

*Future prompts appended below this line.*


### P018 — V3.2.5 dashboard UI redesign (disclosure summary; not verbatim)

**AI tool:** OpenCode (implementation); ChatGPT (architecture/review guidance).

**Task summary:** Refresh the Streamlit dashboard using the supplied dark navy / glassmorphism CRM reference. Apply a consistent design system (dark surfaces, blue/indigo accents, premium typography, clear spacing), improve KPI cards, navigation, tables, charts, empty/loading states, and responsive behavior across all nine dashboard sections. Preserve existing backend behavior, business rules, data contracts, and real metrics; do not introduce fabricated data or alter scoring/exception logic.

**Disclosure limitation:** The exact original UI prompt transcript was not included in the V3.2.5 archive. This entry is an accurate summary of the task brief, not a verbatim prompt. Attach or append the original OpenCode prompt transcript before final challenge submission if the challenge requires exact prompts.
