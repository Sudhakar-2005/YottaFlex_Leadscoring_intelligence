from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np

from yottaflex.config import Settings, load_score_rules
from yottaflex.db.base import Base

UTC = timezone.utc

FIRST_NAMES = [
    "Ava", "Liam", "Noah", "Emma", "Olivia", "Elijah", "Mateo", "Sophia",
    "Isabella", "Lucas", "Mia", "Ethan", "Amelia", "James", "Harper",
    "Benjamin", "Evelyn", "Henry", "Luna", "Jack", "Camila", "Leo",
    "Aria", "Wyatt", "Chloe", "Owen", "Penelope", "Daniel", "Layla",
    "Michael", "Zoe", "Alexander", "Nora", "Sebastian", "Hazel", "David",
    "Violet", "Joseph", "Stella", "Samuel", "Aurora", "Carter", "Bella",
    "Jayden", "Claire", "John", "Skylar", "Luke", "Paisley", "Dylan",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
]

INDUSTRIES = [
    "Technology", "Finance", "Healthcare", "Manufacturing", "Retail",
    "Education", "Energy", "Transportation", "Media", "Hospitality",
    "Construction", "Agriculture", "Telecommunications", "Insurance",
]

ICP_INDUSTRIES = {"Technology", "Finance", "Healthcare", "Manufacturing", "Retail"}

EMPLOYEE_BANDS = ["1-50", "51-200", "201-1000", "1000+"]
EMPLOYEE_BAND_WEIGHTS = [0.30, 0.35, 0.25, 0.10]

REVENUE_BANDS = [None, "<10M", "10M-50M", "50M-200M", "200M+"]
REVENUE_BAND_WEIGHTS = [0.20, 0.25, 0.25, 0.20, 0.10]

COUNTRY_TERRITORY = {
    "US": ("AMER-NE", "North America"),
    "CA": ("AMER-NE", "North America"),
    "US-W": ("AMER-W", "North America"),  # placeholder key not used as country
    "GB": ("EMEA-UK", "EMEA"),
    "DE": ("EMEA-DACH", "EMEA"),
    "FR": ("EMEA-FR", "EMEA"),
    "IN": ("APAC-IN", "APAC"),
    "SG": ("APAC-SEA", "APAC"),
    "AU": ("APAC-AU", "APAC"),
    "JP": ("APAC-JP", "APAC"),
    "BR": ("LATAM-BR", "LATAM"),
    "MX": ("LATAM-MX", "LATAM"),
    "AE": ("EMEA-ME", "EMEA"),
    "ZA": ("EMEA-AF", "EMEA"),
    "NL": ("EMEA-UK", "EMEA"),
    "SE": ("EMEA-DACH", "EMEA"),
}

COUNTRIES = list(COUNTRY_TERRITORY.keys())

TERRITORY_DEFS = [
    ("AMER-NE", "Americas Northeast", "North America", ["US", "CA"]),
    ("AMER-W", "Americas West", "North America", ["US"]),
    ("AMER-SE", "Americas Southeast", "North America", ["US", "MX"]),
    ("AMER-C", "Americas Central", "North America", ["US"]),
    ("EMEA-UK", "UK & Ireland", "EMEA", ["GB", "NL"]),
    ("EMEA-DACH", "DACH", "EMEA", ["DE", "SE"]),
    ("EMEA-FR", "France & Benelux", "EMEA", ["FR", "NL"]),
    ("EMEA-ME", "Middle East", "EMEA", ["AE"]),
    ("EMEA-AF", "Africa", "EMEA", ["ZA"]),
    ("APAC-IN", "India", "APAC", ["IN"]),
    ("APAC-SEA", "Southeast Asia", "APAC", ["SG"]),
    ("APAC-AU", "Australia & NZ", "APAC", ["AU"]),
    ("APAC-JP", "Japan", "APAC", ["JP"]),
    ("LATAM-BR", "Brazil", "LATAM", ["BR"]),
    ("LATAM-MX", "Mexico", "LATAM", ["MX"]),
    ("LATAM-S", "South America", "LATAM", ["BR", "MX"]),
]

PRODUCT_DEFS = [
    ("PROD-CRM", "YottaCRM Core", "CRM"),
    ("PROD-ANL", "YottaAnalytics", "Analytics"),
    ("PROD-AUT", "YottaAutomate", "Automation"),
    ("PROD-SVC", "YottaService Desk", "Service"),
    ("PROD-DAT", "YottaData Hub", "Data"),
    ("PROD-AI", "YottaAI Assist", "AI"),
    ("PROD-INT", "YottaIntegrate", "Integration"),
    ("PROD-SEC", "YottaSecure", "Security"),
    ("PROD-MOB", "YottaMobile", "Mobile"),
    ("PROD-PORT", "YottaPortal", "Portal"),
]

PRODUCT_LINES = [p[2] for p in PRODUCT_DEFS]

SOURCES = ["campaign", "inbound", "list", "web", "partner", "event"]

SENIORITY_BANDS = ["IC", "Manager", "Director", "VP", "C-level"]
SENIORITY_WEIGHTS = [0.35, 0.25, 0.20, 0.12, 0.08]

JOB_TITLES = {
    "IC": ["Analyst", "Engineer", "Coordinator", "Specialist", "Associate"],
    "Manager": ["Manager", "Team Lead", "Supervisor"],
    "Director": ["Director", "Head of", "Principal"],
    "VP": ["VP", "Vice President"],
    "C-level": ["CTO", "CIO", "CFO", "COO", "CEO", "CMO"],
}

COMPANY_PREFIXES = [
    "Nova", "Bright", "Apex", "Quantum", "Vertex", "Nimbus", "Atlas",
    "Pulse", "Orbit", "Cipher", "Fusion", "Zenith", "Catalyst", "Harbor",
    "Summit", "Ridge", "Echo", "Prism", "Forge", "Beacon", "Tide",
    "Crest", "Ember", "Ivory", "Onyx", "Sable", "Lumen", "Vanta",
    "Kite", "Drift",
]

COMPANY_SUFFIXES = [
    "Systems", "Labs", "Group", "Technologies", "Solutions", "Partners",
    "Works", "Dynamics", "Networks", "Industries", "Analytics", "Digital",
    "Global", "Corp", "Holdings", "Trades", "Media", "Logistics",
    "Health", "Finance",
]

DOMAIN_TLDS = ["com", "io", "net", "co", "ai", "tech"]

CAMPAIGN_CHANNELS = ["email", "webinar", "ads", "content", "event", "partner"]


@dataclass
class GenerationResult:
    counts: dict[str, int]
    seed: int
    generated_at: datetime
    manifest: dict[str, Any]


def _band_index(rng: np.random.Generator, bands: list[str], weights: list[float]) -> str:
    return str(rng.choice(bands, p=weights))


def _employee_size_score(band: str) -> int:
    return {"1-50": 25, "51-200": 55, "201-1000": 80, "1000+": 95}[band]


def _normalize_email(first: str, last: str, domain: str | None, rng: np.random.Generator) -> tuple[str, str]:
    if domain is None:
        domain = f"{COMPANY_PREFIXES[int(rng.integers(0, len(COMPANY_PREFIXES)))].lower()}.example.com"
    local = f"{first}.{last}".lower().replace("'", "").replace(" ", "")
    local += str(int(rng.integers(1, 999)))
    email = f"{local}@{domain}"
    return email, email.lower()


def _territory_for_country(country: str) -> str:
    return COUNTRY_TERRITORY[country][0]


def _region_for_country(country: str) -> str:
    return COUNTRY_TERRITORY[country][1]


def _base_time(settings: Settings) -> datetime:
    return settings.base_dt()


def generate_reference_data(session, settings: Settings, rng: np.random.Generator, t0: datetime) -> None:
    from yottaflex.db.models import Product, SalesRep, SalesRepProduct, SalesRepTerritory, Territory

    for code, name, region, countries in TERRITORY_DEFS[: settings.counts.territories]:
        session.add(
            Territory(
                territory_code=code,
                name=name,
                region=region,
                countries_json=str(countries).replace("'", '"'),
            )
        )
    session.flush()

    for code, name, line in PRODUCT_DEFS[: settings.counts.products]:
        session.add(Product(product_code=code, name=name, product_line=line))
    session.flush()

    # Score rules from YAML
    for rule in load_score_rules():
        session.add(_score_rule_from_dict(rule, t0))
    session.flush()

    # Sales reps
    territory_codes = [t[0] for t in TERRITORY_DEFS[: settings.counts.territories]]
    product_codes = [p[0] for p in PRODUCT_DEFS[: settings.counts.products]]
    for i in range(settings.counts.sales_reps):
        first = FIRST_NAMES[int(rng.integers(0, len(FIRST_NAMES)))]
        last = LAST_NAMES[int(rng.integers(0, len(LAST_NAMES)))]
        home_terr = territory_codes[i % len(territory_codes)]
        # Deterministic full-ish coverage: each rep covers home + next 2 territories
        # so every territory is covered by multiple reps across the roster
        extra_count = int(rng.integers(1, 3))
        covered = {home_terr}
        for k in range(1, extra_count + 1):
            covered.add(territory_codes[(i + k) % len(territory_codes)])
        # products: ensure broad coverage — 4-6 products with rotating bias
        prod_count = int(rng.integers(4, 7))
        base = i % len(product_codes)
        covered_products = [(base + j) % len(product_codes) for j in range(prod_count)]
        rep = SalesRep(
            employee_code=f"SR-{i + 1:04d}",
            first_name=first,
            last_name=last,
            email=f"{first.lower()}.{last.lower()}.{i + 1}@yottaflex.example.com",
            role=str(rng.choice(["sdr", "ae", "closing"], p=[0.35, 0.50, 0.15])),
            home_territory_code=home_terr,
            capacity_max_open_leads=int(rng.integers(200, 351)),
            active_leads_count=0,
            is_active=bool(rng.random() > 0.05),
            lifecycle_state="active" if rng.random() > 0.05 else "inactive",
            created_at=t0,
            updated_at=t0,
        )
        session.add(rep)
        session.flush()
        for tc in sorted(covered):
            session.add(
                SalesRepTerritory(
                    salesrep_id=rep.salesrep_id,
                    territory_code=tc,
                    coverage_role="primary" if tc == home_terr else "secondary",
                )
            )
        for pc in sorted(product_codes[j] for j in covered_products):
            session.add(
                SalesRepProduct(
                    salesrep_id=rep.salesrep_id,
                    product_code=pc,
                    skill_level=int(rng.integers(2, 6)),
                )
            )
    session.flush()


def _score_rule_from_dict(rule: dict[str, Any], t0: datetime):
    import json

    from yottaflex.db.models import ScoreRule

    return ScoreRule(
        rule_code=rule["rule_code"],
        dimension=rule["dimension"],
        name=rule["name"],
        description=rule.get("description"),
        condition_json=json.dumps(rule["condition_json"]),
        points=int(rule.get("points", 0)),
        weight=None,
        priority=int(rule.get("priority", 100)),
        effective_from=t0,
        effective_to=None,
        is_active=True,
        created_at=t0,
    )


def generate_companies(session, settings: Settings, rng: np.random.Generator, t0: datetime) -> list:
    from yottaflex.db.models import Company

    from yottaflex.ids import company_bid

    territory_codes = [t[0] for t in TERRITORY_DEFS[: settings.counts.territories]]
    companies = []
    used_domains: set[str] = set()
    total = settings.counts.companies
    # Natural duplicates live inside the baseline (P0-B); capped at 10% of pool
    dupe_n = min(settings.duplicates.natural_duplicate_companies, total // 10)
    unique_n = total - dupe_n
    for i in range(total):
        if i >= unique_n and companies:
            # Natural duplicate: copy key fields from an earlier unique company.
            # Same domain (match rule) → soft-dedup marks it; original preserved.
            src = companies[(i - unique_n) * 37 % unique_n]
            company = Company(
                business_id=company_bid(i + 1),
                name=src.name,
                domain=src.domain,
                industry=src.industry,
                employee_band=src.employee_band,
                annual_revenue_band=src.annual_revenue_band,
                country=src.country,
                region=src.region,
                territory_code=src.territory_code,
                size_score=src.size_score,
                created_at=t0,
                updated_at=t0,
                is_duplicate_of=None,
                lifecycle_state="active",
            )
            session.add(company)
            companies.append(company)
            continue
        country = COUNTRIES[int(rng.integers(0, len(COUNTRIES)))]
        # bias territory to country mapping
        territory = _territory_for_country(country)
        if territory not in territory_codes:
            territory = territory_codes[i % len(territory_codes)]
        region = _region_for_country(country)
        industry = str(rng.choice(INDUSTRIES))
        band = _band_index(rng, EMPLOYEE_BANDS, EMPLOYEE_BAND_WEIGHTS)
        revenue = str(rng.choice(REVENUE_BANDS, p=REVENUE_BAND_WEIGHTS)) if rng.random() > 0.2 else None
        prefix = COMPANY_PREFIXES[int(rng.integers(0, len(COMPANY_PREFIXES)))]
        suffix = COMPANY_SUFFIXES[int(rng.integers(0, len(COMPANY_SUFFIXES)))]
        name = f"{prefix} {suffix} {i + 1}"
        domain = f"{prefix.lower()}{suffix.lower()}{i + 1}.{rng.choice(DOMAIN_TLDS)}"
        while domain in used_domains:
            domain = domain + str(int(rng.integers(1, 9)))
        used_domains.add(domain)
        company = Company(
            business_id=company_bid(i + 1),
            name=name,
            domain=domain,
            industry=industry,
            employee_band=band,
            annual_revenue_band=revenue,
            country=country,
            region=region,
            territory_code=territory,
            size_score=_employee_size_score(band),
            created_at=t0,
            updated_at=t0,
            is_duplicate_of=None,
            lifecycle_state="active",
        )
        session.add(company)
        companies.append(company)
    session.flush()
    return companies


def generate_contacts(
    session, settings: Settings, rng: np.random.Generator, t0: datetime, companies: list
) -> list:
    from yottaflex.db.models import Contact

    from yottaflex.ids import contact_bid

    contacts: list = []
    used_emails: set[str] = set()
    total = settings.counts.contacts
    dupe_n = min(settings.duplicates.natural_duplicate_contacts, total // 10)
    unique_n = total - dupe_n
    for i in range(total):
        if i >= unique_n and contacts:
            # Natural duplicate: same person double-entered (same email)
            src = contacts[(i - unique_n) * 41 % unique_n]
            contact = Contact(
                business_id=contact_bid(i + 1),
                company_id=src.company_id,
                first_name=src.first_name,
                last_name=src.last_name,
                email=src.email,
                email_normalized=src.email_normalized,
                phone=src.phone,
                job_title=src.job_title,
                seniority_band=src.seniority_band,
                country=src.country,
                region=src.region,
                territory_code=src.territory_code,
                lifecycle_state="active",
                created_at=t0,
                updated_at=t0,
                is_duplicate_of=None,
            )
            session.add(contact)
            contacts.append(contact)
            continue
        company = companies[int(rng.integers(0, len(companies)))]
        first = FIRST_NAMES[int(rng.integers(0, len(FIRST_NAMES)))]
        last = LAST_NAMES[int(rng.integers(0, len(LAST_NAMES)))]
        email, email_n = _normalize_email(first, last, company.domain, rng)
        while email_n in used_emails:
            email, email_n = _normalize_email(first, last, company.domain, rng)
        used_emails.add(email_n)
        seniority = _band_index(rng, SENIORITY_BANDS, SENIORITY_WEIGHTS)
        titles = JOB_TITLES[seniority]
        phone = f"+1-555-{int(rng.integers(100, 999))}-{int(rng.integers(1000, 9999))}" if rng.random() > 0.3 else None
        contact = Contact(
            business_id=contact_bid(i + 1),
            company_id=company.company_id,
            first_name=first,
            last_name=last,
            email=email,
            email_normalized=email_n,
            phone=phone,
            job_title=titles[int(rng.integers(0, len(titles)))],
            seniority_band=seniority,
            country=company.country,
            region=company.region,
            territory_code=company.territory_code,
            lifecycle_state="active",
            created_at=t0,
            updated_at=t0,
            is_duplicate_of=None,
        )
        session.add(contact)
        contacts.append(contact)
    session.flush()
    return contacts


def generate_campaigns(session, settings: Settings, rng: np.random.Generator, t0: datetime) -> list:
    from yottaflex.db.models import Campaign

    campaigns = []
    for i in range(settings.counts.campaigns):
        channel = CAMPAIGN_CHANNELS[int(rng.integers(0, len(CAMPAIGN_CHANNELS)))]
        product_line = PRODUCT_LINES[int(rng.integers(0, len(PRODUCT_LINES)))]
        start = t0.date() - timedelta(days=int(rng.integers(0, 60)))
        end = start + timedelta(days=int(rng.integers(30, 120)))
        c = Campaign(
            name=f"Campaign {i + 1:03d} — {product_line} {channel}",
            channel=channel,
            product_line=product_line,
            start_date=start,
            end_date=end,
            status=str(rng.choice(["active", "completed", "paused"], p=[0.5, 0.4, 0.1])),
            created_at=t0,
        )
        session.add(c)
        campaigns.append(c)
    session.flush()
    return campaigns


def generate_leads(
    session,
    settings: Settings,
    rng: np.random.Generator,
    t0: datetime,
    companies: list,
    contacts: list,
    campaigns: list,
) -> list:
    from yottaflex.db.models import Lead, LeadCampaign

    from yottaflex.ids import lead_bid

    leads: list = []
    used_lead_emails: set[str] = set()
    used_contact_ids: set[int] = set()
    n = settings.counts.leads
    year = settings.business_id_year
    dupe_n = min(settings.duplicates.natural_duplicate_leads, n // 10)
    unique_n = n - dupe_n
    # ~50% linked to existing contact (assumption A07); each contact at most one lead
    contact_link_flags = rng.random(n) < 0.50
    heldout_flags = rng.random(n) < settings.evaluation.heldout_fraction

    for i in range(n):
        if i >= unique_n and leads:
            # Natural duplicate lead: same person re-entered (same email).
            # Soft-dedup will mark it; original lead preserved (P0-B).
            src = leads[(i - unique_n) * 53 % unique_n]
            lead = Lead(
                business_id=lead_bid(i + 1, year),
                company_id=src.company_id,
                contact_id=src.contact_id,
                email=src.email,
                email_normalized=src.email_normalized,
                first_name=src.first_name,
                last_name=src.last_name,
                country=src.country,
                region=src.region,
                territory_code=src.territory_code,
                source=src.source,
                campaign_id=src.campaign_id,
                product_line=src.product_line,
                status="new",
                fit_raw=src.fit_raw,
                intent_raw=src.intent_raw,
                engagement_raw=src.engagement_raw,
                eval_split=src.eval_split,
                created_at=t0,
                updated_at=t0,
            )
            session.add(lead)
            leads.append(lead)
            continue

        company = companies[int(rng.integers(0, len(companies)))]
        linked_contact = None
        if contact_link_flags[i]:
            for _ in range(8):
                cand = contacts[int(rng.integers(0, len(contacts)))]
                if cand.contact_id not in used_contact_ids:
                    linked_contact = cand
                    break

        if linked_contact is not None:
            first, last = linked_contact.first_name, linked_contact.last_name
            email, email_n = linked_contact.email, linked_contact.email_normalized
            contact_id = linked_contact.contact_id
        else:
            first = FIRST_NAMES[int(rng.integers(0, len(FIRST_NAMES)))]
            last = LAST_NAMES[int(rng.integers(0, len(LAST_NAMES)))]
            email, email_n = _normalize_email(first, last, company.domain, rng)
            # ensure uniqueness in lead pool
            while email_n in used_lead_emails:
                email, email_n = _normalize_email(first, last, company.domain, rng)
            contact_id = None

        used_lead_emails.add(email_n)
        if linked_contact is not None:
            used_contact_ids.add(linked_contact.contact_id)

        campaign = campaigns[int(rng.integers(0, len(campaigns)))] if rng.random() > 0.15 else None
        product_line = campaign.product_line if campaign else PRODUCT_LINES[int(rng.integers(0, len(PRODUCT_LINES)))]
        source = str(rng.choice(SOURCES, p=[0.30, 0.20, 0.15, 0.20, 0.08, 0.07]))

        # latent factors for later activity generation
        intent_latent = float(rng.random())
        engagement_latent = float(rng.random())

        lead = Lead(
            business_id=lead_bid(i + 1, year),
            company_id=company.company_id,
            contact_id=contact_id,
            email=email,
            email_normalized=email_n,
            first_name=first,
            last_name=last,
            country=company.country,
            region=company.region,
            territory_code=company.territory_code,
            source=source,
            campaign_id=campaign.campaign_id if campaign else None,
            product_line=product_line,
            status="new",
            fit_raw=float(company.size_score),
            intent_raw=intent_latent,
            engagement_raw=engagement_latent,
            eval_split="heldout" if heldout_flags[i] else "dev",
            created_at=t0,
            updated_at=t0,
        )
        session.add(lead)
        leads.append(lead)
        # defer bridge rows until lead_id is assigned
        if campaign is not None:
            lead._pending_campaign_id = campaign.campaign_id  # type: ignore[attr-defined]
    session.flush()
    for lead in leads:
        pending = getattr(lead, "_pending_campaign_id", None)
        if pending is not None:
            session.add(
                LeadCampaign(
                    lead_id=lead.lead_id,
                    campaign_id=pending,
                    first_touch_at=t0,
                    touch_count=int(rng.integers(1, 6)),
                )
            )
    session.flush()
    return leads


def generate_consents(
    session, settings: Settings, rng: np.random.Generator, t0: datetime, leads: list, contacts: list
) -> None:
    from yottaflex.db.models import Consent

    email_rate = settings.consent.email_grant_rate
    phone_rate = settings.consent.phone_grant_rate
    revoke_rate = settings.consent.revoke_rate_of_granted

    def _add_consent(subject_type: str, subject_id: int, channel: str) -> None:
        granted = float(rng.random()) < (email_rate if channel == "email" else phone_rate)
        if granted:
            status = "granted"
            if float(rng.random()) < revoke_rate:
                status = "revoked"
            granted_at = t0 if status in ("granted", "revoked") else None
            revoked_at = t0 + timedelta(days=int(rng.integers(5, 90))) if status == "revoked" else None
            valid_to = revoked_at
        else:
            status = "pending"
            granted_at = None
            revoked_at = None
            valid_to = None
        session.add(
            Consent(
                subject_type=subject_type,
                subject_id=subject_id,
                lead_id=subject_id if subject_type == "lead" else None,
                contact_id=subject_id if subject_type == "contact" else None,
                channel=channel,
                status=status,
                consent_source=str(rng.choice(["web_form", "footer", "sales", "import"])),
                granted_at=granted_at,
                revoked_at=revoked_at,
                expires_at=None,
                valid_from=t0,
                valid_to=valid_to,
                evidence_ref=f"ev-{subject_type}-{subject_id}-{channel}",
                created_at=t0,
                updated_at=t0,
            )
        )

    for lead in leads:
        _add_consent("lead", lead.lead_id, "email")
        _add_consent("lead", lead.lead_id, "phone")
    for contact in contacts:
        _add_consent("contact", contact.contact_id, "email")
        if float(rng.random()) < 0.7:
            _add_consent("contact", contact.contact_id, "phone")
    session.flush()


def generate_activities(
    session,
    settings: Settings,
    rng: np.random.Generator,
    t0: datetime,
    leads: list,
    campaigns: list,
) -> None:
    """Pre-scoring activities only (event_time < scoring window end).

    Latent intent/engagement on lead drives activity mix so scores are meaningful.
    """
    from yottaflex.db.models import Activity

    from yottaflex.ids import activity_bid

    scoring_end = t0 + timedelta(days=60)

    for lead in leads:
        intent_latent = lead.intent_raw if lead.intent_raw is not None else 0.5
        engagement_latent = lead.engagement_raw if lead.engagement_raw is not None else 0.5

        # Boost activity volume so score distribution spans Hot..Cold
        n_intent = int(rng.poisson(2.0 + 5.0 * intent_latent))
        n_engage = int(rng.poisson(3.0 + 12.0 * engagement_latent))
        n_base = int(rng.poisson(2.0 + 3.0 * engagement_latent))

        intent_types: list[str] = []
        if intent_latent > 0.35:
            if rng.random() < 0.45 + 0.45 * intent_latent:
                intent_types.append("demo_request")
            if rng.random() < 0.55:
                intent_types.append("pricing_inquiry")
            if rng.random() < 0.65:
                intent_types.append("form_submit")
        if intent_latent > 0.25 and rng.random() < 0.55:
            intent_types.append("content_download")
        # pad intent activities
        while len(intent_types) < n_intent and intent_latent > 0.4:
            intent_types.append(
                str(rng.choice(["form_submit", "content_download", "pricing_inquiry"]))
            )

        engage_types: list[str] = []
        for _ in range(max(0, n_engage)):
            engage_types.append(
                str(
                    rng.choice(
                        ["email_open", "email_click", "page_view", "content_download"],
                        p=[0.35, 0.20, 0.35, 0.10],
                    )
                )
            )

        base_types = [
            str(rng.choice(["email_sent", "page_view", "note"], p=[0.5, 0.35, 0.15]))
            for _ in range(n_base)
        ]

        all_types = intent_types + engage_types + base_types

        seq = 0
        for atype in all_types:
            seq += 1
            # event times uniform in [t0, scoring_end)
            offset_days = float(rng.uniform(0, 60))
            event_time = t0 + timedelta(days=offset_days)
            session.add(
                Activity(
                    business_id=activity_bid(lead.business_id, seq),
                    lead_id=lead.lead_id,
                    contact_id=lead.contact_id,
                    company_id=lead.company_id,
                    activity_type=atype,
                    channel="email" if atype.startswith("email") else "web",
                    event_time=event_time,
                    campaign_id=lead.campaign_id,
                    metadata_json=None,
                    created_at=event_time,
                )
            )
    session.flush()


def _make_rng(seed: int, stream: int) -> np.random.Generator:
    ss = np.random.SeedSequence([seed, stream])
    return np.random.default_rng(ss)


def generate_all(session, settings: Settings) -> GenerationResult:
    """Deterministic end-to-end baseline generation (A). No anomalies injected here."""
    from sqlalchemy import func, select

    from yottaflex.db.models import (
        Activity,
        Campaign,
        Company,
        Consent,
        Contact,
        Lead,
        Opportunity,
        Product,
        ScoreRule,
        SalesRep,
        StageHistory,
        Territory,
    )

    # Clear existing data (fresh run) in reverse dependency order (no cycles)
    clear_order = [
        "exception_record",
        "exception_resolution_history",
        "ground_truth_exception",
        "anomaly_injection_log",
        "duplicate_gt",
        "lead_score_explanation",
        "lead_status_history",
        "stage_history",
        "task",
        "opportunity",
        "activity",
        "consent",
        "lead_campaign",
        "lead",
        "salesrep_product",
        "salesrep_territory",
        "salesrep",
        "contact",
        "campaign",
        "company",
        "score_rule",
        "product",
        "territory",
    ]
    for name in clear_order:
        table = Base.metadata.tables[name]
        session.execute(table.delete())
    session.commit()

    t0 = _base_time(settings)
    seed = settings.seed

    ref_rng = _make_rng(seed, 1)
    company_rng = _make_rng(seed, 2)
    contact_rng = _make_rng(seed, 3)
    campaign_rng = _make_rng(seed, 4)
    lead_rng = _make_rng(seed, 5)
    consent_rng = _make_rng(seed, 6)
    activity_rng = _make_rng(seed, 7)

    generate_reference_data(session, settings, ref_rng, t0)
    companies = generate_companies(session, settings, company_rng, t0)
    contacts = generate_contacts(session, settings, contact_rng, t0, companies)
    campaigns = generate_campaigns(session, settings, campaign_rng, t0)
    leads = generate_leads(session, settings, lead_rng, t0, companies, contacts, campaigns)

    # P1-1: initial status timeline rows so every lead is reconstructable
    from yottaflex.engines.lead_status_history import record_initial_status

    for lead in leads:
        record_initial_status(session, lead, t0)
    session.flush()
    generate_consents(session, settings, consent_rng, t0, leads, contacts)
    generate_activities(session, settings, activity_rng, t0, leads, campaigns)

    # Baseline opportunity seeds are created later by pipeline after scoring.
    # Here we only materialize master data; opportunity count target enforced by Opportunity engine.
    session.flush()

    counts = {
        "territory": session.scalar(select(func.count()).select_from(Territory)) or 0,
        "product": session.scalar(select(func.count()).select_from(Product)) or 0,
        "score_rule": session.scalar(select(func.count()).select_from(ScoreRule)) or 0,
        "salesrep": session.scalar(select(func.count()).select_from(SalesRep)) or 0,
        "company": session.scalar(select(func.count()).select_from(Company)) or 0,
        "contact": session.scalar(select(func.count()).select_from(Contact)) or 0,
        "campaign": session.scalar(select(func.count()).select_from(Campaign)) or 0,
        "lead": session.scalar(select(func.count()).select_from(Lead)) or 0,
        "consent": session.scalar(select(func.count()).select_from(Consent)) or 0,
        "activity": session.scalar(select(func.count()).select_from(Activity)) or 0,
        "opportunity": session.scalar(select(func.count()).select_from(Opportunity)) or 0,
        "stage_history": session.scalar(select(func.count()).select_from(StageHistory)) or 0,
    }
    session.commit()

    manifest = {
        "seed": seed,
        "base_datetime": settings.base_datetime,
        "business_id_year": settings.business_id_year,
        "counts": counts,
        "targets": {
            "leads": settings.counts.leads,
            "contacts": settings.counts.contacts,
            "companies": settings.counts.companies,
            "opportunities": settings.counts.opportunities,
        },
        "natural_duplicates": {
            "companies": settings.duplicates.natural_duplicate_companies,
            "contacts": settings.duplicates.natural_duplicate_contacts,
            "leads": settings.duplicates.natural_duplicate_leads,
            "opportunities": settings.duplicates.natural_duplicate_opportunities,
        },
        "heldout_fraction": settings.evaluation.heldout_fraction,
    }
    return GenerationResult(
        counts=counts,
        seed=seed,
        generated_at=t0,
        manifest=manifest,
    )
