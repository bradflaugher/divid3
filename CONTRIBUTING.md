# Contributing to divid3

Thanks for helping! divid3 is deliberately small: one HTML file, no build step, no runtime dependencies. Contributions should keep it that way.

## Setup

```bash
npm ci                                   # Playwright, ESLint, TypeScript, serve
npx playwright install --with-deps       # browsers for the E2E suite
pip install -r scripts/requirements.txt -r scripts/requirements-dev.txt
npm run serve                            # http://localhost:3000
```

Node's version is pinned in `.nvmrc` (`nvm use`).

## Before you open a PR

```bash
npm run lint        # ESLint + TypeScript + Ruff + config validator
npm run test:unit   # routing unit tests + accuracy floors
npm test            # Playwright E2E on Chromium, Firefox, WebKit, mobile Safari
```

CI runs all of these, plus CodeQL and Dependency Review.

## Read AGENTS.md first

[`AGENTS.md`](AGENTS.md) is the maintainer guide. It explains the iOS-reliability constraints (single-threaded WASM, no live inference on mobile, the crash-loop guard), the `EMBEDDINGS_VERSION` bump rule, and other gotchas. Several things that look like bugs are deliberate.

Common changes:

- **Routing phrases, engines, bangs, keywords:** edit `scripts/search_phrases.json`, run `python3 scripts/generate_search_embeddings.py`, bump `EMBEDDINGS_VERSION` in `index.html`, and add cases to `tests/unit/test_routing.py`.
- **UI or routing logic:** add or adjust a Playwright test that asserts on `data-*` attributes, not visible text.

## Security

Report vulnerabilities privately; see [SECURITY.md](SECURITY.md).
