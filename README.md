# divid3

A private, on-device search router. **divid3** intelligently routes your queries to the best destination without tracking.

[**Try it at divid3.com**](https://divid3.com)

---

## Why divid3?

Most search engines track you, show ads, or keep your query history. divid3 does none of that. It runs entirely in your browser, routes you directly to the best source, and forgets your query the moment you leave.

---

## Key Features

- **100% Private:** Runs entirely in your browser. No server logs, no analytics, no query tracking.
- **On-Device ML:** Uses a 22MB `all-MiniLM-L6-v2` model to understand intent and route semantically.
- **Fast:** Layered routing logic (Bangs → Regex → Semantic) ensures instant results.
- **Zero Middleman:** Routes you directly to the source. No scraping, no rate limits, no ToS violations.

---

## Usage

### Bang Shortcuts (Instant)

Prefix your query with a bang to bypass the model:

| Bang | Destination | Bang | Destination |
|------|-------------|------|-------------|
| `!d`  | DuckDuckGo | `!ddg` | DuckDuckGo |
| `!g`  | Grok | `!gr` | Grok |
| `!h`  | Hacker News | `!hn` | Hacker News |
| `!i`  | Bing Images | `!img` | Bing Images |
| `!m`  | Google Maps | `!map` | Google Maps |
| `!p`  | Perplexity | `!px` | Perplexity |
| `!w`  | Wolfram Alpha | `!wa` | Wolfram Alpha |
| `!wc` | Wirecutter | `!nyt` | Wirecutter |
| `!y`  | YouTube | `!yt` | YouTube |

### Semantic Routing (Auto)

For everything else, the model decides based on context:

- *"lofi beats"* → **YouTube**
- *"useEffect cleanup"* → **Hacker News**
- *"best USB-C cables"* → **Wirecutter**

The scores panel in the bottom-left shows candidate scores; every chip is clickable to override the model's choice.

---

## Getting Started

Set divid3 as your default search engine: `https://divid3.com/?q=%s`

Detailed instructions for Chrome, Firefox, Safari, and Android are available at [**divid3.com/setup.html**](https://divid3.com/setup.html).

---

## Browser Support

| Browser | Status |
|---------|--------|
| Chrome / Edge | ✅ Full support |
| Firefox | ✅ Full support |
| Safari (desktop) | ✅ Full support |
| Safari (iOS) | ✅ Full support with crash-loop guard |

On mobile Safari, divid3 automatically disables live semantic inference to avoid memory pressure and enters keyword-only fallback if the model fails to load.

---

## Technical Architecture

### Layered Routing

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

### Tech Stack

- **Engine:** Vanilla HTML/JS/CSS (No build step).
- **ML Runtime:** `@huggingface/transformers` v3 (WASM/WebGPU).
- **Model:** `all-MiniLM-L6-v2` (q8-quantized).
- **Hosting:** Cloudflare Pages.

### Resilience (iOS & Mobile)

- **No live inference on mobile:** Minimizes memory pressure; model runs only on commit.
- **Crash-loop guard:** Automatically enters keyword-only mode if model load fails repeatedly.
- **Memory management:** Disposes model on tab hide; periodic pipeline recycling.

---

## Development

```bash
npm ci
npm run serve
# Open http://localhost:3000
```

### Testing

70+ Playwright specs across Chromium, Firefox, WebKit, and Mobile Safari.

```bash
npm test              # Run full suite
npm run test:ci       # CI mode with retries
npm run test:ui       # Interactive UI mode
npm run test:report   # Open last HTML report
```

### Updating Embeddings

Hand-curated phrases live in `scripts/search_phrases.json`.

```bash
# Regenerate search-embeddings.json
python3 scripts/generate_search_embeddings.py
```

> **Important:** After regenerating embeddings, bump `EMBEDDINGS_VERSION` in `index.html` so iOS Safari doesn't serve a stale cached JSON body alongside a fresh HTML page.

---

## Self-Host / Deploy

Since divid3 is a single HTML file + static assets, you can deploy it anywhere:

1. Fork this repository.
2. Connect it to [Cloudflare Pages](https://pages.cloudflare.com/) (or any static host).
3. Done — no build step required.

---

## Contributing

For a deep dive into the architecture, iOS-specific resilience patterns, and development conventions, see [`AGENTS.md`](./AGENTS.md).

---

## License

AGPL-3.0. Model weights are Apache 2.0.
