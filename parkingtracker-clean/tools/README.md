# tools/ — desktop HTML tools

Single-page tools you open by double-clicking the file in Chrome or Edge. They run entirely in the browser, upload nothing (the one exception is address lookup, and only if you choose it), and cost no Actions minutes. Keep them as local files; do not host them.

| Tool | For | Guide |
|---|---|---|
| `search.html` | Search, review and fix records in your local copy of the repository | [README-data-tool.md](README-data-tool.md) |
| `edit.html` | Pull up vehicles, sightings, plates or photos with search, filters and selection; change or remove them. Changes are staged, reviewed, backed up, then written | [README-edit-tool.md](README-edit-tool.md) |
| `import.html` | Import data: a legacy plate-tracker **XML** export, or a spreadsheet saved as **CSV**. Add the file and the page shows the steps for that type | [XML](README-xml-converter.md), [CSV](README-csv-converter.md) |
| `csv-template.csv` | The columns the CSV tool understands, with two made-up example rows. Open it in Excel, replace the rows, save as CSV | |

## Which file?

`import.html` takes both; add the file and it switches to the right steps. One kind of file at a time.

- A legacy plate-tracker **XML** export: add the `.xml` file.
- Anything kept in Excel, Numbers or Google Sheets: save it as **CSV** (File → Save As / Download → CSV) and add the `.csv` file. The column headings do not need to match the template; the tool guesses what each column is and lets you change it.

Both kinds write the same records, can be run again on the same file safely, and cost nothing to run.

## Typical flow

1. Update your copy of the repository (`git pull`).
2. Open `import.html`, add your file, and **choose the repository's `data` folder** (without it the tool cannot tell old records from new ones).
3. Convert. Read the green **Check passed** line and the **Format check** line. Red means stop and do not push (the ZIP is held back; **Ignore conflicts and download anyway** overrides that after a confirmation, see the admin runbook).
4. Download the ZIP and unzip it into the repository folder.
5. Look at the result in `search.html`, then run the same file through the importer again: it must say **Nothing new**.
6. Commit and push. Pushing under `data/` starts no GitHub workflow.

The same steps with the checks to do at each point, written for people who are not programmers: `../07 Operations/Runbook - Importing a Dataset (Admins).md`.

## What both kinds of import do

- **Every row or record is imported.** Nothing is skipped because a value is bad. A missing or unreadable color, make, body style or state becomes `unknown` (`XX` for a state) and the original text stays in the sighting's notes. An unreadable date becomes 1970-01-01 (never shown as recent) and is listed in the result.
- **Records already in the data are never overwritten.** New sightings are added to the vehicle that already has the plate, even if you have edited or merged it since. Existing vehicle details are not changed.
- **Imported sightings are `confirmed`** unless you pick another flag in the options (the CSV tool can also read a Flag column).
- **Source files stay out of the repository.** They can contain street addresses. Make the repository private before pushing real data.

## If you change a tool

- Tools are single self-contained files on purpose, so that double-clicking works. Do not split them or load scripts from elsewhere.
- `import.html` holds two engines (XML and CSV) over one shared core: plate state parsing, make and model parsing, merging into existing vehicles, finding the vehicle that holds a plate, address lookup and the ZIP writer exist once, so a fix applies to both. The XML engine is a port of `../scripts/migrate_xml_to_json.py`; `../tests/e2e_xml_tool.py` requires the page and the script to write identical files, so change them together. The CSV-only logic (CSV reading, column mapping, dates) is below the line "CSV-specific core" in the file and is tested by `../tests/e2e_csv_tool.py`, which also checks the XML/CSV switching.
- If a record format changes, follow `../schema/README.md`: the app, the validator, `search.html` and the importer (`import.html`) change together.
- Run `python3 tests/e2e_xml_tool.py`, `python3 tests/e2e_csv_tool.py` and `python3 tests/e2e_search_tool.py` and `python3 tests/e2e_edit_tool.py` from the repository root after any change here (see `../tests/README.md`).
