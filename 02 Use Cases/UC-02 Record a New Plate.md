---
tags: [usecase]
id: UC-02
actor: Field user
priority: M
status: draft
---

# UC-02 — Record a New Plate

## Goal
Create or update a plate record with status, optional photo, notes, location.

## Trigger
User submits the capture form.

## Preconditions
- User has a write credential.
- Network available, or offline queue enabled.

## Main flow
1. User enters or confirms the plate.
2. User sets a flag, takes a photo, adds notes.
3. User taps Save.
4. App requests location; browser prompts if permission undecided.
5. App builds the record and validates it against the schema.
6. App fetches the current file SHA for data/plates/<PLATE>.json.
7. App PUTs to the GitHub contents API with new content and SHA.
8. On success, app updates the local index and confirms with the commit ref.
9. App clears the form and returns to the home state.

## Alternate flows

A1 Photo capture. Photo downscaled client-side to <= 1600 px long edge and
<= 500 KB, then uploaded to photos/. Record stores the returned path.

A2 Location denied. App proceeds without location and does not block save.
A subtle note explains the omission.

A3 Stale SHA (concurrent edit). PUT returns 409. App re-fetches the file,
re-applies the user's changes onto fresh content, and retries once. If the
retry also fails, the write is queued and the user is told.

A4 Offline. Record is written to the local outbox and the index is updated
optimistically with a pending marker.

A5 Record already exists. This becomes an update: existing firstSeen is
preserved, updated is set to now, unspecified fields retain prior values.

## Acceptance criteria
- [ ] Capture flow completes in < 30 s including photo.
- [ ] Save without location still succeeds.
- [ ] Concurrent edit to a different plate never conflicts.
- [ ] Concurrent edit to same plate does not lose either user's notes.
- [ ] Re-saving an existing plate preserves firstSeen.
