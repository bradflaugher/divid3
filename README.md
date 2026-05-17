# divid3

A private, on-device search router. **divid3** intelligently routes your queries to the best destination without tracking.

[**Try it at divid3.com**](https://divid3.com)

---

## The Philosophy

Most search tools act as a middleman, collecting data and showing ads before sending you to your destination. **divid3** is different. It is a client-side router that lives entirely in your browser. It understands your intent locally and sends you directly to the source. No server logs, no analytics, no middleman.

---

## How it Works

divid3 uses a layered approach to determine where your query should go:

1.  **Direct Shortcuts (Bangs):** If you prefix a query with a bang (e.g., `!yt`), it skips the model and routes immediately to that engine.
2.  **Explicit Rules:** Bare domains (like `github.com`) or specific patterns (like `localhost:3000`) are detected via regex and routed directly.
3.  **Semantic Intent:** For everything else, a 22MB `all-MiniLM-L6-v2` model runs locally using Transformers.js to classify your query against a private index of potential destinations.
4.  **Privacy Fallback:** If the model isn't confident, you are routed to a private, general-purpose fallback engine.

---

## Getting Started

Set divid3 as your default search engine using the following template:
`https://divid3.com/?q=%s`

Detailed instructions for all major browsers and platforms are available at [**divid3.com/setup.html**](https://divid3.com/setup.html).

---

## Tech Stack

- **ML Runtime:** `@huggingface/transformers` v3 (WASM/WebGPU).
- **Model:** `all-MiniLM-L6-v2` (q8-quantized).
- **Frontend:** Vanilla HTML/JS/CSS (No build step).
- **Hosting:** Static hosting (Cloudflare Pages).

---

## Development

```bash
# Serve locally
npm run serve

# Run the Playwright test suite
npm test

# Regenerate the semantic index from scripts/search_phrases.json
python3 scripts/generate_search_embeddings.py
```

---

## License

AGPL-3.0. Model weights are Apache 2.0.
