---
tags: [runbook, operations]
---

# Runbook — Recover from a Bad Commit

Purpose: undo a data commit that introduced incorrect records.

## Decision: revert or repair?
- Few records affected, obvious fix -> repair in place with a new commit.
- Many records affected, or the source was wrong -> revert the commit.
- Sensitive data was committed -> revert and treat as an incident. The data
  remains in history and must be assumed exposed.

## Revert
~~~bash
git log --oneline -20
git revert <sha>
python scripts/build_index.py
git add data/index.json
git commit --amend --no-edit
git push
~~~

Never force-push main on a shared repository. Reverting preserves history and
keeps every device's clone consistent.

## Repair
~~~bash
# fix the affected files
python scripts/validate_records.py
python scripts/build_index.py
git add -A data/
git commit -m "fix: correct records for <scope>"
git push
~~~

## After any recovery
- [ ] data/index.json regenerated and committed.
- [ ] App loads and lookups return correct data.
- [ ] Root cause recorded in Known Failure Modes.
- [ ] If the cause was a script, add a validation check so it cannot recur.

## Related
- Runbook - Bulk Data Update
- Test Plan
