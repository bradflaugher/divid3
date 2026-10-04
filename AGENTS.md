# divid3 — Agent Guide

A private, on-device meta search engine. Single HTML file with inline CSS/JS, static assets, and a committed ONNX model (~22 MB). Hosted on Cloudflare Pages.

---

## Essential Commands

| Command | Purpose |
|---------|---------|
| `npm ci` | Install dev deps (Playwright, `serve`) |
| `npm test` | Run full Playwright E2E suite (~90 s) |
| `npm run test:ci` | CI mode: retries=1, HTML report |
| `npm run test:ui` | Playwright UI mode for debugging |
| `npm run test:report` | Open last HTML report |
| `npm run serve` | Start dev server on `localhost:3000` |
| `npm run lint` | ESLint + TypeScript (`typecheck`) + Ruff + config validator |
| `npm run test:unit` | Python routing unit tests |
| `python3 scripts/generate_brand_assets.py` | Regenerate all favicons, icons, OG images |
| `python3 scripts/review_brand_assets.py` | Generate contact sheet of key assets |
| `python3 scripts/generate_search_embeddings.py` | Rebuild `search-embeddings.json` from `scripts/search_phrases.json` (uses local ONNX model) |

No build step, no bundler, no transpilation. The app is `index.html` + static files served as-is.

---

## Architecture & Control Flow

**Single-page app, everything in `index.html`.** The page is both a search UI and a router entry point (`?q=…`).

### Three-layer routing (fastest → slowest)

1. **Bangs** — DuckDuckGo-style shortcuts (`!yt`, `!eb`, `!m`, etc.; see `bangs` in `search-config.json`). Synchronous regex, no model.
2. **Direct URL detection** — `DOMAIN_RE` / `LOCALHOST_RE` catch domains like `github.com` or `localhost:3000`. Also rule-based, no model.
3. **Semantic routing** — Query is embedded via `@huggingface/transformers` v4 (WASM), compared against pre-computed vectors in `search-embeddings.json`.

### Key data flow

```
User types → debounce 150 ms → classify() →
  rule match? → route immediately
  else if model ready → embed query → dot-product against all route vectors →
    best engine
```

- **Dot product = cosine similarity** because both query and route vectors are L2-normalized. No `sqrt` in the hot path.
- **Per-route score = mean of top-3 cosine similarities** (nearest-neighbor pooling with `TOP_K_NEIGHBORS=3`). Pure max lets a single stray phrase hijack a route; requiring the top-3 nearest neighbors to agree is more robust.
- **Hybrid keyword boost.** `scoreAll(qVec, query)` adds `KEYWORD_BOOST_PER_POINT` (0.03) × the engine's keyword score from `keywordScores()` (capped at `KEYWORD_BOOST_MAX_POINTS` = 5, so at most +0.15). Explicit intent markers (`near me`, `pictures of`, `music video`, `used`) then win over fuzzy semantic neighbors. The same constants live in `scripts/eval_routing.py`; `tests/unit/test_routing.py` fails if they drift. Score chips clamp the displayed % to 100.
- **Race safety:** `hintSeq` counter drops stale inferences when the user types faster than embedding latency.

### Model loading

- `env.allowRemoteModels = false` — only local committed model under `models/sentence-transformers/all-MiniLM-L6-v2/`
- `env.useBrowserCache = true` — transformers.js caches in IndexedDB
- `dtype: 'q8'` — loads `model_quantized.onnx` specifically. Any other dtype would 404; on Cloudflare Pages a 404 returns HTML, which ONNX runtime tries to parse as protobuf, yielding the cryptic *"protobuf parsing failed"* error.
- `modelLoadPromise` is **never-rejecting** (`Promise<boolean>`). All callers `await` it safely. On failure the page degrades to DuckDuckGo pass-through.

---

## File Organization

```
├── index.html                    # Entire app: HTML, CSS, JS module
├── setup.html                    # "Set as default" instructions, browser-aware
├── privacy.html                  # Standalone privacy policy page
├── opensearch.xml                # OpenSearch description for browser auto-discovery
├── search-embeddings.json        # ~1.8 MB pre-computed L2-normalized vectors
├── search.webmanifest            # PWA manifest
├── serve.json                    # Dev-server config: cleanUrls=false (preserves ?q=)
├── _headers                      # Cloudflare Pages cache-control + security headers
├── models/sentence-transformers/all-MiniLM-L6-v2/
│   ├── config.json, tokenizer*.json, special_tokens_map.json
│   └── onnx/model_quantized.onnx    # 22 MB q8-quantized ONNX
├── tests/search.spec.ts          # Playwright E2E suite
├── tests/unit/test_routing.py    # Python unit tests: config checks, routing example tables, accuracy floors
├── playwright.config.ts          # Auto-starts dev server, workers=2 in CI
├── scripts/
│   ├── search_phrases.json       # Source phrases for the semantic index (editable)
│   ├── generate_search_embeddings.py # Rebuild search-embeddings.json from phrases
│   ├── eval_routing.py           # Offline routing eval (mirrors index.html scoring)
│   ├── routing_benchmark.json    # Held-out labeled queries (never copy into phrases)
│   ├── validate_config.py        # Schema + corpus-rule validator (npm run lint:config)
│   ├── requirements.in           # Direct Python deps (numpy / onnxruntime / tokenizers) for eval + unit tests
│   ├── requirements.txt          # Hash-locked from requirements.in by `uv pip compile` (don't hand-edit)
│   ├── generate_brand_assets.py  # Regenerate favicons, icons, OG images
│   └── review_brand_assets.py    # Contact-sheet reviewer
└── favicon-*.png, icon-*.png, apple-touch-icon-*.png, og-image.png, …
```

**No `src/` directory.** All logic lives in `index.html`. There are no JS modules to import besides the CDN transformers.js bundle.

---

## Testing

- **Playwright E2E** for the page, plus **Python unit tests** for routing (`npm run test:unit` → `python3 -m unittest discover -s tests/unit -v`). The unit tests need `pip install -r scripts/requirements.txt` for the semantic cases (they're skipped otherwise); they run in the `unit` job of `lint.yml`. When you edit phrases or keyword rules, add example cases to the tables in `tests/unit/test_routing.py` (`KEYWORD_CASES`, `KEYWORD_FALSE_POSITIVES`, `SEMANTIC_CASES`) and keep the benchmark accuracy floors green.
- Each test gets a **fresh browser context**, so every test re-downloads the ~22 MB model from the local server. `workers: 2` in CI keeps wall-clock time bounded.
- `playwright.config.ts` auto-starts `npx serve -l 3000 .` via `webServer` block.
- Tests assert on `data-*` attributes (`data-state`, `data-engine`) rather than visible text, so copy changes don't break specs.
- `freezeRouteTimer()` stubs `setTimeout` with `ms === 1500` to prevent overlay auto-navigation during assertions.
- Navigation assertions match hostname + encoding-agnostic query substring (engines vary between `+` and `%20`).
- Four Playwright **projects**: `chromium`, `firefox`, `webkit`, `mobile-safari` (iPhone 13). Browser-specific tests use `test.skip(({ browserName }) => …)` rather than tag filtering. Known per-engine quirks: WebKit doesn't expose `clipboard-write`; Firefox doesn't expose `clipboard-read` and silently strips `clipboardData` from synthetic ClipboardEvents — both clipboard-related tests are skipped on those engines.
- `tests/mobile-and-webkit.spec.ts` exists specifically to cover Safari/iOS regressions the desktop-Chromium suite is blind to: theme stability while typing, mobile bottom-of-viewport layout, and the iOS crash-loop guard.

### Running subsets

```bash
npx playwright test -g "bang"                        # one describe block
npx playwright test -g "cancel" --headed             # watch it run
npx playwright test --project=chromium               # single engine, ~90s
npx playwright test --project=firefox                # single engine, ~90s
npx playwright test --project=mobile-safari          # iPhone 13 viewport only
npx playwright test tests/mobile-and-webkit.spec.ts  # Safari-focused suite
```

---

## Critical Conventions & Gotchas

### `serve.json` must exist
`cleanUrls: false` prevents `serve` from 301-redirecting `/index.html?q=foo` to `/?q=foo` and **dropping the query string**. Cloudflare Pages preserves it in production, but the dev server does not without this config.

### `EMBEDDINGS_VERSION` must be bumped when `search-embeddings.json` changes
The page fetches `/search-embeddings.json?v=${EMBEDDINGS_VERSION}`. Without a version bump, iOS Safari may serve a stale cached JSON body alongside a freshly fetched `index.html`, breaking routing. The `_headers` file also pins this URL to a 1-hour TTL with `must-revalidate` as a safety net.

### Embeddings must stay L2-normalized
The runtime assumes `cos(a,b) ≡ a·b`. If you regenerate `search-embeddings.json`, verify:

```bash
python3 -c "
import json, math
for r in json.load(open('search-embeddings.json')):
    for v in r['vectors']:
        assert abs(math.sqrt(sum(x*x for x in v)) - 1) < 1e-6
print('all normalized')
"
```

### ONNX dtype mismatch = cryptic protobuf error
If you change `MODEL_DTYPE` from `'q8'` to anything else, the fetch for the corresponding `.onnx` filename will 404. Because Cloudflare Pages serves HTML for 404s, the ONNX runtime tries to parse HTML as protobuf and fails with *"Failed to load model because protobuf parsing failed"*. The fix is ensuring the requested filename matches the committed file exactly.

### iOS cache recovery
The **Retry** button in the error banner does a full cache nuke: clears all `caches.*`, deletes every IndexedDB database, then `location.reload()`. This is the escape hatch when iOS serves a corrupted half-cache.

### iOS-safe ONNX threading
`env.backends.onnx.wasm.numThreads = 1` and `proxy = false` are intentional. iOS Safari does not give pages cross-origin isolation (no `SharedArrayBuffer`), so the multi-threaded ONNX path either no-ops or crashes with a confusing "protobuf parsing failed". Keep the single-thread pin even if the desktop story improves — it's the iOS pain point.

### Pipeline pinned to `device: 'wasm'`
`pipeline('feature-extraction', MODEL_ID, { dtype: 'q8', device: 'wasm' })` deliberately bypasses transformers.js's `device: 'auto'` probe. The auto-probe tries WebGPU first; on Safari (where WebGPU is gated/buggy as of 2025) this has been observed to crash the WebContent process. The WASM path is fast enough for a 22 MB MiniLM and predictable across browsers.

### Mobile = NO live semantic inference (the iOS reliability fix)
On viewports `(max-width: 767px)`, `updateHint()` only runs `classifyRules()` (bangs, direct URLs). Semantic queries get **no live preview** — the engine hint stays cleared until the user presses Enter, at which point `performRoute()` runs the model exactly once. Equivalent to the `?q=` redirect path, which iOS users already report as reliable. The cumulative-inference WASM-heap drift that used to crash mobile Safari tabs is eliminated, not mitigated.

Desktop keeps the live-typing loop. Don't restore live inference on mobile — that's the regression that brought the "A problem repeatedly occurred" reports back. If you need to render scores on mobile, render them on the routing overlay after Enter, not during typing.

### Single-flight inference
The classify path tracks `inferenceInflight`; a keystroke arriving while a previous inference is running is dropped (returns `null` to `updateHint`, which does nothing). The next debounced tick will run with the latest input. Without this, fast typers stack concurrent WASM allocations on the desktop live loop.

### Tensor disposal + typed-array path
`extractor([q], …)` returns a `Tensor`. Read the embedding via `output.data` (the underlying `Float32Array`), not `output.tolist()[0]` (which copies into a boxed JS Array first). After reading, call `output.dispose()` to free the WASM-side buffer. Both reduce per-call allocation pressure on iOS.

### Periodic pipeline recycle
Every `INFERENCES_PER_RECYCLE` inferences (40), `scheduleRecycle()` queues a dispose-and-reload of the extractor on a 1.5 s idle delay. Reload reads from IndexedDB cache, so it's ~100 ms with no network. The recycle path uses `disposeExtractor()` + `silentReload()`, deliberately bypassing `initModel()` so the crash-loop sentinel and loading overlay stay quiet — those exist for *cold-boot* failures, not deliberate recycles. Don't route the recycle through `initModel()`.

### Visibility-aware dispose + silent reload
`visibilitychange` to hidden + 5 s timer → `disposeExtractor()` (so iOS picks a different tab to evict under memory pressure). On return to visible, `silentReload()` re-creates the pipeline from cache. The 5 s delay protects quick tab-switches; iOS usually freezes JS before it fires for longer backgrounding, in which case nothing happens (the page is suspended anyway). `pagehide` also disposes as a defensive teardown for bfcache transitions.

### bfcache `pageshow` handler — `pendingRedirectAborted`
If iOS restores a `?q=` page from bfcache, the script does NOT re-run, but the original `?q=` IIFE may still resolve and call `performRoute` after the user has visibly come back to the page. The `pageshow` handler with `event.persisted` sets the `pendingRedirectAborted` flag, hides overlays, strips `?q=` from the URL, and pre-fills the input with the query. The `?q=` IIFE checks the flag right before calling `performRoute()` and bails. Don't remove the flag check — without it, the page bounces the user out again right after they came back.

### Crash-loop guard (the "A problem repeatedly occurred" page) → keyword mode
iOS Safari shows a hostile "A problem repeatedly occurred on https://divid3.com/" interstitial after the WebContent process crashes ~3 times in a row, and effectively blacklists the URL. We defend against this with a session-storage sentinel:

- `divid3-loading=1` is set before model load starts; cleared on success or on a *caught* failure.
- On boot, if the flag is still set we know the previous attempt didn't return; we increment `divid3-crash-count`.
- After `MAX_CRASHES_BEFORE_FALLBACK` (= 2) unfinished loads, `initModel()` short-circuits to **keyword mode** — no model load attempted, status dot turns purple, error banner offers Retry, and bangs/Enter still route correctly.
- The Retry button explicitly clears both keys (plus caches + IndexedDB) before reloading.

Embeddings + model are loaded **sequentially** (`await fetchEmbeddings(); await pipeline(...)`) rather than in `Promise.all`, so we don't peak at ~24 MB of concurrent downloads on a memory-pressured iPhone.

### Keyword mode = the model-disabled fallback
`keywordMode` (state variable) gates whether `classify()` ever touches the model. When `true`:
- `initModel()` early-returns (no embeddings fetch, no ONNX download).
- `classify()` short-circuits to `classifyKeywords(q) || 'ddg'`.
- Status dot is purple (`.status-dot.keyword`).
- The error banner explains the mode if it was activated by a failure.

Activation paths (each independently sets `keywordMode = true`):
- `?lite=1` URL param at boot.
- Crash-loop sentinel detects ≥ `MAX_CRASHES_BEFORE_FALLBACK` unfinished loads.
- `initModel()` exhausts retries on a transient failure or hits a deterministic 4xx.

`KEYWORD_RULES` is the source of truth: a flat list of `{ engine, weight, kw: [...] }` rules. Each rule contributes its `weight` to the engine's score if ANY of its `kw` strings match the query. Highest-scoring engine wins, with `MIN_KEYWORD_SCORE` (= 2) gating ambiguous matches into the DDG fallback. A rule marked `"priority": true` short-circuits that: if it matches, its engine wins outright no matter how other rules' weights stack. Four rules use it, in this order: DDG account creation (`create a * account`, `make an * account`, … where `*` is exactly one word), so "create a GitHub account" isn't mistaken for writing; Lumo writing intent (`write a`, `draft a`, `craft a`, `create a`, …), so "write a breaking news post on twitter" stays on Lumo; DDG login and account-help intent (`login`, `sign in`, `password reset`, `twitter account suspended`, `twitter help`, …), so "sign in on twitter" or "delete my twitter account" isn't an X search; and Lumo recommendation/review intent (`recommend`, `suggest a`, `advice for`, `review of`, …), so "recommend a live coverage source" or "reviews of breaking news apps" isn't either (**unless** `near me` / `nearby`: "recommend a restaurant near me" stays on Maps). Any rule can also carry `unless` (it doesn't match if one of these keywords is present); `ruleMatches()` and both Python mirrors implement it and `validate_config.py` checks it. When several priority rules match, the first in the list wins ("write a login page" → Lumo). `classifyKeywords()` in `index.html` and both Python mirrors (`eval_routing.py`, `tests/unit/test_routing.py`) implement it. Keywords (bare words and phrases alike) match whole words only: `code` doesn't match `decode`, and `craft a` matches neither `minecraft armor` nor `craft armor`. The last word may take a plural `s`/`es` (`full album` matches `full albums`), and `*` stands for exactly one word (`create a * account`). Other inflections must be listed explicitly. Before matching, `normalizeForKeywords()` lowercases the query and keywords and folds punctuation to spaces (curly apostrophes from iOS smart punctuation are straightened first; apostrophes survive only inside words, so `'write a poem'` in quotes still matches), so quotes, brackets and dashes count as word boundaries (`"write a poem"`, `(breaking news…)`, `weather?`).

When *adding* a new keyword:
- Multi-word phrases (`pull request`, `buy usb-c cable`) are stable — pretty much always specific enough.
- Polysemous words (`opinion`, `drama`, `reaction to`) need a sense check too: `second opinion`, `korean drama` and `allergic reaction` are not X queries. A weight-8 DDG rule pins those senses to the web. Prefer social phrasings over bare words: X matches `trending on`, `trending now`, `what is trending`, not bare `trending` ("temperature is trending warmer").
- Single words need a sanity check: would adding ` foo ` falsely match a query like `comfort` or `foothold`? If yes, prefer a longer phrase form, or accept the false positive only if the engine is a reasonable destination for the false-match query anyway.
- The `cases[]` table in `tests/search.spec.ts > keyword mode (low-memory fallback)` has per-engine routing assertions — add a case there for any new engine destination, and the word-boundary regression test catches accidental bare-word matches. `KEYWORD_FALSE_POSITIVES` in `tests/unit/test_routing.py` pins known traps (`street fighter 6`, `browser console log`, `cinnamon bun recipe`).

### Removed destinations: Wirecutter and Hacker News
There is no Wirecutter engine (no `!wc`/`!nyt`) and no Hacker News engine (no `!hn`/`!h`) anymore — no route, no keyword rules. Where their queries go now:
- "best X" product shopping → **DDG**.
- Reviews, recommendations, gift ideas, "is X worth it / which should I buy" → **Lumo**.
- Tech discussion: "what do developers think of…" / hot takes → **X**; debates, engineering war stories, explainers → **Lumo**; docs, installs, downloads, project lookups → **DDG**.

`ConfigTests.test_wirecutter_fully_removed` and `test_hacker_news_fully_removed` guard against either creeping back.

### Lumo's scope (replaced Grok)
Lumo is Proton's privacy-first assistant. Besides explainers / research / writing it is the destination for **product reviews, recommendations and advice**. Breaking news and opinions moved to X (see below); the benchmark still accepts Lumo for those, since guest-mode Lumo searches the web on its own. Gemini was considered as a general-purpose AI destination but dropped: gemini.google.com has no native URL query parameter, so the query would be lost.

The URL is `https://lumo.proton.me/guest#q={q}`, on purpose:
- `lumo.proton.me/?q=` does **not** work for signed-out visitors: Lumo redirects them to `/guest` and drops the query. `/guest` reads `q` from the query string or the fragment and auto-sends it (`?prefill=` only fills the box).
- The `#` fragment keeps the query out of the request line, so it isn't in Proton's server logs or a `Referer`.
- Trade-off: signed-in Proton users land in a guest chat (not saved to their account, guest limits).
- lumo.proton.me publishes no `apple-app-site-association` / `assetlinks.json`, so links open the web app, not the native Lumo app. That's Proton's side; if they add it, the same URL will open the app.

`!l` / `!lumo` are the Lumo bangs; `!g`, `!gr`, `!p`, `!px` are kept as aliases from the Grok/Perplexity days. `ConfigTests.test_grok_fully_removed` guards against Grok creeping back.

### X's scope (news and opinions)
X (`x` engine) is the destination for **breaking news, live updates, current events, opinions, hot takes, drama/controversy and social sentiment ("what are people saying…", "what do developers think of…")**. The line against Lumo: *what people are saying right now* → X; *a product review, recommendation or advice* → Lumo. Plain navigational news lookups (`cnn`, `local news`) and live numbers (`dow jones today`, `nfl scores`) stay on DDG, and `twitter login` stays on DDG (the `login` rule outweighs `twitter`).

The URL is `https://x.com/search?q={q}&src=typed_query` (`src=typed_query` is what X's own search box sends). Trade-offs:
- X requires sign-in to search. Signed-out visitors get a 307 to X's login page with the search in `redirect_after_login`, so it resumes after they log in.
- X also refuses headless browsers, so the E2E specs that route to X call `stubX(page)` to answer x.com with a stub page and assert on the URL we built.
- x.com publishes `apple-app-site-association`, so on iOS with the X app installed the link opens the app.
- Unlike Lumo's `#q=`, the query is in the request line and goes to X's servers. That's inherent to searching X.

Bangs: `!x`, `!tw`, `!twitter`. The phrases live in the `x` route of `scripts/search_phrases.json`; keyword rules are the `x` entries in `keywordRules`.

The status-dot palette is now: grey = loading, green = ready (model running), purple = keyword mode (model intentionally not running). The previous red "failed" state is gone — every former-failure mode now lands on keyword mode with a working router.

### Single-letter shortcuts must NOT fire while the search input has focus
The `?`, `/`, and `t` shortcuts live on `document` and short-circuit when `event.target` is an `<input>` / `<textarea>` / `contentEditable` element via the `isTypingTarget()` helper. Attaching them to the `#search` element directly was a long-standing bug: typing any query containing `t` would `preventDefault` the keystroke and silently flip the theme, which users perceived as the page "randomly turning to light mode". Keep the document-level handler; never re-add per-input shortcuts.

### Score chips are real `<button>` elements, by design
`renderScores()` builds each `.score-row` with `document.createElement('button')`, not a `<div>` with `role="button"`. This gives us:
- Native keyboard activation (Enter/Space) without a manual keydown handler.
- An auto-exposed `role=button` for screen readers.
- Real focus styling via `:focus-visible`.

CSS resets the button's user-agent appearance (`border: 1px solid transparent; color: inherit; font: inherit`) so the chip still looks like a chip. Click handling is event-delegated on `#scores` so it survives every re-render. The handler short-circuits if `search.value.trim()` is empty.

### `performRoute(query, immediate, overrideKey)` — the third arg is the override
`performRoute` accepts an optional `overrideKey`. When provided, the function **skips `classify()` entirely** and routes to that engine directly. This is how both the engine-hint click and the score-chip click bypass the model's pick. If you ever need to re-introduce a "manual route" code path, use this signature — don't add another routing function and don't temporarily mutate the engine-selection state.

### Mobile layout: scores live inside `.input-wrap` (currently unused on mobile)
On mobile (`<768px`), `#scores` renders inline beneath the input as wrapping pill-chips (`position: static`, `flex-wrap: wrap`). On desktop (`≥768px`), CSS lifts it back into a fixed bottom-left vertical list. The DOM ordering matters — `#scores` must be the last child of `.input-wrap` so it sits between the engine hint and the bottom-fixed footer. Don't move it back to the page-level layout: the previous fixed-bottom horizontal-scroll strip overlapped the footer links + status dot once the soft keyboard pushed everything up.

Note: mobile no longer renders `#scores` during typing (no live semantic inference) so the inline-chip CSS is currently dormant on mobile. It's kept because the `(max-width: 767px)` matcher includes desktop browsers in narrow windows — they get the inline layout if scores ever do render — and because a future "scores on the routing overlay" change could bring it back to use.

### Footer links + status dot hide when keyboard is up (mobile only)
JS sets `body[data-keyboard="open"]` whenever `visualViewport` reports an inset > 120 px. CSS uses that to fade out `.footer-links` and `.status-dot` on viewports `<768px`. Desktop explicitly opts out via a `min-width: 768px` reset so the footer + dot stay visible regardless of focus state.

### Auto-retry only for transient failures
`isTransientError()` whitelists `AbortError`, network/fetch/timeout messages, and HTTP 408/429/5xx. **Do not** add 4xx (other than 408/429) to that whitelist — a 404 means the URL is wrong, retrying just burns the user's data plan and never succeeds.

### Bumping `EMBEDDINGS_VERSION` is mandatory
Every change to `search-embeddings.json` (including via `scripts/generate_search_embeddings.py`) must be paired with a bump of `EMBEDDINGS_VERSION` in `index.html`. Without it iOS Safari can serve a stale cached body alongside a freshly-fetched HTML and routing silently breaks.

### Source phrases live in `scripts/search_phrases.json`
`search-embeddings.json` is a build artifact. Edit phrases in `scripts/search_phrases.json`, run `python3 scripts/generate_search_embeddings.py`, sanity-check with the L2-normalization snippet in the README, then bump `EMBEDDINGS_VERSION`.

### Mobile keyboard handling
- Viewport meta includes `interactive-widget=resizes-content` (modern Chrome/Safari shrink layout viewport automatically).
- Fallback: `visualViewport` API computes bottom inset and writes `--keyboard-inset` CSS variable. `.scores-panel` and `.status-dot` add this to their `bottom` offset.

### Route delay is CSS-driven
`--route-delay-ms` in `:root` is the single source of truth. JS reads it back via `getComputedStyle` so the visual progress bar and `setTimeout` can never drift out of sync.

### Never use `innerHTML` for dynamic text
The code builds DOM nodes or uses `document.createDocumentFragment` to avoid XSS surfaces. `renderScores` uses `innerHTML` only for static score-row template strings where all values are numeric or controlled.

---

### Direct-link and bang edge cases
- `toDirectUrl()` adds a scheme only when there isn't one (`/^https?:\/\//`), never via `startsWith('http')` — `httpbin.org` is a bare domain. `localhost` targets get `http://`.
- `isDirectTarget()` rejects file-extension "TLDs" (`node.js`, `package.json`) via `FILE_EXT_TLD_RE`. Only list extensions that are **not** delegated TLDs (`.py`, `.md`, `.rs`, `.sh`, `.zip` are real TLDs).
- Look up bangs only through `bangEngine()` (own-property check), so `!constructor` can't resolve to `Object.prototype`. `buildTargetUrl()` strips the leading `!token` only when it's a known bang.
- **`?q=<domain>` is never auto-followed.** A direct link typed into the page navigates right away. One that arrives via `?q=` shows the overlay with an `Open <host>` button (`data-engine="direct"`), otherwise `divid3.com/?q=evil.example` would be an open redirect. Keep it that way.
- URL templates use `replace('{q}', () => q)`: a string replacement would expand `$&` / `` $` `` in the query.

### `_headers` rules are additive
Cloudflare Pages applies every matching rule and **comma-joins** duplicate headers instead of overriding them. Never set `Cache-Control` in the `/*` catch-all, because it would be glued onto the `/models/*` immutable rule. Each path should match at most one `Cache-Control` rule. The `/*` block carries only the security headers (CSP `frame-ancestors`/`base-uri`/`object-src`/`form-action`, HSTS, nosniff, etc.). It deliberately has no `script-src`: the inline module would need a hash re-pinned on every edit.

---

## Dependencies & supply chain

- `package.json` has **devDependencies only**. The site has no runtime npm deps. Don't add transitive packages to `dependencies`.
- Python deps: direct pins live in `scripts/requirements.in` (model/eval) and `scripts/requirements-dev.in` (Ruff). The `.txt` files next to them are hash-locked with `uv pip compile --universal --python-version 3.13 --generate-hashes` (exact command in each `.in` header), and CI installs them with `--require-hashes`. Edit the `.in`, re-run the compile, and commit both.
- Node version for CI lives in `.nvmrc`.
- Every GitHub Action is pinned to a full commit SHA with a `# vX.Y.Z` comment. Dependabot (`.github/dependabot.yml`) bumps Actions, npm and pip weekly, after a 7-day cooldown. Keep `permissions:` least-privilege and `persist-credentials: false` on checkout.
- CodeQL (`.github/workflows/codeql.yml`) scans the Actions workflows, the inline JS in the HTML files, and the Python scripts. Dependency Review (`dependency-review.yml`) blocks PRs that add vulnerable (≥ moderate) or GPL/AGPL dependencies. OpenSSF Scorecard (`scorecard.yml`) runs weekly and feeds the README badge.
- The lint job runs `npm audit signatures`. The specs are type-checked with `strict` TypeScript (`tsconfig.json`, no emit).
- Community files: `SECURITY.md` (private advisories), `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`, `.github/CODEOWNERS`, `.editorconfig`, `.gitattributes` (marks generated JSON).
- transformers.js is imported from jsdelivr at an exact version. Treat a version bump as a real change: run the full four-browser E2E suite and test on a real iPhone. Since v4 the ONNX WASM runtime is fetched from the separate `onnxruntime-web` package on jsdelivr (not from inside the transformers.js dist), so a CSP `connect-src`/`script-src` would need to allow both.

---

## CI / Deploy

- **Cloudflare Pages** deploys on every push to `main` via `.github/workflows/deploy.yml`. It stages only the public files into `_site/` (no `tests/`, `scripts/`, `*.md`, package or CI files) and deploys that. **If you add a new top-level dev-only file, add it to the rsync excludes there.** The job runs in the `production` environment.
- **E2E tests** run on PRs and pushes that touch `index.html`, `search-embeddings.json`, `tests/`, `models/`, or workflow files.
- Tests cache Playwright browsers between runs.
- Failed CI runs upload the HTML report as an artifact.

---

## Brand Assets

- `scripts/generate_brand_assets.py` requires `Pillow` and system fonts (Liberation Sans or Noto Sans). It regenerates ~30 PNG/SVG files.
- `scripts/review_brand_assets.py` creates `brand-assets-contact-sheet.png` for quick visual review.
- The slash icon geometry is derived from SVG path `M631 128 346 896` and scaled proportionally in Python.

---

## License

Code: MIT. Model weights (`models/`): Apache 2.0 (sentence-transformers/all-MiniLM-L6-v2).
