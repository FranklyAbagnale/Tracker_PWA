---
tags: [runbook, operations, import]
---

# Runbook — Importing a dataset (XML or CSV), step by step for admins

For anyone adding old plate-tracker XML exports, or a spreadsheet saved as CSV, to ParkingTracker. No programming needed.
You can import several datasets covering different (or overlapping) time periods, in any
order. Sightings that are already in the data are skipped, never duplicated or overwritten.

You need: a computer with Chrome or Edge, a copy of the repository on that computer
(up to date), and the file(s) to import.

## Pick the file type

| You have | Open | Reference |
|---|---|---|
| An XML export from the old plate tracker | add the `.xml` file in `tools/import.html` | `tools/README-xml-converter.md` |
| A spreadsheet (Excel, Numbers, Google Sheets) | save it as **CSV**, then add the `.csv` file in `tools/import.html` | `tools/README-csv-converter.md` |

It is one tool for both: `tools/import.html` shows the steps that fit the file you add. Import one kind of file at a time.

Not sure how to lay out a spreadsheet? `tools/csv-template.csv` shows the columns (plate, state, color, make, model, type, earliest seen, last seen, notes…).
Your headings do not have to match: the tool guesses and you confirm.

## Before you start (2 minutes)

1. Update your copy of the repository (`git pull`, or **Fetch/Pull** in GitHub Desktop).
2. Open `tools/search.html` in Chrome or Edge (double-click it). Press **Open repo folder…** and pick the repository folder.
   Write down the total in "N of M match" above the table (M, with no filters on). Call it **BEFORE**.
3. Put the file(s) somewhere easy (the Desktop is fine). Do not put them inside the repository.
4. Keep a small log, one line per dataset: file name, date range you expect, how many records or rows you expect (ask whoever made the file).

## Import one dataset

1. Open `tools/import.html` by double-clicking it. Keep it as a file on your computer; do not host it anywhere.
2. **Step 1, add the file:** drop it in, or choose it in the box for its type (XML or CSV). The page then shows the steps for that type. The list shows its name and size (the CSV tool also shows the number of lines).
3. **Step 2, your existing data:** choose the repository's **`data`** folder. Chrome asks to upload the folder's files; allow it (nothing leaves your computer).
   You should see a green line: *Found N vehicles and M plates already in your data.* If it says "No vehicles found", you picked the wrong folder.
   **Do not skip this step.**
4. **CSV only, step 3 (Columns):** the tool guesses what each column is. Read the **Preview**:
   - **Plate** shows as state-plate (for example `CA-DEMO001`). `XX` means no state was found.
   - **Sightings on** shows each date as year-month-day. Compare two or three with the spreadsheet. If day and month are swapped, set **Date order** in the options below and look again.
   - If a column is wrong, change it in the list above the preview. A yellow note appears if nothing is a plate, a date, or a vehicle description.
5. **Options:** leave everything as it is, except:
   - **Default area:** type the area addresses belong to (for example `Pasadena CA`) so address lookups work (XML always; CSV only if a column holds street addresses).
   - **State for plates with none:** leave as unknown unless the whole dataset is from one state.
6. Press **Convert** and wait. Large files can take several minutes if addresses are looked up. Leave the page open.
7. Read the **Check** box at the top of the result. It is the main test:
   - **Green "Check passed"**: *records (XML) or sightings (CSV) read = already in your data + new + repeated within the file.* Everything is accounted for.
   - **Red "CHECK FAILED"**: stop. Do not push. Download the report (JSON) and the log and send them to the tool maintainer.
   - **Red "You did not choose your existing data folder"**: go back to step 3.
   - It also shows the date range of the file and of the new records. Compare with what you expected.
   - A second line says **Format check passed**. If it is red, the ZIP is held back and you should not push. Only if you deliberately want to keep the records as they are (for example a state code the tool does not know), press **Ignore conflicts and download anyway** and confirm; fix the listed problems in `tools/search.html` before anything else uses the data.
8. Press **Download ZIP**. Also press the log button (**record-by-record log** for XML, **sighting-by-sighting log** for CSV) and keep it with your log line: it lists every record and what happened to it.
9. Unzip the ZIP **into the repository folder** so its `data` folder merges with the existing one (choose "Merge"/"Replace" if asked). The ZIP holds only new or changed files.
10. Open `tools/search.html` again and press **Reload from disk**. Continue with "Check the result" below before you push.

## Check the result (do all four)

1. **Counts add up.** In the data tool, note M again: **AFTER**. The result box told you how many vehicles are new
   ("N on new vehicles"). Check: AFTER = BEFORE + that number.
2. **New records are visible.** In the data tool press the **New** chip (its number counts records added since you last pressed **Mark all reviewed**).
   Open three records from the new list, from different dates, and compare each with the source file:
   plate, date, notes, location. Open one that has a map location and one that has none.
3. **Run the same file again.** Go back to the importer, reload the page, load the **same** file and pick the **same**
   `data` folder (now containing the import). Convert. You must see:
   *Check passed* and **"Nothing new"**, with *new = 0* and *already in your data = everything*. This proves nothing was missed.
   Do not download or unzip anything from this second run.
4. **Validate.** In the data tool press **Validate all**. It must report no errors. (Warnings about unknown colors or states are normal for imported data.)

If any of the four fails, do not push. Undo with `git checkout -- data && git clean -fd data photos` (this removes the unpushed import) and ask for help.

## CSV only: plates that need a state

If the result says plates are *in your data without a state (XX)*, the sightings are already on the right vehicle. Set the state afterwards: in `tools/search.html` open each vehicle listed (search the plate), change the plate's state, **Apply to this record**, then **Save to disk**. Do this before you push, so the commit holds both changes.

## Push

1. In the data tool press **Mark all reviewed** (so the next import's "New" list starts empty).
2. Commit and push (GitHub Desktop: select all changed files under `data`, write "Import <file name>", **Commit**, **Push**; or run the three commands shown at the bottom of the tool's result).
   Pushing data does not start any GitHub workflow.
3. Keep the source file and the logs out of the repository: they can contain street addresses.

## Several datasets

- Order does not matter, and overlapping time periods are fine: a record that appears in two files is imported once. XML and CSV can be mixed:
  a CSV row for a plate that came in from XML adds its sightings to the same vehicle (and a sighting on a date the vehicle already has is skipped).
- Finish and push each dataset before starting the next, so each one's *Nothing new* test is run against the latest data.
- Track in your log: file, date range, records read, new, already imported, vehicles AFTER. After the last one, the sum of all "new" figures
  should equal the growth in the number of sightings, and a final re-run of every file should say *Nothing new*.

## What the numbers mean

| Term | Meaning |
|---|---|
| Records read (XML) | Records in the XML file(s) |
| Rows read, sightings in the file (CSV) | Rows in the sheet, and the sightings they make: a row whose Earliest Seen and Last Seen differ is two sightings |
| Already in your data | Imported earlier (possibly edited since); left exactly as they are. CSV: also a sighting on a date the vehicle already has a sighting |
| New | Added now |
| Repeated within the file | The same record id (XML), or the same plate and date (CSV), appears twice; kept once |
| Joined an edited vehicle | A new record matched a vehicle whose plate state you changed or merged, so no duplicate was made |
| Flag changed | A vehicle's flag moved to the new sighting's flag because that sighting is newer than all earlier ones |
| Filled in (CSV) | A vehicle already in the data had details still `unknown` (color, make, model, body type, year); the CSV supplied them. Known values are never replaced |
| Need their state set (CSV) | The data holds the plate as `XX-<plate>` (no state) and the CSV gives a state. The sightings were added to that vehicle and the state is in their notes; set the plate's state in the data tool |
| No usable date | Date missing or invalid; stored as 1970-01-01 and never shown as recent |

## If something looks wrong

- *Check failed* or counts do not add up: stop, keep the log, ask the maintainer. Nothing is lost: the ZIP is only a copy until you unzip it.
- Many records "without a map location": normal when addresses are incomplete (and for a sheet with only a city). Add a **Default area** and re-run before pushing, or add fixes in an address CSV (XML tool, under More options).
- Plates all show state `XX`: the file has no state. Set **State for plates with none** if the data is from one state, and re-run before pushing.
- CSV dates a month off, or a day of 13 or more rejected: set **Date order** and check the **Sightings on** column in the preview.
- CSV accented letters look wrong: save the sheet as "CSV UTF-8" and choose it again.
- "Nothing new" for a file you expected to add data: the sightings, or sightings on those dates, are already in the data.
- Command-line users: `python3 scripts/migrate_xml_to_json.py --in <file> --dry-run` prints the same check for XML; the log is `reports/xml-import-records.csv`. There is no command-line version of the CSV tool.
