# Security Policy

divid3 runs entirely in the browser: no server, no accounts, no query logs. Its attack surface is the static site at divid3.com, the routing code in `index.html`, and this repository's supply chain.

## Reporting a vulnerability

**Please don't open a public issue.** Report privately through [GitHub Security Advisories](https://github.com/bradflaugher/divid3/security/advisories/new). Include:

- what an attacker can do and the URL or input that triggers it,
- the browser and OS you reproduced on.

You'll get an acknowledgement within a few days. Fixes ship as soon as they're ready, because every push to `main` deploys.

## In scope

- XSS or script injection via the query, `?q=`, bangs, pasted text, or `search-config.json`.
- Redirects to a destination the user didn't confirm (for example via `?q=`).
- Anything that sends the user's query somewhere other than the engine they chose.
- Clickjacking, header misconfiguration, or cache poisoning on divid3.com.
- Supply-chain issues in the CI workflows or pinned dependencies.

## Out of scope

- What the destination search engines do with a query once you've been routed there.
- Self-hosted forks with modified configuration.

## Safeguards already in place

- Queries are classified on-device. The model and embeddings are served same-origin, and remote model fetches are disabled.
- `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`, HSTS and `nosniff` on every response (see `_headers`).
- Every GitHub Action is pinned to a commit SHA and runs with least-privilege tokens. Dependabot, CodeQL, Dependency Review and OpenSSF Scorecard run continuously.
