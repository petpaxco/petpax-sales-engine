"""Explainable 0-100 lead score.

Each component returns a 0..1 fraction plus reasons; the weight from
config/settings.yaml turns it into points. Unknown inputs score as *neutral*
(0.5) with an explicit "unknown" reason -- missing data is not negative
evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import settings

NEUTRAL = 0.5


@dataclass
class LeadInputs:
    phase: int | None = None
    drive_minutes: int | None = None
    miles_from_base: float | None = None
    business_type: str | None = None          # salon, mobile, chain, boutique, ...
    offers_relevant_services: bool | None = None   # low-stress, teeth brushing, premium
    sells_retail: bool | None = None
    has_decision_maker: bool = False
    has_business_email: bool = False
    has_any_email: bool = False
    has_phone: bool = False
    sourced_fact_count: int = 0
    review_count: int | None = None
    rating: float | None = None
    locations_count: int | None = None


@dataclass
class Score:
    total: int
    parts: dict[str, int]
    reasons: dict[str, list[str]] = field(default_factory=dict)

    @property
    def band(self) -> str:
        b = settings()["scoring"]["bands"]
        if self.total >= b["high"]:
            return "High priority"
        if self.total >= b["qualified"]:
            return "Qualified"
        if self.total >= b["research"]:
            return "Research required"
        return "Low priority"


def _geo(x: LeadInputs):
    if x.phase is None:
        return 0.0, ["outside current territory plan"]
    base = {1: 0.7, 2: 0.45, 3: 0.3}.get(x.phase, 0.2)
    reasons = [f"territory phase {x.phase}"]
    if x.phase == 1:
        if x.drive_minutes is not None:
            if x.drive_minutes <= 45:
                base, reasons = 1.0, reasons + [f"{x.drive_minutes} min drive from 90008"]
            elif x.drive_minutes <= 75:
                base, reasons = 0.85, reasons + [f"{x.drive_minutes} min drive from 90008"]
        elif x.miles_from_base is not None and x.miles_from_base <= 50:
            base, reasons = 0.85, reasons + [f"~{x.miles_from_base:.0f} mi straight-line (drive time pending)"]
    return base, reasons


def _fit(x: LeadInputs):
    t = (x.business_type or "").lower()
    base = {"salon": 0.7, "mobile": 0.65, "chain": 0.75, "boutique": 0.55, "daycare": 0.5}.get(t, 0.3 if t else NEUTRAL)
    reasons = [f"type: {t or 'unknown'}"]
    if x.offers_relevant_services:
        base += 0.2
        reasons.append("offers relevant services (sourced)")
    if x.sells_retail:
        base += 0.1
        reasons.append("already sells retail")
    return min(base, 1.0), reasons


def _contact(x: LeadInputs):
    pts, reasons = 0.0, []
    if x.has_business_email:
        pts += 0.5; reasons.append("business-domain email")
    elif x.has_any_email:
        pts += 0.35; reasons.append("public email (free-mail)")
    else:
        reasons.append("no email yet")
    if x.has_phone:
        pts += 0.25; reasons.append("phone")
    if x.has_decision_maker:
        pts += 0.25; reasons.append("named owner/manager")
    return min(pts, 1.0), reasons


def _personalization(x: LeadInputs):
    n = x.sourced_fact_count
    return min(n / 3, 1.0), [f"{n} sourced personalization fact(s)"]


def _potential(x: LeadInputs):
    reasons = []
    if x.review_count is None and x.locations_count is None:
        return NEUTRAL, ["unknown size (neutral)"]
    v = 0.4
    if x.review_count is not None:
        if x.review_count >= 150: v = 0.9
        elif x.review_count >= 50: v = 0.7
        elif x.review_count >= 15: v = 0.5
        reasons.append(f"{x.review_count} reviews")
    if x.rating is not None and x.rating >= 4.5:
        v += 0.1; reasons.append(f"rating {x.rating}")
    if x.locations_count and x.locations_count > 1:
        v += 0.15; reasons.append(f"{x.locations_count} locations")
    return min(v, 1.0), reasons


def score_lead(x: LeadInputs) -> Score:
    w = settings()["scoring"]["weights"]
    comps = {"geo": _geo(x), "fit": _fit(x), "contact_quality": _contact(x),
             "personalization": _personalization(x), "potential": _potential(x)}
    parts = {k: round(frac * w[k]) for k, (frac, _) in comps.items()}
    return Score(total=sum(parts.values()), parts=parts, reasons={k: r for k, (_, r) in comps.items()})
