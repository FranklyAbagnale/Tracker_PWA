---
tags: [architecture, repo]
---

# Repository Layout

~~~
repo-root/
  index.html
  manifest.json
  service-worker.js
  css/style.css
  js/
    app.js
    ui.js
    github.js
    geo.js
    store.js
  data/
    index.json
    plates/
      ABC1234.json
      XYZ7890.json
  photos/
    ABC1234.jpg
  schema/
    plate.schema.json
  scripts/
    build_index.py
    validate_records.py
    push_changes.py
    migrate_xml_to_json.py
  reports/
  .github/workflows/
    validate.yml
  README.md
~~~

## Rules
- data/plates/ is the source of truth. Nothing else is authoritative.
- data/index.json is generated. Never hand-edit.
- photos/ holds binaries. Keep them downscaled.
- scripts/ runs locally. No workflow should invoke them on a schedule.
- .github/workflows/validate.yml triggers on pull_request only. Direct
  pushes to main by the data owner bypass it entirely.

## Branching
Trunk-based. main is deployable at all times. Field-app writes commit
directly to main. Bulk imports also go to main after a local dry run.
