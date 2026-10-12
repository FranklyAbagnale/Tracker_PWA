---
tags: [usecase]
id: UC-06
actor: Data owner
priority: M
status: draft
---

# UC-06 — Sync External Data

## Goal
Bring newly collected data from an external source into the repository
without consuming GitHub Actions minutes.

## Main flow
1. Owner runs: python scripts/push_changes.py --source ./export.csv
2. Script parses the source into normalised records matching the schema.
3. Script validates every record; invalid records reported and skipped.
4. Script regenerates data/index.json.
5. Script compares each generated record against the working tree.
   Unchanged files are left alone.
6. Script stages only added and modified files.
7. Script commits with a generated summary message.
8. Script pushes to main.
9. GitHub Pages publishes the new data automatically.

## Alternate flows

A1 Dry run. --dry-run prints the diff summary and exits without writing.

A2 Large batch. More than 500 changed files: split into multiple commits of
500 files each.

A3 Validation failures. Any invalid record aborts the run unless
--skip-invalid is passed; a report is written to reports/.

A4 Nothing changed. Script exits 0 with "no changes" and creates no commit.

## Acceptance criteria
- [ ] Re-running with no source changes creates no commit.
- [ ] Invalid input never reaches main.
- [ ] data/index.json is consistent with the record set after every run.
- [ ] A sync of 1000 records completes in under 60 s locally.
