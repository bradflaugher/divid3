#!/usr/bin/env python3
"""
Validate scripts/search_phrases.json and the generated search-config.json.

Catches the kinds of edits that break routing at runtime:
  - missing or extra engine fields
  - urlTemplates without a {q} placeholder
  - bangs or keyword rules pointing at engines that don't exist
  - _routes entries that the runtime can't dispatch to
  - search-config.json drifting from search_phrases.json

Exits non-zero on any failure so CI fails the build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PHRASES = REPO_ROOT / "scripts" / "search_phrases.json"
CONFIG = REPO_ROOT / "search-config.json"

ALLOWED_ENGINE_FIELDS = {"name", "urlTemplate"}


def fail(msg: str) -> None:
    print(f"validate_config: {msg}", file=sys.stderr)
    sys.exit(1)


def validate_phrases(cfg: dict) -> tuple[dict, dict, list]:
    engines = cfg.get("engines")
    bangs = cfg.get("bangs")
    rules = cfg.get("keywordRules")

    if not isinstance(engines, dict) or not engines:
        fail("'engines' must be a non-empty object in scripts/search_phrases.json")
    if not isinstance(bangs, dict) or not bangs:
        fail("'bangs' must be a non-empty object in scripts/search_phrases.json")
    if not isinstance(rules, list):
        fail("'keywordRules' must be a list in scripts/search_phrases.json")

    if "ddg" not in engines:
        fail("'engines' must define 'ddg' (the default fallback engine)")

    for key, val in engines.items():
        if not isinstance(val, dict):
            fail(f"engine '{key}' must be an object")
        missing = {"name", "urlTemplate"} - val.keys()
        if missing:
            fail(f"engine '{key}' missing required fields: {sorted(missing)}")
        stray = set(val) - ALLOWED_ENGINE_FIELDS
        if stray:
            fail(
                f"engine '{key}' has unsupported fields: {sorted(stray)}. "
                f"Allowed: {sorted(ALLOWED_ENGINE_FIELDS)}"
            )
        if key != "direct" and "{q}" not in val["urlTemplate"]:
            fail(f"engine '{key}' urlTemplate must contain '{{q}}' (got {val['urlTemplate']!r})")

    for shortcut, target in bangs.items():
        if target not in engines:
            fail(f"bang '{shortcut}' points at undefined engine '{target}'")

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            fail(f"keywordRules[{i}] must be an object")
        if rule.get("engine") not in engines:
            fail(f"keywordRules[{i}] points at undefined engine '{rule.get('engine')}'")
        if not isinstance(rule.get("kw"), list) or not rule["kw"]:
            fail(f"keywordRules[{i}] needs a non-empty 'kw' list")
        weight = rule.get("weight")
        if not isinstance(weight, (int, float)) or weight <= 0:
            fail(f"keywordRules[{i}] needs a positive numeric 'weight'")

    for route in cfg.get("_routes", []):
        rkey = route.get("key")
        if rkey not in engines:
            fail(f"_routes entry '{rkey}' is not declared in 'engines'")

    return engines, bangs, rules


def validate_generated(engines: dict, bangs: dict, rules: list) -> None:
    if not CONFIG.exists():
        fail(
            f"{CONFIG.relative_to(REPO_ROOT)} is missing. "
            "Run `python3 scripts/generate_search_embeddings.py` to (re)build it."
        )
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if cfg.get("engines") != engines:
        fail("search-config.json engines drifted from search_phrases.json (regenerate)")
    if cfg.get("bangs") != bangs:
        fail("search-config.json bangs drifted from search_phrases.json (regenerate)")
    if cfg.get("keywordRules") != rules:
        fail("search-config.json keywordRules drifted from search_phrases.json (regenerate)")


def main() -> int:
    if not PHRASES.exists():
        fail(f"{PHRASES} not found")
    try:
        cfg = json.loads(PHRASES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{PHRASES.relative_to(REPO_ROOT)} is invalid JSON: {e}")

    engines, bangs, rules = validate_phrases(cfg)
    validate_generated(engines, bangs, rules)
    print(f"OK: {len(engines)} engines, {len(bangs)} bangs, {len(rules)} keyword rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
