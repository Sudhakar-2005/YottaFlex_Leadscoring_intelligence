-- YottaFlex 00_schema.sql (V3 Phase 1) — CREATE TABLE + CREATE INDEX
-- Restores schema into an empty SQLite database; data follows in 01..06.
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;

DROP TABLE IF EXISTS territory;

CREATE TABLE territory (
	territory_code VARCHAR(20) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	region VARCHAR(50) NOT NULL, 
	countries_json TEXT NOT NULL, 
	PRIMARY KEY (territory_code)
);

DROP TABLE IF EXISTS product;

CREATE TABLE product (
	product_code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	product_line VARCHAR(50) NOT NULL, 
	PRIMARY KEY (product_code)
);

DROP TABLE IF EXISTS score_rule;

CREATE TABLE score_rule (
	score_rule_id INTEGER NOT NULL, 
	rule_code VARCHAR(60) NOT NULL, 
	dimension VARCHAR(20) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT, 
	condition_json TEXT NOT NULL, 
	points INTEGER NOT NULL, 
	weight FLOAT, 
	priority INTEGER NOT NULL, 
	effective_from DATETIME, 
	effective_to DATETIME, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (score_rule_id), 
	CONSTRAINT uq_score_rule_code UNIQUE (rule_code)
);

DROP TABLE IF EXISTS salesrep;

CREATE TABLE salesrep (
	salesrep_id INTEGER NOT NULL, 
	employee_code VARCHAR(30) NOT NULL, 
	first_name VARCHAR(80) NOT NULL, 
	last_name VARCHAR(80) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	home_territory_code VARCHAR(20) NOT NULL, 
	capacity_max_open_leads INTEGER NOT NULL, 
	active_leads_count INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	lifecycle_state VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (salesrep_id), 
	UNIQUE (employee_code), 
	UNIQUE (email), 
	FOREIGN KEY(home_territory_code) REFERENCES territory (territory_code)
);

DROP TABLE IF EXISTS salesrep_territory;

CREATE TABLE salesrep_territory (
	id INTEGER NOT NULL, 
	salesrep_id INTEGER NOT NULL, 
	territory_code VARCHAR(20) NOT NULL, 
	coverage_role VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_srep_territory UNIQUE (salesrep_id, territory_code), 
	FOREIGN KEY(salesrep_id) REFERENCES salesrep (salesrep_id) ON DELETE CASCADE, 
	FOREIGN KEY(territory_code) REFERENCES territory (territory_code)
);

DROP TABLE IF EXISTS salesrep_product;

CREATE TABLE salesrep_product (
	id INTEGER NOT NULL, 
	salesrep_id INTEGER NOT NULL, 
	product_code VARCHAR(30) NOT NULL, 
	skill_level INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_srep_product UNIQUE (salesrep_id, product_code), 
	FOREIGN KEY(salesrep_id) REFERENCES salesrep (salesrep_id) ON DELETE CASCADE, 
	FOREIGN KEY(product_code) REFERENCES product (product_code)
);

DROP TABLE IF EXISTS campaign;

CREATE TABLE campaign (
	campaign_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	channel VARCHAR(20) NOT NULL, 
	product_line VARCHAR(50), 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (campaign_id)
);

DROP TABLE IF EXISTS company;

CREATE TABLE company (
	company_id INTEGER NOT NULL, 
	business_id VARCHAR(40) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	domain VARCHAR(100), 
	industry VARCHAR(50) NOT NULL, 
	employee_band VARCHAR(20) NOT NULL, 
	annual_revenue_band VARCHAR(30), 
	country VARCHAR(2) NOT NULL, 
	region VARCHAR(50) NOT NULL, 
	territory_code VARCHAR(20) NOT NULL, 
	size_score INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	is_duplicate_of INTEGER, 
	lifecycle_state VARCHAR(20) NOT NULL, 
	PRIMARY KEY (company_id), 
	FOREIGN KEY(territory_code) REFERENCES territory (territory_code), 
	FOREIGN KEY(is_duplicate_of) REFERENCES company (company_id)
);

DROP TABLE IF EXISTS contact;

CREATE TABLE contact (
	contact_id INTEGER NOT NULL, 
	business_id VARCHAR(40) NOT NULL, 
	company_id INTEGER NOT NULL, 
	first_name VARCHAR(80) NOT NULL, 
	last_name VARCHAR(80) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	email_normalized VARCHAR(200) NOT NULL, 
	phone VARCHAR(40), 
	job_title VARCHAR(120), 
	seniority_band VARCHAR(30), 
	country VARCHAR(2) NOT NULL, 
	region VARCHAR(50) NOT NULL, 
	territory_code VARCHAR(20) NOT NULL, 
	lifecycle_state VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	is_duplicate_of INTEGER, 
	PRIMARY KEY (contact_id), 
	FOREIGN KEY(company_id) REFERENCES company (company_id) ON DELETE RESTRICT, 
	FOREIGN KEY(territory_code) REFERENCES territory (territory_code), 
	FOREIGN KEY(is_duplicate_of) REFERENCES contact (contact_id)
);

DROP TABLE IF EXISTS lead;

CREATE TABLE lead (
	lead_id INTEGER NOT NULL, 
	business_id VARCHAR(40) NOT NULL, 
	company_id INTEGER, 
	contact_id INTEGER, 
	email VARCHAR(200) NOT NULL, 
	email_normalized VARCHAR(200) NOT NULL, 
	first_name VARCHAR(80) NOT NULL, 
	last_name VARCHAR(80) NOT NULL, 
	country VARCHAR(2) NOT NULL, 
	region VARCHAR(50) NOT NULL, 
	territory_code VARCHAR(20) NOT NULL, 
	source VARCHAR(50) NOT NULL, 
	campaign_id INTEGER, 
	product_line VARCHAR(50), 
	status VARCHAR(20) NOT NULL, 
	eval_split VARCHAR(10) NOT NULL, 
	fit_raw FLOAT, 
	intent_raw FLOAT, 
	engagement_raw FLOAT, 
	fit_score INTEGER, 
	intent_score INTEGER, 
	engagement_score INTEGER, 
	lead_score INTEGER, 
	lead_category VARCHAR(20), 
	scored_at DATETIME, 
	assigned_salesrep_id INTEGER, 
	assigned_at DATETIME, 
	converted_opportunity_id INTEGER, 
	converted_at DATETIME, 
	disqualified_reason VARCHAR(200), 
	is_duplicate_of INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (lead_id), 
	FOREIGN KEY(company_id) REFERENCES company (company_id) ON DELETE RESTRICT, 
	FOREIGN KEY(contact_id) REFERENCES contact (contact_id) ON DELETE RESTRICT, 
	FOREIGN KEY(territory_code) REFERENCES territory (territory_code), 
	FOREIGN KEY(campaign_id) REFERENCES campaign (campaign_id), 
	FOREIGN KEY(assigned_salesrep_id) REFERENCES salesrep (salesrep_id), 
	UNIQUE (converted_opportunity_id), 
	FOREIGN KEY(converted_opportunity_id) REFERENCES opportunity (opportunity_id) ON DELETE SET NULL, 
	FOREIGN KEY(is_duplicate_of) REFERENCES lead (lead_id)
);

DROP TABLE IF EXISTS lead_campaign;

CREATE TABLE lead_campaign (
	id INTEGER NOT NULL, 
	lead_id INTEGER NOT NULL, 
	campaign_id INTEGER NOT NULL, 
	first_touch_at DATETIME, 
	touch_count INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lead_campaign UNIQUE (lead_id, campaign_id), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE CASCADE, 
	FOREIGN KEY(campaign_id) REFERENCES campaign (campaign_id) ON DELETE CASCADE
);

DROP TABLE IF EXISTS lead_status_history;

CREATE TABLE lead_status_history (
	history_id INTEGER NOT NULL, 
	lead_id INTEGER NOT NULL, 
	from_status VARCHAR(20), 
	to_status VARCHAR(20) NOT NULL, 
	changed_at DATETIME NOT NULL, 
	reason VARCHAR(300) NOT NULL, 
	actor_type VARCHAR(20) NOT NULL, 
	actor_id VARCHAR(60), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (history_id), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE RESTRICT
);

DROP TABLE IF EXISTS consent;

CREATE TABLE consent (
	consent_id INTEGER NOT NULL, 
	subject_type VARCHAR(20) NOT NULL, 
	subject_id INTEGER NOT NULL, 
	lead_id INTEGER, 
	contact_id INTEGER, 
	channel VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	consent_source VARCHAR(100), 
	granted_at DATETIME, 
	revoked_at DATETIME, 
	expires_at DATETIME, 
	valid_from DATETIME NOT NULL, 
	valid_to DATETIME, 
	evidence_ref VARCHAR(200), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (consent_id), 
	CONSTRAINT uq_consent_subject_channel_from UNIQUE (subject_type, subject_id, channel, valid_from), 
	CONSTRAINT ck_consent_lead_subject CHECK (subject_type != 'lead' OR lead_id IS NOT NULL), 
	CONSTRAINT ck_consent_contact_subject CHECK (subject_type != 'contact' OR contact_id IS NOT NULL), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE RESTRICT, 
	FOREIGN KEY(contact_id) REFERENCES contact (contact_id) ON DELETE RESTRICT
);

DROP TABLE IF EXISTS activity;

CREATE TABLE activity (
	activity_id INTEGER NOT NULL, 
	business_id VARCHAR(40) NOT NULL, 
	lead_id INTEGER, 
	contact_id INTEGER, 
	company_id INTEGER, 
	activity_type VARCHAR(40) NOT NULL, 
	channel VARCHAR(30), 
	event_time DATETIME NOT NULL, 
	campaign_id INTEGER, 
	metadata_json TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (activity_id), 
	CONSTRAINT ck_activity_subject CHECK (lead_id IS NOT NULL OR contact_id IS NOT NULL OR company_id IS NOT NULL), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE RESTRICT, 
	FOREIGN KEY(contact_id) REFERENCES contact (contact_id) ON DELETE RESTRICT, 
	FOREIGN KEY(company_id) REFERENCES company (company_id) ON DELETE RESTRICT, 
	FOREIGN KEY(campaign_id) REFERENCES campaign (campaign_id)
);

DROP TABLE IF EXISTS task;

CREATE TABLE task (
	task_id INTEGER NOT NULL, 
	business_id VARCHAR(40) NOT NULL, 
	lead_id INTEGER NOT NULL, 
	salesrep_id INTEGER NOT NULL, 
	task_type VARCHAR(30) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT, 
	due_date DATETIME NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	priority VARCHAR(10) NOT NULL, 
	consent_checked BOOLEAN NOT NULL, 
	blocked_reason VARCHAR(200), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (task_id), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE RESTRICT, 
	FOREIGN KEY(salesrep_id) REFERENCES salesrep (salesrep_id) ON DELETE RESTRICT
);

DROP TABLE IF EXISTS opportunity;

CREATE TABLE opportunity (
	opportunity_id INTEGER NOT NULL, 
	business_id VARCHAR(40) NOT NULL, 
	lead_id INTEGER NOT NULL, 
	company_id INTEGER NOT NULL, 
	contact_id INTEGER, 
	salesrep_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	product_line VARCHAR(50) NOT NULL, 
	amount FLOAT, 
	currency VARCHAR(3) NOT NULL, 
	stage VARCHAR(20) NOT NULL, 
	stage_entered_at DATETIME NOT NULL, 
	close_date DATE, 
	won_at DATETIME, 
	lost_at DATETIME, 
	loss_reason VARCHAR(200), 
	is_duplicate_flag BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (opportunity_id), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE RESTRICT, 
	FOREIGN KEY(company_id) REFERENCES company (company_id) ON DELETE RESTRICT, 
	FOREIGN KEY(contact_id) REFERENCES contact (contact_id), 
	FOREIGN KEY(salesrep_id) REFERENCES salesrep (salesrep_id) ON DELETE RESTRICT
);

DROP TABLE IF EXISTS stage_history;

CREATE TABLE stage_history (
	stage_history_id INTEGER NOT NULL, 
	opportunity_id INTEGER NOT NULL, 
	from_stage VARCHAR(20), 
	to_stage VARCHAR(20) NOT NULL, 
	changed_at DATETIME NOT NULL, 
	reason VARCHAR(300) NOT NULL, 
	actor_type VARCHAR(20) NOT NULL, 
	actor_id VARCHAR(60), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (stage_history_id), 
	FOREIGN KEY(opportunity_id) REFERENCES opportunity (opportunity_id) ON DELETE RESTRICT
);

DROP TABLE IF EXISTS lead_score_explanation;

CREATE TABLE lead_score_explanation (
	explanation_id INTEGER NOT NULL, 
	lead_id INTEGER NOT NULL, 
	scored_at DATETIME NOT NULL, 
	fit_score INTEGER NOT NULL, 
	intent_score INTEGER NOT NULL, 
	engagement_score INTEGER NOT NULL, 
	lead_score INTEGER NOT NULL, 
	lead_category VARCHAR(20) NOT NULL, 
	weights_json TEXT NOT NULL, 
	rules_fired_json TEXT NOT NULL, 
	activity_cutoff_id INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (explanation_id), 
	FOREIGN KEY(lead_id) REFERENCES lead (lead_id) ON DELETE RESTRICT
);

DROP TABLE IF EXISTS exception_record;

CREATE TABLE exception_record (
	exception_id INTEGER NOT NULL, 
	issue_type VARCHAR(60) NOT NULL, 
	affected_entity VARCHAR(40) NOT NULL, 
	affected_record_id INTEGER NOT NULL, 
	detection_timestamp DATETIME NOT NULL, 
	expected_behavior TEXT NOT NULL, 
	actual_behavior TEXT NOT NULL, 
	ground_truth_label VARCHAR(100), 
	severity VARCHAR(20) NOT NULL, 
	resolution_status VARCHAR(20) NOT NULL, 
	related_lead_id INTEGER, 
	evidence_json TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (exception_id)
);

DROP TABLE IF EXISTS exception_resolution_history;

CREATE TABLE exception_resolution_history (
	resolution_id INTEGER NOT NULL, 
	exception_id INTEGER, 
	issue_type VARCHAR(60) NOT NULL, 
	affected_entity VARCHAR(40) NOT NULL, 
	affected_record_id INTEGER NOT NULL, 
	from_status VARCHAR(20) NOT NULL, 
	to_status VARCHAR(20) NOT NULL, 
	reason VARCHAR(300), 
	actor_id VARCHAR(60), 
	resolved_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (resolution_id)
);

DROP TABLE IF EXISTS anomaly_injection_log;

CREATE TABLE anomaly_injection_log (
	injection_id INTEGER NOT NULL, 
	issue_type VARCHAR(60) NOT NULL, 
	target_entity VARCHAR(40) NOT NULL, 
	target_record_id INTEGER NOT NULL, 
	related_lead_id INTEGER, 
	injected_at DATETIME NOT NULL, 
	gt_label VARCHAR(100) NOT NULL, 
	details_json TEXT, 
	PRIMARY KEY (injection_id)
);

DROP TABLE IF EXISTS ground_truth_exception;

CREATE TABLE ground_truth_exception (
	exception_gt_id INTEGER NOT NULL, 
	issue_type VARCHAR(60) NOT NULL, 
	affected_entity VARCHAR(40) NOT NULL, 
	affected_record_id INTEGER NOT NULL, 
	related_lead_id INTEGER, 
	expected_behavior TEXT NOT NULL, 
	actual_behavior TEXT NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	injected_at DATETIME NOT NULL, 
	PRIMARY KEY (exception_gt_id)
);

DROP TABLE IF EXISTS duplicate_gt;

CREATE TABLE duplicate_gt (
	duplicate_gt_id INTEGER NOT NULL, 
	entity VARCHAR(20) NOT NULL, 
	primary_record_id INTEGER NOT NULL, 
	duplicate_record_id INTEGER NOT NULL, 
	primary_business_id VARCHAR(40) NOT NULL, 
	duplicate_business_id VARCHAR(40) NOT NULL, 
	match_key VARCHAR(40) NOT NULL, 
	match_value VARCHAR(200) NOT NULL, 
	origin VARCHAR(20) NOT NULL, 
	detected BOOLEAN NOT NULL, 
	detected_at DATETIME, 
	PRIMARY KEY (duplicate_gt_id)
);

CREATE INDEX ix_activity_activity_type ON activity (activity_type);

CREATE UNIQUE INDEX ix_activity_business_id ON activity (business_id);

CREATE INDEX ix_activity_company_id ON activity (company_id);

CREATE INDEX ix_activity_contact_event_time ON activity (contact_id, event_time);

CREATE INDEX ix_activity_contact_id ON activity (contact_id);

CREATE INDEX ix_activity_event_time ON activity (event_time);

CREATE INDEX ix_activity_lead_event_time ON activity (lead_id, event_time);

CREATE INDEX ix_activity_lead_id ON activity (lead_id);

CREATE INDEX ix_anomaly_injection_log_issue_type ON anomaly_injection_log (issue_type);

CREATE UNIQUE INDEX ix_company_business_id ON company (business_id);

CREATE INDEX ix_company_domain ON company (domain);

CREATE INDEX ix_company_territory_code ON company (territory_code);

CREATE INDEX ix_consent_contact_id ON consent (contact_id);

CREATE INDEX ix_consent_lead_id ON consent (lead_id);

CREATE INDEX ix_consent_subject ON consent (subject_type, subject_id, channel);

CREATE UNIQUE INDEX ix_contact_business_id ON contact (business_id);

CREATE INDEX ix_contact_company_id ON contact (company_id);

CREATE INDEX ix_contact_email_normalized ON contact (email_normalized);

CREATE INDEX ix_contact_territory_code ON contact (territory_code);

CREATE UNIQUE INDEX ix_dup_gt_entity_dup ON duplicate_gt (entity, duplicate_record_id);

CREATE INDEX ix_exc_resol_exception ON exception_resolution_history (exception_id);

CREATE INDEX ix_exc_resol_issue ON exception_resolution_history (issue_type);

CREATE INDEX ix_exception_record_affected_record_id ON exception_record (affected_record_id);

CREATE INDEX ix_exception_record_issue_type ON exception_record (issue_type);

CREATE INDEX ix_exception_record_related_lead_id ON exception_record (related_lead_id);

CREATE INDEX ix_exception_record_resolution_status ON exception_record (resolution_status);

CREATE INDEX ix_exception_record_severity ON exception_record (severity);

CREATE INDEX ix_exception_resolution_history_issue_type ON exception_resolution_history (issue_type);

CREATE INDEX ix_ground_truth_exception_issue_type ON ground_truth_exception (issue_type);

CREATE INDEX ix_lead_assigned_salesrep_id ON lead (assigned_salesrep_id);

CREATE UNIQUE INDEX ix_lead_business_id ON lead (business_id);

CREATE INDEX ix_lead_campaign_id ON lead (campaign_id);

CREATE INDEX ix_lead_campaign_lead_id ON lead_campaign (lead_id);

CREATE INDEX ix_lead_company_id ON lead (company_id);

CREATE INDEX ix_lead_contact_id ON lead (contact_id);

CREATE INDEX ix_lead_email_normalized ON lead (email_normalized);

CREATE INDEX ix_lead_is_duplicate_of ON lead (is_duplicate_of);

CREATE INDEX ix_lead_lead_category ON lead (lead_category);

CREATE INDEX ix_lead_lead_score ON lead (lead_score);

CREATE INDEX ix_lead_score_explanation_lead_id ON lead_score_explanation (lead_id);

CREATE INDEX ix_lead_status ON lead (status);

CREATE INDEX ix_lead_status_hist_lead_time ON lead_status_history (lead_id, changed_at);

CREATE INDEX ix_lead_status_history_lead_id ON lead_status_history (lead_id);

CREATE INDEX ix_lead_territory_code ON lead (territory_code);

CREATE INDEX ix_opp_lead_stage ON opportunity (lead_id, stage);

CREATE INDEX ix_opp_stage ON opportunity (stage);

CREATE UNIQUE INDEX ix_opportunity_business_id ON opportunity (business_id);

CREATE INDEX ix_opportunity_company_id ON opportunity (company_id);

CREATE INDEX ix_opportunity_lead_id ON opportunity (lead_id);

CREATE INDEX ix_opportunity_salesrep_id ON opportunity (salesrep_id);

CREATE INDEX ix_opportunity_stage ON opportunity (stage);

CREATE INDEX ix_salesrep_home_territory_code ON salesrep (home_territory_code);

CREATE INDEX ix_score_expl_lead_time ON lead_score_explanation (lead_id, scored_at);

CREATE INDEX ix_stage_hist_opp_time ON stage_history (opportunity_id, changed_at);

CREATE INDEX ix_stage_history_opportunity_id ON stage_history (opportunity_id);

CREATE UNIQUE INDEX ix_task_business_id ON task (business_id);

CREATE INDEX ix_task_due_date ON task (due_date);

CREATE INDEX ix_task_lead_id ON task (lead_id);

CREATE INDEX ix_task_lead_status ON task (lead_id, status);

CREATE INDEX ix_task_salesrep_id ON task (salesrep_id);

CREATE INDEX ix_task_status ON task (status);

COMMIT;
