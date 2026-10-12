---
tags: [usecase]
id: UC-03
actor: Field user
priority: S
status: draft
---

# UC-03 — Flag a Plate

## Goal
Mark a plate as needing attention without changing its record otherwise.

## Main flow
1. User taps Flag on a result card or capture form.
2. App presents options: confirmed, cleared, unknown, suspected, pig.
3. User selects one.
4. User optionally adds a short reason into notes.
5. App writes the updated record.
6. Result card re-renders with the new flag.

## Alternate flows
A1 Adding a flag. User selects flag. up to 3 displayed in priority order confirmed, suspected, pig, cleared, unknown;
firstSeen and all other fields untouched.

A2 Flag on an unknown plate. No record exists. App routes to UC-02 with the
flag pre-selected and status defaulted to unknown.

## Acceptance criteria
- [ ] Flag change is a single-tap operation from the result card, single click selection from visible list.
- [ ] Flag appears in nearby results without a reload.
- [ ] Flag values constrained by the schema; free text not accepted.
