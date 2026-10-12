---
tags: [code, moc]
---

# Code Index

## Web app (deployed to GitHub Pages)

| File | Purpose |
|---|---|
| web/index.html | App shell and markup |
| web/manifest.json | PWA manifest |
| web/service-worker.js | Caching and offline |
| web/css/style.css | Mobile-first styles |
| web/js/app.js | Controller, wiring, event handling |
| web/js/ui.js | Rendering functions |
| web/js/github.js | GitHub API read/write, retry logic |
| web/js/geo.js | Geolocation and Haversine |
| web/js/store.js | Index cache, outbox, IndexedDB |

## Data

| File | Purpose |
|---|---|
| data/index.json | Derived projection (generated) |
| data/plates/ | Record directory |
| schema/plate.schema.json | JSON Schema for validation |

## Local tooling (never runs in CI)

| File | Purpose |
|---|---|
| scripts/build_index.py | Regenerate data/index.json |
| scripts/validate_records.py | Validate records against schema |
| scripts/push_changes.py | Diff-aware selective commit and push |
| scripts/migrate_xml_to_json.py | One-time XML to JSON migration |

## CI (pull_request only, zero cost on direct pushes)

| File | Purpose |
|---|---|
| .github/workflows/validate.yml | Schema validation gate |

## Conventions
- Vanilla JS, no framework, no build step. Modules via script type=module.
- All network calls wrapped in a single function per concern.
- No innerHTML with user data. Use textContent or a sanitising helper.
- Every user-visible string that could contain a plate or note is escaped.

## Related
- Repository Layout
- Test Plan
