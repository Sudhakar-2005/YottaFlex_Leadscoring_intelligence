from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.db.models import Company, Contact, DuplicateGroundTruth, Lead, Opportunity
from yottaflex.logging_setup import get_logger

log = get_logger("deduplication")


@dataclass
class DuplicatePair:
    entity: str
    primary_id: int
    duplicate_id: int
    match_key: str
    match_value: str
    primary_business_id: str = ""
    duplicate_business_id: str = ""
    origin: str = "natural"


@dataclass
class DedupReport:
    pairs: list[DuplicatePair] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.pairs)

    def to_dict(self) -> dict:
        return {"count": self.count, "pairs": [p.__dict__ for p in self.pairs]}


def _norm_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None


def record_duplicate_gt(
    session: Session,
    entity: str,
    primary_id: int,
    duplicate_id: int,
    match_key: str,
    match_value: str,
    origin: str,
    primary_business_id: str,
    duplicate_business_id: str,
) -> bool:
    """Idempotently record duplicate ground truth (P0-B). Returns True if inserted."""
    existing = session.scalar(
        select(DuplicateGroundTruth).where(
            DuplicateGroundTruth.entity == entity,
            DuplicateGroundTruth.duplicate_record_id == duplicate_id,
        )
    )
    if existing is not None:
        return False
    session.add(
        DuplicateGroundTruth(
            entity=entity,
            primary_record_id=primary_id,
            duplicate_record_id=duplicate_id,
            primary_business_id=primary_business_id,
            duplicate_business_id=duplicate_business_id,
            match_key=match_key,
            match_value=match_value,
            origin=origin,
            # Every caller soft-marks the duplicate at the same time, which
            # constitutes detection by the dedup / duplicate-opportunity rules.
            detected=True,
            detected_at=None,
        )
    )
    return True


def _mark_detected_gt(session: Session, entity: str, duplicate_id: int, at=None) -> None:
    row = session.scalar(
        select(DuplicateGroundTruth).where(
            DuplicateGroundTruth.entity == entity,
            DuplicateGroundTruth.duplicate_record_id == duplicate_id,
        )
    )
    if row is not None and not row.detected:
        row.detected = True
        row.detected_at = at


def deduplicate_leads(session: Session, mark_only: bool = True) -> DedupReport:
    """Soft-mark duplicate leads by email_normalized (BR-D01/D02). Never hard-delete."""
    report = DedupReport()
    rows = session.execute(
        select(Lead.lead_id, Lead.email_normalized, Lead.business_id)
        .where(Lead.is_duplicate_of.is_(None))
        .order_by(Lead.email_normalized, Lead.lead_id)
    ).all()

    by_email: dict[str, list[tuple[int, str]]] = {}
    for lead_id, email, bid in rows:
        by_email.setdefault(email, []).append((lead_id, bid))

    for email, entries in sorted(by_email.items()):
        if len(entries) < 2:
            continue
        primary_id, primary_bid = entries[0]
        for dup_id, dup_bid in entries[1:]:
            report.pairs.append(
                DuplicatePair(
                    "lead", primary_id, dup_id, "email_normalized", email,
                    primary_bid, dup_bid, "natural",
                )
            )
            record_duplicate_gt(
                session, "lead", primary_id, dup_id, "email_normalized", email,
                "natural", primary_bid, dup_bid,
            )
            if mark_only:
                lead = session.get(Lead, dup_id)
                if lead is not None:
                    lead.is_duplicate_of = primary_id
    session.commit()
    log.info("lead duplicate pairs: %d", report.count)
    return report


def deduplicate_contacts(session: Session, mark_only: bool = True) -> DedupReport:
    report = DedupReport()
    rows = session.execute(
        select(Contact.contact_id, Contact.email_normalized, Contact.business_id)
        .where(Contact.is_duplicate_of.is_(None))
        .order_by(Contact.email_normalized, Contact.contact_id)
    ).all()
    by_email: dict[str, list[tuple[int, str]]] = {}
    for cid, email, bid in rows:
        by_email.setdefault(email, []).append((cid, bid))
    for email, entries in sorted(by_email.items()):
        if len(entries) < 2:
            continue
        primary_id, primary_bid = entries[0]
        for dup_id, dup_bid in entries[1:]:
            report.pairs.append(
                DuplicatePair(
                    "contact", primary_id, dup_id, "email_normalized", email,
                    primary_bid, dup_bid, "natural",
                )
            )
            record_duplicate_gt(
                session, "contact", primary_id, dup_id, "email_normalized", email,
                "natural", primary_bid, dup_bid,
            )
            if mark_only:
                c = session.get(Contact, dup_id)
                if c is not None:
                    c.is_duplicate_of = primary_id
    session.commit()
    return report


def deduplicate_companies(session: Session, mark_only: bool = True) -> DedupReport:
    report = DedupReport()
    rows = session.execute(
        select(Company.company_id, Company.domain, Company.business_id)
        .where(Company.is_duplicate_of.is_(None), Company.domain.is_not(None))
        .order_by(Company.domain, Company.company_id)
    ).all()
    by_domain: dict[str, list[tuple[int, str]]] = {}
    for cid, domain, bid in rows:
        by_domain.setdefault(domain, []).append((cid, bid))
    for domain, entries in sorted(by_domain.items()):
        if len(entries) < 2:
            continue
        primary_id, primary_bid = entries[0]
        for dup_id, dup_bid in entries[1:]:
            report.pairs.append(
                DuplicatePair(
                    "company", primary_id, dup_id, "domain", domain,
                    primary_bid, dup_bid, "natural",
                )
            )
            record_duplicate_gt(
                session, "company", primary_id, dup_id, "domain", domain,
                "natural", primary_bid, dup_bid,
            )
            if mark_only:
                c = session.get(Company, dup_id)
                if c is not None:
                    c.is_duplicate_of = primary_id
    session.commit()
    return report


def deduplicate_opportunities(session: Session, mark_only: bool = True) -> DedupReport:
    """Soft-mark leads holding >1 opportunity (natural double-entry).

    Injected duplicate opportunities are labelled origin='injected' by the
    anomaly injector and skipped here (their duplicate_gt row already exists).
    """
    from sqlalchemy import func

    report = DedupReport()
    rows = session.execute(
        select(
            Opportunity.lead_id,
            func.count().label("c"),
            func.group_concat(Opportunity.opportunity_id),
        )
        .group_by(Opportunity.lead_id)
        .having(func.count() > 1)
    ).all()
    for lead_id, _c, opp_ids_csv in rows:
        opp_ids = [int(x) for x in str(opp_ids_csv).split(",") if x]
        opp_ids.sort()
        primary_id = opp_ids[0]
        primary = session.get(Opportunity, primary_id)
        if primary is None:
            continue
        for dup_id in opp_ids[1:]:
            dup = session.get(Opportunity, dup_id)
            if dup is None:
                continue
            # Skip pairs already labelled by injection (origin='injected')
            already = session.scalar(
                select(DuplicateGroundTruth).where(
                    DuplicateGroundTruth.entity == "opportunity",
                    DuplicateGroundTruth.duplicate_record_id == dup_id,
                )
            )
            if already is not None:
                if mark_only:
                    dup.is_duplicate_flag = True
                continue
            report.pairs.append(
                DuplicatePair(
                    "opportunity", primary_id, dup_id, "lead_id", str(lead_id),
                    primary.business_id, dup.business_id, "natural",
                )
            )
            record_duplicate_gt(
                session, "opportunity", primary_id, dup_id, "lead_id", str(lead_id),
                "natural", primary.business_id, dup.business_id,
            )
            if mark_only:
                dup.is_duplicate_flag = True
    session.commit()
    return report


def run_deduplication(session: Session) -> DedupReport:
    """Run all dedup passes; merge reports."""
    merged = DedupReport()
    for fn in (deduplicate_leads, deduplicate_contacts, deduplicate_companies):
        r = fn(session)
        merged.pairs.extend(r.pairs)
    return merged
