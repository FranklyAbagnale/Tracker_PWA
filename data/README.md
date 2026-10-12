# data/ — the records

This folder **is the database**. The app reads and writes it through the GitHub API; there is no server.

| Path | Contents |
|---|---|
| `vehicles/VEH_xxxxxxxx.json` | One file per vehicle: description, flag, plate aliases and every sighting (time, location, photos, notes, observer). A sighting entered after the fact ("previous sighting") has `timestamp` set to when it happened and `recordedAt` set to when it was saved. A sighting edited by its observer within 24 hours carries `editedAt` (and the vehicle gets `editedAt`) |
| `plates/<STATE>-<PLATE>.json` | One file per plate (state + plate, e.g. `CA-7ABC123`, `SON-ABC123` for Sonora, `GOV-DHS-12345` for a government plate with code DHS; `XX` = state unknown; see `../schema/README.md`). Points to the vehicle that currently has it |
| `index.json` | A derived summary of all vehicles (key, name, flag, last seen, latest location, plate aliases, plus color, make, model, year, body style and features when known, for the app's "Find by description") used for fast local search. Rebuilt by the app and by `npm run build-index`; never edit by hand |
| `samples/` | Two example records that show the format (checked by the validator) |

The shape of each record is defined in `../schema/`. Checks: `npm run validate`.

## Rules

- Vehicle files are the source of truth; `index.json` and plate files are kept in step with them. Change several things at once with the data tool (`../tools/README-data-tool.md`), which keeps them consistent, rather than editing files by hand.
- Files are 2-space JSON with a trailing newline, so diffs stay small.
- Pushing changes under `data/` starts no GitHub Actions run (see `../.github/README.md`).
- Importing old XML exports: `../tools/README-xml-converter.md`. Importing a spreadsheet (CSV): `../tools/README-csv-converter.md`.

## Privacy

Records contain locations, addresses in notes and observer names. Treat the repository as sensitive: keep it private once real data is in it.
