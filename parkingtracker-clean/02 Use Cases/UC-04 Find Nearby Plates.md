---
tags: [usecase]
id: UC-04
actor: Field user
priority: S
status: draft
---

# UC-04 — Find Nearby Plates

## Goal
See which plates have already been logged in the user's current area.

## Main flow
1. App requests current position with enableHighAccuracy: true.
2. Browser returns lat, lng, accuracy.
3. App loads the cached index, fetching fresh if older than a threshold.
4. App filters to a bounding box, then applies Haversine within radius
   (default 1000 m).
5. App sorts ascending by distance.
6. App renders the list: plate, flag, distance, last updated.
7. Tapping a row opens the full result card from UC-01.

## Alternate flows

A1 Location denied. App shows an explanation and offers a manual "search
this area" fallback.

A2 Empty result. No plates within radius. Show empty state with a Widen
radius control and a Capture here button.

A3 Stale index. Cached index older than 24 h. Fetch fresh in the background
and re-run the filter when it arrives.

A4 Dense area. More than 100 matches. Group by flag first, then sort by
distance, paginate at 25 rows.

## Acceptance criteria
- [ ] Query completes in < 3 s with a warm index.
- [ ] Distance shown is accurate to within the GPS accuracy figure.
- [ ] Denying location does not break the app.
- [ ] Flagged plates sort to the top of their distance band.
