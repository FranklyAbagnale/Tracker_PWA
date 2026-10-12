---
tags: [roadmap, phase]
status: not-started
---

# Phase 2 — Offline and Nearby

Goal: the app works in a parking garage with no signal and tells you what you
already logged or searched here.

## Deliverables
- [ ] manifest.json and service-worker.js
- [ ] Home screen install verified on iOS and Android
- [ ] web/js/store.js — IndexedDB outbox and index cache
- [ ] Offline capture per UC-05 Capture Offline
- [ ] Flush on reconnect, verified across app restart
- [ ] Pending-upload indicator in the UI
- [ ] web/js/geo.js — geolocation and Haversine
- [ ] Location captured on save, consent-gated
- [ ] UC-04 Find Nearby Plates with bounding-box pre-filter
- [ ] photo field with client-side downscale
- [ ] flag field per UC-03 Flag a Plate

## Exit criteria
- Airplane-mode capture survives app restart and syncs on reconnect.
- Nearby query returns in under 3 s with a warm index.
- Photos are under 500 KB after downscale.
- Denying location permission does not degrade any other feature.

## Risks
- iOS IndexedDB eviction under storage pressure. Test with a nearly-full
  device.
- Service worker update races producing a stale shell. Version the cache
  name.

## Related
- Phase 3 - Hardening
- PWA and Offline
