---
tags: [adr]
status: accepted
date: 2026-10-09
---

# ADR-003 — JSON over XML

## Context
The initial design used a single plates.xml file. XML parses slower than
JSON in the browser, is more verbose, and forces whole-file rewrites.

## Decision
Use JSON, one file per plate record, plus a derived index.json.

## Rationale
JSON.parse is native and fast. Per-record files diff cleanly in Git. The
verbosity difference matters less than the parse difference, but both point
the same way.

## Consequences
Positive: faster parse, smaller payload, clean diffs, hand-editable.
Negative: XML consumers need a conversion step.

## Revisit triggers
- Need for relational queries the index cannot serve.
- Dataset large enough that per-file overhead dominates.
