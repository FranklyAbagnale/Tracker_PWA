---
tags: [adr]
status: accepted
date: 2026-10-09
---

# ADR-004 — One File Per Plate Record

## Context
The GitHub contents API replaces an entire file on PUT and guards against
lost updates with a SHA check that fails with 409 when stale. A single large
file makes every write contend for the same SHA.

## Decision
One JSON file per plate at data/plates/<PLATE>.json, plus a derived
data/index.json for list and proximity queries.

## Rationale
Converts a global concurrency problem into a rare per-record one. Write
payload is a few hundred bytes instead of megabytes. Git history becomes
readable per plate.

## Consequences
Positive: minimal conflicts, small writes, legible diffs.
Negative: two artefacts to keep consistent; index must be regenerated.

## Revisit triggers
- Record count above ~10,000.
- Need for atomic multi-record writes.
