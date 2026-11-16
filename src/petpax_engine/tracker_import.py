"""Read-only import of PetPax_Retail_Account_Tracker_1 (Accounts tab).

Maps each row to a business + pipeline stage, and ordering rows to an account
record. Nothing is invented: missing or inconsistent values become entries in
`issues`, and every record keeps a reference back to its tracker row.
The source spreadsheet is never written to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .normalize import email_domain, phone_digits, split_emails, website_domain

TRACKER_ID = "1sWvxBCZ5aT8s4C64Vvoeu2z6WMvaMB-IwE57hK5mHq4"
ACCOUNTS_TAB = "Accounts"

STAGE_MAP = {
    "1 - lead": "researching",
    "2 - contacted": "engaged",
    "3 - interested": "engaged",
    "4 - sample sent": "proposal_or_sample",
    "5 - first order": "active_account",
    "6 - repeat customer": "active_account",
    "closed - not interested": "lost",
    "closed - lost": "lost",
}
HEALTH_TO_STATUS = {
    "healthy": "active", "reorder soon": "active", "overdue": "at_risk",
    "lapsed": "inactive", "check order dates": "active",
}
TYPE_MAP = {
    "groomer": "salon", "mobile groomer": "mobile", "daycare / boarding": "daycare",
    "pet boutique / retail": "boutique", "holistic / natural retail": "retail",
    "grocery / market": "retail", "trainer": "trainer", "veterinary": "vet",
    "online retailer": "retail", "distributor": "distributor", "chain / big-box": "chain",
    "individual / other": "individual",
}


def parse_date(s: str | None) -> date | None:
    s = (s or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_money(s: str | None) -> float | None:
    s = (s or "").strip()
    if not s or s == "-":
        return None
    try:
        return float(re.sub(r"[^\d.\-]", "", s))
    except ValueError:
        return None


def parse_int(s: str | None) -> int | None:
    s = (s or "").strip()
    return int(s) if s.isdigit() else None


@dataclass
class ImportedRecord:
    row_ref: str
    name: str
    stage: str
    business: dict
    contact: dict
    account: dict | None = None
    issues: list[str] = field(default_factory=list)
    exclude_from_cold: bool = True     # every tracker row is already known to PetPax


def map_accounts(values: list[list[str]]) -> list[ImportedRecord]:
    header, *rows = values
    idx = {h.strip(): i for i, h in enumerate(header)}

    def get(row, col):
        i = idx.get(col)
        return row[i].strip() if i is not None and i < len(row) and row[i] else ""

    out: list[ImportedRecord] = []
    for n, row in enumerate(rows, start=2):
        name = get(row, "Account / Shop Name")
        if not name:
            continue
        issues: list[str] = []
        raw_stage = get(row, "Stage").lower()
        stage = STAGE_MAP.get(raw_stage)
        if not stage:
            issues.append(f"unknown stage '{get(row, 'Stage')}'")
            stage = "researching"

        emails = split_emails(get(row, "Email"))
        phone = get(row, "Phone")
        country = get(row, "Country") or "USA"
        acct_type = TYPE_MAP.get(get(row, "Account Type").lower(), "other" if get(row, "Account Type") else "salon")
        if "(no shop name)" in name.lower():
            acct_type = "individual"
            issues.append("no shop name (individual buyer)")
        if country.upper() not in {"USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA"}:
            issues.append(f"international ({country})")
        if not emails:
            issues.append("no email")
        if "bounced" in get(row, "Notes").lower():
            issues.append("email bounced")
        if not get(row, "Street Address"):
            issues.append("no street address")
        if phone and not phone_digits(phone) and country.upper() in {"USA", "US"}:
            issues.append(f"phone not parseable: {phone!r}")

        business = {
            "name": name, "type": acct_type,
            "street": get(row, "Street Address") or None, "city": get(row, "City") or None,
            "state": get(row, "State") or None, "zip": get(row, "ZIP") or None, "country": country,
            "website": get(row, "Website") or None,
            "website_domain": website_domain(get(row, "Website")) or next(filter(None, map(email_domain, emails)), None),
            "phone": phone or None, "phone_digits": phone_digits(phone),
            "source": "retail_tracker", "source_ref": f"{TRACKER_ID}:{ACCOUNTS_TAB}!A{n}",
        }
        contact = {"name": get(row, "Contact Name") or None, "role": get(row, "Contact Role") or None,
                   "emails": emails, "phone": phone or None}

        account = None
        first, last = parse_date(get(row, "First Order")), parse_date(get(row, "Last Order"))
        n_orders = parse_int(get(row, "# Orders")) or 0
        revenue = parse_money(get(row, "Lifetime Revenue"))
        if stage == "active_account":
            if n_orders == 0:
                issues.append("marked as customer but 0 orders recorded")
                stage = "engaged"
            else:
                if not first or not last:
                    issues.append("order dates missing")
                if revenue is None:
                    issues.append("order amounts missing")
                health = get(row, "Account Health").lower()
                owner = (get(row, "Owner") or "").lower() or "anthony"
                if not get(row, "Owner"):
                    issues.append("owner blank (defaulted to Anthony)")
                account = {
                    "status": HEALTH_TO_STATUS.get(health, "active"),
                    "owner": owner,
                    "products_carried": get(row, "Products Carried") or None,
                    "first_order_at": first, "last_order_at": last,
                    "order_count": n_orders, "lifetime_revenue": revenue,
                    "last_order_value": parse_money(get(row, "Avg Order")) if n_orders == 1 else None,
                    "next_follow_up": parse_date(get(row, "Next Action Date")),
                    "last_interaction": parse_date(get(row, "Last Contact")),
                    "notes": get(row, "Notes") or None,
                    "next_action": get(row, "Next Action") or None,
                    "tracker_row_ref": business["source_ref"],
                    "tracker_health": get(row, "Account Health") or None,
                }
        out.append(ImportedRecord(row_ref=business["source_ref"], name=name, stage=stage,
                                  business=business, contact=contact, account=account, issues=issues))
    return out


def summarize(records: list[ImportedRecord]) -> dict:
    accts = [r for r in records if r.account]
    return {
        "rows": len(records),
        "active_accounts": len(accts),
        "leads": len(records) - len(accts) - sum(r.stage == "lost" for r in records),
        "lost": sum(r.stage == "lost" for r in records),
        "with_issues": sum(bool(r.issues) for r in records),
        "california": sum((r.business.get("state") or "").upper() == "CA" for r in records),
    }
