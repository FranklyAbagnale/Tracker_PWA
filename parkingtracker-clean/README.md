# ParkingTracker v1.0

A photo-first, neighborhood-watch vehicle tracker built as a PWA. Records live
in this GitHub repository; the app talks to GitHub directly from the phone.

## Features

- **Photo-first capture**: take photos of a vehicle, then add details
- **Vehicle records**: color, make, model, body style, distinguishing features
- **Plate aliases**: standard, dealer, temporary and vanity plates; fuzzy matching suggests near-misses
- **Local search**: vehicles within 1 km, by device GPS or typed coordinates
- **Manual lookup (always on)**: when a plate has no result, buttons open FaxVIN, Carfax, EpicVIN and FindByPlate in a new tab (plate copied); FaxVIN and Carfax can be marked Verified / Not found / Wrong on the vehicle (`siteChecks`), and the optional `year` is entered once one is Verified
- **Plate lookup (optional, off by default)**: year, make and model for California plates through a small proxy in `api/`; looked up only for unlisted plates or vehicles with unknown details, never stores a VIN (`07 Operations/Runbook - Plate Lookup.md`)
- **Local ranking**: by flag (confirmed, suspected, cleared and pigs, unknown), nearest first within a flag
- **Offline support**: every save goes through an on-device queue and uploads when online
- **GitHub-backed**: one JSON file per vehicle and plate, photos as separate files
- **Conflict handling**: a stale-SHA write re-reads, merges and retries once

## Repository map

| Folder | What is in it |
|---|---|
| [`web/`](web/README.md) | The app (PWA) published by GitHub Pages |
| [`data/`](data/README.md) | The records: vehicles, plates, search index |
| [`photos/`](photos/README.md) | Sighting photos |
| [`schema/`](schema/README.md) | JSON Schemas for the records |
| [`tools/`](tools/README.md) | Desktop HTML tools: data editor, XML converter and CSV converter |
| [`scripts/`](scripts/README.md) | Command-line tools: validate, index, import, audit |
| [`api/`](api/README.md) | Optional plate lookup proxy |
| [`tests/`](tests/README.md) | Automated tests |
| [`.github/`](.github/README.md) | Workflows and the Actions-minutes rules |
| `00 Home` to `99 Templates` | Project documentation (an Obsidian vault); start at `00 Home/Project Overview.md` |


## Setup

### 1. Deploy the app (once)

1. Repo **Settings → Pages → Source: GitHub Actions**.
2. Push to `main`. `.github/workflows/pages.yml` publishes `web/` to
   `https://<owner>.github.io/ParkingTracker/`.

See `07 Operations/Deployment Guide.md` for details and local development.

### 2. Create a token

One token, created by the account that **owns the repo** (a fine-grained token
can only reach repos owned by its own account, so collaborators cannot make
their own). For a test group you share this single token; see
`07 Operations/Runbook - Shared Test Token.md` for exact settings, how to hand
it out, and the safeguards.

In short: fine-grained, **only this repository**, **Contents: Read and write**,
nothing else, 30-day expiry.

### 3. Use it

Open the Pages URL on your phone, enter **your name** and the token, and (iOS)
Share -> **Add to Home Screen**. Your name is stamped on every sighting you add,
because with a shared token it is the only record of who wrote what
(`python3 scripts/audit_observers.py`). The app checks that the token can reach
the repo before saving it.

> **Security note.** In v1 the token is stored in the browser (`localStorage`).
> Anyone with the phone can extract it, and the app has no server to rate-limit
> or validate writes. A shared token is acceptable for a short test with trusted
> people; for anything longer build the proxy (ADR-006). See the
> *Public repo warning* below.

## Usage

| Button | What it does |
|---|---|
| **Photo** | Capture (or pick) photos, accept each one, then continue to the vehicle form. Photos are held in memory until you save. |
| **Plate** | Look up a plate. Found: edit and save a new sighting. Not found: see similar plates or create a new vehicle with that plate. |
| **Vehicle** | Enter details manually. If the plate is already on file, a sighting is added instead of a duplicate. |
| **Local** | Find vehicles within 1 km. Tap one to view and update it. |
| **Sync now** | Upload anything waiting in the queue. Also runs on app start and when the connection returns. |

Photos can be added from the Vehicle and Update forms with **Add photos**; what
you have typed is kept while you take them.

## Data layout

```
data/
  vehicles/VEH_xxxxxxxx.json   source of truth
  plates/ABC1234.json          plate -> vehicle pointer
  index.json                   GENERATED search projection (never hand-edit)
  samples/                     examples, validated in CI
photos/
  VEH_xxxxxxxx_20261010T143205_001.jpg
schema/
  vehicle.schema.json  plate.schema.json
```

### Vehicle record

```json
{
  "vehicleKey": "VEH_7a3f9c2b",
  "displayName": "Grey Nissan Pathfinder",
  "color": "grey", "make": "Nissan", "model": "Pathfinder", "bodyStyle": "suv",
  "distinguishing": ["roof rack", "dented rear bumper"],
  "plateAliases": ["ABC1234"],
  "flag": "suspected",
  "sightings": [
    {
      "id": "S_5f6a7b8c",
      "timestamp": "2026-10-10T14:32:00.000Z",
      "location": { "lat": 34.148, "lng": -118.145 },
      "photos": ["photos/VEH_7a3f9c2b_20261010T143200_001.jpg"],
      "flag": "suspected",
      "notes": "Back again, same spot.",
      "source": "field-app"
    }
  ],
  "firstSeen": "2026-10-09T09:15:00.000Z",
  "lastSeen": "2026-10-10T14:32:00.000Z"
}
```

Flags: `unknown`, `suspected`, `confirmed`, `cleared`, `pigs`. `location` is optional
(declining location permission is a valid state). Full examples are in
`data/samples/`.

### Plate record

```json
{ "plate": "ABC1234", "plateType": "standard", "currentVehicleKey": "VEH_7a3f9c2b",
  "firstSeen": "2026-10-09T09:15:00.000Z", "updated": "2026-10-10T14:32:00.000Z" }
```

### Search index

`data/index.json` is an array of compact entries, rebuilt automatically after
every push that touches `data/vehicles/` or `data/plates/`:

```json
[{ "vehicleKey": "VEH_7a3f9c2b", "displayName": "Grey Nissan Pathfinder", "flag": "suspected",
   "lastSeen": "2026-10-10T14:32:00.000Z", "location": { "lat": 34.148, "lng": -118.145 },
   "plateAliases": ["ABC1234"] }]
```

Local search reads only this file, not every vehicle. Records saved on the
current device are overlaid on it, so your own sightings show up immediately
even before the rebuild finishes (usually under a minute).

## Ranking rules

Within the search radius, nearest first inside each tier:

1. **Confirmed** (red)
2. **Suspected** (orange)
3. **Cleared** (green) and **pigs** (blue), mixed together by distance
4. **Unknown** (yellow), always last

Only confirmed vehicles last seen more than 14 days ago are hidden; every other flag stays visible however
old. Lists show 10 vehicles, with a **View more** button for up to 20 more.

The home screen has plate entry on top, a photo button, and the live nearby list below. The menu (☰) has Add vehicle (no photo),
**Tutorial** (`web/tutorial.html`, a screenshot walkthrough), **Glossary** (`web/glossary.html`: states, flags and every abbreviation),
Sync now, Retry failed and Log out.
The **back arrow** left of the location pin returns to the last screen viewed (home, plate search, Local search or a vehicle). It is hidden when the app first opens and after you go back; forms and the camera are not kept, so unsaved entries are never restored.
Vehicles with no stored location cannot be placed and are not listed.

## Keeping records fresh

- **Automatic**: the cached index is refreshed on app start if older than 24 hours
- **Manual**: **Refresh index** on the Local page
- **Sync**: pending uploads show on the home screen; failed or conflicted items have a **Retry failed** button

## Privacy and the public-repo warning

While testing, a red banner on every screen says the data is public
(`BANNER_TEXT` in `web/js/config.js`; set it to `''` once the repo is private).
**Make the repo private before entering real data**, not after: public history is permanent.

If this repository is **public**, every record, photo, timestamp and location
is world-readable, indexed and permanent in git history, and anyone can fork a
copy. Decide deliberately:

- **Keep it public** only if the data is non-sensitive. Locations are rounded to
  4 decimal places (about 11 m) before storage (`COARSEN_DECIMALS` in
  `web/js/config.js`), and "suspected" flags about identifiable vehicles are
  still published.
- **Make it private** if you want full-precision locations (`COARSEN_DECIMALS = null`)
  or to keep flags and photos from the public. Pages for a private repo needs a
  paid GitHub plan; otherwise host `web/` elsewhere.

Location is read only when you save with **Attach my location** ticked, never
in the background, and your position for Local search is never stored.

## Tech stack

- **Frontend**: vanilla JavaScript (ES modules), no framework, no build step
- **Storage**: IndexedDB (outbox + cache), localStorage (token)
- **API**: GitHub REST contents API
- **Hosting**: GitHub Pages (workflow deploy of `web/`)
- **Hardening**: strict Content-Security-Policy, all record text HTML-escaped

## Testing on a phone

`npm run sample-data` creates a deterministic set of fake vehicles that exercises
every ranking tier and edge case. Follow `09 Testing/Phone Test with Sample Data.md`
for the scripted pass and expected results, then `npm run sample-data:clean`.

## Known limitations

- Token lives in the browser (a serverless proxy is the planned fix; ADR-006)
- Camera and offline behaviour are covered by an automated smoke test in
  Chromium but have not yet been run on real iPhone and Android hardware
- A second edit conflict on the same record stops and waits for **Retry failed**
- Photos accumulate in git history; plan a move to object storage if the repo grows large
- No real-time collaborative editing

## Development

```bash
npm run serve        # http://localhost:8080 (localhost counts as a secure context)
npm test             # unit tests (Node 22+, no dependencies)
npm run test:py      # script tests (needs: pip install -r requirements.txt)
npm run validate     # check data/ against the schemas
npm run build-index  # regenerate data/index.json
npm run import-xml -- --in import/export.xml --media-root import --dry-run   # legacy XML -> JSON (see 07 Operations/Runbook - XML Import.md)
python3 scripts/audit_observers.py   # who wrote what (shared-token audit trail)
npm run sample-data  # generate 18 fake vehicles around Pasadena (--center LAT,LNG for elsewhere)
npm run sample-data:clean   # remove them again (only records tagged sample-data)
npm run test:e2e     # browser tests (needs: pip install playwright)
node api/serve-node.mjs   # plate lookup proxy on an internal host (see 07 Operations/Runbook - Plate Lookup.md)
```

CI (`.github/workflows/`): `validate.yml` (schemas + tests; pull requests and
manual only) and `pages.yml` (deploys the app when `web/` changes). Nothing the
app does starts a workflow, so Actions usage does not grow with users; see
`07 Operations/Actions Budget.md`. The app maintains `data/index.json` itself;
`npm run build-index` is an owner repair tool.

## Support

For issues or feature requests, open an issue on this repo.
