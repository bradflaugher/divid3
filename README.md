# divid3

**Private, on-device search routing.**

divid3 is a meta-search router that runs entirely in your browser. It uses a small local ML model to read your intent, then sends you to whichever search engine you've decided handles that kind of query best — without a server, an account, or a middleman.

[**Try the hosted instance at divid3.com**](https://divid3.com)

---

## ⚡ What you get

- **Private by design.** Classification happens in your browser's WASM heap. No telemetry, no server logs, no query stream for someone else to monetize.
- **You decide where queries go.** All routing is configured by a single JSON file you control. Self-host with only the destinations you trust; remove anything you don't.
- **Semantic intent.** A 22 MB `all-MiniLM-L6-v2` model embeds your query and picks the best-matching destination from your configured set.
- **Bangs.** DuckDuckGo-style shortcuts (`!yt`, `!hn`, `!m`, …) that always win over the semantic router.
- **Rule-based fallbacks.** Bare domains (`github.com`) and `localhost:3000` route directly. Low-memory phones get a deterministic keyword router instead of the model.
- **Choose-don't-autoroute on mobile + `?q=` URLs.** No 4-second countdown. On mobile and on any link with a query string (e.g. browser-bar searches), the router shows you the top match plus the ranked alternatives and waits for you to tap. Desktop typing still routes immediately because the live score chips already let you click any destination.
- **No build step.** Pure HTML / CSS / vanilla JS. Easy to audit. Easy to self-host.

---

## 🛡 Self-hosting & the privacy story

divid3 is built for people who want a search bar they actually trust — even when the destination itself isn't end-to-end private. The threat model is:

1. **Where the query is read.** On your device, by a model whose weights are committed to the repo. You can read the script that builds the embeddings (`scripts/generate_search_embeddings.py`) — there is no remote inference.
2. **What gets sent over the network.** Only the final HTTPS request to whatever engine you tapped. divid3 itself doesn't see any of it; there's no `/api/route` to intercept.
3. **What you control.** The full set of destinations, their URL templates, their bang shortcuts, and the keyword/embedding rules that pick between them. Delete an engine from `scripts/search_phrases.json` and it's gone everywhere, including from the on-device classifier.

You're welcome to ship a fork that points only at Kagi, Brave, SearXNG, your own engine, or anything else. Same code, your engines.

---

## 🛠 How routing works

1. **Bangs.** Regex match for `!yt`, `!hn`, etc. Always wins.
2. **Explicit rules.** Bare-domain (`github.com`) and `localhost:port` detection.
3. **Semantic match.** Transformers.js embeds the query and scores each destination by the **mean of its top-3 cosine similarities** against that destination's phrase corpus. Top-3 pooling (instead of plain nearest-neighbor) means a single stray phrase can't hijack a route — three examples have to agree.
4. **Keyword fallback.** When the model isn't usable (low-memory device, repeated crashes, `?lite=1`), a deterministic weighted-keyword scorer takes over.
5. **DDG as the universal fallback.** In keyword mode, queries with no matching keywords fall back to DuckDuckGo (HTML) by default.

### Measured accuracy

Routing quality is measured by `scripts/eval_routing.py` against a **held-out benchmark** of 353 labeled real-world queries (`scripts/routing_benchmark.json` — the validator enforces that no benchmark query is ever copied into the training phrases):

| Router                  | Accuracy |
|-------------------------|----------|
| Semantic (top-3 cosine) | **98.9%** |
| Keyword (`?lite=1`)     | **97.5%** |

Run it yourself after any corpus edit:

```bash
python3 scripts/eval_routing.py                      # full report + misroute analysis
python3 scripts/eval_routing.py --query "best ramen" # probe a single query
```

The misroute report names the exact phrase that "won" each wrong routing, which makes corpus debugging mechanical: find the hijacking phrase, sharpen or remove it, re-run.

---

## 🚀 Default destinations

The shipped configuration routes between:

| Engine        | Used for                                   | Bang(s)            |
|---------------|--------------------------------------------|--------------------|
| DuckDuckGo    | Generic web search; fallback for anything ambiguous | `!d`, `!ddg`       |
| Bing Images   | Image queries                              | `!i`, `!img`       |
| Brave Search  | Conversational AI answers and web search           | `!g`, `!gr`, `!p`, `!px` |
| Google Maps   | Locations, "near me", directions           | `!m`, `!map`       |
| YouTube       | Music, video, tutorials                    | `!y`, `!yt`        |
| Wirecutter    | Buying advice, product recommendations     | `!wc`, `!nyt`      |
| eBay          | Used / vintage / parts / hard-to-find items | `!eb`, `!ebay`     |
| Hacker News   | Tech news, startup discussion              | `!h`, `!hn`        |

Plus the `direct` virtual engine, which opens a typed URL (`github.com`) literally instead of searching for it.

---

## ⌨️ Browser integration

Add as a custom search engine:

```
https://divid3.com/?q=%s
```

Setup instructions for Chrome, Firefox, Safari, and Arc live at [divid3.com/setup.html](https://divid3.com/setup.html).

Keyboard shortcuts: `/` focus search · `Esc` close overlay · `T` toggle theme · `?` help.

---

## 💻 Development

```bash
# install deps (Playwright + serve + ESLint)
npm ci

# local dev server
npm run serve

# end-to-end tests (Chromium / Firefox / WebKit / mobile Safari)
npm test

# lint everything (ESLint + Ruff + JSON config validator)
npm run lint
```

---

## 🎨 Configuring your own router

Everything is driven by **one file**: [`scripts/search_phrases.json`](scripts/search_phrases.json). That file is the source of truth for engines, bangs, keyword fallback rules, and the training phrases that build the semantic index. The Python script reads it and emits two runtime artifacts:

- `search-config.json` — small lookup tables the page loads at boot
- `search-embeddings.json` — L2-normalized phrase vectors for the ML router

### Schema

```jsonc
{
  "engines": {
    "my_engine": {
      "name": "My Custom Search",
      "urlTemplate": "https://example.com/?q={q}"   // {q} is the URL-encoded query
    }
  },
  "bangs": {
    "my": "my_engine"                                // !my  → my_engine
  },
  "keywordRules": [
    { "engine": "my_engine", "weight": 5, "kw": ["custom topic", "thing i want here"] }
  ],
  "_routes": [
    {
      "key": "my_engine",
      "label": "Display label for the index",
      "phrases": [
        "search for my custom topic",
        "lookup something on my search engine"
      ]
    }
  ]
}
```

Notes:

- Every engine must define `name` and `urlTemplate`. No other fields are accepted — the validator rejects strays (including `color`, which the UI no longer uses).
- The `direct` engine is special: its `urlTemplate` is `"{q}"` and it opens a literal URL the user typed.
- Every engine used by a bang, keyword rule, or `_routes` entry must be declared in `engines`. The validator and the generator both enforce this.
- `ddg` must exist; it's the universal fallback when nothing else is confident.

### Phrase-writing rules (enforced by the validator)

- **No single-word phrases** outside the `ddg` fallback route. Under nearest-neighbor pooling a bare word (`buy`, `music`, `guide`) becomes a universal attractor that hijacks unrelated queries — removing them was worth ~10 points of measured accuracy.
- **No phrase may appear in two routes** — that's a guaranteed conflict.
- Every phrase must be unambiguous about its destination *on its own*. If it could plausibly belong to two engines, sharpen it or drop it.
- Never copy a query from `scripts/routing_benchmark.json` into the corpus; the benchmark must stay held-out (also enforced).

### Workflow

```bash
# 1. Edit scripts/search_phrases.json — add engines, tweak bangs, drop phrases.
$EDITOR scripts/search_phrases.json

# 2. Measure the change against the routing benchmark.
python3 scripts/eval_routing.py

# 3. Regenerate the runtime artifacts.
python3 scripts/generate_search_embeddings.py

# 4. Bump EMBEDDINGS_VERSION in index.html so caches invalidate atomically.
#    (search the file for EMBEDDINGS_VERSION = '...')

# 5. Sanity-check the change locally.
npm run lint     # validates schema + corpus rules + drift with search-config.json
npm run serve
npm test
```

That's it — no JS edits required.

---

## 🔬 Lint & CI

Three checks run on every PR via `.github/workflows/lint.yml`:

- **ESLint** over the `<script>` blocks in `index.html` and `setup.html` (via `eslint-plugin-html`).
- **Ruff** over the `scripts/` directory.
- **Config validator** (`scripts/validate_config.py`) that catches missing engines, broken bang references, urlTemplates without `{q}`, and drift between `search_phrases.json` and the generated `search-config.json`.

The Playwright E2E suite (`.github/workflows/search-tests.yml`) runs the full router on Chromium, Firefox, WebKit, and mobile Safari.

---

## 📜 License

Code: **AGPL-3.0** · Bundled model weights: **Apache 2.0** (see [`models/`](models/)).
