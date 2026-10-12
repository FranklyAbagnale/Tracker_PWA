---
tags: [usecase]
id: UC-01
actor: Field user
status: draft
---

# UC-01 — Look Up a Plate

## Goal
Determine whether a plate is already known and see everything about it.

## Main flow
1. User types a plate string.
2. App normalises: uppercase, strip non-alphanumerics.
3. If length >= 3, debounce 250 ms then resolve.
4. App checks the in-memory index for the normalised plate.
5. Hit: app fetches data/plates/<PLATE>.json.
6. App renders the result card.

## Alternate flows
- A1 Not found: show "No record for ABC1234" with a Create button.
- A2 Offline: show cached record with a stale-data banner.
- A3 Fetch failure: fall back to index data only.

## Acceptance criteria
- [ ] Known plate returns in < 2 s on 4G.
- [ ] Input ab-123 cd resolves to AB123CD.
- [ ] Input ab123 shows AB123CD, 1AB123FR, 2REAB123 (at least 3 consecutive needed)
- [ ] Unknown plate offers a create path.
- [ ] Flag is prominent when not none.
- [ ] No write is issued.
