# scripts/ — command-line tools (Python 3)

Run from the repository root. They run on your computer and cost no Actions minutes. Setup: `pip install -r requirements.txt`.

| Script | npm shortcut | What it does |
|---|---|---|
| `validate_records.py` | `npm run validate` | Checks every record against `schema/`, file names, plate-to-vehicle links and photo paths. Run before pushing data. Exit code 1 on errors |
| `build_index.py` | `npm run build-index` | Rebuilds `data/index.json` from the vehicle files (deterministic: no change, no diff) |
| `migrate_xml_to_json.py` | `npm run import-xml -- <options>` | Converts legacy XML exports into records; safe to re-run with old and new records. Options: `--in`, `--dry-run`, `--default-area`, `--default-state`, `--media-root`, `--debug`. Writes `reports/xml-import*.{json,csv}`. Guide: `07 Operations/Runbook - Importing a Dataset (Admins).md` |
| `migrate_plate_state.py` | | One-off: upgrades plates written before states existed (`ABC123` becomes `XX-ABC123`). `--state ST`, `--dry-run` |
| `audit_observers.py` | | Who wrote what: sightings per observer name; `--who "Name"` lists one person's sightings |
| `generate_sample_data.py` | `npm run sample-data`, `sample-data:clean` | Creates (or removes) obviously fake test records for phone testing. See `09 Testing/Phone Test with Sample Data.md` |
| `plate_states.py` | | Shared state list (US, Canada, Mexico, USG/GOV with optional code, XX) and plate-key helpers (keep in sync with `web/js/config.js`, `tools/import.html`, `tools/search.html` and the schemas; see `../schema/README.md`) |

Most scripts accept `--root PATH` to work on another copy of the repository. The browser version of the importer and a data editor are in `../tools/`.
