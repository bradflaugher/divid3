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
| `python3 scripts/generate_brand_assets.py` | Regenerate all favicons, icons, OG images |
| `python3 scripts/review_brand_assets.py` | Generate contact sheet of key assets |
| `python3 scripts/generate_search_embeddings.py` | Rebuild `search-embeddings.json` from `scripts/search_phrases.json` (uses local ONNX model) |

No build step, no bundler, no transpilation. The app is `index.html` + static files served as-is.

---

## Architecture & Control Flow

**Single-page app, everything in `index.html`.** The page is both a search UI and a router entry point (`?q=…`).

### Three-layer routing (fastest → slowest)

1. **Bangs** — DuckDuckGo-style shortcuts (`!yt`, `!gh`, `!w`, etc.). Synchronous regex, no model.
2. **Direct URL detection** — `DOMAIN_RE` / `LOCALHOST_RE` catch domains like `github.com` or `localhost:3000`. Also rule-based, no model.
3. **Semantic routing** — Query is embedded via `@huggingface/transformers` v3 (WebGPU/WASM), compared against pre-computed vectors in `search-embeddings.json`. Falls back to DuckDuckGo if top score < `SIMILARITY_THRESHOLD` (0.30).

### Key data flow

```
User types → debounce 150 ms → classify() →
  rule match? → route immediately
  else if model ready → embed query → dot-product against all route vectors →
    max score ≥ 0.30? → best engine
    else → DuckDuckGo
```

- **Dot product = cosine similarity** because both query and route vectors are L2-normalized. No `sqrt` in the hot path.
- **Per-route score = max over examples** (nearest-neighbor pooling), not mean. More robust with varied phrasings.
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
├── _headers                      # Cloudflare Pages cache-control rules
├── models/sentence-transformers/all-MiniLM-L6-v2/
│   ├── config.json, tokenizer*.json, special_tokens_map.json
│   └── onnx/model_quantized.onnx    # 22 MB q8-quantized ONNX
├── tests/search.spec.ts          # Playwright E2E suite (45 specs)
├── playwright.config.ts          # Auto-starts dev server, workers=2 in CI
├── scripts/
│   ├── search_phrases.json       # Source phrases for the semantic index (editable)
│   ├── generate_search_embeddings.py # Rebuild search-embeddings.json from phrases
│   ├── generate_brand_assets.py  # Regenerate favicons, icons, OG images
│   └── review_brand_assets.py    # Contact-sheet reviewer
└── favicon-*.png, icon-*.png, apple-touch-icon-*.png, og-image.png, …
```

**No `src/` directory.** All logic lives in `index.html`. There are no JS modules to import besides the CDN transformers.js bundle.

---

## Testing

- **Playwright E2E only** — no unit tests, no Jest/Vitest.
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
`pipeline('feature-extraction', MODEL_ID, { dtype: 'q8', device: 'wasm' })` deliberately bypasses transformers.js v3's `device: 'auto'` probe. The auto-probe tries WebGPU first; on Safari (where WebGPU is gated/buggy as of 2025) this has been observed to crash the WebContent process. The WASM path is fast enough for a 22 MB MiniLM and predictable across browsers.

### Crash-loop guard (the "A problem repeatedly occurred" page)
iOS Safari shows a hostile "A problem repeatedly occurred on https://divid3.com/" interstitial after the WebContent process crashes ~3 times in a row, and effectively blacklists the URL. We defend against this with a session-storage sentinel:

- `divid3-loading=1` is set before model load starts; cleared on success or on a *caught* failure.
- On boot, if the flag is still set we know the previous attempt didn't return; we increment `divid3-crash-count`.
- After `MAX_CRASHES_BEFORE_FALLBACK` (= 2) unfinished loads, `initModel()` short-circuits to "lite mode": no model load attempted, status dot goes red, error banner suggests Retry, and bangs/Enter still route correctly.
- The Retry button explicitly clears both keys (plus caches + IndexedDB) before reloading.

Embeddings + model are loaded **sequentially** (`await fetchEmbeddings(); await pipeline(...)`) rather than in `Promise.all`, so we don't peak at ~24 MB of concurrent downloads on a memory-pressured iPhone.

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

### Mobile layout: scores live inside `.input-wrap`
On mobile (`<768px`), `#scores` renders inline beneath the input as wrapping pill-chips (`position: static`, `flex-wrap: wrap`). On desktop (`≥768px`), CSS lifts it back into a fixed bottom-left vertical list. The DOM ordering matters — `#scores` must be the last child of `.input-wrap` so it sits between the engine hint and the bottom-fixed footer. Don't move it back to the page-level layout: the previous fixed-bottom horizontal-scroll strip overlapped the footer links + status dot once the soft keyboard pushed everything up.

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

## CI / Deploy

- **Cloudflare Pages** deploys on every push to `main` via `.github/workflows/deploy.yml`.
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

Code: GNU AGPL v3. Model weights (`models/`): Apache 2.0 (sentence-transformers/all-MiniLM-L6-v2).
