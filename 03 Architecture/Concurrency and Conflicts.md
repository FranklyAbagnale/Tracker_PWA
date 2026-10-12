---
tags: [architecture, concurrency]
---

# Concurrency and Conflicts

## Where conflicts come from
The GitHub contents API is optimistic-concurrency by SHA. A PUT carrying a
sha that no longer matches the current file fails with 409 Conflict. That
single fact drives the whole storage design.

## Why per-record files solve most of it
With one file per plate, two users editing different plates touch different
files. No shared SHA, no conflict. The residual case is two users editing
the same plate within the same window. Rare, but it must not lose data.

## Handling the residual case
Field-level merge. When a 409 occurs:
1. Re-GET the file for fresh content and current SHA.
2. Merge field by field:
   - notes: append the new text with timestamp and attribution.
   - status, flag: incoming wins (user just observed it).
   - photo: incoming wins if present; otherwise keep existing.
   - location, updated, updatedBy: incoming wins.
   - firstSeen: always keep the existing (earlier) value.
3. PUT the merged record with the fresh SHA.
4. If the retry also returns 409, stop. Queue for manual resolution.

Cap retries at one. Infinite retry loops against a shared resource are how
you get banned.

## Notes as append-only
Because notes are the field most likely to be clobbered, treat them as
append-only from the app's perspective:

~~~
2026-09-14T09:12Z (jdoe): Silver sedan, rear bumper damage.
2026-10-09T14:30Z (asmith): Moved to row 4, still parked.
~~~

The app appends; only the data owner edits history by hand.

## What we do not attempt
- No operational transforms, no CRDTs, no vector clocks.
- No locking. Git has no locks.
