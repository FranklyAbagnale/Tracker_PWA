# api/ — plate lookup proxy (optional)

A small proxy that turns a California plate into **year, make and model** for the app's "Look up details" button. It is **off by default**: the app works fully without it.

Why a proxy: a lookup provider's API key must never be in the phone app. The app sends the plate and the user's GitHub token to this proxy; the proxy checks the token can write to this repository, asks the provider, and returns only year, make and model. VINs, owner data and anything else the provider sends are dropped here. Answers are cached (found: 30 days, not found: 1 day) so repeats cost nothing.

| File | Purpose |
|---|---|
| `lookup.js` | The request handler (`handleLookup`), written with standard Request/Response so it runs anywhere |
| `worker.js` | Cloudflare Worker entry point |
| `serve-node.mjs` | Same handler as a plain Node service for an internal host |
| `providers/` | Adapters: `stub.js` (answers "not configured", the default), `mock.js` (tests), `index.js` (register a real adapter here) |
| `errors.js` | Error types shared by the handler and adapters |
| `wrangler.toml` | Cloudflare settings: repo name, allowed states, daily limit. The provider key is a secret (`npx wrangler secret put PROVIDER_KEY`), never a setting |

Tests: `npm test` (`tests/lookup.test.mjs`) and `python3 tests/e2e_lookup.py`.

If the repository is renamed or split into app and data repositories, update `REPO_OWNER` / `REPO_NAME` in `wrangler.toml` to the repository whose write access should authorise lookups.

More: `07 Operations/Runbook - Plate Lookup.md`, `04 Decisions/ADR-010 Plate Lookup via Proxy.md`.
