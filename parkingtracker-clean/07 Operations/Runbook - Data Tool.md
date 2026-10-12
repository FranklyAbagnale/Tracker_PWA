---
tags: [runbook, operations]
---

# Runbook — Data Tool (search, review and fix records)

Purpose: find records, spot what the field team added, and correct data in your
local clone, then push, without starting any GitHub Actions run.

File: `tools/search.html`. Open it in desktop **Chrome or Edge** (it needs the
folder-picker API; Safari and phones cannot run it). It makes no network
requests: its Content-Security-Policy forbids them, so it can only read and
write the folder you pick.

## Routine

~~~bash
cd /path/to/repo
git checkout main
git pull
~~~
1. Open `tools/search.html`, press **Open repo folder…** and pick the clone's top folder
   (**Reopen last folder** remembers it).
2. The **New** and **Updated** chips show records added, or given new sightings,
   since you last pressed **Mark all reviewed**. The first time on a folder,
   everything counts as reviewed.
3. Filter: type words in the search box (`make:ford -cleared "roof rack"`) and tick
   values in the lists on the left. Every value in use is listed with a count; counts follow
   the other filters. Click a column heading to sort. **Download CSV** exports the list.
4. Click a record to edit its details, plates and sighting notes/flags. **Apply to this record**
   stages the change.
5. To change many at once: tick rows (or leave none ticked for "all matching") and use the
   bar above the table (flag, body style, duplicate mark, unknown plate state), or hover a
   color/make/model/year value and press ✎ to rename it everywhere.
6. **Save to disk** writes the changed records and plate files and rebuilds `data/index.json`.
   Then, in the clone:

~~~bash
npm run validate          # authoritative check (also looks for missing photos)
git add data photos
git commit -m "Data cleanup"
git push
~~~

Data pushes start no workflow (see [[Actions Budget]]). **Validate all** in the tool is a quick
check of the same rules.

## What the tool will and will not do
- Changing a plate's state or number renames `data/plates/<state>-<plate>.json` and the vehicle's
  alias together. It refuses if the new plate already exists on another vehicle (probably a
  duplicate to merge by hand).
- Editing color, make or model rebuilds the display name; other edits leave it alone.
- Edited records get `lastUpdatedBy: "desktop-tool"`.
- It cannot delete vehicles, merge duplicates, or add sightings. To delete vehicles use `tools/edit.html` (`tools/README-edit-tool.md`).
- Undo before saving: **Discard all**. After saving: `git checkout -- data` (nothing is committed
  until you commit).
