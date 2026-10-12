---
tags: [obsidian, dataview]
---

# Dataview Snippets

Copy-paste ready. All require the Dataview plugin.

## Open questions

~~~dataview
TASK
FROM "01 Requirements/Open Questions"
WHERE !completed
~~~

## ADR status table

~~~dataview
TABLE status AS Status, date AS Date
FROM "04 Decisions"
WHERE contains(file.name, "ADR")
SORT file.name ASC
~~~

## Superseded decisions

~~~dataview
LIST
FROM "04 Decisions"
WHERE status = "superseded"
~~~

## Use cases by priority

~~~dataview
TABLE id AS ID, actor AS Actor, priority AS Priority, status AS Status
FROM "02 Use Cases"
WHERE id
SORT priority ASC, id ASC
~~~

## Recently modified

~~~dataview
TABLE file.mtime AS Modified, file.folder AS Folder
FROM ""
WHERE file.name != "Dashboard" AND file.name != "Dataview Snippets"
SORT file.mtime DESC
LIMIT 20
~~~

## Orphan notes (no inbound links)

~~~dataview
LIST
FROM ""
WHERE length(file.inlinks) = 0 AND !contains(file.folder, "99 Templates")
~~~

## Roadmap phase progress

~~~dataview
TABLE status AS Status
FROM "08 Roadmap"
WHERE contains(file.name, "Phase")
SORT file.name ASC
~~~

## Checklist items across all use cases

~~~dataview
TASK
FROM "02 Use Cases"
WHERE !completed
GROUP BY file.link
~~~

## Inline query example

There are `= length(filter(pages("02 Use Cases"), (p) => p.id))` use cases
defined.

## Related
- Vault Setup
- Plugins and Settings
