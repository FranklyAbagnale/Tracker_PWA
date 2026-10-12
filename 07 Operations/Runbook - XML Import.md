---
tags: [runbook, operations]
---

# Runbook — XML Import

Purpose: convert legacy plate-tracker XML exports into ParkingTracker records.
Runs on your computer and costs no Actions minutes. This page is the technical reference for the XML importer; for a spreadsheet
(CSV) use the same page, `tools/import.html` (`tools/README-csv-converter.md`), and for the step-by-step admin routine for either, see
`Runbook - Importing a Dataset (Admins).md`.

## Where things go

| What | Where | Committed? |
|---|---|---|
| XML export file(s) | `import/` (one file, or a folder of them) | No (git-ignored: street addresses) |
| Converted vehicles | `data/vehicles/VEH_xxxxxxxx.json` | Yes |
| Converted plates | `data/plates/<ST>-<PLATE>.json` (state, dash, plate; `XX` = unknown state) | Yes |
| Photos (only if you import media) | `photos/` | Yes |
| Search index (rebuilt for you) | `data/index.json` | Yes |
| Address lookup cache | `import/geocode-cache.json` | No |
| Report of everything unusual | `reports/xml-import.json` | No |

The script writes the converted files into those folders itself. The app reads
the committed files through the GitHub API, so no app change is needed.

## Steps
```bash
git checkout main && git pull
mkdir -p import          # put the XML file(s) here
pip install -r requirements.txt

# 1. Preview (writes nothing; geocoding still runs so you can see the match rate)
python3 scripts/migrate_xml_to_json.py --in import/ --default-area "Pasadena CA" --dry-run

# 2. Convert (rebuilds the index and validates)
python3 scripts/migrate_xml_to_json.py --in import/ --default-area "Pasadena CA"

# 3. Review the summary and reports/xml-import.json, spot-check, then commit
git status
git add data photos
git commit -m "Import legacy XML records" && git push
```
`--in` can be repeated and accepts files or folders (searched for `*.xml`).
`npm run import-xml -- <options>` runs the same script.

## Rules the import follows
1. **Every record is imported.** Nothing is skipped for a bad value.
2. **A missing, unmatched or failed field becomes `unknown`:** colour, make,
   body style and distinguishing features. Model and location stay empty.
   An unusable date becomes 1970-01-01 (never "recent", sorts oldest) and is
   listed under `needs_review`.
3. **Every imported sighting is `confirmed`.** `--flag` changes this for a run.
4. **Data that has no field goes into the sighting's notes**, one `name: value`
   line each: unrecognised XML elements and attributes (such as `guest`), the
   street address, a plate that cannot be stored, and media that could not be
   attached. The same items are listed in the report.
5. **Addresses become locations** by geocoding (below).
6. **Legacy media is not imported by default.** Image paths are kept in the notes
   ("Legacy media (not imported): ...") so nothing is lost. Photos taken in the
   app from now on are unaffected.
7. **Any XML layout works.** A record is any `<record>` element, or any element
   with an `alert_token` or `vehicle_license` child, at any depth. Element names
   are case-insensitive, and common alternates (`plate`, `make`, `date`,
   `notes`, ...) are understood. A file that cannot be read is reported and the
   others are still imported (exit code 1 so you notice).

## Field mapping
- Each record is a sighting. Records with the same plate become one vehicle.
  `NOPLATE` records become one vehicle each.
- `vehicle_make` "Black Ford Explorer" splits into colour, make, model. Body
  style comes from the model (Explorer is an SUV, Ram is a truck) and is
  `unknown` for models the tool does not recognise.
- Plates are 1-20 letters and digits (schema and app). Anything else stays in
  the notes.
- `datestamp` is converted to UTC. Zones PST, PDT, MST, MDT, CST, CDT, EST, EDT,
  AKST, AKDT, HST, UTC, GMT are built in; add one with `--tz-offset AEST=10`. ISO
  dates and epoch seconds/milliseconds also work. An unrecognised zone is read as
  UTC and noted.
- `alert_token` becomes the sighting id (and is kept in the sighting's `source`
  as `xml-import:<token>`). See "Re-importing" below. Repeated tokens within one
  export are merged and reported.

## Re-importing (old and new records in one XML)
Export again from the old system and import the whole file. It is safe after you
have edited data in the data tool.

1. **Old records are left exactly as they are.** A record whose `alert_token` is
   already in `data/` (under any vehicle, any plate state) is skipped: its notes,
   flag, location, photos and vehicle are never overwritten, and it is not geocoded
   again. The summary says how many were skipped.
2. **New records are added.** They join the vehicle that currently holds the plate:
   - the vehicle derived from the XML, if it still exists and still lists the plate;
   - otherwise the vehicle whose plate record or alias is that state+plate (for
     example after you changed `XX-ABC123` to `CA-ABC123`, or merged two vehicles);
   - an XML record with no state joins the one vehicle that has that plate number
     under a known state.
   Otherwise a new vehicle is created. Existing vehicle fields (colour, make,
   model, features) and plate records (including `plateType`) are never changed,
   and a plate you renamed is not recreated under the old state.
3. **The vehicle flag follows a new sighting only if it is newer** than everything
   already recorded. Those changes are listed (`flag_changed` in the report).
4. **Photos can still be added later** with `--media-root`: a skipped sighting
   that has no photos yet gets them; its other fields stay as they are.

Routine: `git status` clean, run with `--dry-run` and read the "new sighting(s)"
line, run for real, `git diff --stat` (only new/changed vehicles and plates
appear), commit, push. In the browser tool, pick the repo `data` folder first or
old records cannot be recognised; the ZIP then holds only new or changed files.
Same plate, but the XML now gives a different state than the data holds: that is
treated as a different plate (new vehicle).

## Addresses to locations
```bash
--geocode census        # default: US Census geocoder, free, no key, US addresses
--geocode nominatim     # OpenStreetMap, worldwide, 1 request per second
--geocode none          # skip
--default-area "Pasadena CA"        # added to addresses that do not mention it
--geocode-overrides fixes.csv       # columns: address,lat,lng; wins over the service
--coarsen 4 | none                  # default: COARSEN_DECIMALS in web/js/config.js
```
- Locations are rounded like the app rounds them (4 decimals, about 11 m)
  while the repository is public.
- Each distinct address is looked up once and cached, so a re-run is fast and
  works offline for known addresses.
- An address the service cannot match leaves that sighting's location unknown
  (the address stays in the notes). Fix the stragglers by adding them to an
  overrides CSV and re-running.
- If the service cannot be reached three times in a row the tool stops asking,
  imports the rest with unknown locations and tells you. Outages are not cached;
  re-run later.
- Imported sightings **without** a location appear in plate search and vehicle
  lookup but not in Local search.

## Things to expect
- **Local search hides old confirmed records.** Anything confirmed and older than 14 days
  is hidden from Local search, so imported history shows up in plate search and
  vehicle lookup, not on the Local screen.
- **Distinguishing features** are `unknown` for every imported vehicle.
- **Address privacy:** addresses end up in notes in the repository. Make the
  repository private before importing real data.

## Importing media later
Re-run the same command with `--media-root` pointing at the folder the XML's
`media/...` paths are relative to. Photos are converted to JPEG (max 1600 px,
under 500 KB) and attached to the sightings already imported; nothing is
duplicated.

## Undo
Nothing is deleted by the import. Before committing:
`git checkout -- data && git clean -fd data photos`. After committing:
`git revert <commit>`.

## Plate state

Every plate has a state, stored as `plateState` and in the file name (`data/plates/CA-7ABC123.json`). The importer finds it, in this order:

1. a state element in the record (`state`, `plate_state`, `license_state`, `province`, `st`, ...);
2. `State: CA` (or `State: California`, `State: Sonora`, `State: GOV DHS`) written in the comments, address or other text of the record (a code after USG or GOV is read here only when it is up to 4 letters or digits);
3. the **default state** you choose (`--default-state CA`, or the "State for plates with none" option in the browser tool);
4. otherwise `XX` (unknown).

A value that is not a US state, Canadian province, Mexican state (`Sonora` or `SON`) or federal/government plate (`USG`, `GOV`, with an optional code: `GOV DHS` becomes `GOV-DHS`) becomes `XX` and is listed in the report. The same plate in two states (or with and without a state) is kept as separate plates and flagged.

## Debug detail

Run the Python tool with `--debug` (add `--dry-run` to write nothing) or tick "Debug detail" in the browser tool. You get, per file: size, line count, encoding, and every character that had to be repaired with its line and column; how every XML element was used (which field it became, or "notes"); and for every record its line number, how its plate and state were read, the timestamp, address lookup, media and vehicle decisions, and the raw XML. Python writes `reports/xml-import-debug.txt` and `.json`; the browser tool shows it on the page and downloads a text file. If plates come out as `XX`, this is where to see which element holds the state.

## No Python? Use the browser tool

`tools/import.html` (choose an XML file) does the same conversion in a browser and produces a ZIP you unpack at the repo root.

1. Open the file from your computer (double-click it; do not host it). The US Census lookup only works from a local file.
2. Add the XML file(s) or folder. Optionally pick your repo's `data` folder (so existing records are merged and `data/index.json` is rebuilt) and the legacy media folder.
3. Convert, then **Download ZIP**.
4. Unpack the ZIP at the repo root (it contains `data/...` and, with media, `photos/...`), commit and push.
5. If you did not pick the `data` folder, run `python3 scripts/build_index.py` before pushing.

`tests/e2e_xml_tool.py` checks that the page and the Python tool write byte-identical records, so either can be used.
