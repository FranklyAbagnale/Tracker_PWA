# Record editor (`edit.html`)

Pulls up any level of the data, lets you search, filter and select, and changes or removes what you pick. Everything is staged first; nothing is written until you review it. Open it by double-clicking in Chrome or Edge on a desktop. It makes no network requests and only touches the folder you pick. Tested by `tests/e2e_edit_tool.py`.

`search.html` is the quick tool for reviewing new records and fixing a vehicle's details by form. Use `edit.html` when you need to remove things, work on sightings, plates or photos directly, or change many records at once.

## The four levels

| Level | A row is | You can |
|---|---|---|
| **Vehicles** | one vehicle file | remove vehicles (with their plate files and photos); set flag, body style, color, make, model or year on many; edit the whole record as JSON |
| **Sightings** | one sighting of one vehicle | remove sightings; clear location, notes or photos; set flag, observer or source on many; edit one sighting by form (time, flag, observer, source, latitude/longitude, notes) or as JSON; remove a single photo from it |
| **Plates** | one plate file (and any plate a vehicle lists that has no file) | remove plates; set the plate type or change the state on many; edit state, code, number and type by form; edit the file as JSON |
| **Photos** | one photo path, from the sightings that use it and from the files in `photos/` | remove from records (keep the file), remove from records and delete the file, delete files nothing uses (`status:unreferenced`), drop references to files that are missing (`status:missing`) |

## Finding and selecting

Each level has its own search box, date range, and value lists with counts. They remember their settings while you switch levels.

- Search: words are ANDed. `"two words"`, `-exclude`, `field:value`. The fields differ by level (the hint under the box lists them). Examples: `date:2026-03` (sightings in a month), `status:"no plate file"` (plates), `status:unreferenced` (photos), `make:ford -cleared` (vehicles).
- Click a row to open its detail drawer; **Show the vehicle / its sightings / its plates** jump between levels with the search filled in.
- Tick rows; Shift-click ticks a range. **Select all N matching** picks every match, not only the shown page. There are also select-the-shown, invert, unselect-these and clear. The selection stays while you change filters. **Show selected only** lists just what is picked.
- **Download list (CSV)** saves the rows of the current level.

## Staging and saving

Every action changes only the page's working copy and adds to the bar at the bottom (**Staged, not written**). Edited rows are badged; rows to be removed are struck through. **Discard all** drops everything. In the drawer, **Undo changes to this record** drops the staged changes of one vehicle, plate or photo.

**Review & save…** shows how many vehicle, plate and photo files will be rewritten or removed, any re-pointed plates or kept photos, and the list of what was staged. Then:

1. The edits are checked against the data rules. Any new problem blocks saving and is listed.
2. If files are being deleted, type the phrase it shows (`SAVE <count>`).
3. A **backup ZIP** downloads first (leave it ticked). It holds the originals of every file that changes, the photos that are deleted, `CHANGES.txt` and a `README.txt` saying how to undo. Unzip it into the repo folder to put things back.
4. The files are written (plate files, vehicle files), then deleted, then `data/index.json` is rewritten.
5. Run `python3 scripts/validate_records.py`, look at `git status`, commit and push. Pushing under `data/` starts no workflow.

## Rules the tool keeps

- A vehicle must have at least one sighting. Removing the last sighting of a vehicle asks first, then removes the vehicle.
- After removing or editing sightings, `firstSeen` and `lastSeen` are recomputed from what is left. Edited vehicles get `lastUpdatedBy: "desktop-tool"`.
- Removing a vehicle deletes the plate files it owns, except a plate that a vehicle that stays also lists: that file is kept and re-pointed to it. Photos used by a sighting that stays are never deleted.
- Removing a plate takes it off the vehicle and deletes its file. Changing a plate's state or number renames its file, and refuses if the new plate already exists on another vehicle (probably a duplicate to merge by hand).
- If any file changed on disk since the tool read it (for example after a `git pull`), saving stops before writing anything. Press **Reload from disk** and redo the edits.
- Closing the page with staged changes asks first.

## What this does not do

It does not add sightings or vehicles, merge duplicate vehicles, or rewrite git history. Removed records stay in git history after you commit. If the aim is to take private data out of a public repository, deleting files is not enough.
