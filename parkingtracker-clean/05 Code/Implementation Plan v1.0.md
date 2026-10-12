---
tags: [implementation, plan]
status: active
date: 2026-10-10
---

# v1.0 Implementation Plan

> **Status update (2026-10-10):** Phases 1-10 are implemented in code and
> covered by unit tests plus a browser smoke test (`tests/e2e_smoke.py`). The
> per-phase "Approval needed" gates were collapsed into three milestones.
> Remaining: Phase 11 (real iPhone + Android testing, `07 Operations/Deployment
> Guide.md` written), and the open decisions in `01 Requirements/Open Questions.md`.
> Deviations from earlier ADRs are recorded in ADR-009.

## Overview
Build a minimal, working PWA for neighborhood watch vehicle tracking with:
- Photo-first capture flow
- Vehicle as the primary record (plate is optional alias)
- Local area search with manual coordinates fallback
- GitHub-backed storage and sync
- Offline-capable with IndexedDB queue

## Implementation Phases

### Phase 1: App Shell & Navigation (DONE)
- [x] Home screen with 4 actions: Photo, Plate, Vehicle, Local
- [x] Photo capture screen with accept/retake/save-to-device
- [x] Plate lookup and update screen
- [x] Vehicle capture form
- [x] Local results screen
- [x] Base CSS styling
- [x] Service worker for offline shell

**Status**: Complete. App shell and UX flows are in place.

---

### Phase 2: Data Model & Schema (IN PROGRESS)
**Deliverables**:
- [ ] JSON schemas for vehicle and plate records
- [ ] Sample vehicle record with sighting structure
- [ ] Sample plate record
- [ ] Local storage helpers (IndexedDB for outbox + cache)
- [ ] GitHub API helper for reads/writes

**Files to create/update**:
1. `schema/vehicle.schema.json` — canonical vehicle schema
2. `schema/plate.schema.json` — canonical plate schema
3. `schema/sighting.schema.json` — sighting sub-schema
4. `web/js/storage.js` — IndexedDB helpers for outbox and cache
5. `web/js/github.js` — GitHub REST API wrappers
6. `data/samples/vehicle-example.json` — example record for testing
7. `data/samples/plate-example.json` — example record for testing

**Approval needed**: Review the schema files and sample records before moving to Phase 3.

---

### Phase 3: Photo Capture Flow
**Deliverables**:
- [ ] Photo capture → device save → collection in memory
- [ ] Pass photos to Vehicle form
- [ ] Pass photos to existing Plate/Vehicle update flow
- [ ] Photo blob compression and storage

**Files to update**:
1. `web/js/app.js` — wire photo flow to vehicle/plate forms
2. `web/js/photo-manager.js` (new) — handle capture, compression, device save

**Approval needed**: Photo flow integration before moving to Phase 4.

---

### Phase 4: Vehicle Capture & Local Save
**Deliverables**:
- [ ] Vehicle form validation (required: color, make, body style; distinguishing tags optional)
- [ ] Plate optional but supported
- [ ] Generate stable vehicle key (VEH_XXXXX)
- [ ] Create vehicle record locally (IndexedDB outbox)
- [ ] Queue write to GitHub
- [ ] Success/error feedback

**Files to create/update**:
1. `web/js/vehicle-manager.js` (new) — capture, validation, record creation
2. `web/js/app.js` — wire form to vehicle-manager
3. `web/js/storage.js` — add outbox queue methods

**Approval needed**: Vehicle capture flow before moving to Phase 5.

---

### Phase 5: Plate Lookup & Update
**Deliverables**:
- [ ] Plate normalization (uppercase, strip non-alphanumeric)
- [ ] Search for plate in local cache or via GitHub fetch
- [ ] Display existing vehicle record if found
- [ ] Allow user to update fields (NOT plate itself):
  - color, make, bodyStyle, model
  - distinguishing features
  - notes
  - add photos
- [ ] Queue update to GitHub

**Files to create/update**:
1. `web/js/plate-manager.js` (new) — lookup, display, update
2. `web/js/app.js` — wire lookup form and results

**Approval needed**: Plate lookup flow before moving to Phase 6.

---

### Phase 6: Local Search & Ranking
**Deliverables**:
- [ ] Get user location via Geolocation API
- [ ] Fall back to manual lat/long input
- [ ] Load local cache of vehicles (or fetch from GitHub)
- [ ] Filter by radius (default 1000m)
- [ ] Rank by recency and flag:
  - Confirmed/suspected within 48h → top
  - Confirmed/suspected 48h-14d → middle
  - Cleared vehicles → bottom (always visible unless removed)
  - Older than 14d → hidden
- [ ] Display results with distance and time-since-sighting

**Files to create/update**:
1. `web/js/local-manager.js` (new) — geolocation, filtering, ranking
2. `web/js/geo.js` — Haversine distance calculation
3. `web/js/app.js` — wire local screen

**Approval needed**: Local search logic before moving to Phase 7.

---

### Phase 7: GitHub Sync & Conflict Retry
**Deliverables**:
- [ ] Write vehicle record to `data/vehicles/<KEY>.json`
- [ ] Write plate record to `data/plates/<PLATE>.json`
- [ ] Handle 409 Conflict (stale SHA):
  - Re-fetch file
  - Re-apply user changes
  - Retry once
  - Queue for manual retry if fails again
- [ ] Auth via GitHub token (stored in browser localStorage, v1 only)
- [ ] Commit message format: "Add/update vehicle VEH_XXXXX" or "Add/update plate ABC1234"

**Files to create/update**:
1. `web/js/github.js` — PUT with retry logic
2. `web/js/app.js` — flush outbox on reconnect or manual sync

**Approval needed**: GitHub sync flow before moving to Phase 8.

---

### Phase 8: Offline Queue & Sync Status
**Deliverables**:
- [ ] IndexedDB outbox for writes when offline
- [ ] Pending sync indicator on home screen
- [ ] Auto-flush on reconnect
- [ ] Manual retry button for failed writes
- [ ] Local cache of index for offline search

**Files to create/update**:
1. `web/js/storage.js` — IndexedDB helpers
2. `web/js/app.js` — outbox flush and sync status

**Approval needed**: Offline queue before moving to Phase 9.

---

### Phase 9: Data Record Locations
**Deliverables**:
- [ ] `data/vehicles/` — authoritative vehicle records
- [ ] `data/plates/` — plate alias records
- [ ] `data/index.json` — derived projection for fast search (generated by script)
- [ ] `photos/` — uploaded sighting photos
- [ ] Sample records for testing
- [ ] .gitkeep files for empty directories

**Structure**:
```
data/
├── vehicles/
│   ├── .gitkeep
│   └── VEH_7a3f9c2.json
├── plates/
│   ├── .gitkeep
│   └── ABC1234.json
├── index.json (generated)
└── samples/
    ├── vehicle-example.json
    └── plate-example.json

photos/
├── .gitkeep
└── VEH_7a3f9c2_20261115_001.jpg
```

**Approval needed**: Record location structure before moving to Phase 10.

---

### Phase 10: Index & Validation Scripts
**Deliverables**:
- [ ] `scripts/build_index.py` — regenerate `data/index.json` from vehicle records
- [ ] `scripts/validate_records.py` — validate all records against schema
- [ ] GitHub Actions CI gate on pull requests (schema validation)
- [ ] Local development: `npm run build-index` and `npm run validate`

**Files to create**:
1. `scripts/build_index.py`
2. `scripts/validate_records.py`
3. `.github/workflows/validate.yml` (CI)
4. `package.json` (if using npm scripts)

**Approval needed**: Build and validation tooling before moving to Phase 11.

---

### Phase 11: v1.0 Testing & Documentation
**Deliverables**:
- [ ] Manual test checklist (photo capture, vehicle save, plate lookup, local search)
- [ ] Tested on one real iPhone and one real Android
- [ ] README with setup, usage, and GitHub token setup
- [ ] Sample data for quick testing
- [ ] Deployment guide for GitHub Pages

**Files to create/update**:
1. `README.md` — setup and usage
2. `09 Testing/Manual Test Checklist.md`
3. `07 Operations/Deployment Guide.md`

**Approval needed**: Documentation and test results before v1.0 release.

---

## GitHub Token Setup (v1.0)

**Current approach**: User provides a personal access token (PAT) in the app settings.
- Token stored in browser localStorage (v1 only; Phase 3 will replace with proxy)
- Scopes required: `repo` (read/write to ParkingTracker repo only)
- Revocable and user-controlled

**Future (Phase 3 - Hardening)**: Replace with serverless proxy (ADR-006) to keep token off client.

---

## Keeping Records Updated: Data Flow

### Path 1: Add a New Vehicle
1. User taps **Photo** → captures images → continues
2. User taps **Vehicle** → fills form → **Save vehicle**
3. App creates vehicle key and record
4. Record queued in IndexedDB outbox
5. On next sync (auto or manual):
   - Write to `data/vehicles/<KEY>.json`
   - If plate provided, also write to `data/plates/<PLATE>.json`
   - Commit to GitHub
   - Update local cache

### Path 2: Update an Existing Plate
1. User taps **Plate** → enters plate → searches
2. App finds existing vehicle record
3. User edits any field (except plate itself):
   - Color, make, body style, model
   - Distinguishing features
   - Notes
   - Add more photos
4. User taps **Save updates**
5. App appends new sighting + re-fetches file (409 retry) + writes to GitHub

### Path 3: Find Local Vehicles
1. User taps **Local** → app requests GPS
2. App fetches (or uses cached) vehicle index
3. Filters by radius + ranking rules
4. User can tap a result to view full record and edit it

### Keep Records Fresh
- **Automatic**: On app launch, check if local cache is older than 24h; fetch fresh index
- **Manual**: **Refresh** button on Local page
- **Sync**: Pending writes shown on home screen; flush on reconnect or manual tap

---

## Next Steps

**Immediate**:
1. Approve Phase 2 (data model & schema)
2. Create schema files and sample records
3. Move to Phase 3 (photo capture integration)

**Please review and approve** the plan above. Let me know:
- Any phase you want to reorder or skip
- Any concerns about the data flow
- Any questions about GitHub token setup or record storage
- Any specific testing requirements

Once approved, I can proceed phase by phase, with approval checkpoints after each one.
