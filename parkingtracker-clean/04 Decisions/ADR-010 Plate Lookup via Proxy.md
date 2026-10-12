---
tags: [adr]
status: accepted
date: 2026-10-10
---

# ADR-010 — Plate lookup through a proxy, vehicle details only

## Status
Accepted. Built provider-neutral: the shipped adapter is a stub until a provider is chosen.

## Context
The owner wants make, model and year for California plates. There is no public California API: DMV record
access is limited to approved requesters under the federal Drivers Privacy Protection Act. The practical source is
a commercial plate-to-VIN reseller, which needs an API key. The app is a static PWA and the repository is
public, so a key cannot live in the app.

## Decision
1. **Vehicle details only.** The proxy returns year, make and model. Owner, address and registration data are
   never requested, and the proxy's sanitiser drops anything else a provider sends, VIN included.
2. **A small proxy holds the key** (`api/`). The same handler runs as a Cloudflare Worker (free tier, no Actions
   minutes) or as a Node service on an internal host. It accepts only callers whose GitHub token can write to the
   repository, caches answers (30 days found, 1 day not found) and can cap provider calls per day.
3. **Provider-neutral.** One adapter file per provider (`api/providers/`); switching providers touches no app code.
   `stub` (default) answers "not configured"; `mock` is for tests.
4. **Check what is on file first.** A lookup runs automatically only for a California plate that is not listed, a
   listed vehicle whose make or model is unknown, or a plate typed into the new-vehicle form that is not on file.
   A listed vehicle with known details gets a manual "Check against registration data" button instead.
5. **Store the answer only when it agrees.** The vehicle record gets a `plateLookup` field
   (plate, year, make, model, checkedAt) only when make and model were both entered or filled and match the
   answer. A mismatch is shown to the person and stored nowhere. No VIN is stored.
6. **Off by default.** An empty `LOOKUP_URL` in `web/js/config.js` hides the feature entirely.

## Consequences
- Needs a provider account and a one-time deployment; see `07 Operations/Runbook - Plate Lookup.md`.
- Providers' terms on storing results in a public repository were not readable when this was written. Read them
  before turning the feature on, and consider making the repository private first. Year, make and model are
  low-sensitivity, but they are still tied to a plate.
- Each lookup that is not cached costs the provider's per-call price. The on-file check, the cache and
  `DAILY_LIMIT` keep that bounded.
- Colour is not returned by these providers, so the form fills make and model only.
