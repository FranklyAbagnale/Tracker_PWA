---
tags: [requirements]
---

# Functional Requirements

M = must have, S = should have, C = could have.

## Capture
- FR-01 M — Large plate text field.
- FR-02 M — Normalise case, strip spaces/hyphens.
- FR-03 M - Attach color make model
- FR-04 S — Attach a photo.
- FR-05 S — Attach notes.
- FR-06 S — Set flag (confirmed, cleared, unknown, suspected, pig).
- FR-07 M — Record capture timestamp.
- FR-08 S — Record location if permitted.

## Lookup
- FR-09 M — Show flag, photo, notes for a plate.
- FR-10 M — Tolerate minor formatting differences.
- FR-11 M — Report not-found and offer to create.
- FR-12 S — Show plates previously recorded nearby.

## Data
- FR-14 M — One JSON file per plate under data/plates/.
- FR-15 M — Lightweight data/index.json for list and nearby queries.
- FR-16 M — Writes go to GitHub via REST API, one commit per change.
- FR-17 M — Retry stale-SHA writes against fresh content.
- FR-18 S — Queue offline writes, flush on reconnect.
- FR-19 S — Bulk imports generated outside GitHub, pushed as commits.
