---
tags: [roadmap, phase]
status: not-started
---

# Phase 1 — MVP

Goal: a working capture and lookup flow against real data.

## Deliverables
- [ ] data/plates/ populated via UC-07 Bulk Import and Migration
- [ ] schema/plate.schema.json written and enforced
- [ ] scripts/build_index.py working
- [ ] scripts/validate_records.py working
- [ ] web/index.html with plate field, status selector, notes field
- [ ] web/js/github.js with GET/PUT and one-shot 409 retry
- [ ] web/js/app.js wiring lookup and save
- [ ] Result card rendering: plate, flag, color, make, model, notes, photo, updated
- [ ] Deployed to GitHub Pages
- [ ] Tested on one real iPhone and one real Android

## Exit criteria
- A plate can be looked up in under 2 s on 4G.
- A plate can be captured and saved from a phone.
- Concurrent edits to different plates never conflict (verify with two
  devices).
- validate_records.py passes on the full dataset.

## Explicitly out of scope
Offline, photos, location, flags, nearby, PWA install, proxy.

## Related
- Phase 2 - Offline and Nearby
- Manual Test Checklist
