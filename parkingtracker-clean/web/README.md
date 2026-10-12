# web/ — the app (PWA)

What GitHub Pages publishes: a vanilla JavaScript progressive web app (ES modules, no framework, no build step). Pushing a change here is the only thing that triggers the Pages deploy workflow.

| Path | Purpose |
|---|---|
| `index.html` | Page shell, Content-Security-Policy, the always-visible **Take photo** bar |
| `js/app.js` | Screens, rendering and event handling |
| `js/config.js` | Repository, limits, state list, enums (keep in step with `schema/`) |
| `js/github.js` | GitHub contents API client (read, write, conflict retry) |
| `js/storage.js`, `sync-manager.js` | On-device cache and outbox; uploads when online |
| `js/vehicle-manager.js`, `plate-manager.js`, `photo-manager.js` | Records, plates and photo capture/resize |
| `js/index-manager.js`, `local-manager.js`, `geo.js`, `matching.js` | Search index, nearby ranking, distances, fuzzy plate matching |
| `js/lookup.js` | Optional plate lookup through `../api/` |
| `js/permissions.js`, `state.js`, `ui.js` | Location/camera permissions, view state, small UI helpers |
| `css/style.css`, `icons/`, `manifest.json` | Styling, icons, install manifest |
| `service-worker.js` | Offline app shell. **Bump `CACHE_NAME` whenever any file listed in it changes**, or phones keep the old app |

Run locally: `npm run serve` (http://localhost:8080). Tests: `npm test`, `npm run test:e2e`. Deployment and token setup: root `README.md` and `07 Operations/Deployment Guide.md`.
