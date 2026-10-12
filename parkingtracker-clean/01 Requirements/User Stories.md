---
tags: [requirements, stories]
---

# User Stories

## Field capture

As a field user, I want to type a plate and see everything already known
about it so that I do not re-log a vehicle I already handled.

Acceptance: lookup returns flag, color, make, model, photo, notes, and last-seen time,
or an explicit "not found, create?" prompt.

As a field user, I want to attach a photo and a note in the same motion as
entering the plate so that I do not context-switch.

Acceptance: photo and notes are part of the same save action, one commit.

As a field user, I want my location captured automatically when I save so
that I can later find what I logged in this area.

Acceptance: coordinates attached when permission granted; record saves fine
without them.

## Review

As a field user, I want to see which "cleared" plates have already been logged nearby so that I can avoid duplicate work.

Acceptance: nearby list sorted by distance, each row showing plate, status,
flag, and distance.

## Data ownership

As the data owner, I want to regenerate records from my master dataset and
push only what changed so that I do not burn Actions minutes.

Acceptance: a local script diffs, stages, and commits only modified files.

As the data owner, I want every change traceable so that I can undo a bad
import.

Acceptance: one commit per logical change, with a descriptive message.
