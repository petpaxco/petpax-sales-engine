"""Territory assignment and distance from Nathan's base (ZIP 90008).

Straight-line distance is only a pre-filter. Whether a stop is visit-worthy is
decided by real drive minutes from the Routes API (filled in later on the
business record as drive_minutes_from_base).
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from .config import settings

SOCAL_COUNTIES = {
    "los angeles": ("LA County", 1),
    "orange": ("Orange County", 1),
    "ventura": ("Ventura County", 1),
    "riverside": ("Inland Empire", 1),
    "san bernardino": ("Inland Empire", 1),
    "san diego": ("San Diego County", 1),
}
PHASE3_STATES = {"AZ", "NV", "OR", "WA"}


def miles_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * 3958.8 * asin(sqrt(a))


def miles_from_base(lat: float, lng: float) -> float:
    b = settings()["base"]
    return miles_between(b["lat"], b["lng"], lat, lng)


def assign_territory(state: str | None, county: str | None) -> tuple[str | None, int | None]:
    """Returns (territory name, phase) or (None, None) when out of plan."""
    st = (state or "").strip().upper()
    if st == "CA":
        c = (county or "").lower().replace(" county", "").strip()
        return SOCAL_COUNTIES.get(c, ("Rest of California", 2))
    if st in PHASE3_STATES:
        return ("Regional expansion", 3)
    return (None, None)


def visit_candidate(lat: float | None, lng: float | None, drive_minutes: int | None = None) -> bool:
    b = settings()["base"]
    if drive_minutes is not None:
        return drive_minutes <= b["visit_max_drive_minutes"]
    if lat is None or lng is None:
        return False
    return miles_from_base(lat, lng) <= b["visit_radius_miles"]
