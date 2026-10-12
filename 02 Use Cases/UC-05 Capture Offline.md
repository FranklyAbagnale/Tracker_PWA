---
tags: [usecase]
id: UC-05
actor: Field user
priority: S
status: draft
---

# UC-05 — Capture Offline

## Goal
Record a plate with no connectivity, without losing the capture.

## Main flow
1. User completes UC-02 steps 1-6.
2. Write attempt fails with a network error.
3. App serialises the record plus a client-generated UUID and enqueuedAt
   into the local outbox (IndexedDB).
4. App applies the change optimistically to the local index and marks the
   entry pending: true.
5. App shows a non-blocking banner: "Saved locally, will sync."
6. On reconnect or app foreground, app flushes the outbox in FIFO order.

## Flush behaviour
- On success, entry removed from outbox, pending cleared.
- On 409, app re-fetches, re-applies changes, retries once.
- On repeated failure, entry stays queued and surfaces in a Pending uploads
  list with manual retry.

## Photos offline
Photos held as blobs in IndexedDB and uploaded on flush, before the record
that references them. If a photo upload fails, the record is still committed
with the photo path omitted, and the photo is retried separately.

## Acceptance criteria
- [ ] Airplane-mode capture survives an app restart.
- [ ] Pending indicator is visible on the affected plate.
- [ ] Flush on reconnect completes without user action.
- [ ] Repeated failure never discards queued data.
