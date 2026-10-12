# Importing a CSV (`import.html`)

Turns a spreadsheet saved as CSV into ParkingTracker records. Safe to run with sheets holding **old and new** rows: sightings already in the data are skipped (never overwritten), new ones are added to the right vehicle, and a vehicle you renamed or merged since the last import is not duplicated.

`csv-template.csv` in this folder shows the columns, with two made-up rows. Your headings do not have to match it.

## Use
1. Open `import.html`. Add the CSV file (it switches to the CSV steps by itself) (several files work if they have the same columns).
2. **Choose the repository's `data` folder** (step 2). Without it the tool cannot tell old records from new.
3. **Columns** (step 3): the tool guesses what each column is from its heading. Read the **Preview** and change any column that is wrong. Check the **Sightings on** column: it shows each date as year-month-day, so a swapped day and month is easy to see. The choices are remembered the next time you open a file with the same headings.
4. **Options** (step 4): leave them alone unless something is wrong. Useful ones: **State for plates with none** (if the whole sheet is one state), **Date order**, **Flag**, **Default area** (only if a column holds street addresses).
5. **Convert**. Read the **Check** box: *sightings in the file = already in your data + new + repeated within the file*. Green means every sighting is accounted for. The **Format check** line confirms every new file matches `schema/`.
6. **Download ZIP** (new or changed files only) and unzip it into the repository folder. **Download sighting-by-sighting log (CSV)** lists what happened to each one.
7. Prove nothing was missed: convert the same CSV again against the updated data; it must say **Nothing new**.
8. Check in `search.html`, commit, push.

Step-by-step guide for admins, with checks: `07 Operations/Runbook - Importing a Dataset (Admins).md`.

## Columns it understands

| Column (example headings) | Becomes |
|---|---|
| Plate (`License Plate`, `Plate`, `Tag`) | The plate. Spaces and dashes are ignored; `NONE` or `NO PLATE` or blank means no plate. More than 20 letters or digits is kept in the notes only |
| State (`State`, `Province`) | Plate state: `CA`, `California`, `Calif.` all work, as do Canadian provinces and Mexican states (`Sonora` or `SON`, `Nuevo León`, `CDMX`). `USG` and `GOV` are federal and government plates and may carry a code after a space or dash (`GOV DHS` becomes `GOV-DHS`, `USG G42` becomes `USG-G42`). Not understood becomes `XX` and the text goes to the notes |
| Color, Make, Model | The vehicle. Colors are lower-cased (`gray` becomes `grey`); an all-capitals or all-lowercase make is title-cased, as the XML tool does |
| Vehicle | Color, make and model in one column (`Silver Land Rover Defender 90`), split like the XML tool |
| Type (`Type`, `Body Style`) | sedan, SUV (also crossover), truck (also pickup), van (also minivan), coupe, hatchback. Blank: guessed from the model, otherwise `unknown`. Anything else (wagon…) stays in the notes and the style is guessed |
| Year | Model year, 1900 to 2100 |
| Earliest Seen, Last Seen | One sighting at each date; one sighting if both dates are the same or only one is given |
| Date | One sighting per row, for sheets with a single date column |
| Address | Looked up on the map (US Census or OpenStreetMap). The address also goes in the notes. A city name alone is not an address; leave it as an ordinary column |
| Latitude, Longitude | Exact location, rounded like the app (4 decimals) |
| Flag | `unknown`, `suspected`, `confirmed`, `cleared` or `pigs`. Blank uses the flag from the options |
| Notes (`NOTES`, `Comments`, `Remarks`) | The sighting's notes, line breaks kept |
| Any other column | Added to the notes as `Heading: value`, so nothing is lost. Choose **Ignore this column** to drop one |

## Rules the import follows
1. **Every row is imported.** Blank lines are not rows. A value that cannot be read is kept in the notes and the row is listed under **Rows that need a look**.
2. **A row is one sighting per date.** Earliest and Last Seen on different dates make two sightings with the same notes, so the vehicle's page shows the note whichever is newest.
3. **Rows with the same plate and state are one vehicle.** If the repository already has a vehicle with that plate (from XML, the app, or an earlier CSV), the new sightings are added to it. Otherwise a new vehicle is created from the newest row.
   - **Details that are still `unknown`** on a vehicle that already exists (color, make, model, body type, year) are filled in from the CSV, and its name follows if the name was the automatic one. A detail that is already known is never replaced. Untick the option in step 4 to turn this off. The result lists which vehicles were filled in.
   - **Plates the data holds without a state (`XX`).** The old XML export usually had no state. If the CSV gives a state for a plate the data holds as `XX-<plate>`, the new sightings go to that vehicle (no duplicate is made), the state is written in their notes, and the plate is listed in the result under "need their state set". The plate record is **not** renamed by the import: open the vehicle in `search.html` and set the plate's state there.
4. **A sighting is "already in your data"** when the same plate and date were imported from a CSV before, or (option on by default) when the vehicle already has any sighting on that date from any source, which stops overlap with XML or app records from creating duplicates. Turn the option off in step 4 if you really want two sightings on one day. Changing a note in the CSV later does not change a sighting already imported: edit it in `search.html`.
5. **Rows repeating the same plate and date** inside one file become one sighting, with their notes combined.
6. **The same plate text in two states is two vehicles.** A plate with no state (`XX`) and the same plate with a state in the same file are reported under the result; fill in the State column and run again, or fix them in `search.html`.
7. **Dates.** Read as month/day/year, unless a date such as `25/01/26` proves day/month/year (**Date order** overrides). Two-digit years 00 to 69 are 2000s, 70 to 99 are 1900s. Also understood: `2026-01-08`, `Jan 8, 2026`, `8 Jan 2026`, times like `6:30 PM`, ISO timestamps, Excel serial dates, Unix times. A date with no time is set to 12:00 in the chosen **Time zone** (default PST).
8. **No photos.** The CSV tool never imports photos.
9. **Extra plates written in the notes** (`back plate DEMO999`) stay in the notes. Add a second plate to the vehicle in `search.html` if it should be searchable.

## File handling
UTF-8 (with or without a byte order mark), UTF-16 and Windows-1252 (older Excel) are all read; accents are shown in the preview so you can tell. Comma, semicolon and tab separators are detected. A quote that is never closed is reported before you convert. Nothing is uploaded; the only network use is address lookup, and only when a column is set to **Address**.

## If something looks wrong
- **Dates are a month off or on the wrong side:** set **Date order** (step 4), check **Sightings on** in the preview.
- **A column is read as the wrong thing:** change it in step 3. If nothing in the sheet is a plate or a date the tool warns you.
- **Every plate shows `XX`:** the sheet has no state column. If it is all one state, set **State for plates with none**.
- **Accented letters look wrong:** save the sheet as "CSV UTF-8".
- **A second copy of a vehicle appeared (CA and XX of the same plate):** this happens only if the data folder was not chosen in step 2, or the existing plate is under a different known state. Fix in `search.html`; there is no automatic merge.
- **"Nothing new" when you expected new rows:** the sightings are already in the data, or the vehicle already has a sighting on those dates (the same-date option in step 4).
- **Check failed or Format check failed:** do not push. Download the report (JSON) and send it, with the CSV, to whoever maintains the tool. When only the format check fails, the ZIP is held back; **Ignore conflicts and download anyway** (asks you to confirm) gives it to you as it is, for example to keep a value this tool does not recognise. The data validator will then report the same problems until they are fixed, and the report notes that conflicts were ignored.

Tested by `tests/e2e_csv_tool.py`.
