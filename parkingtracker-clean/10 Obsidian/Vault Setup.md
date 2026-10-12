---
tags: [obsidian, meta]
---

# Vault Setup

## Opening the vault
Point Obsidian at the ParkingPlateTracker folder as a new vault. Do not nest
it inside another vault. Dataview queries and tag scoping get confusing.

## Recommended core settings
- Files & Links -> Default location for new notes: 00 Inbox (create it).
- Files & Links -> New link format: Shortest path when possible.
- Files & Links -> Use Wikilinks: On.
- Files & Links -> Automatically update internal links: On.
- Appearance -> Base font size: 16 (matches the app's minimum input size).
- Editor -> Readable line length: Off (tables here are wide).
- Core plugin -> Templates: On, folder set to 99 Templates.
- Core plugin -> Daily notes: On, folder 00 Inbox/Daily.

## Folder purpose

| Folder | Contents | Rule |
|---|---|---|
| 00 Home | Dashboards and overviews | Start here |
| 01 Requirements | What the system must do | Stable IDs, never renumber |
| 02 Use Cases | How each behaviour unfolds | One file per use case |
| 03 Architecture | How it is built | Describes the current design |
| 04 Decisions | Why it is built that way | Immutable once accepted |
| 05 Code | The actual code | Real files, not notes about files |
| 06 References | External sources | Link, do not copy |
| 07 Operations | How to run and fix it | Written for a tired person at 2am |
| 08 Roadmap | What is next | Phase files |
| 09 Testing | How we know it works | Checklists and failure modes |
| 10 Obsidian | How to use this vault | Meta |
| 99 Templates | Note templates | Do not link from content notes |

## Git and the vault
You can keep this vault in the same repository as the app, in a docs/ folder,
or in its own repository. If you put it in the app repo, add
.obsidian/workspace.json to .gitignore. It changes constantly and creates
noise.

## Related
- Plugins and Settings
- Dataview Snippets
