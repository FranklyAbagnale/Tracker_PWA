---
tags: [testing, risks]
---

# Known Failure Modes

Failure modes observed or anticipated, with mitigations. Add to this as
things actually break. This is the most valuable document in the vault over
time.

| # | Mode | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Stale SHA on same-plate concurrent write | Low | Medium | One-shot retry with field merge |
| 2 | Offline capture lost on app restart | Medium | High | IndexedDB outbox, never discard |
| 3 | iOS evicts IndexedDB under storage pressure | Medium | High | Treat outbox as queue; flush eagerly |
| 4 | Photo uploaded but record write fails | Low | Low | Orphan reconciliation script |
| 5 | Record references a missing photo | Low | Low | Graceful degradation in UI |
| 6 | Token leaked from a device | Low | High | Short expiry, per-user tokens, proxy |
| 7 | index.json drifts from records | Medium | Medium | Regenerate on every sync; validate in CI |
| 8 | Plate with non-A-Z0-9 chars creates bad filename | Low | Medium | Strict normalisation + validation |
| 9 | Service worker serves a stale shell after deploy | Medium | Medium | Versioned cache name; skipWaiting |
| 10 | Rate limit hit during a burst of saves | Low | Medium | Sequential flush, backoff |
| 11 | Notes clobbered by a merge | Low | High | Append-only notes with attribution |
| 12 | Bulk import writes 1,000 commits instead of 1 | Medium | Low | Diff-aware staging in push_changes.py |
| 13 | GPS accuracy worse than the search radius | Medium | Medium | Display accuracy; warn when it exceeds radius |
| 14 | Repo exceeds 1 GB from photos | Low | Medium | Size budget check monthly; object storage |
| 15 | iOS PWA loses state on OS update | Low | Low | Repo is the store; local state is disposable |

## Post-incident template

When a mode actually occurs, add a note here:

YYYY-MM-DD — Mode #n
What happened:
Blast radius:
Root cause:
Fix applied:
Prevention added:

## Related
- Test Plan
- Runbook - Resolve Write Conflict
