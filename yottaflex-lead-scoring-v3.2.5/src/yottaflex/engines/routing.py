from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from yottaflex.db.models import Lead, SalesRep, SalesRepProduct, SalesRepTerritory
from yottaflex.logging_setup import get_logger

log = get_logger("routing")


@dataclass
class RouteCandidate:
    salesrep_id: int
    employee_code: str
    score_reasons: list[str] = field(default_factory=list)


def territory_covers(session: Session, salesrep_id: int, territory_code: str) -> bool:
    row = session.execute(
        select(SalesRepTerritory.id).where(
            SalesRepTerritory.salesrep_id == salesrep_id,
            SalesRepTerritory.territory_code == territory_code,
        )
    ).first()
    return row is not None


def product_skilled(session: Session, salesrep_id: int, product_line: str | None) -> bool:
    if not product_line:
        return True  # no product constraint
    # product_line matches Product.product_line; skills stored by product_code
    from yottaflex.db.models import Product

    codes = session.scalars(
        select(Product.product_code).where(Product.product_line == product_line)
    ).all()
    if not codes:
        return True
    row = session.execute(
        select(SalesRepProduct.id).where(
            SalesRepProduct.salesrep_id == salesrep_id,
            SalesRepProduct.product_code.in_(list(codes)),
        )
    ).first()
    return row is not None


def _coverage_maps(session: Session) -> tuple[dict[int, set[str]], dict[int, set[str]]]:
    """Preload territory and product skill maps (avoids N+1 during assignment)."""
    from yottaflex.db.models import Product

    terr_map: dict[int, set[str]] = {}
    for sid, tc in session.execute(
        select(SalesRepTerritory.salesrep_id, SalesRepTerritory.territory_code)
    ).all():
        terr_map.setdefault(sid, set()).add(tc)

    # product_code -> product_line
    code_to_line = dict(session.execute(select(Product.product_code, Product.product_line)).all())
    prod_map: dict[int, set[str]] = {}
    for sid, pc in session.execute(
        select(SalesRepProduct.salesrep_id, SalesRepProduct.product_code)
    ).all():
        line = code_to_line.get(pc)
        if line:
            prod_map.setdefault(sid, set()).add(line)
    return terr_map, prod_map


def eligible_reps_for_lead(
    session: Session,
    lead: Lead,
    require_capacity: bool = True,
    _maps: tuple[dict[int, set[str]], dict[int, set[str]]] | None = None,
) -> list[SalesRep]:
    """Territory & Product Routing Engine (F).

    Primary: territory + product match.
    Fallback: territory-only if no rep has the product skill (documented rule BR-R02b).
    Deterministic ordering by salesrep_id.
    """
    reps = session.scalars(
        select(SalesRep)
        .where(SalesRep.is_active.is_(True))
        .order_by(SalesRep.salesrep_id)
    ).all()

    terr_map, prod_map = _maps if _maps is not None else _coverage_maps(session)

    territory_ok: list[SalesRep] = []
    territory_and_product: list[SalesRep] = []
    for rep in reps:
        if lead.territory_code not in terr_map.get(rep.salesrep_id, set()):
            continue
        if require_capacity and rep.active_leads_count >= rep.capacity_max_open_leads:
            continue
        territory_ok.append(rep)
        if not lead.product_line or lead.product_line in prod_map.get(rep.salesrep_id, set()):
            territory_and_product.append(rep)

    if territory_and_product:
        return territory_and_product
    return territory_ok


def route_lead(session: Session, lead: Lead) -> list[RouteCandidate]:
    reps = eligible_reps_for_lead(session, lead)
    return [
        RouteCandidate(
            salesrep_id=r.salesrep_id,
            employee_code=r.employee_code,
            score_reasons=[
                f"territory={lead.territory_code}",
                f"product={lead.product_line or 'any'}",
                f"load={r.active_leads_count}/{r.capacity_max_open_leads}",
            ],
        )
        for r in reps
    ]
