# tests/ — automated tests

| Command | Runs | Needs |
|---|---|---|
| `npm test` | `core.test.mjs`, `github.test.mjs`, `lookup.test.mjs`, `states.test.mjs`: app logic, GitHub client, lookup proxy, plate states (US, Canada, Mexico, USG/GOV) | Node |
| `npm run test:py` | `test_*.py`: importer (`test_migrate_xml`, `test_xml_reimport`), scripts, sample data, workflow guard rails | Python |
| `npm run test:e2e` | `e2e_smoke.py`, `e2e_sample_data.py`, `e2e_lookup.py`, `e2e_search_tool.py`, `e2e_edit_tool.py`: drive the real app and the data tool in Chromium against fake data, no network | `pip install playwright pillow` and Chromium |
| `python3 tests/e2e_xml_tool.py` | The XML side of `tools/import.html` against the Python importer (outputs must be byte-identical) | same as above |
| `python3 tests/e2e_csv_tool.py` | The CSV side of `tools/import.html` (and the XML/CSV switching): column guessing, dates, encodings, re-runs ("Nothing new"), joining vehicles that came from XML, and the output checked with `scripts/validate_records.py` and `scripts/build_index.py` | same as above, plus `jsonschema` |

`test_workflows.py` enforces the Actions-minutes rules (validate runs only on pull requests or by hand; Pages deploys only when `web/` changes). `fixtures/` holds a sample XML export. Run all of them before merging anything that touches `web/`, `schema/`, `scripts/` or `tools/`.
