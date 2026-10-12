---
tags: [references, glossary]
---

# Glossary

ADR — Architecture Decision Record. A short document capturing one decision,
its context, and its consequences.

ALPR — Automatic License Plate Recognition. Machine reading of plates from
images. Out of scope for v1.

App shell — The minimal HTML/CSS/JS needed to render the interface, cached
by the service worker so the app opens instantly and offline.

Bounding box — A cheap rectangular filter applied before precise distance
calculation.

Commit SHA (file) — In the GitHub contents API, a hash identifying the
current version of a file. Not the same as a Git commit SHA, though both are
hashes.

Derived artefact — Data generated from a source of truth and never edited by
hand. data/index.json is derived.

Haversine — Formula for great-circle distance between two lat/lng points.

Index (data/index.json) — A flat projection of all plate records containing
only the fields list views need.

Normalisation (plate) — Converting user input to the canonical key form:
uppercase, alphanumeric only.

Outbox — A local queue of writes that have not yet succeeded.

PAT — Personal Access Token. A GitHub credential.

PWA — Progressive Web App. A website with a manifest and service worker that
can be installed to the home screen and run offline.

Record — One plate's JSON file in data/plates/.

SHA conflict (409) — The error returned when a PUT supplies a stale file SHA.

Source of truth — The authoritative copy of the data. Here, the record files
in data/plates/.

Stale-while-revalidate — A caching strategy that serves cached content
immediately and refreshes it in the background.
