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

## 🎨 Customizing & Building Your Own Router

divid3 is fully customizable! You can easily add your own search destinations, define custom bang shortcuts, customize keyword fallback rules, and regenerate the semantic routing index without touching any HTML/JS code. All configurations are centralized in a single file.

### 1. Centralized Configuration Schema
All router behavior is defined in [scripts/search_phrases.json](file:///root/divid3/scripts/search_phrases.json). This file contains four core keys:

- **`engines`**: A dictionary defining the available search destinations.
  ```json
  "engines": {
    "my_engine": {
      "name": "My Custom Search",
      "color": "#8b5cf6",
      "urlTemplate": "https://example.com/?q={q}"
    }
  }
  ```
- **`bangs`**: DuckDuckGo-style shorthand mappings (e.g. `!my` routing directly to `my_engine` bypassing semantic routing).
  ```json
  "bangs": {
    "my": "my_engine"
  }
  ```
- **`keywordRules`**: Fallback routing rules for low-memory devices (like older iOS devices) when the ML model is bypassed.
  ```json
  "keywordRules": [
    {
      "engine": "my_engine",
      "weight": 5,
      "kw": ["custom topic", "my query"]
    }
  ]
  ```
- **`phrases`**: The training corpus mapping intent categories to example search phrases. These are embedded by the local ML model to calculate similarity.
  ```json
  "phrases": [
    {
      "engine": "my_engine",
      "phrases": [
        "search for my custom topic",
        "lookup something on my search engine"
      ]
    }
  ]
  ```

> [!NOTE]
> All search destinations must include a `urlTemplate` where `{q}` is replaced with the search term. For the specialized `direct` engine (which opens domains directly), the `urlTemplate` is simply `{q}`.

---

### 2. Customization Workflow

Follow these simple steps to customize your search router:

#### Step 1: Edit `scripts/search_phrases.json`
Add or modify engines, bangs, keyword rules, and phrases to match your preferred search destinations.

#### Step 2: Regenerate Configuration & Embeddings
Run the Python script to build the L2-normalized embedding vectors (`search-embeddings.json`) and the lightweight UI config file (`search-config.json`):
```bash
python3 scripts/generate_search_embeddings.py
```

> [!TIP]
> Ensure you have the `sentence-transformers` library and dependencies installed for the Python script.

#### Step 3: Bump the Config Version
To prevent browsers (especially iOS Safari) from serving a stale cached configuration, open [index.html](file:///root/divid3/index.html) and increment the `EMBEDDINGS_VERSION` string:
```javascript
const EMBEDDINGS_VERSION = '11'; // Increment this number
```

#### Step 4: Run & Test Locally
Start the development server and run E2E assertions:
```bash
npm run serve
npm test
```

---

## 📜 License

Code is licensed under **AGPL-3.0**. The embedded model weights are **Apache 2.0**.
