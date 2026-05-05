# divid3

A private, opinionated meta search engine. We divide your query and intelligently route it to the best search providers — so you get superior results without unnecessary tracking.

> **Privacy is a trade-off, not a binary.** We believe it's better to give your search queries to an on-device router that forgets them immediately than to give everything you type into the location bar to a single engine that builds a permanent profile. divid3 runs entirely in your browser — no server logs, no analytics, no query tracking. Your searches leave your device only when they reach the destination you chose.

---

## Getting Started

### Set divid3 as your default search engine

The search router lives at:

```
https://divid3.com/?q=%s
```

The fastest path is to visit [**https://divid3.com/setup.html**](https://divid3.com/setup.html) — that page detects your browser, shows the right step-by-step instructions, and gives you a one-click copy of the URL.

The page also serves an [OpenSearch description](opensearch.xml), so most modern browsers will **auto-detect divid3** the first time you visit `divid3.com` and offer it in their search-engine settings.

There are really only three flavors of browser engine to deal with here: Chromium (everybody except Firefox and Safari), Gecko (Firefox), and WebKit (Safari). Pick whichever section matches.

#### Chromium-based browsers — Chrome, Edge, Brave, Arc, Opera, Vivaldi, DuckDuckGo on macOS, etc.

They all share the same engine and the same search-engine UI under the hood:

1. Open `chrome://settings/searchEngines` (or the equivalent `<browser>://` URL — `edge://`, `brave://`, etc.). Arc and Vivaldi expose the same panel via *Settings → Search*.
2. Under **Site search**, click **Add**.
3. Name `divid3`, Keyword `d`, URL `https://divid3.com/?q=%s`.
4. **⋮** next to the new entry → *Make default*.

If you don't want to change your default, leave the keyword as `d` — `d`+<kbd>Tab</kbd> in the address bar searches divid3 directly without committing to anything.

#### Firefox

Firefox auto-discovers divid3 via OpenSearch. Visit [divid3.com](https://divid3.com), then *Settings → Search → Default Search Engine → divid3*. If the auto-detect didn't fire, *Search Shortcuts → Add* and paste `https://divid3.com/?q=%s`.

#### Safari (iOS / macOS)

Safari doesn't expose a native "use any URL as default search" setting, so you need an extension. The cleanest option is [**Customize Search Engine**](https://apps.apple.com/us/app/customize-search-engine/id6445840140):

1. Install from the App Store.
2. Safari → Settings → Extensions → enable *Customize Search Engine*.
3. Add `https://divid3.com/?q=%s` as your custom search URL.
4. Set it as the default.

On iOS you can also tap **Share → Add to Home Screen** on `divid3.com` for an app-like launcher that bypasses Safari's chrome entirely — useful as a no-extension fallback.

#### Android

Chromium variants (Chrome, Brave, Edge, etc.): visit `divid3.com`, then *Settings → Search engine → Recently visited* → pick `divid3`. Samsung Internet wants the URL explicitly: *Settings → Search engine → Add search engine* → paste `https://divid3.com/?q=%s`.

---

## Bang shortcuts — instant routing without the model

If you already know where you want to go, prefix your query with a bang. These are rule-based, instant, and never touch the embedding model.

| Bang | Alias | Goes to | Example |
|------|-------|---------|---------|
| `!d` | `!ddg` | **DuckDuckGo (html)** | `!d climate news` |
| `!yt` | `!y` | **YouTube** | `!yt lofi hip hop` |
| `!hn` | `!h` | **Hacker News** *(past month, popularity-sorted)* | `!hn react server components` |
| `!w` | `!wa` | **Wolfram Alpha** | `!w integral of x^2` |
| `!wc` | `!nyt` | **Wirecutter** | `!wc usb-c cable` |
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
| "react useEffect cleanup" | **Hacker News** *(or Perplexity, depending on phrasing)* |
| "integral of x sin(x)" | **Wolfram Alpha** |
| "best USB-C cables" | **Wirecutter** |
| "coffee near me" | **Google Maps** |
| "github.com" | **Direct link** — no engine |
| "what is a transformer model" | **DuckDuckGo** (fallback) |

The scores panel in the bottom-left shows all candidate scores so you can see exactly *why* the router chose what it chose. **Every chip is clickable** — if the model picks YouTube but you actually wanted Wolfram Alpha for "integral of x sin(x)", just click the Wolfram chip and you go there instead. The chips are real `<button>` elements, so keyboard users can Tab to them and hit <kbd>Enter</kbd> to override too. The model gets the first guess; you get the final say.

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

**Layer 1 — bangs.** DuckDuckGo-style shortcuts. `!yt cats` → YouTube, `!hn react` → Hacker News, `!w sin(x)` → Wolfram, `!wc usb-c` → Wirecutter, etc. Synchronous, no model needed, never gets it wrong.

**Layer 2 — direct URL detection.** A regex catches things that look like domains (`github.com`, `news.ycombinator.com`) or `localhost:3000` and routes them as a literal URL instead of a search.

**Layer 3 — semantic routing.** For everything else, embed the query and compare against pre-computed embeddings of ~50 example phrases per engine. Pick the engine with the highest similarity, or fall back to DuckDuckGo if even the winner is below the confidence threshold.

The scores panel in the bottom-left shows all 9 candidate scores so you can see exactly *why* the router chose what it chose. It's a debugger masquerading as a UI element — and every score is also a clickable button, so you can override the model's pick with a single tap.

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

## How divid3 differs from other "private" search options

There's a whole spectrum of tools that bill themselves as privacy-respecting alternatives to Google, and each makes a different bargain. It's worth being honest about where divid3 sits in that landscape — and where the rest of the genre quietly cuts corners.

### Proxy-scrapers: SearXNG, Searx, Whoogle

[**SearXNG**](https://github.com/searxng/searxng) (and its predecessor Searx, and the more focused [**Whoogle**](https://github.com/benbusby/whoogle-search)) work by running a server that takes your query, **scrapes the actual Google / Bing / DuckDuckGo / Brave SERPs on your behalf**, strips the trackers, merges the results, and shows them to you. The upstream engines see *the SearXNG instance's IP*, not yours. That's the privacy story.

It's a clever trick, and it does work — for the user. But it has three real costs that the marketing doesn't always lead with:

1. **You are now trusting whoever runs the instance.** Self-hosting fixes that, but the convenience-win evaporates: you've replaced "Google sees my queries" with "I run a Linux server, keep it patched, and notice when its IP gets rate-limited by Google at 3am." Most people who say they use SearXNG actually use a stranger's public instance, which is exactly as private as that stranger feels like making it. Public instances *can* log everything you type — the same threat model SearXNG is supposed to defeat — and you have no way to verify they don't.

2. **It depends on scraping behavior the upstream engines explicitly forbid.** Google's, Bing's, and DDG's terms of service all prohibit automated scraping. SearXNG works only because the engines tolerate a certain amount of breakage from low-volume scrapers; when an instance gets popular, it starts hitting CAPTCHAs and silently degrades. The whole architecture is parasitic on infrastructure other people pay for and explicitly told you not to use this way. Reasonable people disagree about whether that's *theft* in a meaningful sense — you're consuming the index, not the ads that fund it — but it isn't quite the clean ethical position the README front pages suggest. It's more like "I jaywalk because the crosswalk is far away."

3. **The engines fight back, and the user feels it.** SearXNG instances break constantly. Engines change their HTML, ship new bot-detection, or just block the IP range. The fix is always "use a different instance" or "wait for an upstream parser update". From the user's seat, "private search" turns into "search that sometimes works".

### Hosted alternatives: Kagi, Brave Search, Mojeek, Marginalia

[**Kagi**](https://kagi.com), [**Brave Search**](https://search.brave.com), [**Mojeek**](https://www.mojeek.com), and [**Marginalia**](https://marginalia-search.com) take a different bet: build (or license) an actual web index, charge money or run small ads, and don't track users. These are the most honest options on the privacy axis — there's no scraping someone else's work — but you're paying ($10/month for Kagi) or accepting a smaller / weirder index (Mojeek, Marginalia) or trusting Brave's separate ad business model. That's a perfectly defensible trade; it's just a different one.

### Where divid3 fits

divid3 isn't a search engine. **We don't have an index, we don't crawl the web, we don't scrape anybody.** We're a 22 MB neural network that runs in your browser and decides *which existing engine* to send each query to — and then sends you straight to that engine's normal results page. Your query reaches Google / YouTube / GitHub *exactly* the way it would have if you'd typed it into their search box directly: same TLS connection, same IP, same observable behavior on their side. We add no privacy on the destination side.

What we *do* add:

- **Better default routing.** Most generalist queries don't belong on a generalist engine. "lofi beats" is a YouTube question. "useEffect cleanup" is a GitHub or Perplexity question. "integral of x sin(x)" is a Wolfram Alpha question. The model is a tiny dispatcher that catches the worst routing mistake everyone makes — typing every query into the same box.
- **No middleman.** No public instance, no admin, no rate limit, no CAPTCHAs. Nothing degrades when a result-page HTML structure changes upstream because we never look at result pages.
- **No ToS violations.** We only do what every browser already does: redirect to a URL the user effectively asked for. Each destination gets to run its business model exactly the way it intended. That feels like the right ethical seat — we're respecting upstream engines, not freeloading on their infrastructure.
- **No server, no logs, no operator to trust.** divid3 is a static page on Cloudflare Pages plus a model that runs on-device. There is no `divid3.com` backend that processes queries because there's no backend at all. We genuinely cannot see what you typed; the JS code is all there, in plain sight, in `index.html`.

So the divid3 pitch isn't "we hide you from Google" — it's "we send you to a *better default* than Google for most of what you type, without ever seeing what you typed." That's a smaller privacy claim than SearXNG's, but it's one we can actually keep.

If you want full upstream-side privacy, run a Tor SearXNG instance or pay Kagi. If you want to stop wasting clicks on the wrong search engine — without giving anything new to anyone — divid3 is for you. The two approaches stack: divid3 is happy to redirect you to a SearXNG instance you trust if you set DuckDuckGo's `ddg_url` example phrases to point there.

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

A Playwright suite ([`tests/search.spec.ts`](./tests/search.spec.ts) + [`tests/mobile-and-webkit.spec.ts`](./tests/mobile-and-webkit.spec.ts), 70 specs) runs against **four browser projects** — chromium, firefox, webkit (desktop Safari engine), and mobile-safari (iPhone 13 / WebKit) — for a total of 280 test cases. Each project gets its own browser context so coverage of cache + IndexedDB + visualViewport behavior is real, not mocked.

| Group                          | What it asserts                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------- |
| boot                           | model loads, status indicator reaches `ready`, no console errors, input is accessible, embeddings.json is requested with a `?v=…` cache-buster |
| bang shortcuts                 | each `!x` (plus aliases `!y`, `!nyt`, `!ddg`, `!gr`) routes to the right host; bang-only (`!yt`) and unknown bang (`!nope foo`) don't crash |
| `?q=` redirect                 | `?q=!yt+lofi` auto-redirects; `?q=github.com` direct-links; `?q=how+to+make+pizza` waits for the model and routes semantically; empty / whitespace-only `?q=` stays on the page |
| direct URL detection           | domains, `domain/path`, and `localhost:3000` classify as direct; phrases with spaces don't; Enter on `github.com` actually navigates |
| semantic routing               | scores panel renders all 9 routes with exactly one `.best`; clearing input clears the UI; rapid-fire keystrokes settle on the latest query (`hintSeq` race) |
| click-to-route                 | hint click navigates immediately; chip click overrides the model's pick; chips are real `<button>`s with accessible names; <kbd>Enter</kbd> on a focused chip routes |
| cancel button                  | clicking cancel or pressing Escape stops the redirect, restores focus, preserves the query; rapid double-Enter doesn't stack timers |
| keyboard shortcuts             | `?` opens the overlay, `/` focuses the input, `t` toggles theme — but **only when the search input doesn't have focus** (the typing-`t`-flips-the-theme regression has a permanent test) |
| smart paste                    | pasting `https://github.com` strips the protocol and routes as direct; pasting a regular query is left untouched |
| theme stability while typing   | typing queries containing `t`, `/`, `?` does NOT trigger any shortcut; theme-color meta is updated when the user toggles |
| mobile layout                  | scores panel renders inline beneath the input on mobile; doesn't overlap any footer link or the status dot; footer hides when keyboard is up |
| iOS crash-loop guard           | two unfinished model loads in a row enters lite mode and shows the recovery banner; a successful load clears the counter and sentinel |
| mobile keyboard awareness      | `visualViewport` resize sets `body[data-keyboard="open"]` and the keyboard inset variable; footer links fade out while keyboard is up |
| model load failure             | a 500 on `search-embeddings.json` flips status to `failed`, shows the error banner with a working **Retry**, falls back to DuckDuckGo on Enter and on `?q=…` |
| transient retries              | a single 503 is silently retried and the model reaches `ready` without surfacing the error; deterministic 404s skip retries (no data-plan abuse) |
| browser registration           | `index.html` exposes a `<link rel="search">`, `opensearch.xml` is served correctly, `setup.html` renders with a working Copy button, the homepage footer links to it |
| cache reliability              | a second page load on the same context reuses the cached ONNX model              |

Run them:

```bash
npm ci                                                    # one-time
npx playwright install --with-deps chromium firefox webkit  # one-time
npm test                                                  # full suite, ~10 min across 4 projects
npm run test:ci                                           # CI mode (retries=1, html report)
npx playwright test --project=chromium                    # just one engine, ~90s
npx playwright test --project=mobile-safari -g "mobile"   # mobile suite only
npx playwright test -g "click-to-route"                   # one describe block
npx playwright test -g "cancel" --headed                  # watch it run
npm run test:report                                       # open last HTML report
```

The `webServer` block in [`playwright.config.ts`](./playwright.config.ts) auto-starts the dev server, so you don't have to.

CI runs the same suite on every PR via [`.github/workflows/search-tests.yml`](./.github/workflows/search-tests.yml), installs all three browser engines (chromium + firefox + webkit, the last of which also covers mobile-safari), caches the Playwright browsers, and uploads the HTML report as an artifact when something fails.

---

## iOS reliability and caching

iOS Safari is famously creative about caches: it can drop one resource from disk while keeping a paired one, or serve an immutable-cached asset across builds even after a server-side change. It also doesn't grant pages cross-origin isolation, so anything that needs `SharedArrayBuffer` (including ONNX worker threads) blows up in interesting ways. And when the WebContent process crashes three times in a row on the same URL, Safari permanently shows the "**A problem repeatedly occurred**" interstitial — effectively blacklisting your site from that user's session until they reset Safari.

The single biggest source of pain on iOS isn't the cold model load — it's *cumulative* main-thread inference during typing. The 22 MB ONNX model and its WASM runtime live on the page's main thread; running a fresh inference on every keystroke incrementally grows the WASM heap, and after enough typing the tab crosses the WebContent memory ceiling and gets killed. The `?q=…` redirect path runs inference exactly once and never crashes; the live-typing loop runs it dozens of times per query and eventually does. So we treat live and committed inference as two separate problems:

### Cold-load defenses

1. **Versioned embeddings URL.** `index.html` requests `/search-embeddings.json?v=<EMBEDDINGS_VERSION>`. Bumping the constant invalidates every browser cache atomically. The [`_headers`](./_headers) file pins this URL to a 1-hour TTL with `must-revalidate` regardless, as a safety net.
2. **iOS-safe ONNX runtime tuning.** `env.backends.onnx.wasm.numThreads = 1` and `proxy = false` keep transformers.js on the main WASM execution path everywhere. iOS Safari can't spawn ONNX worker threads (no SAB without COOP/COEP); pinning to a single thread up-front removes a class of mid-init crashes that produced "protobuf parsing failed" reports from iOS users.
3. **Pinned `device: 'wasm'`.** transformers.js v3 defaults to `device: 'auto'`, which probes WebGPU first. On Safari (where WebGPU is gated and buggy as of 2025) that probe has been observed to crash the WebContent process. We bypass it.
4. **Sequential model + embeddings download.** The two largest assets (~22 MB ONNX, ~1.8 MB embeddings JSON) load one after the other instead of in `Promise.all`, so we don't peak at ~24 MB of concurrent in-flight allocation on a memory-pressured iPhone.
5. **Crash-loop guard.** A `sessionStorage` sentinel is set before model load and cleared on success. When a fresh boot still sees the sentinel, we know the previous tab crashed mid-load and bump a counter. After two unfinished attempts the page enters **"lite mode"** automatically: no model load, status dot turns red, the error banner suggests Retry, and bangs / Enter still route via DuckDuckGo. This is the actual mitigation for the "A problem repeatedly occurred" screen — by the time Safari would have shown it, we've already given the user a usable page.
6. **Auto-retry with exponential backoff.** Transient model-load failures (5xx responses, timeouts, network blips) are retried up to two times with 0.8 s → 1.6 s backoff before the error banner appears. Deterministic failures (404, hard parse errors) skip retries so we don't burn the user's data plan.
7. **Never-rejecting init promise + fetch timeout.** If the embeddings fetch hangs (slow network, partial body) it aborts after 30 s; if the model itself errors after retries, the page degrades to a DuckDuckGo pass-through instead of getting stuck on the loading overlay.
8. **Self-service Retry.** A failed load shows an error banner with a **Retry** link. The handler clears `caches.*`, blasts every IndexedDB the origin owns (transformers.js parks the model there), wipes the crash-loop sentinel + counter, and full-reloads. That's the recovery path you reach for when iOS serves a corrupted half-cache and nothing else helps.

### Steady-state defenses (the real iOS killer)

9. **No live inference on mobile.** Below 768 px viewport, `updateHint` only runs the *rule-based* classifier (bangs, direct URLs) during typing. Semantic queries show no preview until the user commits with Enter — at which point `performRoute` runs the model exactly once, the same single-shot path the `?q=…` redirect uses. This eliminates the cumulative-inference failure mode entirely on the platform that's most sensitive to it. Desktop keeps the original live-typing loop because it has the headroom.
10. **220 ms debounce + min-char gate (desktop).** The desktop live loop debounces input at 220 ms (was 150) and skips inference for 1-character queries. Together these cut typical inference frequency by roughly 50 %.
11. **Single-flight inference.** A new keystroke arriving while a previous inference is mid-flight is dropped, not queued. Without this, fast typers stack concurrent WASM allocations and inflate peak memory.
12. **Tensor disposal.** After each inference we call `output.dispose()` and read the embedding via `output.data` (the underlying `Float32Array`) rather than `tolist()` (which would copy into a boxed JS Array first). Both reduce per-call allocation pressure.
13. **Periodic pipeline recycle.** After every 40 inferences the page schedules a dispose-and-reload of the extractor on idle. The model file is read from IndexedDB cache (no network), so it's a ~100 ms reset that resets any drift in the WASM heap's high-water mark.
14. **Background-tab dispose + lazy silent reload.** When `visibilitychange` reports the tab as hidden for >5 s, the extractor is disposed and `modelReady` flips to false. iOS prioritizes evicting the tabs with the largest footprints under memory pressure, so dropping the model makes us a less attractive target. On `visibilitychange` back to visible (or on the next semantic query), `silentReload()` re-creates the pipeline from cache without showing the loading UI again.
15. **bfcache `pageshow` recovery.** If iOS Safari restores a `divid3.com/?q=foo` page from bfcache (e.g. swiping back from a hung destination), the script doesn't re-run; the user sees a frozen overlay. The `pageshow` handler detects the restore (`event.persisted === true`), aborts any pending redirect IIFE via the `pendingRedirectAborted` flag, hides the overlays, drops `?q=` from the URL via `history.replaceState`, and surfaces the original query in the input — turning a stale-redirect trap into a fresh search box with the query pre-filled.

### Keyword-only mode (the low-memory backup)

When the model can't be used at all — repeated cold-load crashes on a memory-constrained iPhone, a hard 4xx on the embeddings file, an explicit `?lite=1` opt-in — the page enters **keyword mode**. The status dot turns **purple**, the model never loads, and `classify()` routes via a deterministic table of ~100 weighted keyword patterns across the 9 destination engines.

Keyword mode is the *third* layer of resilience under the model:

- **Bangs and direct URLs** still preview live and route instantly (they were never model-dependent).
- **Keyword phrases** like `lofi beats`, `buy usb-c cable`, `integral of x^2`, `coffee shops near me`, `image of saturn`, `explain quantum mechanics`, `write a haiku` route to YouTube, Amazon, Wolfram, Maps, Bing Images, Perplexity, Grok respectively — without ever loading the model. Multi-word phrases score higher than single words; a minimum score gates ambiguous matches into a DDG fallback.
- **Word-boundary matching** prevents single-word keywords from misfiring inside larger words (`code` doesn't match `decode`).

Activation paths:

- **`?lite=1` URL param** — explicit opt-in. Useful as a deep link from a "this site keeps crashing on my phone" support reply, or for power users who don't want a 22 MB model on their data plan. Skips embeddings + ONNX downloads entirely.
- **Crash-loop guard** — the existing `sessionStorage` sentinel that detected ≥ 2 unfinished cold loads now flips to keyword mode instead of the previous DDG-only fallback. Same trigger, much smarter routing.
- **Model-load failure after retries** — if the `embeddings.json` fetch deterministically fails (4xx) or transient retries are exhausted, the page transitions to keyword mode and shows the error banner with a working **Retry** link.

The status-dot palette: grey (loading), green (ready / model running), purple (keyword mode / model intentionally not running). There is no red "failed" state anymore — every failure mode now has a working router behind it.

Top-level `window.error` and `window.unhandledrejection` listeners log everything to the console (no network — privacy first) so power users can attach a screenshot of devtools when reporting issues.

---

## Mobile keyboard handling

iOS Safari anchors `position: fixed` to the layout viewport, not the visual viewport, so the soft keyboard happily covers any bottom-anchored UI. The page handles this three ways:

1. **`interactive-widget=resizes-content`** in the viewport meta tag — modern Chrome and Safari shrink the layout viewport itself when the keyboard appears (no JS needed there).
2. **`visualViewport` listener** (the fallback) — JavaScript computes the obscured bottom inset and writes it to a `--keyboard-inset` CSS variable that the desktop scores panel and the status dot add to their `bottom` offset. Works on older iOS too.
3. **Different layout entirely on mobile.** Below 768 px, the scores panel is hoisted **into the input wrapper** and renders inline as wrapping pill chips directly under the search field — no longer competing with the soft keyboard for the bottom edge. The footer links and status dot fade out whenever the keyboard is detected (`body[data-keyboard="open"]`), reappearing the moment the input loses focus. Desktop keeps the original bottom-left list.

---

## What's in the repo

```
.
├── index.html                       # The router (everything described above)
├── setup.html                       # Browser-aware "Set as default" instructions
├── privacy.html                     # Privacy policy
├── opensearch.xml                   # OpenSearch description for browser auto-discovery
├── search-embeddings.json           # ~1.8 MB of pre-computed L2-normalized vectors
├── search.webmanifest               # PWA manifest
├── models/sentence-transformers/all-MiniLM-L6-v2/
│   ├── config.json, tokenizer*.json, special_tokens_map.json
│   └── onnx/model_quantized.onnx    # 22 MB, q8-quantized
├── scripts/
│   ├── search_phrases.json          # Source phrases for each route (curated)
│   ├── generate_search_embeddings.py # Regenerate search-embeddings.json
│   ├── generate_brand_assets.py     # Regenerate favicons / icons / OG images
│   └── review_brand_assets.py       # Contact-sheet preview of brand assets
├── tests/
│   ├── search.spec.ts               # Core E2E suite (~57 specs / project)
│   └── mobile-and-webkit.spec.ts    # Safari + iOS regression suite (13 specs / project)
├── playwright.config.ts             # 4 projects: chromium, firefox, webkit, mobile-safari
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

The example phrases in `search-embeddings.json` are hand-curated — ~50 per route across 9 routes (~480 vectors total, 384 dimensions each). They live as plain text in [`scripts/search_phrases.json`](./scripts/search_phrases.json) so they can be diffed and reviewed.

To regenerate the index after editing phrases, run:

```bash
# one-time:
pip install onnxruntime tokenizers numpy

# every time you change scripts/search_phrases.json:
python3 scripts/generate_search_embeddings.py
```

The script loads the same q8-quantized ONNX model the browser uses (under `models/`), so the regenerated vectors are bit-identical to what transformers.js would produce client-side. It runs the standard `all-MiniLM-L6-v2` pipeline (WordPiece tokenize → BERT forward → mean-pool by attention mask → L2 normalize), trims floats to 6 digits to keep the JSON compact, and asserts every output vector is unit-length before writing.

The runtime requires every vector to be L2-normalized — the dot-product fast path assumes `cos(a, b) ≡ a · b`. Sanity-check with:

```bash
python3 -c "
import json, math
for r in json.load(open('search-embeddings.json')):
    for v in r['vectors']:
        assert abs(math.sqrt(sum(x*x for x in v)) - 1) < 1e-4
print('all normalized')
"
```

**Then bump `EMBEDDINGS_VERSION` in `index.html`.** The page fetches `/search-embeddings.json?v=<EMBEDDINGS_VERSION>`, so without a bump clients can serve a stale cached copy alongside the new HTML.

---

## License

Code in this repository is released under the GNU AGPL v3. See [`LICENSE`](./LICENSE) for the full text.

The model weights under `models/` are [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), released by their authors under Apache 2.0.
