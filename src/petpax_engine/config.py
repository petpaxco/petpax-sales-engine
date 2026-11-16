from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@lru_cache
def settings(path: str | None = None) -> dict:
    p = Path(path) if path else ROOT / "config" / "settings.yaml"
    data = yaml.safe_load(p.read_text())
    w = data["scoring"]["weights"]
    if sum(w.values()) != 100:
        raise ValueError(f"scoring weights must sum to 100, got {sum(w.values())}")
    return data
