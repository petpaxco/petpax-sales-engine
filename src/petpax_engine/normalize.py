"""Normalization helpers used for dedup keys. Pure functions, no I/O."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

_NAME_NOISE = {
    "llc", "inc", "co", "corp", "ltd", "the", "and", "&",
    "grooming", "groomers", "groomer", "salon", "spa", "pet", "pets", "dog", "dogs",
    "mobile", "boutique", "shop", "studio",
}
_FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
              "icloud.com", "optonline.net", "live.com", "msn.com", "me.com"}
_STREET_ABBR = {
    "street": "st", "avenue": "ave", "boulevard": "blvd", "road": "rd", "drive": "dr",
    "lane": "ln", "court": "ct", "place": "pl", "parkway": "pkwy", "highway": "hwy",
    "suite": "ste", "north": "n", "south": "s", "east": "e", "west": "w",
}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def normalize_name(name: str | None) -> str:
    """'The Dapper Dog Salon, LLC' -> 'dapper'. Keeps the distinctive words only."""
    if not name:
        return ""
    words = re.findall(r"[a-z0-9]+", _ascii(name).lower().replace("'", ""))
    core = [w for w in words if w not in _NAME_NOISE]
    return " ".join(core or words)


def website_domain(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    host = (urlparse(url).hostname or "").lower()
    host = host.removeprefix("www.")
    return host or None


def email_domain(email: str | None) -> str | None:
    """Business domain from an email, or None for free-mail providers."""
    if not email or "@" not in email:
        return None
    dom = email.strip().lower().rsplit("@", 1)[1]
    return None if dom in _FREE_MAIL else dom


def phone_digits(phone: str | None) -> str | None:
    """US numbers to 10 digits. Returns None for non-US / unparseable."""
    if not phone:
        return None
    first = re.split(r"[\n/;]| ext| x", phone, maxsplit=1, flags=re.I)[0]
    digits = re.sub(r"\D", "", first)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def normalize_street(street: str | None) -> str:
    if not street:
        return ""
    words = re.findall(r"[a-z0-9]+", _ascii(street).lower())
    return " ".join(_STREET_ABBR.get(w, w) for w in words)


def split_emails(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [e.strip() for e in re.split(r"[;,\s]+", raw) if "@" in e]
