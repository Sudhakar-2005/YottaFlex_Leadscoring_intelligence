from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yottaflex.db.base import Base


def _dt_kwargs() -> dict:
    return {"nullable": False}


class LifecycleState(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    merged = "merged"
    draft = "draft"
    paused = "paused"
    completed = "completed"


class LeadStatus(str, enum.Enum):
    new = "new"
    scored = "scored"
    assigned = "assigned"
    working = "working"
    qualified = "qualified"
    converted = "converted"
    disqualified = "disqualified"
    opted_out = "opted_out"


class LeadCategory(str, enum.Enum):
    hot = "hot"
    warm = "warm"
    nurture = "nurture"
    cold = "cold"


class OpportunityStage(str, enum.Enum):
    new_lead = "new_lead"
    qualified = "qualified"
    demo = "demo"
    proposal = "proposal"
    won = "won"
    lost = "lost"


STAGE_ORDER: list[OpportunityStage] = [
    OpportunityStage.new_lead,
    OpportunityStage.qualified,
    OpportunityStage.demo,
    OpportunityStage.proposal,
    OpportunityStage.won,
    OpportunityStage.lost,
]

# Allowed transitions (canonical path; lost may exit early; won only from proposal)
ALLOWED_STAGE_TRANSITIONS: dict[OpportunityStage, set[OpportunityStage]] = {
    OpportunityStage.new_lead: {OpportunityStage.qualified},
    OpportunityStage.qualified: {OpportunityStage.demo, OpportunityStage.lost},
    OpportunityStage.demo: {OpportunityStage.proposal, OpportunityStage.lost},
    OpportunityStage.proposal: {OpportunityStage.won, OpportunityStage.lost},
    OpportunityStage.won: set(),
    OpportunityStage.lost: set(),
}


class TaskType(str, enum.Enum):
    call = "call"
    email = "email"
    demo = "demo"
    linkedin = "linkedin"
    follow_up = "follow_up"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    blocked = "blocked"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ConsentChannel(str, enum.Enum):
    email = "email"
    phone = "phone"
    sms = "sms"


class ConsentStatus(str, enum.Enum):
    granted = "granted"
    revoked = "revoked"
    expired = "expired"
    pending = "pending"


class ConsentSubjectType(str, enum.Enum):
    lead = "lead"
    contact = "contact"


class ActivityType(str, enum.Enum):
    email_sent = "email_sent"
    email_open = "email_open"
    email_click = "email_click"
    page_view = "page_view"
    content_download = "content_download"
    form_submit = "form_submit"
    demo_request = "demo_request"
    pricing_inquiry = "pricing_inquiry"
    call_logged = "call_logged"
    meeting_held = "meeting_held"
    note = "note"


class CampaignChannel(str, enum.Enum):
    email = "email"
    webinar = "webinar"
    ads = "ads"
    content = "content"
    event = "event"
    partner = "partner"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"


class ScoreDimension(str, enum.Enum):
    fit = "fit"
    intent = "intent"
    engagement = "engagement"


class SalesRepRole(str, enum.Enum):
    sdr = "sdr"
    ae = "ae"
    closing = "closing"
    manager = "manager"


class ActorType(str, enum.Enum):
    system = "system"
    user = "user"


class Severity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class ResolutionStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"
    false_positive = "false_positive"
    wont_fix = "wont_fix"


class IssueType(str, enum.Enum):
    opted_out_lead_contacted = "opted_out_lead_contacted"
    score_uses_post_conversion_event = "score_uses_post_conversion_event"
    lead_assigned_outside_territory = "lead_assigned_outside_territory"
    duplicate_creates_duplicate_opportunity = "duplicate_creates_duplicate_opportunity"
    stage_history_has_gaps = "stage_history_has_gaps"


# ---------------------------------------------------------------------------
# Supporting reference tables
# ---------------------------------------------------------------------------


class Territory(Base):
    __tablename__ = "territory"

    territory_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    countries_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class Product(Base):
    __tablename__ = "product"

    product_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    product_line: Mapped[str] = mapped_column(String(50), nullable=False)


# ---------------------------------------------------------------------------
# 1. Company
# ---------------------------------------------------------------------------


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Non-unique index: natural duplicate companies share a domain (soft-dedup)
    domain: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=False)
    employee_band: Mapped[str] = mapped_column(String(20), nullable=False)
    annual_revenue_band: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    territory_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("territory.territory_code"), nullable=False, index=True
    )
    size_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_duplicate_of: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("company.company_id"), nullable=True
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LifecycleState.active.value
    )

    contacts: Mapped[list[Contact]] = relationship(back_populates="company", foreign_keys="Contact.company_id")
    leads: Mapped[list[Lead]] = relationship(back_populates="company")


# ---------------------------------------------------------------------------
# 2. Contact
# ---------------------------------------------------------------------------


class Contact(Base):
    __tablename__ = "contact"
    __table_args__ = (Index("ix_contact_email_normalized", "email_normalized"),)

    contact_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("company.company_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    seniority_band: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    territory_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("territory.territory_code"), nullable=False, index=True
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LifecycleState.active.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_duplicate_of: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact.contact_id"), nullable=True
    )

    company: Mapped[Company] = relationship(back_populates="contacts", foreign_keys=[company_id])


# ---------------------------------------------------------------------------
# 4. Campaign
# ---------------------------------------------------------------------------


class Campaign(Base):
    __tablename__ = "campaign"

    campaign_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    product_line: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CampaignStatus.active.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# 3. Lead
# ---------------------------------------------------------------------------


class Lead(Base):
    __tablename__ = "lead"
    __table_args__ = (
        Index("ix_lead_email_normalized", "email_normalized"),
    )

    lead_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("company.company_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact.contact_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    territory_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("territory.territory_code"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaign.campaign_id"), nullable=True, index=True
    )
    product_line: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LeadStatus.new.value, index=True
    )
    # Held-out evaluation split assigned at generation; never a scoring feature
    eval_split: Mapped[str] = mapped_column(String(10), nullable=False, default="dev")
    fit_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intent_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    engagement_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fit_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    intent_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lead_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    lead_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assigned_salesrep_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("salesrep.salesrep_id"), nullable=True, index=True
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    converted_opportunity_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("opportunity.opportunity_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )  # FK link lead -> converted opportunity (P1: enforced, SET NULL)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    disqualified_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_duplicate_of: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("lead.lead_id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    company: Mapped[Optional[Company]] = relationship(back_populates="leads", foreign_keys=[company_id])
    activities: Mapped[list[Activity]] = relationship(back_populates="lead")
    tasks: Mapped[list[Task]] = relationship(back_populates="lead")
    opportunity: Mapped[Optional[Opportunity]] = relationship(
        back_populates="lead", uselist=False, foreign_keys="Opportunity.lead_id"
    )
    score_explanations: Mapped[list[LeadScoreExplanation]] = relationship(back_populates="lead")


class LeadStatusHistory(Base):
    """Append-only lead status transitions (P1-1).

    Mirrors stage_history: lead timelines are reconstructable from records
    without recomputation. initial row from None -> new at lead creation.
    """

    __tablename__ = "lead_status_history"
    __table_args__ = (
        Index("ix_lead_status_hist_lead_time", "lead_id", "changed_at"),
    )

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ActorType.system.value
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    lead: Mapped[Lead] = relationship()


# ---------------------------------------------------------------------------
# 5. Activity
# ---------------------------------------------------------------------------


class Activity(Base):
    __tablename__ = "activity"
    __table_args__ = (
        CheckConstraint(
            "lead_id IS NOT NULL OR contact_id IS NOT NULL OR company_id IS NOT NULL",
            name="ck_activity_subject",
        ),
        Index("ix_activity_lead_event_time", "lead_id", "event_time"),
        Index("ix_activity_contact_event_time", "contact_id", "event_time"),
    )

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact.contact_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("company.company_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    channel: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("campaign.campaign_id"), nullable=True
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    lead: Mapped[Optional[Lead]] = relationship(back_populates="activities")
    contact: Mapped[Optional[Contact]] = relationship()


# ---------------------------------------------------------------------------
# 6. Consent
# ---------------------------------------------------------------------------


class Consent(Base):
    __tablename__ = "consent"
    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "channel",
            "valid_from",
            name="uq_consent_subject_channel_from",
        ),
        Index("ix_consent_subject", "subject_type", "subject_id", "channel"),
        CheckConstraint(
            "subject_type != 'lead' OR lead_id IS NOT NULL",
            name="ck_consent_lead_subject",
        ),
        CheckConstraint(
            "subject_type != 'contact' OR contact_id IS NOT NULL",
            name="ck_consent_contact_subject",
        ),
    )

    consent_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Typed FKs mirroring the polymorphic subject (P1 consent FK)
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact.contact_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    consent_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    granted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    evidence_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# 7. ScoreRule
# ---------------------------------------------------------------------------


class ScoreRule(Base):
    __tablename__ = "score_rule"
    __table_args__ = (UniqueConstraint("rule_code", name="uq_score_rule_code"),)

    score_rule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    condition_json: Mapped[str] = mapped_column(Text, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# 8. SalesRep
# ---------------------------------------------------------------------------


class SalesRep(Base):
    __tablename__ = "salesrep"

    salesrep_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=SalesRepRole.ae.value)
    home_territory_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("territory.territory_code"), nullable=False, index=True
    )
    capacity_max_open_leads: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    active_leads_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LifecycleState.active.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    territories: Mapped[list[SalesRepTerritory]] = relationship(back_populates="salesrep")
    products: Mapped[list[SalesRepProduct]] = relationship(back_populates="salesrep")


class SalesRepTerritory(Base):
    __tablename__ = "salesrep_territory"
    __table_args__ = (
        UniqueConstraint("salesrep_id", "territory_code", name="uq_srep_territory"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    salesrep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salesrep.salesrep_id", ondelete="CASCADE"), nullable=False
    )
    territory_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("territory.territory_code"), nullable=False
    )
    coverage_role: Mapped[str] = mapped_column(String(30), nullable=False, default="primary")

    salesrep: Mapped[SalesRep] = relationship(back_populates="territories")


class SalesRepProduct(Base):
    __tablename__ = "salesrep_product"
    __table_args__ = (
        UniqueConstraint("salesrep_id", "product_code", name="uq_srep_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    salesrep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salesrep.salesrep_id", ondelete="CASCADE"), nullable=False
    )
    product_code: Mapped[str] = mapped_column(
        String(30), ForeignKey("product.product_code"), nullable=False
    )
    skill_level: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    salesrep: Mapped[SalesRep] = relationship(back_populates="products")


class LeadCampaign(Base):
    __tablename__ = "lead_campaign"
    __table_args__ = (
        UniqueConstraint("lead_id", "campaign_id", name="uq_lead_campaign"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaign.campaign_id", ondelete="CASCADE"), nullable=False
    )
    first_touch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    touch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# ---------------------------------------------------------------------------
# 9. Task
# ---------------------------------------------------------------------------


class Task(Base):
    __tablename__ = "task"
    __table_args__ = (Index("ix_task_lead_status", "lead_id", "status"),)

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    salesrep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salesrep.salesrep_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskStatus.pending.value, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default=Priority.medium.value
    )
    consent_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="tasks")
    salesrep: Mapped[SalesRep] = relationship()


# ---------------------------------------------------------------------------
# 10. Opportunity
# ---------------------------------------------------------------------------


class Opportunity(Base):
    __tablename__ = "opportunity"
    __table_args__ = (
        Index("ix_opp_lead_stage", "lead_id", "stage"),
        Index("ix_opp_stage", "stage"),
    )

    opportunity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("company.company_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contact.contact_id"), nullable=True
    )
    salesrep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("salesrep.salesrep_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OpportunityStage.new_lead.value, index=True
    )
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    won_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lost_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    loss_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_duplicate_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    lead: Mapped[Lead] = relationship(
        back_populates="opportunity", foreign_keys=[lead_id],
        primaryjoin="Opportunity.lead_id == Lead.lead_id",
    )
    stage_history: Mapped[list[StageHistory]] = relationship(
        back_populates="opportunity", order_by="StageHistory.changed_at"
    )


# ---------------------------------------------------------------------------
# 11. StageHistory (append-only)
# ---------------------------------------------------------------------------


class StageHistory(Base):
    __tablename__ = "stage_history"
    __table_args__ = (
        Index("ix_stage_hist_opp_time", "opportunity_id", "changed_at"),
    )

    stage_history_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunity.opportunity_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    from_stage: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ActorType.system.value
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    opportunity: Mapped[Opportunity] = relationship(back_populates="stage_history")


# ---------------------------------------------------------------------------
# Explainability + Ground truth (supporting; GT isolated from scoring features)
# ---------------------------------------------------------------------------


class LeadScoreExplanation(Base):
    __tablename__ = "lead_score_explanation"
    __table_args__ = (
        Index("ix_score_expl_lead_time", "lead_id", "scored_at"),
    )

    explanation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lead.lead_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scored_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    intent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    engagement_score: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_score: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_category: Mapped[str] = mapped_column(String(20), nullable=False)
    weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    rules_fired_json: Mapped[str] = mapped_column(Text, nullable=False)
    activity_cutoff_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="score_explanations")


class AnomalyInjectionLog(Base):
    """Audit log of deliberately injected anomalies. Not a scoring feature."""

    __tablename__ = "anomaly_injection_log"

    injection_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_entity: Mapped[str] = mapped_column(String(40), nullable=False)
    target_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    related_lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    injected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    gt_label: Mapped[str] = mapped_column(String(100), nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GroundTruthException(Base):
    """Ground-truth labels for evaluation. Never used as model/scoring features."""

    __tablename__ = "ground_truth_exception"

    exception_gt_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    affected_entity: Mapped[str] = mapped_column(String(40), nullable=False)
    affected_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    related_lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    actual_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    injected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ExceptionRecord(Base):
    """Operational exception produced by detectors."""

    __tablename__ = "exception_record"

    exception_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    affected_entity: Mapped[str] = mapped_column(String(40), nullable=False)
    affected_record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    detection_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    actual_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    ground_truth_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    resolution_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ResolutionStatus.open.value, index=True
    )
    related_lead_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ExceptionResolutionHistory(Base):
    """Append-only exception resolution transitions (P1-4).

    The brief requires resolution history to be recorded, not just re-detected.
    Re-detection hard-deletes exception_record rows, so this table snapshots
    issue_type/affected entity/record alongside the transition — history
    survives re-detection.
    """

    __tablename__ = "exception_resolution_history"
    __table_args__ = (
        Index("ix_exc_resol_exception", "exception_id"),
        Index("ix_exc_resol_issue", "issue_type"),
    )

    resolution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    affected_entity: Mapped[str] = mapped_column(String(40), nullable=False)
    affected_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DuplicateGroundTruth(Base):
    """Ground truth for duplicate records.

    Distinguishes naturally generated baseline duplicates (origin='natural')
    from deliberately injected anomaly duplicates (origin='injected').
    Never used as a scoring feature.
    """

    __tablename__ = "duplicate_gt"
    __table_args__ = (
        Index("ix_dup_gt_entity_dup", "entity", "duplicate_record_id", unique=True),
    )

    duplicate_gt_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_business_id: Mapped[str] = mapped_column(String(40), nullable=False)
    duplicate_business_id: Mapped[str] = mapped_column(String(40), nullable=False)
    match_key: Mapped[str] = mapped_column(String(40), nullable=False)
    match_value: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)  # natural | injected
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
