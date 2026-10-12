---
tags: [architecture, data]
---

# Data Model

## Record shape

~~~json
{
  "plate": "ABC1234",
  "color": "white",
  "make": "Nissan",
  "model": "Pathfinder",
  "flag": "watch",
  "notes": "Silver sedan, rear bumper damage.",
  "photo": "photos/ABC1234.jpg",
  "location": { "lat": 40.7128, "lng": -74.0060, "accuracy": 12 },
  "firstSeen": "2026-09-14T09:12:00Z",
  "updated": "2026-10-09T14:30:00Z",
  "updatedBy": "jdoe"
}
~~~

## Enumerations

flag: confirmed, cleared, unknown, suspected, pig.

Enums are closed. Adding a value is a schema change plus an ADR.

## Relationships
None. The model is deliberately flat. One plate, one file, no foreign keys.
Cross-cutting views (nearby, flagged, recently updated) are served by
data/index.json, which is derived.

## Identity
The normalised plate string is the key. No surrogate ID.

## Evolution
- Additive fields are safe. Readers treat absence as null.
- Removing or renaming a field requires a migration script and a versioned
  schema. If this becomes frequent, add a schemaVersion field.
- Never change the meaning of an existing field. Add a new one.
- Multiple vehicles and locations can be saved under one plate, more than two shows drop-down to show all
