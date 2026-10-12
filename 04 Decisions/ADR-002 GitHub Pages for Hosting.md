---
tags: [adr]
status: accepted
date: 2026-10-09
---

# ADR-002 — GitHub Pages for Hosting

## Context
The app needs static hosting over HTTPS with a stable URL. Geolocation
requires a secure context. The audience is small, the traffic modest.

## Options considered

### Option 1 — GitHub Pages
Free, HTTPS by default, deploys on push to main, serves from the same
repository that holds the data. No configuration, no separate account.

### Option 2 — Netlify / Vercel / Cloudflare Pages
Better build pipeline, preview deploys, edge functions, response headers.
Requires a second account and a second deploy target to keep in sync.

### Option 3 — Self-hosted
Full control. Full maintenance burden. Not justified.

## Decision
Host on GitHub Pages from the main branch of the data repository.

## Rationale
Co-locating app and data in one repository means one push updates both, and
relative paths work without configuration. The lack of response headers is a
real cost but a meta CSP is an acceptable substitute at this risk level.

## Consequences

Positive:
- Zero cost, zero configuration, HTTPS for free.
- One repository, one deploy, one history.
- Data and app versions are always consistent.

Negative:
- Cannot set HTTP response headers. No HSTS, no header-based CSP, no
  X-Frame-Options.
- CDN caching not finely controllable. Cache-bust with query strings.
- 1 GB repository soft limit, 100 GB/month bandwidth soft limit.

## Revisit triggers
- Need for server-side logic (which would also resolve ADR-006).
- Repo size approaching 1 GB.
- A security requirement that demands response headers.

## Related
- Repository Layout
- Authentication and Secrets
