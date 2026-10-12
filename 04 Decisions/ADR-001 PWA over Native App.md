---
tags: [adr]
status: accepted
date: 2026-10-09
---

# ADR-001 — PWA over Native App

## Context
The tool must run on both iPhones and Androids used by field staff. Native
development means two codebases, two build pipelines, two store submission
processes, and a $99/year Apple developer account.

The required capabilities are modest: text input, camera, geolocation, local
storage, network writes. All are available to the web platform on both iOS
and Android.

## Options considered

### Option 1 — Native (Swift + Kotlin)
Best platform integration and performance. Highest cost: two codebases, two
review cycles, slow iteration.

### Option 2 — Cross-platform native (React Native / Flutter)
One codebase, near-native performance. Still requires store distribution,
developer accounts, a build toolchain.

### Option 3 — Progressive Web App
One HTML/CSS/JS codebase. Installable to home screen on both platforms.
Instant updates on push. No store review. Camera and geolocation work.
Offline works via service worker.

## Decision
Build a Progressive Web App hosted on GitHub Pages.

## Rationale
The capability gap between PWA and native is irrelevant to this use case.
The cost gap is enormous. Update latency — fixing a field bug in minutes
rather than days — matters more than any native advantage here.

## Consequences

Positive:
- Single codebase, single deploy, zero store overhead.
- Updates reach users instantly on push.
- No developer accounts or fees.
- Trivially testable in a browser.

Negative:
- No iOS push notifications without the 16.4+ installed-PWA path.
- No background location. Not needed.
- iOS PWA storage can be evicted under pressure. Treat IndexedDB as a queue,
  not a store; the repo is the store.
- Users must be told how to add to home screen on iOS.

## Revisit triggers
- A requirement for reliable iOS push notifications.
- A requirement for background location or Bluetooth.
- An organisational policy mandating store-distributed apps.

## Related
- PWA and Offline
- Architecture Overview
