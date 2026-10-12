---
tags: [roadmap, phase]
status: not-started
---

# Phase 3 — Hardening

Goal: safe for users you do not personally know, and safe to leave alone.

## Deliverables
- [ ] Serverless proxy for the write path (ADR-006)
- [ ] Server-side schema validation in the proxy
- [ ] Per-user rate limiting
- [ ] Meta CSP verified and tightened
- [ ] Client-side input escaping audited (no innerHTML with user data)
- [ ] Photo thumbnail generation
- [ ] Orphan reconciliation script
- [ ] Retention policy implemented for location data
- [ ] Backup export: full dataset as a single archive, runnable locally
- [ ] Accessibility pass — contrast, focus order, screen reader labels
- [ ] Error reporting (opt-in, no PII)

## Exit criteria
- No credential in client code or network traffic.
- Lighthouse accessibility >= 95.
- Backup and restore exercised end to end.
- Documented retention policy is enforced by a script, not by discipline.

## Related
- Phase 2 - Offline and Nearby
- ADR-006 Token Storage and Proxy
