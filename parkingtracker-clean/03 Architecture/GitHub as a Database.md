---
tags: [architecture, github]
---

# GitHub as a Database

## Read path
- Static reads: https://<user>.github.io/<repo>/data/...
  Served by GitHub Pages CDN over HTTPS, no auth, no rate limit concerns.
- Raw reads: https://raw.githubusercontent.com/<user>/<repo>/main/data/...
  Cached ~5 min at the CDN edge.

Prefer Pages URLs. Faster, cached, unaffected by API limits.

## Write path
Writing a file requires three steps:
1. GET /repos/{owner}/{repo}/contents/{path} returns sha and base64 content.
2. Modify content locally.
3. PUT /repos/{owner}/{repo}/contents/{path} with message, content, sha.

If sha is stale, PUT fails with 409 Conflict. That is the concurrency
mechanism, and the whole reason for the file-per-record design.

## Rate limits
- Authenticated: 5,000 requests/hour.
- Unauthenticated: 60 requests/hour (do not rely on this for writes).
- One field capture costs 2 requests (GET + PUT); 3 if a retry is needed.
- 5,000/hour supports roughly 1,600 captures per hour.

## What would force a change
- Sustained write volume above a few thousand per hour.
- Multi-tenant use with untrusted writers.
- Query needs the index cannot answer.
- Repo size above ~1 GB (photos).
- Any requirement for sub-200 ms write acknowledgement.

If two or more appear, move to a real backend and keep Git as an export
target rather than the store.
