"""Reorder estimates for Active Accounts / Reorders Due.

- 2+ dated orders: the account's own median gap between orders
- 1 dated order: the default cycle (90 days, from the existing tracker)
- no dated orders: no estimate -> "Check order dates"
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from .config import settings


@dataclass
class ReorderEstimate:
    next_reorder: date | None
    cycle_days: int | None
    basis: str            # own_median | default_cycle | unknown
    status: str           # Healthy | Reorder Soon | Overdue | Lapsed | Check order dates
    days_overdue: int | None


def estimate(order_dates: list[date | None], today: date) -> ReorderEstimate:
    cfg = settings()["reorder"]
    dated = sorted(d for d in order_dates if d)
    if not dated:
        return ReorderEstimate(None, None, "unknown", "Check order dates", None)
    if len(dated) >= 2:
        gaps = [(b - a).days for a, b in zip(dated, dated[1:]) if (b - a).days > 0]
        cycle, basis = (round(median(gaps)), "own_median") if gaps else (cfg["default_cycle_days"], "default_cycle")
    else:
        cycle, basis = cfg["default_cycle_days"], "default_cycle"
    last = dated[-1]
    nxt = last + timedelta(days=cycle)
    since = (today - last).days
    over = (today - nxt).days
    if since >= cfg["lapsed_after_days"]:
        status = "Lapsed"
    elif over > 0:
        status = "Overdue"
    elif -over <= cfg["reorder_soon_days"]:
        status = "Reorder Soon"
    else:
        status = "Healthy"
    return ReorderEstimate(nxt, cycle, basis, status, max(over, 0))


def is_reorder_due(est: ReorderEstimate) -> bool:
    """Rows shown on the Reorders Due tab."""
    return est.status in {"Reorder Soon", "Overdue", "Lapsed", "Check order dates"}
