---
tags: [testing]
---

# Test Plan

## Scope
The app is small; the test surface is mostly about data integrity and mobile
platform quirks. Manual testing on real devices carries most of the weight.
Automated tests cover the scripts.

## Layers

| Layer | What | Tooling |
|---|---|---|
| Schema | Every record validates | validate_records.py in CI on PR |
| Script unit | Normalisation, merge, index build | pytest locally |
| Client unit | Haversine, normalisation, merge | Plain JS assertions, run in Node |
| Integration | GET/PUT round trip | Manual or scripted harness |
| Manual device | Real iPhone, real Android | Manual Test Checklist |
| Adversarial | Bad input, offline, conflicts | See below |

## Adversarial cases worth writing down
1. Two devices save the same plate within 1 second.
2. Save while offline, restart app, then reconnect.
3. Save with location permission denied.
4. Save with location permission granted but GPS unavailable indoors.
5. Photo capture on a 12 MP camera, verify downscale.
6. Input ab-123 cd must resolve to AB123CD.
7. Input with emoji or non-Latin characters must not create a bad filename.
8. index.json deleted from cache, app must recover on next fetch.
9. GitHub API returns 500, user sees a retry, not a silent failure.
10. Token revoked mid-session, user sees a clear re-auth prompt.
11. Very long notes (2000+ chars), truncation or rejection, not corruption.
12. 50 rapid saves, rate limit not exceeded, no lost writes.

## Coverage targets
- Scripts: high. These are where silent data corruption would originate.
- Client: moderate. Cover pure functions; do not chase UI coverage.
- Integration: the critical paths only.

## What we deliberately do not test
Cross-browser beyond Safari and Chrome. No automated UI tests — the manual
checklist is faster to maintain at this scale.

## Related
- Manual Test Checklist
- Known Failure Modes
