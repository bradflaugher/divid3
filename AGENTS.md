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
├── privacy.html                  # Standalone privacy policy page
├── search-embeddings.json        # ~3.5 MB pre-computed L2-normalized vectors
├── search.webmanifest            # PWA manifest
├── serve.json                    # Dev-server config: cleanUrls=false (preserves ?q=)
├── _headers                      # Cloudflare Pages cache-control rules
├── models/sentence-transformers/all-MiniLM-L6-v2/
│   ├── config.json, tokenizer*.json, special_tokens_map.json
│   └── onnx/model_quantized.onnx    # 22 MB q8-quantized ONNX
├── tests/search.spec.ts          # Playwright E2E suite (40 specs)
├── playwright.config.ts          # Auto-starts dev server, workers=2 in CI
├── scripts/
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

### Running subsets

```bash
npx playwright test -g "bang"          # one describe block
npx playwright test -g "cancel" --headed  # watch it run
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
