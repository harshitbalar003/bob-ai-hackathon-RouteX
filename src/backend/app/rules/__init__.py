"""
app/rules/__init__.py — Rule pack loader.

Loads all YAML files in this directory at import time.
Rule packs are the single source of truth for severity thresholds.
Changing a threshold = edit the YAML + bump `version`. No Python change needed.
"""
from __future__ import annotations

import pathlib
from functools import lru_cache

import yaml

from app.models.domain import RulePack, SeverityRule, TempRange

_RULES_DIR = pathlib.Path(__file__).parent


@lru_cache(maxsize=None)
def load_rule_packs() -> dict[str, RulePack]:
    """Return all rule packs keyed by their id. Cached after first load."""
    packs: dict[str, RulePack] = {}
    for yaml_file in sorted(_RULES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        pack = _parse_rule_pack(raw)
        packs[pack.id] = pack
    return packs


def get_rule_pack(regime_id: str) -> RulePack | None:
    """Return the rule pack for the given regulatory regime id, or None."""
    return load_rule_packs().get(regime_id)


def _parse_rule_pack(raw: dict) -> RulePack:
    range_raw = raw["allowed_range_c"]
    allowed_range = TempRange(min=range_raw["min"], max=range_raw["max"])

    rules = []
    for r in raw.get("severity_rules", []):
        rules.append(
            SeverityRule(
                id=r["id"],
                severity=r["severity"],
                citation=r["citation"],
                min_degree_minutes=r.get("min_degree_minutes"),
                min_minutes_out_of_range=r.get("min_minutes_out_of_range"),
                max_temp_exceeded_by_c=r.get("max_temp_exceeded_by_c"),
                below_range=r.get("below_range"),
                applies_to_cargo=r.get("applies_to_cargo"),
            )
        )

    return RulePack(
        id=raw["id"],
        version=raw["version"],
        display_name=raw["display_name"],
        citation_base=raw["citation_base"],
        allowed_range_c=allowed_range,
        severity_rules=rules,
        disposition_map=raw.get("disposition_map", {}),
    )
