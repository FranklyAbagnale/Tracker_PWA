# schema/ — record formats

JSON Schemas for the two record types stored in `../data/`.

| File | Describes |
|---|---|
| `vehicle.schema.json` | A vehicle and its sightings. Required in the file (the app fills in `unknown` when a person leaves color, make or body style blank; nothing is required of the person): `vehicleKey`, `displayName`, `color`, `make`, `bodyStyle`, `distinguishing` (may be empty), `plateAliases`, `flag`, `sightings`, `firstSeen`, `lastSeen`; `model` is optional. Enums: flag `unknown/suspected/confirmed/cleared/pigs`, body style `sedan/suv/truck/van/coupe/hatchback/unknown` |
| `plate.schema.json` | A plate: number, state, type (`standard/dealer/temporary/vanity`), current vehicle, first seen, updated |

Plate keys are `<STATE>-<PLATE>` (state, dash, 1-20 letters or digits; `XX` = unknown state; see Plate states below).

## Plate states

A plate's state (`plateState`, and the part of the file name before the plate) is one of:

| Kind | Form | Examples |
|---|---|---|
| US state, DC, territory (AS GU MP PR VI) | 2 letters | `CA`, `NV`, `PR` |
| Canadian province or territory | 2 letters | `BC`, `ON`, `QC`, `NL` |
| Mexican state (32, including Ciudad de México) | 3 letters, ISO 3166-2:MX without the country | `SON` (Sonora), `BCN`, `NLE`, `CMX` |
| US federal plates | `USG`, optionally `USG-<code>` | `USG`, `USG-G42` |
| Other government plates | `GOV`, optionally `GOV-<code>` | `GOV`, `GOV-DHS` |
| Not known | `XX` | `XX` |

The optional code after `USG-` or `GOV-` is 1 to 8 letters or digits and is part of the state; the plate keeps its own number. A key is therefore `<STATE>-<PLATE>`, split at its **last** dash (plates never contain a dash): `GOV-DHS-12345` is state `GOV-DHS`, plate `12345`. Searching the state `GOV` finds every `GOV-*` plate; searching `GOV-DHS` finds only that agency.

The list lives in four places that must change together: `scripts/plate_states.py`, `web/js/config.js`, `tools/import.html` and `tools/search.html`, plus the schemas. `tests/fixtures/state_cases.json` is checked against all of them (`tests/test_plate_states.py`, `tests/states.test.mjs`, `tests/e2e_csv_tool.py`).


Used by `scripts/validate_records.py` (`npm run validate`) and mirrored by the app's checks in `web/js/vehicle-manager.js`. If you change a schema, change the app check, the validator, `tools/search.html` and the importers (`scripts/migrate_xml_to_json.py`, `tools/import.html`) together, and run `npm test`, `npm run test:py`, `npm run test:e2e`.
