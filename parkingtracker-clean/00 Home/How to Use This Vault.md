---
tags: [meta]
---

# How to Use This Vault

## Conventions

| Prefix | Meaning | Example |
|---|---|---|
| UC-nn | Use case | UC-03 Flag a Plate |
| ADR-nnn | Architecture decision record | ADR-003 JSON over XML |
| FR-nn / NFR-nn | Requirement IDs | FR-04 |

Requirement and use case IDs are stable. Never renumber. Supersede and mark
deprecated instead.

## Linking discipline
- Link generously with wikilinks. Orphan notes are invisible notes.
- When a decision changes, edit the ADR status field and add a
  "Superseded by" line rather than deleting it.
- Tag tasks with #todo and questions with #question so the Dataview queries
  on the Dashboard pick them up.

## Workflow
1. New idea or problem -> #question in Open Questions.
2. Resolved -> promote to a requirement or an ADR.
3. Requirement -> write or update the matching use case.
4. Use case -> implement -> tick acceptance criteria in Manual Test Checklist.
