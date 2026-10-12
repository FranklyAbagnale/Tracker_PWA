---
tags: [testing, checklist]
---

# Manual Test Checklist

Run before each phase release. Real iPhone and real Android. Simulators lie
about camera, GPS, and storage pressure.

## Install and launch
- [ ] Opens in Safari (iOS) without errors
- [ ] Add to Home Screen produces a working icon
- [ ] Launches without browser chrome

## Lookup
- [ ] Known plate returns the full card
- [ ] Unknown plate offers a create path
- [ ] ab-123 cd resolves to AB123CD

## Capture
- [ ] Notes field does not zoom the viewport on iOS focus
- [ ] Camera opens directly with the camera button
- [ ] Photo downscales to under 500 KB
- [ ] Re-saving preserves firstSeen

## Offline
- [ ] Airplane mode, app still opens
- [ ] Capture offline, pending indicator appears
- [ ] Restart app while offline, pending capture survives
- [ ] Reconnect, capture flushes automatically

## Conflict
- [ ] Two devices, different plates, simultaneous saves, both succeed
- [ ] Two devices, same plate, second merges, no data loss
