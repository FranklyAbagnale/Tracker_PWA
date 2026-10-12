# Importing XML (`import.html`)

Turns legacy plate-tracker XML exports into ParkingTracker records. (For a spreadsheet, add a CSV to the same page instead, see [the CSV guide](README-csv-converter.md); both write the same records and follow the same rules, listed in [README.md](README.md).) Safe to run with files holding **old and new** records: records already in the data are skipped (never overwritten), new ones are added, and vehicles you renamed or merged since the last import are not duplicated.

## Use
1. Open `import.html`. Add the XML file(s) (it switches to the XML steps by itself).
2. **Choose the repository's `data` folder** (step 2). Without it the tool cannot tell old records from new.
3. Set **Default area** (e.g. `Pasadena CA`) so addresses become map locations. Leave other options alone.
4. **Convert**. Read the **Check** box: *records read = already in your data + new + repeated within the file*. Green means every record is accounted for.
5. **Download ZIP** (new or changed files only) and unzip it into the repository folder. **Download record-by-record log (CSV)** lists what happened to each record.
6. Prove nothing was missed: convert the same XML again against the updated data; it must say **Nothing new**.
7. Check in `search.html`, commit, push.

After unzipping, `python3 scripts/validate_records.py` (`npm run validate`) checks the records against `schema/`; the importer page does the same check before it gives you the ZIP. Step-by-step guide for admins, with checks: `07 Operations/Runbook - Importing a Dataset (Admins).md`. Rules and field mapping: `07 Operations/Runbook - XML Import.md`. The same logic as a command: `../scripts/migrate_xml_to_json.py`. Tested by `tests/e2e_xml_tool.py` (output identical to the Python version).
