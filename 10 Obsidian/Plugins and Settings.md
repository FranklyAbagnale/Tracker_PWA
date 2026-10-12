---
tags: [obsidian, meta]
---

# Plugins and Settings

## Essential

### Dataview
The single highest-value plugin for this vault. It turns the static folders
into live views: open questions, ADR statuses, recently changed notes.

Settings: enable JavaScript queries and Inline queries.

### Templater
Better than the core Templates plugin because it can compute dates, prompt
for input, and run small scripts. Use it for ADRs and use cases so the
frontmatter is always correct.

Settings: template folder 99 Templates, enable Trigger Templater on new file
creation.

### Tasks
Turns checkbox lines into a queryable system. Useful for the checklists in
Manual Test Checklist and Open Questions.

### Git
Lets you commit and sync the vault from inside Obsidian. Genuinely useful if
the vault lives in the same repository as the app.

## Strongly recommended

### Excalidraw
For sketching the architecture, the offline outbox flow, and the conflict
merge decision tree. A diagram of the outbox flow will save you an hour of
reading code later.

### Advanced Tables
The vault is table-heavy — requirement matrices, failure modes, quotas. This
makes them editable without fighting pipes.

### Linter
Enforces frontmatter consistency, heading capitalisation, trailing
whitespace. Useful when several notes are edited in a hurry.

## Optional
- Obsidian Kanban — for the roadmap, if you prefer a board to phase files.
- Calendar — pairs with daily notes.
- Homepage — auto-open Dashboard on launch.
- Tag Wrangler — rename tags across the vault safely.
- QuickAdd — capture a bug or an idea into the right folder without
  navigating. Good on mobile.

## Avoid
- Heavy graph-analysis plugins. The vault is small; the graph is not where
  the insight is.
- Any plugin that requires a paid sync service when the repo already exists.
- Canvas plugins beyond Excalidraw.

## Mobile
Install Obsidian on your phone and open the same vault. Most of this vault
is reference material you want in your pocket during field testing. Disable
heavy plugins on mobile if the app feels slow.

## Related
- Vault Setup
- Dataview Snippets
