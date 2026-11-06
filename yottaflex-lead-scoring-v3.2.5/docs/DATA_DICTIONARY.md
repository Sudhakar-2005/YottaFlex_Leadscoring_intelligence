# Data Dictionary

Timestamps are naive UTC. IDs are autoincrement integers unless noted.

## Core entities (11)

### company
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| company_id | INT PK | | |
| name | VARCHAR(200) | NOT NULL | |
| domain | VARCHAR(100) | UNIQUE NULL | used for dedup |
| industry | VARCHAR(50) | NOT NULL | ICP industries drive Fit |
| employee_band | VARCHAR(20) | NOT NULL | 1-50 / 51-200 / 201-1000 / 1000+ |
| annual_revenue_band | VARCHAR(30) | NULL | |
| country / region | VARCHAR | NOT NULL | ISO country |
| territory_code | FK territory | NOT NULL | |
| size_score | INT | 0–100 | Fit base |
| is_duplicate_of | FK company NULL | | soft dedup mark |
| lifecycle_state | VARCHAR | active/merged/inactive | |
| created_at / updated_at | DATETIME | NOT NULL | |

### contact
company_id FK, names, email + email_normalized (UNIQUE), phone, job_title, seniority_band, territory, lifecycle_state, is_duplicate_of.

### lead
| Column | Notes |
|--------|-------|
| lead_id PK | |
| company_id / contact_id | nullable FKs |
| email / email_normalized | NOT NULL |
| territory_code FK | routing key |
| campaign_id FK NULL, product_line | routing inputs |
| status | new→scored→assigned→working→qualified→converted \| disqualified \| opted_out |
| fit/intent/engagement_raw | latent factors from generator |
| fit/intent/engagement_score | 0–100 at scoring time |
| lead_score, lead_category | hot/warm/nurture/cold |
| scored_at | temporal cutoff |
| assigned_salesrep_id, assigned_at | |
| converted_opportunity_id, converted_at | logical link to opportunity |
| is_duplicate_of | soft dedup |

### campaign
name, channel (email/webinar/ads/content/event/partner), product_line, start/end_date, status.

### activity
activity_id PK, optional lead/contact/company (CHECK ≥1), activity_type, channel, **event_time** (scoring cutoff), campaign_id, metadata_json.

Types: email_sent, email_open, email_click, page_view, content_download, form_submit, demo_request, pricing_inquiry, call_logged, meeting_held, note.

### consent
subject_type (lead|contact), subject_id, channel (email|phone|sms), status (granted/revoked/expired/pending), valid_from/valid_to, granted_at/revoked_at, consent_source, evidence_ref. Unique (subject_type, subject_id, channel, valid_from).

### score_rule
rule_code UNIQUE, dimension (fit/intent/engagement), condition_json, points, priority, effective_from/to, is_active.

### salesrep
employee_code UNIQUE, name/email UNIQUE, role, home_territory_code FK, capacity_max_open_leads, active_leads_count, is_active.

### task
lead_id FK, salesrep_id FK, task_type (call/email/demo/linkedin/follow_up), title, due_date, status (pending/in_progress/completed/cancelled/blocked), priority, consent_checked, blocked_reason.

### opportunity
lead_id FK, company_id FK, contact_id FK NULL, salesrep_id FK, name, product_line, amount, currency, stage (new_lead/qualified/demo/proposal/won/lost), stage_entered_at, won_at/lost_at, loss_reason, is_duplicate_flag.

### stage_history (append-only)
stage_history_id PK, opportunity_id FK, from_stage NULL on initial, to_stage, changed_at, reason, actor_type, actor_id, created_at.

## Supporting tables

| Table | Purpose |
|-------|---------|
| territory | territory_code PK, region, countries_json |
| product | product_code PK, product_line |
| lead_campaign | M:N lead↔campaign + touch metadata |
| salesrep_territory | M:N coverage |
| salesrep_product | M:N skill |
| lead_score_explanation | per-score weights + rules_fired JSON |
| exception_record | operational detections |
| ground_truth_exception | GT labels (never a scoring feature) |
| anomaly_injection_log | injection audit trail |
