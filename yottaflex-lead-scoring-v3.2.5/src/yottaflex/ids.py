"""Deterministic business identifiers (P0-A).

Formats (zero-padded, immutable, stable across CSV/JSON/SQL exports):
  Company    CO-000001
  Contact    CON-000001
  Lead       LEAD-2026-000001
  Activity   ACT-LEAD-2026-000001-001   (per-lead sequence)
  Opportunity OPP-2026-000001
  Task       TASK-LEAD-2026-000001-001  (per-lead sequence)

Integer primary keys remain as internal surrogates; business_id is the
external key exposed by API and all exports.
"""
from __future__ import annotations

import re

COMPANY_RE = re.compile(r"^CO-\d{6}$")
CONTACT_RE = re.compile(r"^CON-\d{6}$")
LEAD_RE = re.compile(r"^LEAD-\d{4}-\d{6}$")
OPPORTUNITY_RE = re.compile(r"^OPP-\d{4}-\d{6}$")
ACTIVITY_RE = re.compile(r"^ACT-LEAD-\d{4}-\d{6}-\d{3}$")
TASK_RE = re.compile(r"^TASK-LEAD-\d{4}-\d{6}-\d{3}$")


def company_bid(n: int) -> str:
    return f"CO-{n:06d}"


def contact_bid(n: int) -> str:
    return f"CON-{n:06d}"


def lead_bid(n: int, year: int) -> str:
    return f"LEAD-{year}-{n:06d}"


def opportunity_bid(n: int, year: int) -> str:
    return f"OPP-{year}-{n:06d}"


def activity_bid(lead_business_id: str, seq: int) -> str:
    return f"ACT-{lead_business_id}-{seq:03d}"


def task_bid(lead_business_id: str, seq: int) -> str:
    return f"TASK-{lead_business_id}-{seq:03d}"


def is_valid_business_id(entity: str, value: str) -> bool:
    patterns = {
        "company": COMPANY_RE,
        "contact": CONTACT_RE,
        "lead": LEAD_RE,
        "opportunity": OPPORTUNITY_RE,
        "activity": ACTIVITY_RE,
        "task": TASK_RE,
    }
    pattern = patterns.get(entity)
    if pattern is None:
        return False
    return bool(pattern.match(value))
