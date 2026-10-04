#!/usr/bin/env python3
"""
Unit tests for divid3's routing logic.

Run from the repo root:
    python3 -m unittest discover -s tests/unit -v     (or: npm run test:unit)

Three layers:
  * ConfigTests          — static checks on the config + generated artifacts
                           (no model needed, milliseconds).
  * KeywordRouterTests   — the lite-mode keyword router (mirror of
                           classifyKeywords in index.html), no model needed.
  * SemanticRouterTests  — embeds real queries with the committed ONNX model
                           and checks routing end to end. Skipped when
                           numpy / onnxruntime / tokenizers are missing
                           (`pip install -r scripts/requirements.txt`).

The example tables below are the "spec" for where queries should go. When
you change phrases or keyword rules and a case here fails, either the
change is a regression or the table needs a deliberate update — never
loosen a case just to go green.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

PHRASES = json.loads((SCRIPTS / "search_phrases.json").read_text(encoding="utf-8"))
CONFIG = json.loads((REPO_ROOT / "search-config.json").read_text(encoding="utf-8"))
EMBEDDINGS = json.loads((REPO_ROOT / "search-embeddings.json").read_text(encoding="utf-8"))
BENCH = json.loads((SCRIPTS / "routing_benchmark.json").read_text(encoding="utf-8"))["queries"]
INDEX_HTML = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
RULES = PHRASES["keywordRules"]

ENGINES = {"ddg", "lumo", "x", "maps", "youtube", "images", "ebay"}

try:
    import eval_routing  # needs numpy (+ onnxruntime/tokenizers for the model)
    HAVE_MODEL_DEPS = True
except ImportError:  # pragma: no cover - depends on the environment
    eval_routing = None
    HAVE_MODEL_DEPS = False


# ───────────────────────────────────────────────────────────────────────
# Pure-Python mirror of classifyKeywords (index.html), so the keyword
# tests run without numpy. eval_routing.classify_keywords is the same
# logic; KeywordRouterTests.test_mirror_matches_eval_script keeps them
# honest.
# ───────────────────────────────────────────────────────────────────────
MIN_KEYWORD_SCORE = 2


_NON_WORD_RE = re.compile(r"[^\w']+|_+")


def normalize_for_keywords(text: str) -> str:
    return _NON_WORD_RE.sub(" ", re.sub("[‘’]", "'", text.lower())).strip()


def rule_matches(rule: dict, padded: str) -> bool:
    return any(
        f" {normalize_for_keywords(kw)} " in padded
        for kw in rule["kw"]
    )


def keyword_scores(query: str) -> dict[str, float]:
    padded = " " + normalize_for_keywords(query) + " "
    scores: dict[str, float] = {}
    for rule in RULES:
        if rule_matches(rule, padded):
            scores[rule["engine"]] = scores.get(rule["engine"], 0) + rule["weight"]
    return scores


def classify_keywords(query: str) -> str | None:
    padded = " " + normalize_for_keywords(query) + " "
    for rule in RULES:
        if rule.get("priority") and rule_matches(rule, padded):
            return rule["engine"]
    best, best_score = None, 0
    for engine, score in keyword_scores(query).items():
        if score > best_score:
            best, best_score = engine, score
    return best if best_score >= MIN_KEYWORD_SCORE else None


def js_const(name: str) -> str:
    m = re.search(rf"const {name} = ([^;]+);", INDEX_HTML)
    if not m:
        raise AssertionError(f"index.html: const {name} not found")
    return m.group(1).strip().strip("'\"")


# ───────────────────────────────────────────────────────────────────────
# Example tables
# ───────────────────────────────────────────────────────────────────────

# Queries the keyword router alone must get right (lite mode / model not
# loaded yet). Each should hinge on an explicit intent marker.
KEYWORD_CASES: list[tuple[str, str]] = [
    ("pizza near me", "maps"),
    ("directions to the airport", "maps"),
    ("car wash open now", "maps"),
    ("taylor swift music video", "youtube"),
    ("ted talk on leadership", "youtube"),
    ("asmr rain", "youtube"),
    ("pictures of golden retrievers", "images"),
    ("what does a black widow look like", "images"),
    ("kitchen backsplash design ideas", "images"),
    ("funny office memes", "images"),
    ("breaking news in denver", "x"),
    ("what are people saying about the fed", "x"),
    ("thoughts on the new react compiler", "x"),
    ("tweets from the nws about the storm", "x"),
    ("why is the new pope trending", "x"),
    ("fans react to the finale", "x"),
    ("honest review of the kindle colorsoft", "lumo"),
    ("advice for a new grad engineer", "lumo"),
    ("react documentation", "ddg"),
    ("pip install numpy", "ddg"),
    ("used road bike", "ebay"),
    ("vintage seiko watch", "ebay"),
    ("replacement parts for kitchenaid mixer", "ebay"),
    ("baseball card collection value", "ebay"),
    ("pros and cons of solar panels", "lumo"),
    ("write a poem about the ocean", "lumo"),
    ("help me craft a tweet about my product launch", "lumo"),  # writing, not an X search
    ("generate a tweet announcing our sale", "lumo"),
    # writing intent outranks X news / opinion keywords
    ("write a breaking news article about climate change", "lumo"),
    ("draft a reaction to the new policy", "lumo"),
    ("write a hot take about javascript", "lumo"),
    ("craft a twitter thread about our launch", "lumo"),
    ("write a breaking news post on twitter", "lumo"),  # priority beats stacked X rules
    ("opinions on the cybertruck", "x"),
    ("fan reaction to the finale", "x"),
    ("twitter reactions to the trade", "x"),
    # punctuation is a word boundary too
    ('"write a poem about rain"', "lumo"),
    ("please—write a poem", "lumo"),
    ("(breaking news in chicago)", "x"),
    ("weather?", "ddg"),
    # recommendation / login intent beats a bare platform mention
    ("recommend a privacy-friendly alternative to twitter", "lumo"),
    ("recommend books about twitter", "lumo"),
    ("sign in on twitter", "ddg"),
    ("log in to x", "ddg"),
    ("recommend a live coverage source", "lumo"),
    ("reviews of breaking news apps", "lumo"),
    ("review of live coverage services", "lumo"),
    ("people’s reactions to the verdict", "x"),  # iOS curly apostrophe
    ("why is the new pope trending", "x"),
    ("itinerary for a weekend in lisbon", "lumo"),
    ("is a masters degree worth it", "lumo"),
    ("shows like severance", "lumo"),
    ("weather in denver", "ddg"),
    ("banana bread recipe", "ddg"),
    ("gmail login", "ddg"),
]

# Bare-word keywords must not fire inside longer words or on unrelated
# phrases — these used to (or easily could) misroute. None = DDG fallback.
KEYWORD_FALSE_POSITIVES: list[tuple[str, str | None]] = [
    ("street fighter 6", None),         # not a maps address
    ("wall street journal", None),
    ("healthy chicken recipes", None),  # 'healthy' is not a lumo signal
    ("browser console log", None),      # 'console' alone is not ebay
    ("xbox series x console", None),
    ("cinnamon bun recipe", "ddg"),
    ("lakers vs celtics score", None),  # bare 'vs' is not an opinion signal
    ("decode base64 string", None),     # 'code' must not match 'decode'
    ("comfort food ideas", None),
    ("twitter login", "ddg"),           # navigation, not an X search
    ("how to fix roof leaks", None),    # 'leaks' is not a news signal
    ("viral infection symptoms", None), # bare 'viral' is not an X signal
    ("cross threaded box thread", None),
    # non-social senses of opinion / drama / reaction stay on the web
    ("second opinion on cancer diagnosis", "ddg"),
    ("legal opinion pdf", "ddg"),
    ("best korean drama 2026", "ddg"),
    ("allergic reaction to penicillin", "ddg"),
    ("skin reaction to retinol", "ddg"),
    ("chemical reaction to water", "ddg"),
    ("adverse reactions to antibiotics", None),
    ("immune reactions to vaccines", None),
    ("blood pressure trending downward", "ddg"),
    ("sales are trending down this quarter", "ddg"),
    # phrases must start at a word: 'craft a' is not in 'minecraft armor'
    ("minecraft armor recipe", "ddg"),
    ("warcraft addon download", "ddg"),
    ("aircraft accident report", None),
    # keyword phrases end at a word too: 'craft a' is not in 'craft armor'
    ("craft armor minecraft", "youtube"),
    ("write ahead log postgres", None),
    ("write amplification ssd", None),
    ("world news", None),  # generic news navigation stays on the web
]

# End-to-end semantic routing spec: clear-cut queries per destination.
SEMANTIC_CASES: list[tuple[str, str]] = [
    # ddg — facts, navigation, quick lookups, and product shopping
    ("facebook", "ddg"),
    ("news", "ddg"),  # bare news navigation stays on the web
    ("google news", "ddg"),
    ("weather this weekend in miami", "ddg"),
    ("how many teaspoons in a tablespoon", "ddg"),
    ("amazon prime login", "ddg"),
    ("best wireless earbuds under 100", "ddg"),
    ("top rated air purifier", "ddg"),
    ("best laptop for video editing", "ddg"),
    # lumo — synthesized answers, planning, writing, advice
    ("explain how nuclear fusion works", "lumo"),
    ("write a thank you note to my teacher", "lumo"),
    ("plan a 4 day trip to barcelona", "lumo"),
    ("pros and cons of renting vs buying a house", "lumo"),
    ("why did the dinosaurs go extinct", "lumo"),
    ("is the vision pro worth the money", "lumo"),
    # maps
    ("mexican restaurant near me", "maps"),
    ("directions to the nearest hospital", "maps"),
    ("laundromat open late", "maps"),
    # youtube
    ("coldplay yellow official video", "youtube"),
    ("how to replace a bike chain video", "youtube"),
    ("champions league highlights", "youtube"),
    # images
    ("pictures of the aurora", "images"),
    ("wallpaper of a forest at dawn", "images"),
    ("tattoo designs for forearm", "images"),
    # x — breaking news, live events, opinions / social sentiment
    ("breaking news about the wildfire", "x"),
    ("what is everyone saying about the new pope", "x"),
    ("honest opinions on the framework laptop", "x"),
    ("what do developers think of htmx", "x"),
    ("live updates on the mars landing", "x"),
    ("public reaction to the verdict", "x"),
    # lumo — reviews, advice
    ("is the switch 2 worth upgrading to", "lumo"),
    ("advice for surviving a long distance relationship", "lumo"),
    # ddg — tech lookups (no Hacker News route anymore)
    ("python requests documentation", "ddg"),
    ("node js download", "ddg"),
    # ebay
    ("used nikon d750 body", "ebay"),
    ("vintage pyrex bowls", "ebay"),
    ("replacement battery for thinkpad t480", "ebay"),
]

MIN_SEMANTIC_ACCURACY = 0.97  # current: ~99%
MIN_KEYWORD_ACCURACY = 0.95   # current: ~98%


# ───────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────
class ConfigTests(unittest.TestCase):
    def test_engine_set(self):
        routable = set(PHRASES["engines"]) - {"direct"}
        self.assertEqual(routable, ENGINES)
        self.assertEqual({r["key"] for r in PHRASES["_routes"]}, ENGINES)

    def test_wirecutter_fully_removed(self):
        """Wirecutter is no longer a destination: no engine, bang, keyword
        rule, route, embedding, or benchmark expectation may reference it."""
        self.assertNotIn("wirecutter", PHRASES["engines"])
        blobs = {
            "scripts/search_phrases.json": json.dumps(PHRASES),
            "search-config.json": json.dumps(CONFIG),
            "search-embeddings.json key list": json.dumps([r["key"] for r in EMBEDDINGS]),
            "scripts/routing_benchmark.json": json.dumps(
                [[q["expect"], *q.get("also_ok", [])] for q in BENCH]
            ),
        }
        for name, blob in blobs.items():
            with self.subTest(file=name):
                self.assertNotIn("wirecutter", blob.lower(), f"{name} mentions wirecutter")
                self.assertNotIn("nytimes.com", blob.lower(), f"{name} links nytimes.com")
        # index.html may mention the removal in a changelog comment, but
        # must not reference the engine key or its domain.
        html = INDEX_HTML.lower()
        for needle in ("'wirecutter'", '"wirecutter"', "nytimes.com"):
            self.assertNotIn(needle, html, f"index.html contains {needle}")
        for bang in ("wc", "nyt"):
            self.assertNotIn(bang, PHRASES["bangs"])

    def test_grok_fully_removed(self):
        """Grok was replaced by Lumo: no engine, bang, rule, route, embedding,
        benchmark expectation, or grok.com link may remain."""
        self.assertNotIn("grok", PHRASES["engines"])
        self.assertNotIn("grok", CONFIG["engines"])
        self.assertNotIn("grok", PHRASES["bangs"].values())
        self.assertFalse(any(r["engine"] == "grok" for r in RULES))
        self.assertNotIn("grok", [r["key"] for r in EMBEDDINGS])
        for q in BENCH:
            self.assertNotIn("grok", [q["expect"], *q.get("also_ok", [])], q["q"])
        for blob in (json.dumps(PHRASES), json.dumps(CONFIG)):
            self.assertNotIn("grok.com", blob.lower(), "grok.com still referenced")
        # index.html may mention Grok in the EMBEDDINGS_VERSION changelog.
        self.assertNotIn("'grok'", INDEX_HTML.lower())

    def test_lumo_uses_guest_fragment_url(self):
        """Signed-out visitors to lumo.proton.me/?q= are redirected to /guest
        and the query is dropped; /guest#q= keeps it and auto-sends it."""
        self.assertEqual(
            PHRASES["engines"]["lumo"]["urlTemplate"],
            "https://lumo.proton.me/guest#q={q}",
        )

    def test_x_search_url_and_bangs(self):
        """X search: `src=typed_query` makes x.com treat it as a typed search
        (same as its own search box). `!x`, `!tw` and `!twitter` reach it."""
        self.assertEqual(
            PHRASES["engines"]["x"]["urlTemplate"],
            "https://x.com/search?q={q}&src=typed_query",
        )
        for bang in ("x", "tw", "twitter"):
            self.assertEqual(PHRASES["bangs"][bang], "x", bang)

    def test_hacker_news_fully_removed(self):
        """Hacker News is no longer a destination."""
        self.assertNotIn("hn", PHRASES["engines"])
        self.assertNotIn("hn", CONFIG["engines"])
        for bang in ("hn", "h"):
            self.assertNotIn(bang, PHRASES["bangs"])
        self.assertFalse(any(r["engine"] == "hn" for r in RULES))
        self.assertNotIn("hn", [r["key"] for r in EMBEDDINGS])
        for q in BENCH:
            self.assertNotIn("hn", [q["expect"], *q.get("also_ok", [])], q["q"])
        for blob in (json.dumps(CONFIG), INDEX_HTML):
            self.assertNotIn("algolia.com", blob.lower(), "hn.algolia.com still referenced")
            self.assertNotIn("hacker news", blob.lower(), "Hacker News still referenced")

    def test_bangs_and_rules_point_at_real_engines(self):
        for bang, target in PHRASES["bangs"].items():
            with self.subTest(bang=bang):
                self.assertIn(target, PHRASES["engines"])
        for rule in RULES:
            self.assertIn(rule["engine"], PHRASES["engines"])

    def test_generated_config_in_sync(self):
        for key in ("engines", "bangs", "keywordRules"):
            with self.subTest(key=key):
                self.assertEqual(CONFIG[key], PHRASES[key],
                                 "regenerate: python3 scripts/generate_search_embeddings.py")

    def test_embeddings_match_phrases(self):
        self.assertEqual([r["key"] for r in EMBEDDINGS], [r["key"] for r in PHRASES["_routes"]])
        for emb, src in zip(EMBEDDINGS, PHRASES["_routes"], strict=True):
            with self.subTest(route=emb["key"]):
                seen, dedup = set(), []
                for p in (p.strip() for p in src["phrases"]):
                    if p and p.lower() not in seen:
                        seen.add(p.lower())
                        dedup.append(p)
                self.assertEqual(emb["examples"], dedup,
                                 "search-embeddings.json is stale — regenerate it")
                self.assertEqual(len(emb["vectors"]), len(emb["examples"]))

    def test_embeddings_l2_normalized(self):
        for route in EMBEDDINGS:
            for v in route["vectors"]:
                self.assertEqual(len(v), 384)
                self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, delta=1e-4)

    def test_benchmark_is_held_out(self):
        phrases = {p.strip().lower() for r in PHRASES["_routes"] for p in r["phrases"]}
        leaked = [q["q"] for q in BENCH if q["q"].strip().lower() in phrases]
        self.assertEqual(leaked, [])

    def test_benchmark_labels_are_valid(self):
        for q in BENCH:
            with self.subTest(q=q["q"]):
                self.assertIn(q["expect"], ENGINES)
                for alt in q.get("also_ok", []):
                    self.assertIn(alt, ENGINES)

    def test_runtime_constants_in_sync_with_eval(self):
        """eval_routing.py must mirror index.html or the offline numbers lie."""
        src = (SCRIPTS / "eval_routing.py").read_text(encoding="utf-8")
        for name in ("MIN_KEYWORD_SCORE", "KEYWORD_BOOST_PER_POINT", "KEYWORD_BOOST_MAX_POINTS"):
            with self.subTest(const=name):
                m = re.search(rf"^{name} = ([0-9.]+)", src, re.M)
                self.assertIsNotNone(m, f"eval_routing.py: {name} missing")
                self.assertEqual(float(m.group(1)), float(js_const(name)))
        self.assertEqual(int(js_const("TOP_K_NEIGHBORS")), 3)
        self.assertEqual(float(js_const("MIN_KEYWORD_SCORE")), MIN_KEYWORD_SCORE)


class KeywordRouterTests(unittest.TestCase):
    def test_examples(self):
        for query, expect in KEYWORD_CASES:
            with self.subTest(query=query):
                self.assertEqual(classify_keywords(query), expect, keyword_scores(query))

    def test_false_positives(self):
        for query, expect in KEYWORD_FALSE_POSITIVES:
            with self.subTest(query=query):
                self.assertEqual(classify_keywords(query), expect, keyword_scores(query))

    def test_empty_and_unmatched_queries_fall_back(self):
        self.assertIsNone(classify_keywords(""))
        self.assertIsNone(classify_keywords("zxqv plorb"))

    def test_below_min_score_falls_back(self):
        # 'museum' is a weight-1 maps keyword: not enough to commit alone.
        self.assertEqual(keyword_scores("museum").get("maps"), 1)
        self.assertIsNone(classify_keywords("museum"))

    def test_shopping_queries_default_to_ddg(self):
        # With Wirecutter gone, plain product-shopping queries go to the
        # general web (DDG fallback), not to a niche engine.
        for q in ("best robot vacuum", "best budget monitor", "buy a new mattress"):
            with self.subTest(query=q):
                self.assertIn(classify_keywords(q) or "ddg", {"ddg", "lumo"})

    @unittest.skipUnless(HAVE_MODEL_DEPS, "numpy not installed")
    def test_mirror_matches_eval_script(self):
        for q in [c[0] for c in KEYWORD_CASES + KEYWORD_FALSE_POSITIVES] + [b["q"] for b in BENCH]:
            self.assertEqual(classify_keywords(q), eval_routing.classify_keywords(q, RULES), q)

    def test_keyword_benchmark_accuracy(self):
        hits = sum(
            (classify_keywords(b["q"]) or "ddg") in {b["expect"], *b.get("also_ok", [])}
            for b in BENCH
        )
        acc = hits / len(BENCH)
        self.assertGreaterEqual(acc, MIN_KEYWORD_ACCURACY,
                                f"keyword router accuracy {acc:.1%} ({hits}/{len(BENCH)})")


@unittest.skipUnless(HAVE_MODEL_DEPS, "needs numpy, onnxruntime, tokenizers")
class SemanticRouterTests(unittest.TestCase):
    router = None

    @classmethod
    def setUpClass(cls):
        try:
            cls.router = eval_routing.SemanticRouter(pooling="topk", k=3)
        except ImportError as e:  # pragma: no cover
            raise unittest.SkipTest(str(e)) from e

    def test_examples(self):
        for query, expect in SEMANTIC_CASES:
            with self.subTest(query=query):
                got, ranked, phrase = self.router.score(query)
                self.assertEqual(got, expect, f"won via {phrase!r}; ranked={ranked[:3]}")

    def test_scores_are_sorted_and_cover_every_route(self):
        _, ranked, _ = self.router.score("best pizza in brooklyn")
        self.assertEqual({k for k, _ in ranked}, ENGINES)
        scores = [s for _, s in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_keyword_boost_is_capped(self):
        """A pile of weak keyword matches can't add more than the cap."""
        cap = eval_routing.KEYWORD_BOOST_PER_POINT * eval_routing.KEYWORD_BOOST_MAX_POINTS
        q = "used vintage replacement parts for sale ebay auction"
        boosted = dict(self.router.score(q)[1])
        self.router.boost = False
        try:
            plain = dict(self.router.score(q)[1])
        finally:
            self.router.boost = True
        for k in ENGINES:
            self.assertLessEqual(boosted[k] - plain[k], cap + 1e-6)

    def test_benchmark_accuracy(self):
        hits, misses = 0, []
        for b in BENCH:
            got = self.router.score(b["q"])[0]
            if got in {b["expect"], *b.get("also_ok", [])}:
                hits += 1
            else:
                misses.append(f"{b['q']!r}: expected {b['expect']}, got {got}")
        acc = hits / len(BENCH)
        self.assertGreaterEqual(
            acc, MIN_SEMANTIC_ACCURACY,
            f"semantic accuracy {acc:.1%} ({hits}/{len(BENCH)}); misses:\n  " + "\n  ".join(misses),
        )


if __name__ == "__main__":
    unittest.main()
