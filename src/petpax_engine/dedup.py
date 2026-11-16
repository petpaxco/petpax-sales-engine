"""Duplicate detection.

Order of evidence (strongest first):
  1. Same Google place_id
  2. Same website domain (or business email domain)
  3. Same 10-digit phone
  4. Same normalized street + ZIP
  5. Fuzzy name match within the same ZIP/city  -> *review*, never auto-merge
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .normalize import (email_domain, normalize_name, normalize_street,
                        phone_digits, split_emails, website_domain)


@dataclass
class Candidate:
    key: str                       # caller's id (row ref, place_id, biz id)
    name: str
    street: str | None = None
    city: str | None = None
    zip: str | None = None
    phone: str | None = None
    website: str | None = None
    emails: str | None = None
    place_id: str | None = None

    def keys(self) -> dict[str, str | None]:
        domains = {website_domain(self.website)} | {email_domain(e) for e in split_emails(self.emails)}
        domains.discard(None)
        street = normalize_street(self.street)
        return {
            "place": self.place_id,
            "domains": sorted(domains),
            "phone": phone_digits(self.phone),
            "addr": f"{street}|{(self.zip or '').strip()[:5]}" if street and self.zip else None,
            "name": normalize_name(self.name),
            "locality": ((self.zip or "").strip()[:5] or (self.city or "").strip().lower()),
        }


@dataclass
class Match:
    a: str
    b: str
    reason: str
    auto_merge: bool
    score: float = 100.0


@dataclass
class DedupResult:
    matches: list[Match] = field(default_factory=list)

    @property
    def auto(self) -> list[Match]:
        return [m for m in self.matches if m.auto_merge]

    @property
    def review(self) -> list[Match]:
        return [m for m in self.matches if not m.auto_merge]


def find_duplicates(cands: list[Candidate], fuzzy_threshold: int = 88) -> DedupResult:
    res = DedupResult()
    keyed = [(c, c.keys()) for c in cands]
    seen: set[tuple[str, str]] = set()

    def add(a: Candidate, b: Candidate, reason: str, auto: bool, score: float = 100.0):
        pair = tuple(sorted((a.key, b.key)))
        if pair in seen:
            return
        seen.add(pair)
        res.matches.append(Match(pair[0], pair[1], reason, auto, score))

    for i, (a, ka) in enumerate(keyed):
        for b, kb in keyed[i + 1:]:
            if ka["place"] and ka["place"] == kb["place"]:
                add(a, b, "same place_id", True)
            elif set(ka["domains"]) & set(kb["domains"]):
                add(a, b, "same website/email domain", True)
            elif ka["phone"] and ka["phone"] == kb["phone"]:
                add(a, b, "same phone", True)
            elif ka["addr"] and ka["addr"] == kb["addr"]:
                add(a, b, "same street address", True)
            elif ka["locality"] and ka["locality"] == kb["locality"] and ka["name"] and kb["name"]:
                s = fuzz.token_set_ratio(ka["name"], kb["name"])
                if s >= fuzzy_threshold:
                    add(a, b, "similar name, same area", False, s)
    return res
