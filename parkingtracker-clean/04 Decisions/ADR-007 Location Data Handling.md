---
tags:
  - adr
status: accepted
date: 2026-10-09
---

# ADR-007 — Location Data Handling

## Status
Proposed. Needs a decision, and possibly legal review, before field use.

## Context
Location is attached to plate records to enable the nearby-plates feature.
Location data about staff movements is personal data about those staff, and
location data about vehicles is potentially sensitive in aggregate.

## Options considered

### Option 1 — Full precision, always captured
Store raw lat/lng at full precision whenever permission is granted.
- Pro: maximum utility for proximity queries and mapping.
- Con: precise historical movement data accumulates. Higher breach impact.

### Option 2 — Coarsened at write time
Round to 3 decimal places (~100 m) before storing.
- Pro: materially lower sensitivity.
- Con: proximity queries become fuzzy. At 100 m rounding, a 50 m radius
  query is meaningless.

### Option 3 — Full precision stored, coarsened on read/export
Store what the device gives, apply rounding only in views shared outside the
trusted circle.
- Pro: full utility internally, reduced exposure externally.
- Con: the raw data still exists and can leak. Requires discipline.

### Option 4 — No location at all
Drop the feature.
- Pro: zero risk.
- Con: loses a genuinely useful capability.

## Recommendation
Option 3 for a private repository with a small trusted group. Option 2 if the
repository is public, or if field staff have not given informed consent for
location capture.

Regardless of choice, these apply unconditionally:
- Capture only on explicit save. No background polling.
- A declined permission is a valid state; the record saves without location.
- Never place coordinates in URLs or share links.
- Document a retention period and honour it.

## Decision
Option 3

## Revisit triggers
- Repository visibility change.
- Any change to who can read the data.
- Applicable privacy regulation coming into scope.

## Related
- Security and Privacy
- Geolocation and Proximity

## Update (2026-10-10)

Precision raised from 3 to 4 decimal places (~11 m) at the owner's request, so nearby distances are tighter.
The repository is still public, so locations stay rounded; records saved earlier keep their 3-decimal values.
