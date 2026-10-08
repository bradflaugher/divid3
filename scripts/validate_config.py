#!/usr/bin/env python3
"""
Validate scripts/search_phrases.json and the generated search-config.json.

Catches the kinds of edits that break routing at runtime:
  - missing or extra engine fields
  - urlTemplates without a {q} placeholder
  - bangs or keyword rules pointing at engines that don't exist
  - _routes entries that the runtime can't dispatch to
  - destinations (the per-route pickers) that are malformed, not https,
    out of step with `engines`, or whose bangs collide
  - search-config.json drifting from search_phrases.json

Exits non-zero on any failure so CI fails the build.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PHRASES = REPO_ROOT / "scripts" / "search_phrases.json"
CONFIG = REPO_ROOT / "search-config.json"

ALLOWED_ENGINE_FIELDS = {"name", "urlTemplate"}
DESTINATION_FIELDS = {"short", "label", "blurb", "options"}
OPTION_FIELDS = {"name", "by", "note", "urlTemplate", "bangs"}
BANG_RE = re.compile(r"^[a-z0-9]+$")


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
        if "priority" in rule and not isinstance(rule["priority"], bool):
            fail(f"keywordRules[{i}] 'priority' must be true or false")
        if "unless" in rule and (not isinstance(rule["unless"], list) or not rule["unless"]):
            fail(f"keywordRules[{i}] 'unless' must be a non-empty list")

    for route in cfg.get("_routes", []):
        rkey = route.get("key")
        if rkey not in engines:
            fail(f"_routes entry '{rkey}' is not declared in 'engines'")

    validate_route_phrases(cfg.get("_routes", []))
    validate_destinations(cfg.get("destinations"), engines, bangs)
    return engines, bangs, rules


def validate_destinations(dests: object, engines: dict, bangs: dict) -> None:
    """The destination pickers. Every routable engine has a section whose
    options the user can choose between; the first option is the default
    and must be exactly what `engines` says (it's what routes before the
    picker runs, and what the Python evals see). Option bangs (`!claude`,
    `!yt`) reach one option directly; they must be unique and must not
    shadow a route bang (`!ai`, `!m`), which follows the user's choice."""
    if not isinstance(dests, dict) or not dests:
        fail("'destinations' must be a non-empty object in scripts/search_phrases.json")
    routable = set(engines) - {"direct"}
    if set(dests) != routable:
        fail(f"'destinations' must have one section per engine: {sorted(routable)} (got {sorted(dests)})")
    seen: dict[str, str] = {}
    for route, sec in dests.items():
        if not isinstance(sec, dict):
            fail(f"destinations['{route}'] must be an object")
        if set(sec) != DESTINATION_FIELDS:
            fail(f"destinations['{route}'] needs exactly {sorted(DESTINATION_FIELDS)}")
        for field in ("short", "label", "blurb"):
            if not isinstance(sec[field], str) or not sec[field].strip():
                fail(f"destinations['{route}'].{field} must be a non-empty string")
        if len(sec["short"]) > 8:
            fail(f"destinations['{route}'].short is shown beside every pick; keep it to 8 characters")
        options = sec["options"]
        if not isinstance(options, dict) or len(options) < 2:
            fail(f"destinations['{route}'].options needs at least two choices")
        for oid, val in options.items():
            where = f"destinations['{route}'].options['{oid}']"
            if not BANG_RE.match(oid):
                fail(f"{where}: id must be lowercase letters/digits")
            if not isinstance(val, dict):
                fail(f"{where} must be an object")
            if set(val) != OPTION_FIELDS:
                fail(f"{where} needs exactly {sorted(OPTION_FIELDS)} (got {sorted(val)})")
            for field in ("name", "by", "note", "urlTemplate"):
                if not isinstance(val[field], str) or not val[field].strip():
                    fail(f"{where}.{field} must be a non-empty string")
            url = val["urlTemplate"]
            if not url.startswith("https://") or url.count("{q}") != 1:
                fail(f"{where} urlTemplate must be https with one {{q}} (got {url!r})")
            if not isinstance(val["bangs"], list):
                fail(f"{where}.bangs must be a list")
            for b in val["bangs"]:
                if not isinstance(b, str) or not BANG_RE.match(b):
                    fail(f"{where} bang {b!r} must be lowercase letters/digits")
                if b in bangs:
                    fail(f"{where} bang '!{b}' shadows the route bang for '{bangs[b]}'")
                if b in seen:
                    fail(f"bang '!{b}' is used by both {seen[b]} and {route}/{oid}")
                seen[b] = f"{route}/{oid}"
        default = next(iter(options.values()))
        if engines[route] != {"name": default["name"], "urlTemplate": default["urlTemplate"]}:
            fail(f"engines['{route}'] must match the first (default) option of destinations['{route}']")


def validate_route_phrases(routes: list) -> None:
    """Corpus-quality rules learned from eval (scripts/eval_routing.py):

    1. No single-word phrases outside the 'ddg' fallback route. Under
       nearest-neighbor pooling a bare word ('buy', 'music', 'guide')
       becomes a universal attractor that hijacks unrelated queries —
       removing them was worth ~10 points of routing accuracy. The ddg
       route is exempt because navigational brand words ('wikipedia',
       'facebook') genuinely belong to the fallback engine.
    2. No phrase may appear in two different routes — that's a
       guaranteed routing conflict.
    """
    seen: dict[str, str] = {}
    for route in routes:
        rkey = route.get("key")
        for phrase in route.get("phrases", []):
            p = phrase.strip().lower()
            if not p:
                fail(f"route '{rkey}' contains an empty phrase")
            if " " not in p and rkey != "ddg":
                fail(
                    f"route '{rkey}' has single-word phrase {p!r} — bare words "
                    "hijack the nearest-neighbor router; use a multi-word, "
                    "intent-specific phrase instead"
                )
            if p in seen and seen[p] != rkey:
                fail(f"phrase {p!r} appears in both '{seen[p]}' and '{rkey}'")
            seen[p] = rkey

    bench_file = REPO_ROOT / "scripts" / "routing_benchmark.json"
    if bench_file.exists():
        bench = json.loads(bench_file.read_text(encoding="utf-8"))
        overlap = [
            item["q"] for item in bench.get("queries", [])
            if item["q"].strip().lower() in seen
        ]
        if overlap:
            fail(
                "benchmark queries copied verbatim into _routes (the benchmark "
                f"must stay held-out): {overlap[:5]}"
            )


def validate_generated(engines: dict, bangs: dict, rules: list, destinations: dict) -> None:
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
    if cfg.get("destinations") != destinations:
        fail("search-config.json destinations drifted from search_phrases.json (regenerate)")


def main() -> int:
    if not PHRASES.exists():
        fail(f"{PHRASES} not found")
    try:
        cfg = json.loads(PHRASES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{PHRASES.relative_to(REPO_ROOT)} is invalid JSON: {e}")

    engines, bangs, rules = validate_phrases(cfg)
    validate_generated(engines, bangs, rules, cfg["destinations"])
    print(
        f"OK: {len(engines)} engines, {len(bangs)} bangs, {len(rules)} keyword rules, "
        f"{sum(len(d['options']) for d in cfg['destinations'].values())} destination options"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
