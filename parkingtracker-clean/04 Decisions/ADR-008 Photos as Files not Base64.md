---
tags: [adr]
status: accepted
date: 2026-10-09
---

# ADR-008 — Photos as Files, not Base64

## Context
Photos must be attached to plate records. Two storage shapes are possible:
embed the image in the record as a base64 string, or store it as a separate
binary file and reference it by path.

## Options considered

### Option 1 — Base64 inside the record
Self-contained records. One fetch gets everything.
- Con: ~33% size inflation. Diffs unreadable walls of base64. Every read
  loads the full image into memory even when only the status is wanted.

### Option 2 — Separate file, path in record
photo: "photos/ABC1234.jpg"
- Pro: record stays small and diffable. Images cached independently by the
  service worker and the CDN. Thumbnails become possible.
- Con: two uploads per capture, and the record can reference a missing file
  if the upload is partial.

## Decision
Store photos as separate files under photos/, referenced by relative path.
Upload the photo before the record that references it.

## Rationale
Record size is the deciding factor. Lookups are frequent and often only need
status and flag; forcing an image through that path would make the common
case slow to serve the uncommon one.

## Consequences

Positive:
- Small, fast, diffable records.
- Independent caching and CDN behaviour for images.
- Thumbnails are straightforward.
- Photos can be moved to object storage later without touching the record
  shape — only the path prefix changes.

Negative:
- Two API calls per capture with a photo.
- Orphaned photos possible if the record write fails after the photo upload.
  Cleaned up by an occasional reconciliation script.

## Revisit triggers
- A need for atomic photo-plus-record writes.
- Migration to object storage.

## Related
- Photo Handling
- Performance and Caching
