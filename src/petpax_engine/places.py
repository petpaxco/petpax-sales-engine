"""Google Places API (New) discovery client.

Uses Text Search with a field mask so we only pay for the fields we need.
Key comes from the GOOGLE_MAPS_API_KEY env var (Secret Manager in production).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.addressComponents",
    "places.location", "places.types", "places.primaryType", "places.businessStatus",
    "places.nationalPhoneNumber", "places.websiteUri", "places.googleMapsUri",
    "places.rating", "places.userRatingCount", "nextPageToken",
])

DEFAULT_QUERIES = ["dog grooming", "pet grooming salon", "mobile dog grooming"]


@dataclass
class Place:
    place_id: str
    name: str
    address: str | None
    street: str | None
    city: str | None
    county: str | None
    state: str | None
    zip: str | None
    lat: float | None
    lng: float | None
    phone: str | None
    website: str | None
    maps_url: str | None
    rating: float | None
    review_count: int | None
    primary_type: str | None
    operational: bool


def _component(comps: list[dict], kind: str, short: bool = False) -> str | None:
    for c in comps or []:
        if kind in c.get("types", []):
            return c.get("shortText" if short else "longText")
    return None


def parse_place(p: dict) -> Place:
    comps = p.get("addressComponents", [])
    num, route = _component(comps, "street_number"), _component(comps, "route")
    county = _component(comps, "administrative_area_level_2")
    return Place(
        place_id=p["id"],
        name=p.get("displayName", {}).get("text", ""),
        address=p.get("formattedAddress"),
        street=" ".join(x for x in (num, route) if x) or None,
        city=_component(comps, "locality"),
        county=county.replace(" County", "") if county else None,
        state=_component(comps, "administrative_area_level_1", short=True),
        zip=_component(comps, "postal_code"),
        lat=p.get("location", {}).get("latitude"),
        lng=p.get("location", {}).get("longitude"),
        phone=p.get("nationalPhoneNumber"),
        website=p.get("websiteUri"),
        maps_url=p.get("googleMapsUri"),
        rating=p.get("rating"),
        review_count=p.get("userRatingCount"),
        primary_type=p.get("primaryType"),
        operational=p.get("businessStatus", "OPERATIONAL") == "OPERATIONAL",
    )


def search(query: str, location: str, api_key: str | None = None, max_pages: int = 3,
           session: requests.Session | None = None) -> list[Place]:
    """e.g. search('dog grooming', 'Inglewood, CA'). Max 20 results/page, 3 pages."""
    key = api_key or os.environ["GOOGLE_MAPS_API_KEY"]
    s = session or requests.Session()
    body = {"textQuery": f"{query} in {location}", "pageSize": 20, "regionCode": "US"}
    out: list[Place] = []
    for _ in range(max_pages):
        r = s.post(SEARCH_URL, json=body, timeout=30,
                   headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK})
        r.raise_for_status()
        data = r.json()
        out += [parse_place(p) for p in data.get("places", [])]
        tok = data.get("nextPageToken")
        if not tok:
            break
        body = {**body, "pageToken": tok}
        time.sleep(1)
    return [p for p in out if p.operational]
