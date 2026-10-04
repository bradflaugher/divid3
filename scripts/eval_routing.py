#!/usr/bin/env python3
"""
Offline routing-quality evaluation for divid3.

Replicates the browser's routing pipeline exactly (see index.html):
  1. classifyRules  — bangs, bare domains, localhost
  2. semantic match — embed query with the same quantized ONNX MiniLM the
                      page uses, score each route by the mean of its top-3
                      cosine similarities plus a small capped keyword boost
                      (matching scoreAll), highest wins
  3. (separately) the keyword fallback router used in ?lite=1 / low-memory
     mode, so corpus edits keep BOTH routers consistent

and scores both routers against the labeled benchmark in
scripts/routing_benchmark.json.

Usage:
  python3 scripts/eval_routing.py                 # full report
  python3 scripts/eval_routing.py --misses-only   # just the misroutes
  python3 scripts/eval_routing.py --pooling topk --k 3
  python3 scripts/eval_routing.py --query "best running shoes"  # one-off probe

Benchmark entries:
  { "q": "the query", "expect": "engine", "also_ok": ["engine", ...] }
`also_ok` marks genuinely ambiguous queries where more than one routing
is defensible; those count as correct for any listed engine.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from generate_search_embeddings import embed_all, load_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
PHRASES_FILE = REPO_ROOT / "scripts" / "search_phrases.json"
BENCH_FILE = REPO_ROOT / "scripts" / "routing_benchmark.json"

MIN_KEYWORD_SCORE = 2  # keep in sync with index.html
# Hybrid keyword boost applied on top of semantic scores (scoreAll in
# index.html). Keep in sync with KEYWORD_BOOST_* there.
KEYWORD_BOOST_PER_POINT = 0.03
KEYWORD_BOOST_MAX_POINTS = 5


# ───────────────────────────────────────────────────────────────────────
# Keyword router (mirror of classifyKeywords in index.html)
# ───────────────────────────────────────────────────────────────────────
def keyword_scores(query: str, rules: list) -> dict[str, float]:
    """Mirror of keywordScores in index.html."""
    padded = " " + normalize_for_keywords(query) + " "
    scores: dict[str, float] = defaultdict(float)
    for rule in rules:
        if rule_matches(rule, padded):
            scores[rule["engine"]] += rule["weight"]
    return scores


_NON_WORD_RE = re.compile(r"[^\w']+|_+")


def normalize_for_keywords(text: str) -> str:
    """Mirror of normalizeForKeywords in index.html: lowercase, fold
    punctuation to single spaces."""
    return _NON_WORD_RE.sub(" ", re.sub("[‘’]", "'", text.lower())).strip()


def rule_matches(rule: dict, padded: str) -> bool:
    """Mirror of ruleMatches in index.html: keywords match whole words."""
    return any(
        f" {normalize_for_keywords(kw)} " in padded
        for kw in rule["kw"]
    )


def classify_keywords(query: str, rules: list) -> str | None:
    # A matching priority rule (explicit writing intent) wins outright.
    padded = " " + normalize_for_keywords(query) + " "
    for rule in rules:
        if rule.get("priority") and rule_matches(rule, padded):
            return rule["engine"]
    scores = keyword_scores(query, rules)
    if not scores:
        return None
    best_engine, best_score = None, 0
    for engine, score in scores.items():
        if score > best_score:
            best_engine, best_score = engine, score
    return best_engine if best_score >= MIN_KEYWORD_SCORE else None


# ───────────────────────────────────────────────────────────────────────
# Semantic router (mirror of scoreAll in index.html)
# ───────────────────────────────────────────────────────────────────────
class SemanticRouter:
    def __init__(self, pooling: str = "max", k: int = 3, boost: bool = True):
        cfg = json.loads(PHRASES_FILE.read_text(encoding="utf-8"))
        self.cfg = cfg
        self.pooling = pooling
        self.k = k
        self.boost = boost
        tok, sess = load_pipeline()
        self.tok, self.sess = tok, sess
        self.routes = []
        for route in cfg["_routes"]:
            phrases = [p.strip() for p in route["phrases"] if p.strip()]
            # de-dup like the generator does
            seen: set[str] = set()
            dedup = []
            for p in phrases:
                if p.lower() not in seen:
                    seen.add(p.lower())
                    dedup.append(p)
            vecs = np.array(embed_all(tok, sess, dedup), dtype=np.float32)
            self.routes.append({"key": route["key"], "phrases": dedup, "vectors": vecs})

    def embed_query(self, query: str) -> np.ndarray:
        return np.array(embed_all(self.tok, self.sess, [query])[0], dtype=np.float32)

    def score(self, query: str):
        """Returns (best_key, ranked [(key, score)], winning_phrase)."""
        qv = self.embed_query(query)
        kw = keyword_scores(query, self.cfg["keywordRules"]) if self.boost else {}
        ranked = []
        winners = {}
        for r in self.routes:
            sims = r["vectors"] @ qv
            if self.pooling == "max":
                s = float(sims.max())
            else:  # topk mean
                k = min(self.k, len(sims))
                s = float(np.sort(sims)[-k:].mean())
            s += KEYWORD_BOOST_PER_POINT * min(kw.get(r["key"], 0), KEYWORD_BOOST_MAX_POINTS)
            ranked.append((r["key"], s))
            winners[r["key"]] = r["phrases"][int(sims.argmax())]
        ranked.sort(key=lambda t: -t[1])
        best = ranked[0][0]
        return best, ranked, winners[best]


def main() -> int:
    ap = argparse.ArgumentParser()
    # default mirrors index.html scoreAll(): mean of top-3 neighbors
    ap.add_argument("--pooling", choices=["max", "topk"], default="topk")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--no-boost", action="store_true",
                    help="disable the hybrid keyword boost (pure semantic)")
    ap.add_argument("--misses-only", action="store_true")
    ap.add_argument("--query", help="probe a single query and exit")
    args = ap.parse_args()

    router = SemanticRouter(pooling=args.pooling, k=args.k, boost=not args.no_boost)
    rules = router.cfg["keywordRules"]

    if args.query:
        best, ranked, phrase = router.score(args.query)
        kw = classify_keywords(args.query, rules)
        print(f"query:    {args.query!r}")
        print(f"semantic: {best}  (won via phrase: {phrase!r})")
        print(f"keyword:  {kw or 'ddg (fallback)'}")
        for key, s in ranked:
            print(f"  {key:<12} {s:.4f}")
        return 0

    bench = json.loads(BENCH_FILE.read_text(encoding="utf-8"))["queries"]
    sem_hits, kw_hits = 0, 0
    per_engine = defaultdict(lambda: [0, 0])  # expect → [hits, total]
    kw_per_engine = defaultdict(lambda: [0, 0])
    misses = []
    kw_misses = []

    for item in bench:
        q, expect = item["q"], item["expect"]
        ok = {expect, *item.get("also_ok", [])}

        got, ranked, phrase = router.score(q)
        per_engine[expect][1] += 1
        if got in ok:
            sem_hits += 1
            per_engine[expect][0] += 1
        else:
            margin = ranked[0][1] - next(s for k, s in ranked if k in ok)
            misses.append((q, expect, got, phrase, margin))

        kw_got = classify_keywords(q, rules) or "ddg"
        kw_per_engine[expect][1] += 1
        if kw_got in ok:
            kw_hits += 1
            kw_per_engine[expect][0] += 1
        else:
            kw_misses.append((q, expect, kw_got))

    n = len(bench)
    print(f"\n=== SEMANTIC ROUTER ({args.pooling}"
          f"{f', k={args.k}' if args.pooling == 'topk' else ''}) ===")
    print(f"accuracy: {sem_hits}/{n} = {100 * sem_hits / n:.1f}%")
    for eng in sorted(per_engine):
        h, t = per_engine[eng]
        print(f"  {eng:<12} {h:>3}/{t:<3} {100 * h / t:.0f}%")
    print("\n=== KEYWORD ROUTER (lite mode) ===")
    print(f"accuracy: {kw_hits}/{n} = {100 * kw_hits / n:.1f}%")
    for eng in sorted(kw_per_engine):
        h, t = kw_per_engine[eng]
        print(f"  {eng:<12} {h:>3}/{t:<3} {100 * h / t:.0f}%")

    if misses:
        print(f"\n--- semantic misroutes ({len(misses)}) ---")
        for q, expect, got, phrase, margin in sorted(misses, key=lambda m: -m[4]):
            print(f"  [{expect:>10} → {got:<10}] (Δ{margin:.3f}) {q!r}")
            print(f"      hijacked by phrase: {phrase!r}")
    if kw_misses and not args.misses_only:
        print(f"\n--- keyword misroutes ({len(kw_misses)}) ---")
        for q, expect, got in kw_misses:
            print(f"  [{expect:>10} → {got:<10}] {q!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
