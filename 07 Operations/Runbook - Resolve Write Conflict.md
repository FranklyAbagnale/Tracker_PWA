---
tags: [runbook, operations]
---

# Runbook — Resolve Write Conflict

Purpose: handle a 409 that survived the app's single automatic retry.

## Symptom
User reports: "Could not save, another update happened at the same time."
The record appears in Pending uploads.

## Procedure

### 1. Inspect
~~~bash
git log --oneline -10 -- data/plates/<PLATE>.json
git show HEAD:data/plates/<PLATE>.json
~~~

### 2. Reconstruct intent
Get the user's intended values from the pending entry.

### 3. Merge manually
Apply the user's intended changes to the current content, following the
merge rules in Concurrency and Conflicts:
- notes: append with timestamp and attribution
- status, flag, photo, location, updated: incoming wins
- firstSeen: keep the earliest

### 4. Validate and commit
~~~bash
python scripts/validate_records.py --file data/plates/<PLATE>.json
python scripts/build_index.py
git add data/plates/<PLATE>.json data/index.json
git commit -m "resolve: merge concurrent edit on <PLATE>"
git push
~~~

### 5. Clear the pending entry
Tell the user to clear it manually, or provide a Discard pending control in
the app for resolved entries.

## Prevention
Repeated conflicts on one plate indicate either a hot record or a stuck
outbox entry. Check for the latter first.

## Related
- Concurrency and Conflicts
- Known Failure Modes
