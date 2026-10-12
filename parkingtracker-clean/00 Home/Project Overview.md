---
tags: [overview]
---

# Project Overview

A phone-friendly tool for logging parked vehicles by license plate, with
location context, photos, notes, and flags, backed by a Git repository
instead of a database server.

## Who uses it
- Field user — enters or looks up plates on a phone.
- Data owner — controls the master dataset, runs bulk imports.
- External collector — produces plate data elsewhere, feeds it in.
- Reviewer — reviews data changes within a time period

## Hard constraints
1. Works on iPhone Safari and Android Chrome without an app store.
2. Tolerates poor or no connectivity.
3. GitHub Actions minutes are scarce, bulk work happens locally.
4. Writes must not corrupt or clobber concurrent edits.

## Success criteria
- Plate lookup under 2 s on 4G.
- Field capture under 30 s.
- No lost writes under normal two-user concurrency.
- Zero Actions minutes consumed in a typical week.
