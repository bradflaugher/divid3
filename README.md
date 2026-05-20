# divid3

**Private, on-device search routing.**

divid3 is a meta-search engine that lives entirely in your browser. It uses local machine learning to understand your intent and route your queries to the best destination—without tracking, server logs, or middlemen.

[**Try it at divid3.com**](https://divid3.com)

---

## ⚡ Key Features

- **Private by Design**: No queries ever leave your device for classification. All routing logic happens in your browser's memory.
- **Semantic Intent**: Uses a 22MB `all-MiniLM-L6-v2` model to intelligently route queries like "best pizza nearby" to Maps, or "rust result type" to tech discussions.
- **Instant Bangs**: DuckDuckGo-style shortcuts (e.g., `!yt`, `!gh`, `!m`) for when you know exactly where you want to go.
- **Rule-Based Routing**: Detects domains and localhost patterns automatically.
- **Low Memory Fallback**: Automatically switches to a lightweight keyword-based router on low-memory devices or if the model fails to load.
- **No Build Step**: Pure HTML/CSS/JS. Easy to audit, easy to self-host.

---

## 🛠 How it Works

divid3 uses a multi-layered classification strategy:

1.  **Bangs**: Synchronous regex matching for explicit shortcuts (e.g., `!yt` for YouTube).
2.  **Explicit Rules**: Detects bare domains (`github.com`) or specific environments (`localhost:3000`).
3.  **Semantic Routing**: A locally running Transformers.js model embeds your query and compares it against pre-computed vectors of hundreds of common intents.
4.  **Top-Choice Routing**: The model picks the most likely destination based on semantic similarity. DuckDuckGo serves as the natural general-purpose fallback when no specific engine intent is detected.

---

## 🚀 Getting Started

### Set as Default Search Engine

Add the following URL as a custom search engine in your browser:
```text
https://divid3.com/?q=%s
```

Detailed setup instructions for Chrome, Firefox, Safari, and Arc are available at [divid3.com/setup.html](https://divid3.com/setup.html).

### Keyboard Shortcuts

- `/`: Focus search input
- `Esc`: Cancel pending redirect
- `T`: Toggle light/dark theme
- `?`: Show help overlay

---

## 💻 Development

divid3 is built with vanilla web technologies and requires no build step.

```bash
# Install development dependencies (Playwright, serve)
npm ci

# Start the local development server
npm run serve

# Run the full end-to-end test suite
npm test

# Regenerate semantic embeddings from scripts/search_phrases.json
python3 scripts/generate_search_embeddings.py
```

### Adding New Routes

1.  Edit `index.html` to add the engine to the `engines` object.
2.  Add example phrases to `scripts/search_phrases.json`.
3.  Run the embedding generation script.
4.  Bump `EMBEDDINGS_VERSION` in `index.html`.

---

## 📜 License

Code is licensed under **AGPL-3.0**. The embedded model weights are **Apache 2.0**.
