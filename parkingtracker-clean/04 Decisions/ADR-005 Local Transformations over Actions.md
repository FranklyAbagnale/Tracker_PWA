---
tags: [adr]
status: accepted
date: 2026-10-09
---

# ADR-005 — Local Transformations over Actions

## Context
Actions minutes are finite on private repos. A workflow running every 15
minutes consumes 2,880 minutes per month, over budget on its own.

Note: a git pull or git push by a local Git client does NOT consume Actions
minutes. Only workflow jobs on GitHub-hosted runners do.

## Decision
Perform all data transformations locally and push results as ordinary
commits. No scheduled workflows. A single validation workflow on
pull_request only.

## Consequences
Positive: zero Actions minutes, dry runs, fast iteration, visible failures.
Negative: refresh reliability depends on operator discipline.

## Revisit triggers
- Genuine need for unattended high-frequency sync.
- Move to a public repository.
