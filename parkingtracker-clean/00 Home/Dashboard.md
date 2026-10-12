---
tags: [moc, home]
---

# Dashboard

- [[Project Overview]]
- [[Functional Requirements]]
- [[Use Case Index]]
- [[Architecture Overview]]
- [[Decision Log]]
- [[Manual Test Checklist]]
- [[Roadmap]]

## Live views (requires Dataview plugin)

### Open questions
~~~dataview
TASK
FROM "01 Requirements"
WHERE !completed
~~~

### Decisions
~~~dataview
TABLE status AS Status, date AS Date
FROM "04 Decisions"
WHERE contains(file.name, "ADR")
SORT file.name ASC
~~~

### Recently touched notes
~~~dataview
TABLE file.mtime AS "Modified"
FROM ""
SORT file.mtime DESC
LIMIT 15
~~~
