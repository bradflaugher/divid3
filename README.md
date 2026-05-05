# divid3

A private, on-device search router. **divid3** intelligently routes your queries to the best destination without tracking.

[**Try it at divid3.com**](https://divid3.com)

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
| `!d` | DuckDuckGo | `!hn` | Hacker News |
| `!yt`| YouTube | `!w` | Wolfram Alpha|
| `!m` | Google Maps | `!wc`| Wirecutter |
| `!i` | Bing Images | `!p` | Perplexity |
| `!g` | Grok | `!yt`| YouTube |

### Semantic Routing (Auto)
For everything else, the model decides based on context:
- *"lofi beats"* → **YouTube**
- *"useEffect cleanup"* → **Hacker News**
- *"best USB-C cables"* → **Wirecutter**

*The scores panel in the bottom-left shows candidate scores; every chip is clickable to override the model's choice.*

---

## Getting Started

Set divid3 as your default search engine: `https://divid3.com/?q=%s`

Detailed instructions for Chrome, Firefox, Safari, and Android are available at [**divid3.com/setup.html**](https://divid3.com/setup.html).

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
- **Crash-loop guard:** Automatically enters "lite mode" if model load fails.
- **Memory management:** Disposes model on tab hide; periodic pipeline recycling.

---

## Development

```bash
npm ci
npx serve -l 3000 .
# Open http://localhost:3000
```

### Testing
70+ Playwright specs across Chromium, Firefox, WebKit, and Mobile Safari.
```bash
npm test
```

### Updating Embeddings
Hand-curated phrases live in `scripts/search_phrases.json`.
```bash
# Regenerate search-embeddings.json
python3 scripts/generate_search_embeddings.py
```

---

## License
AGPL-3.0. Model weights are Apache 2.0.
