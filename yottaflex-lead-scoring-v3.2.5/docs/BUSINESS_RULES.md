# Business Rules

IDs are referenced by tests and code comments.

## Scoring (BR-S)

| ID | Rule |
|----|------|
| BR-S01 | `lead_score = round(Fit×w_f + Intent×w_i + Engagement×w_e)` with default weights 0.40/0.35/0.25 (sum must = 1.0). |
| BR-S02 | Each dimension clamped to [0,100]. |
| BR-S03 | Category: Hot ≥80, Warm ≥60, Nurture ≥40, else Cold (thresholds configurable). |
| BR-S04 | Only `activity.event_time <= scored_at` contributes; converted leads never use post-conversion events. |
| BR-S05 | Persist explanation: weights, rules fired, component scores, scored_at. |
| BR-S06 | Re-scoring appends a new explanation row (history preserved). |
| BR-S07 | Ground truth, injection logs, and `is_duplicate_*` are forbidden scoring features. |

## Consent (BR-C)

| ID | Rule |
|----|------|
| BR-C01 | Outreach task creation requires latest lead-level consent = granted for the channel at `as_of`. |
| BR-C02 | revoked/expired/missing → task blocked or not created; recorded via enforcement. |
| BR-C03 | Baseline grant rates from `config/settings.yaml` (email ~88%, phone ~75%, revoke ~10%). |

## Routing & assignment (BR-R)

| ID | Rule |
|----|------|
| BR-R01 | Lead territory must be in rep coverage (`salesrep_territory` or home). |
| BR-R02 | Prefer reps skilled in lead product_line; **BR-R02b** fallback to territory-only if nobody matches. |
| BR-R03 | Only active reps with `active_leads_count < capacity` are eligible. |
| BR-R04 | Strategy `least_loaded_then_id`: min load, then lowest salesrep_id (deterministic). |
| BR-R05 | Out-of-territory assignment forbidden in baseline; injected only for EX-03. |

## Tasks (BR-T)

| ID | Rule |
|----|------|
| BR-T01 | Due days by category: hot 1, warm 3, nurture 7, cold 14 (config). |
| BR-T02 | One open (pending/in_progress) task per lead. |
| BR-T03 | Task requires assigned rep. |
| BR-T04 | Task type by category: hot→demo, warm→call, nurture/cold→email (config). |

## Opportunities (BR-O)

| ID | Rule |
|----|------|
| BR-O01 | Convert only qualified leads with score + assignment + company. |
| BR-O02 | Conversion sets lead status=converted, links opportunity_id/converted_at. |
| BR-O03 | Target exact 3,000 opportunities via score-rank selection. |
| BR-O04 | Won/Lost terminal; no further transitions. |

## Stage history (BR-H)

| ID | Rule |
|----|------|
| BR-H01 | Every stage change inserts a StageHistory row; past rows never updated. |
| BR-H02 | Initial row: from_stage=NULL, to_stage=new_lead. |
| BR-H03 | Legal transitions: new_lead→qualified; qualified→demo\|lost; demo→proposal\|lost; proposal→won\|lost. Skips (e.g. new_lead→proposal) = EX-05. |
| BR-H04 | changed_at strictly non-decreasing per opportunity. |

## Deduplication (BR-D)

| ID | Rule |
|----|------|
| BR-D01 | Match keys: email_normalized (leads/contacts), domain (companies). |
| BR-D02 | Soft-mark `is_duplicate_of`; exclude marked rows from scoring/assignment primaries. |
| BR-D03 | >1 opportunity per lead = EX-04 (baseline forbids; injection only). |

## Exceptions (BR-E)

| ID | Rule |
|----|------|
| BR-E01 | Detectors write Exception rows only; they do not mutate domain data. |
| BR-E02 | GT stored in separate tables/modules; never feeds scoring. |
| BR-E03 | Severity: critical (consent, leakage), high (territory, dup opp), medium (stage gap). |
| BR-E04 | Fields: id, issue_type, entity, record_id, detection_timestamp, expected, actual, ground_truth_label, severity, resolution_status. |

## Analytics (BR-A)

| ID | Formula |
|----|---------|
| BR-A01 | Lead conversion rate = converted / eligible (eligible excludes disqualified, opted_out, duplicates). |
| BR-A02 | Opportunity win rate = won / (won + lost). |
| BR-A03 | Lead qualification rate = (qualified + converted) / total leads. |
| BR-A04 | Assignment coverage = assigned / assignable. |
| BR-A05 | Consent compliance = compliant outreach / total outreach (violations from EX-01). |
| BR-A06 | Duplicate detection rate = detected / injected (dup-opportunity class). |
