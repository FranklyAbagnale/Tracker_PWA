# Data tool (`search.html`)

Find, review and correct records in your local clone, then push, without using GitHub Actions minutes. Desktop **Chrome or Edge** only (it needs the folder picker). It makes no network requests.

## Use
1. `git pull`, open `search.html`, press **Open repo folder…**, pick the repository folder (**Reopen last folder** remembers it).
2. **New** and **Updated** chips show records added or given sightings since you last pressed **Mark all reviewed**.
3. Filter with the search box (`make:ford -cleared "roof rack"`) and the value lists on the left (every value in use, with counts). Sort by column heading. **Download CSV** exports the list.
4. Click a record to edit details, plates and sighting notes/flags, then **Apply to this record**. Bulk edits: tick rows, or none for "all matching", then use the bar above the table. Hover a color/make/model value and press ✎ to rename it everywhere.
5. **Save to disk** writes changed records and plate files and rebuilds `data/index.json`. **Validate all** runs the same checks as `npm run validate`.
6. Commit and push (the tool offers the commands). Run **Mark all reviewed** afterwards.

## Limits
It cannot delete vehicles, merge duplicate vehicles or add sightings. Plate state changes rename the plate file and keep the alias in step.

Full routine: `07 Operations/Runbook - Data Tool.md`. Tested by `tests/e2e_search_tool.py`.
