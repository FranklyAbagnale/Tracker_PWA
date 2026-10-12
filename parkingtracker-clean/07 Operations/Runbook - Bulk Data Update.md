---
tags: [runbook, operations]
---

# Runbook — Bulk Data Update

Purpose: bring externally collected data into the repository without
consuming Actions minutes.

Frequency: as needed, typically daily or weekly.

Prerequisites: repository cloned locally, Python 3.10+, jsonschema installed,
GITHUB_TOKEN set in the environment.

## Procedure

### 1. Prepare
~~~bash
cd /path/to/repo
git checkout main
git pull
git status
~~~
If git status is not clean, stop. Commit or stash before syncing.

### 2. Dry run
~~~bash
python scripts/push_changes.py --source ./export.csv --dry-run
~~~
Review the summary: added, updated, unchanged, invalid. If the numbers look
wrong, fix the source before continuing.

### 3. Full run
~~~bash
python scripts/push_changes.py --source ./export.csv
~~~
The script validates each record, regenerates data/index.json, stages only
changed files, commits with a summary message, and pushes to main.

### 4. Verify
~~~bash
git log -1 --stat | head -40
~~~
Confirm the commit contains only expected files. Confirm data/index.json is
included and consistent.

### 5. Publish check
Wait ~60 seconds, then load the Pages URL and confirm the new data appears.

## Rollback
~~~bash
git revert HEAD
git push
~~~
Reverting is safe. Records are small and independent. Do not force-push.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| no changes but data differs | normalisation mismatch | check plate normalisation rule |
| Validation failures | schema drift in source | inspect reports/ output |
| Push rejected | remote ahead | git pull --rebase then retry |
| Index inconsistent | script interrupted | re-run build_index.py |

## Related
- UC-06 Sync External Data
- ADR-005 Local Transformations over Actions
