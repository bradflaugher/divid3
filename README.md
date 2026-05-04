# divid3

A private, opinionated meta search engine. We divide your query and intelligently route it to the best search providers — so you get superior results without unnecessary tracking.

Hosted at [https://divid3.com](https://divid3.com) on Cloudflare Pages.

---

## Getting Started

### Set divid3 as your default search engine

The search router lives at:

```
https://divid3.com/?q=%s
```

Use that URL as your browser's default search engine. Every query you type goes through a small classifier that picks the best destination.

#### Safari on iOS / macOS

Safari doesn't let you change the default search engine natively. We recommend [**Customize Search Engine**](https://apps.apple.com/us/app/customize-search-engine/id6445840140) — a lightweight extension that lets you set any URL as your default search provider.

1. Install the app from the App Store
2. Open Safari → Settings → Extensions → Enable "Customize Search Engine"
3. Add `https://divid3.com/?q=%s` as your custom search URL
4. Set it as the default

#### Chrome / Edge / Firefox

1. Settings → Search engine → Manage search engines
2. Click **Add** (or "Site search")
3. Name: `divid3`, Keyword: `d`, URL: `https://divid3.com/?q=%s`
4. Set as default

#### Arc

Settings → Search → Add search engine → paste `https://divid3.com/?q=%s`

#### DuckDuckGo Browser

Settings → Default Search Engine → Other → paste `https://divid3.com/?q=%s`

---

## Bang shortcuts — instant routing without the model

If you already know where you want to go, prefix your query with a bang. These are rule-based, instant, and never touch the embedding model.

| Bang | Alias | Goes to | Example |
|------|-------|---------|---------|
| `!d` | `!ddg` | **DuckDuckGo** | `!d climate news` |
| `!yt` | `!y` | **YouTube** | `!yt lofi hip hop` |
| `!gh` | `!git` | **GitHub** | `!gh react hooks` |
| `!w` | `!wa` | **Wolfram Alpha** | `!w integral of x^2` |
| `!a` | `!amz` | **Amazon** | `!a usb-c cable` |
| `!m` | `!map` | **Google Maps** | `!m coffee near me` |
| `!i` | `!img` | **Bing Images** | `!i black hole` |
| `!p` | `!px` | **Perplexity** | `!p explain quantum gravity` |
| `!g` | `!gr` | **Grok** | `!g write a haiku` |

**Direct URLs** also bypass the model: typing `github.com` or `localhost:3000` (no spaces) routes directly without any search engine.

---

## Semantic routing — let the model decide

For everything else, divid3 embeds your query and compares it against ~50 example phrases per engine. The best match wins; if nothing scores above the confidence threshold, you fall back to DuckDuckGo.

Some examples of what the model routes automatically:

| Query | Routed to |
|-------|-----------|
| "lofi beats" | **YouTube** |
| "react useEffect cleanup" | **GitHub** *(or Perplexity, depending on phrasing)* |
| "integral of x sin(x)" | **Wolfram Alpha** |
| "best USB-C cables" | **Amazon** |
| "coffee near me" | **Google Maps** |
| "github.com" | **Direct link** — no engine |
| "what is a transformer model" | **DuckDuckGo** (fallback) |

The scores panel in the bottom-left shows all candidate scores so you can see exactly *why* the router chose what it chose.

---

## How it works

### Why is this interesting?

Three reasons.

#### 1. It runs the embedding model **in your browser**

There's no API call to OpenAI, no Cloudflare Worker doing inference, no analytics endpoint logging your queries. The model ([`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), 22 MB q8-quantized ONNX) is committed to this repository, downloaded once by your browser, cached forever, and executed on-device via [`@huggingface/transformers`](https://github.com/huggingface/transformers.js) v3 (WebGPU/WASM). After the first load, the page works offline and queries never leave your machine.

It's a useful, fast, real-world ML feature with **zero server cost** and **zero privacy footprint**.

#### 2. The routing logic is layered, not monolithic

The model is the slowest layer, so we only invoke it when faster rules can't decide. Three layers run in order:

```
                        ┌──────────────┐
input ────────────────→ │ classifyRules │ ── bang or domain match? ──┐
                        └──────────────┘                              │
                              │ no                                    ▼
                              ▼                                  route immediately
                        ┌──────────────┐    score ≥ 0.30    ┌──────────────┐
                        │   classify    │ ─────────────────→ │  best engine │
                        │ (embedding +  │                    └──────────────┘
                        │  dot product) │    score < 0.30   ┌──────────────┐
                        └──────────────┘ ─────────────────→ │  DuckDuckGo  │
                                                            └──────────────┘
```

**Layer 1 — bangs.** DuckDuckGo-style shortcuts. `!yt cats` → YouTube, `!gh react` → GitHub, `!w sin(x)` → Wolfram, `!a usb-c` → Amazon, etc. Synchronous, no model needed, never gets it wrong.

**Layer 2 — direct URL detection.** A regex catches things that look like domains (`github.com`, `news.ycombinator.com`) or `localhost:3000` and routes them as a literal URL instead of a search.

**Layer 3 — semantic routing.** For everything else, embed the query and compare against pre-computed embeddings of ~50 example phrases per engine. Pick the engine with the highest similarity, or fall back to DuckDuckGo if even the winner is below the confidence threshold.

The scores panel in the bottom-left shows all 9 candidate scores so you can see exactly *why* the router chose what it chose. It's a debugger masquerading as a UI element.

#### 3. The embedding-comparison details actually matter

Naive cosine-similarity code is everywhere on the internet, and most of it is doing more work than necessary.

This page **L2-normalizes both sides at index time and at query time**, which means the cosine of the angle between two vectors is exactly equal to their dot product. So we can drop the `sqrt`s entirely:

```js
// search.html — the hot path
function dot(a, b) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}
```

Each route stores its example vectors as a `Float32Array` (allocated once at load time), so a query needs ~461 × 384 ≈ 180 K float multiplications total — fast enough that we run it on every keystroke (debounced 150 ms) on the main thread, no Web Worker.

**Per-route score = max dot product over the route's examples** (i.e., nearest-neighbor pooling, not mean pooling). This is more robust when example phrasings vary widely: a query that closely matches *one* example shouldn't get diluted by 49 unrelated ones.

There's also a sequence-token race fix (`hintSeq`) so that if you type fast and inferences resolve out of order, the latest keystroke always wins.

---

## Build / run / serve

There is no build step. The page is a single HTML file with inline CSS and an ES-module script tag. Static files only.

To preview locally:

```bash
npm ci
npx serve -l 3000 .
# open http://localhost:3000/index.html
```

You need [`serve.json`](./serve.json) on disk so the dev server doesn't 301-redirect `/search.html?q=…` and drop the query string in the process. Cloudflare Pages preserves it, but `serve` defaults don't.

The first page load downloads the ~22 MB model from the local server; subsequent loads use the browser cache.

---

## Tests

A Playwright suite ([`tests/search.spec.ts`](./tests/search.spec.ts), 40 specs) covers the whole stack:

| Group                          | What it asserts                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------- |
| boot                           | model loads, status indicator reaches `ready`, no console errors, input is accessible, embeddings.json is requested with a `?v=…` cache-buster |
| bang shortcuts                 | each `!x` (plus aliases `!y`, `!git`, `!ddg`, `!gr`) routes to the right host; bang-only (`!yt`) and unknown bang (`!nope foo`) don't crash |
| `?q=` redirect                 | `?q=!yt+lofi` auto-redirects; `?q=github.com` direct-links; `?q=how+to+make+pizza` waits for the model and routes semantically; empty / whitespace-only `?q=` stays on the page |
| direct URL detection           | domains, `domain/path`, and `localhost:3000` classify as direct; phrases with spaces don't; Enter on `github.com` actually navigates |
| semantic routing               | scores panel renders all 9 routes with exactly one `.best`; clearing input clears the UI; rapid-fire keystrokes settle on the latest query (`hintSeq` race) |
| cancel button                  | clicking cancel or pressing Escape stops the redirect, restores focus, preserves the query; rapid double-Enter doesn't stack timers |
| mobile keyboard awareness      | a synthetic `visualViewport` resize lifts the scores panel above the keyboard    |
| model load failure             | a 500 on `search-embeddings.json` flips status to `failed`, shows the error banner with a working **Retry**, falls back to DuckDuckGo on Enter and on `?q=…` |
| cache reliability              | a second page load on the same context reuses the cached ONNX model              |

Run them:

```bash
npm ci                                          # one-time
npx playwright install --with-deps chromium    # one-time
npm test                                        # full suite, ~90s
npm run test:ci                                 # CI mode (retries=1, html report)
npx playwright test -g "bang"                  # one describe block
npx playwright test -g "cancel" --headed       # watch it run
npm run test:report                             # open last HTML report
```

The `webServer` block in [`playwright.config.ts`](./playwright.config.ts) auto-starts the dev server, so you don't have to.

CI runs the same suite on every PR via [`.github/workflows/search-tests.yml`](./.github/workflows/search-tests.yml), caches the Playwright browsers, and uploads the HTML report as an artifact when something fails.

---

## iOS reliability and caching

iOS Safari is famously creative about caches: it can drop one resource from disk while keeping a paired one, or serve an immutable-cached asset across builds even after a server-side change. To keep the router working through those moods, the page does three things:

1. **Versioned embeddings URL.** `index.html` requests `/search-embeddings.json?v=<EMBEDDINGS_VERSION>`. Bumping the constant invalidates every browser cache atomically. The [`_headers`](./_headers) file pins this URL to a 1-hour TTL with `must-revalidate` regardless, as a safety net.
2. **Never-rejecting init promise + fetch timeout.** If the embeddings fetch hangs (slow network, partial body) it aborts after 30 s; if the model itself errors, the page degrades to a DuckDuckGo pass-through instead of getting stuck on the loading overlay.
3. **Self-service Retry.** A failed load shows an error banner with a **Retry** link. The handler clears `caches.*`, blasts every IndexedDB the origin owns (transformers.js parks the model there), and full-reloads. That's the recovery path you reach for when iOS serves a corrupted half-cache and nothing else helps.

---

## Mobile keyboard handling

iOS Safari anchors `position: fixed` to the layout viewport, not the visual viewport, so the soft keyboard happily covers any bottom-anchored UI. The page handles this two ways:

1. **`interactive-widget=resizes-content`** in the viewport meta tag — modern Chrome and Safari shrink the layout viewport itself when the keyboard appears (no JS needed there).
2. **`visualViewport` listener** (the fallback) — JavaScript computes the obscured bottom inset and writes it to a `--keyboard-inset` CSS variable that `.scores-panel` and `.status-dot` add to their `bottom` offset. Works on older iOS too.

---

## What's in the repo

```
.
├── index.html                       # The router (everything described above)
├── privacy.html                     # Privacy policy
├── search-embeddings.json           # ~3.5 MB of pre-computed L2-normalized vectors
├── search.webmanifest               # PWA manifest
├── models/sentence-transformers/all-MiniLM-L6-v2/
│   ├── config.json, tokenizer*.json, special_tokens_map.json
│   └── onnx/model_quantized.onnx    # 22 MB, q8-quantized
├── tests/search.spec.ts             # Playwright E2E test suite
├── playwright.config.ts             # Test runner config
├── serve.json                       # `npx serve` config (cleanUrls: false)
├── package.json / package-lock.json # Dev deps only (Playwright, serve)
├── _headers                         # Cloudflare Pages cache headers
├── .github/workflows/
│   ├── deploy.yml                   # CF Pages deploy → divid3 project
│   └── search-tests.yml             # Runs the Playwright suite on PRs
├── favicon-*.png, favicon.ico       # Static assets
└── README.md                        # You are here
```

---

## Updating the embeddings

The example phrases in `search-embeddings.json` are hand-curated — about 50 per route across 9 routes (461 vectors total, 384 dimensions each). To add or swap examples, regenerate the file with a Python script that loads `sentence-transformers/all-MiniLM-L6-v2` and calls `model.encode(phrases, normalize_embeddings=True)`. The output must keep all vectors L2-normalized, because the runtime relies on `cos(a, b) ≡ a · b` to skip the `sqrt`s.

If you regenerate the file, sanity-check it with:

```bash
python3 -c "
import json, math
for r in json.load(open('search-embeddings.json')):
    for v in r['vectors']:
        assert abs(math.sqrt(sum(x*x for x in v)) - 1) < 1e-6
print('all normalized')
"
```

**Then bump `EMBEDDINGS_VERSION` in `index.html`.** The page fetches `/search-embeddings.json?v=<EMBEDDINGS_VERSION>`, so without a bump clients can serve a stale cached copy alongside the new HTML.

---

## License

Code in this repository is released under the GNU AGPL v3. See [`LICENSE`](./LICENSE) for the full text.

The model weights under `models/` are [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), released by their authors under Apache 2.0.
