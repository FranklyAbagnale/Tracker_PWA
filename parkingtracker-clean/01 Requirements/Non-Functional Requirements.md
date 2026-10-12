---
tags: [requirements, nonfunctional]
---

# Non-Functional Requirements

## Performance
- NFR-01 Single-plate lookup < 2 s on 4G.
- NFR-02 Nearby-plates query < 3 s using the cached index.
- NFR-03 Cold load (cached) < 1 s; cold load (uncached) < 4 s.
- NFR-04 No single fetched file exceeds 100 KB.

## Reliability
- NFR-05 Captures made offline are never silently dropped.
- NFR-06 A failed write is surfaced with a retry path.
- NFR-07 Concurrent edits to different plates never conflict.
- NFR-08 Concurrent edits to the same plate resolve without data loss.

## Cost
- NFR-09 Zero GitHub Actions minutes in a normal operating week.
- NFR-10 Zero recurring hosting cost.
- NFR-11 GitHub API usage stays under 10% of the hourly rate limit.

## Security and privacy
- NFR-12 No long-lived write credential embedded in served client code.
- NFR-13 Location data recorded only with explicit user consent.
- NFR-14 Location precision coarsened in shared or exported views.
- NFR-15 All traffic over HTTPS.

## Usability
- NFR-16 Core capture flow reachable within one tap of app open.
- NFR-17 Primary controls >= 44x44 px.
- NFR-18 Usable one-handed on a 5.4 inch screen.
- NFR-19 Installs to home screen, launches without browser chrome.

## Maintainability
- NFR-20 No build step required to deploy.
- NFR-21 Data format documented well enough to hand-edit confidently.
