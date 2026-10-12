---
tags: [adr]
status: proposed
date: 2026-10-10
---

# ADR-009 — Hosting and Automation Changes

## Status
Proposed. These changes were made while completing v1.0; confirm or revert.

## Context
The implementation diverged from earlier ADRs in three places:

1. **ADR-005** said "no scheduled workflows, one validation workflow on
   pull_request only". The app commits straight to `main`, so a PR-only gate
   never sees field writes, and `data/index.json` goes stale after every save.
2. **ADR-007** chose full-precision location (Option 3). The repository is
   public, and ADR-007 itself recommends Option 2 (coarsen at write time) in
   that case.
3. **ADR-008** (photos as files) was not implemented; photos were embedded as
   base64.

## Decision
1. Keep Actions usage independent of user count. No workflow runs on data or
   photo pushes. The client updates `data/index.json` itself (merge by
   vehicleKey, newest `lastSeen` wins, up to 4 attempts). `validate.yml` runs
   on pull requests and manually; `pages.yml` runs when `web/` changes. All
   jobs have timeouts and concurrency. `tests/test_workflows.py` enforces
   this. See `07 Operations/Actions Budget.md`.
2. Coarsen locations to 3 decimal places at write time while the repo is
   public (`COARSEN_DECIMALS` in `web/js/config.js`). Set to `null` for full
   precision once the repo is private.
3. Implement ADR-008: photos are uploaded to `photos/` before the record that
   references them; records store relative paths only.

## Consequences
- Search stays fresh without operator discipline or Actions minutes.
- Direct pushes from the app are not validated by CI; run `npm run validate`
  locally after test sessions. The index can drift if an item fails between
  the vehicle write and the index write; the retry fixes it, and
  `build_index.py` repairs it.
- Each save adds one more write (the index), which counts against the shared
  token's secondary rate limit.
- Proximity queries are accurate to roughly 110 m.

## Revisit triggers
- Repository visibility change (all three decisions).
- Any need for CI on field writes (would need a budget and a batching design).

## Related
- ADR-005, ADR-007, ADR-008
