---
tags: [requirements, data]
---

# Data Requirements

## Vehicle Record Schema

Vehicle records (`data/vehicles/<VEHICLE_KEY>.json`) are the primary entity for neighborhood watch. One file per vehicle, keyed by an opaque, stable identifier.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| vehicleKey | string | yes | Opaque slug (e.g., `VEH_7a3f9c2`). Primary key. Never changes. |
| displayName | string | yes | User-editable, human-readable description. Grows more accurate over time (e.g., "Grey 2015 Nissan Pathfinder with roof rack"). |
| color | string | yes | white, black, grey, silver, red, blue, green, yellow, brown, orange, gold, purple, etc. |
| make | string | yes | Ford, GM, Nissan, Toyota, Honda, Subaru, Jeep, etc. Common car brands. |
| bodyStyle | string | yes | sedan, suv, truck, van, hatchback, coupe, unknown. |
| model | string | no | Specific model name if known (e.g., "Pathfinder", "F-150"). |
| distinguishing | array | yes | Array of short, searchable tags (e.g., `["roof rack", "dented rear bumper", "aftermarket rims"]`). Critical for matching plateless vehicles. May be empty; the field itself is always present. |
| distinguishingNotes | string | no | Free text for features not captured by tags. Soft cap 500 chars. |
| vin | string | no | Vehicle Identification Number if known. |
| plateAliases | array | yes | Array of plate keys this vehicle has carried, written `<state>-<plate>` (e.g., `["CA-ABC1234", "NV-DLRCMX1"]`). `XX` means the state is not known. Empty array for plateless vehicles. |
| flag | enum | yes | confirmed, suspected, cleared, unknown. Closed enum. |
| sightings | array | yes | Array of sighting records (see Sighting Schema below). At least one sighting required. |
| firstSeen | ISO 8601 | yes | Timestamp of the first sighting. Set on creation, never changed. |
| lastSeen | ISO 8601 | yes | Timestamp of the most recent sighting. Updated on each new sighting. |
| possibleDuplicate | boolean | no | Set to `true` if this vehicle was created as a "not sure" fork during matching. Aids manual deduplication. |
| lastUpdatedBy | enum | no | source, member, resident. Indicates who most recently edited the vehicle record (not a sighting). |

## Sighting Schema

A sighting is a single observation of a vehicle at a location and time. Multiple sightings are stored in the `sightings` array of a vehicle record.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| seenAt | ISO 8601 | yes | Timestamp of observation. |
| location | object | no | `{ "lat": 40.7128, "lng": -74.006, "accuracy": 12 }`. Accuracy in meters (GPS accuracy estimate). Optional if permission denied. |
| plateAtTime | string | no | The plate observed at this sighting, if any. Null if not seen or not present. Does not update vehicle's `plateAliases`; that is explicit. |
| photos | array | no | Array of repo-relative paths (e.g., `["photos/VEH_7a3f9c2_20261115_001.jpg", "photos/VEH_7a3f9c2_20261115_002.jpg"]`). Zero to N photos per sighting. Immutable once stored. |
| notes | string | no | Free-text observation notes. Soft cap 2000 chars. |
| by | enum | yes | resident, member, source. Indicates who/how the sighting was recorded. |

## Plate Record Schema

Every plate has a state. A plate is identified by state + plate, so `CA-ABC1234` and `NV-ABC1234` are different plates. Plate records (`data/plates/<STATE>-<PLATE>.json`, e.g. `CA-ABC1234.json`) are minimal alias records pointing to vehicles, with `plate` (up to 20 letters/digits) and `plateState` (2 letters for a US state or Canadian province, 3 letters for a Mexican state such as `SON`, `USG` or `GOV` with an optional code such as `GOV-DHS`, `XX` = unknown; see `schema/README.md`). Because a state can contain a dash, a plate key is split at its last dash. One file per plate currently in use.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| plate | string | yes | Normalized plate (e.g., `ABC1234`, `DLR_CARMAX`). Uppercase, alphanumeric only. Filename key. |
| plateType | enum | yes | standard, dealer, temporary, vanity. Closed enum. |
| currentVehicleKey | string | yes | Which vehicle this plate is currently on. Points to a vehicle record. |
| firstSeen | ISO 8601 | yes | Timestamp when this plate was first associated with a vehicle. |
| updated | ISO 8601 | yes | Timestamp of last update. |

### Plate Normalization

- Uppercase all characters.
- Remove all non-alphanumeric characters (spaces, hyphens, apostrophes).
- Example: `ab-123 cd` → `AB123CD`.
- Filename is `<PLATE>.json` where `<PLATE>` contains only `[A-Z0-9]`.
- If a jurisdiction uses special characters (e.g., European plates), document and extend the allowed character set via ADR.

### Plate Lifecycle

- When a new plate is sighted on a vehicle, a new plate record is created pointing to that vehicle's `vehicleKey`.
- The vehicle's `plateAliases` array is updated to include the new plate.
- If the same plate is later observed on a *different* vehicle, the plate record's `currentVehicleKey` is updated to point to the new vehicle.
- The old vehicle's `plateAliases` retains the plate in history.

## Index File

`data/index.json` is a derived projection of all vehicles for fast reads. It is **never authoritative**; any conflict resolves in favor of the vehicle records.

### Index Schema

```json
{
  "generated": "2026-10-10T14:30:00Z",
  "vehicleCount": 1284,
  "vehicles": [
    {
      "vehicleKey": "VEH_7a3f9c2",
      "displayName": "Grey 2015 Nissan Pathfinder with roof rack",
      "color": "grey",
      "make": "Nissan",
      "bodyStyle": "suv",
      "flag": "confirmed",
      "distinguishing": ["roof rack", "dented rear bumper"],
      "lastPlate": "ABC1234",
      "lastSighting": "2026-11-15T21:10:00Z",
      "lastLat": 40.7128,
      "lastLng": -74.0060,
      "lastAccuracy": 12
    }
  ]
}
```

### Index Regeneration

- Updated by the app on every sync (one entry merged per save); no workflow.
- `scripts/build_index.py` rebuilds it from scratch (owner repair tool, run locally).
- Sorted by `lastSighting` descending (most recent first) for efficient prefix scans.

## Photo Storage

Photos are stored as files in `photos/` and referenced by path in sighting records.

| Aspect | Policy |
| --- | --- |
| Format | JPEG (.jpg), WebP (.webp), or PNG (.png). |
| Filename | `photos/<VEHICLE_KEY>_<ISO_DATE>_<SEQUENCE>.jpg`. Example: `photos/VEH_7a3f9c2_20261115_001.jpg`. |
| Client-side limits | Downscale to ≤ 1600 px on long edge, ≤ 500 KB, lossily compressed before upload. |
| Retention | Immutable once stored. Photo removal is a manual repo action. |

(Photo storage ceiling and external object storage transition covered by a future ADR when record count or file size triggers limits.)

## Identity and Versioning

- The vehicle key is the primary key and **never changes** to ensure references remain stable.
- Additive fields are always safe. Readers treat absence as null.
- Removing or renaming a field requires a migration script and a versioned schema. If this becomes frequent, add a `schemaVersion` field to records.
- Never change the meaning of an existing field. Add a new one.
- Schema version and structure tracked in `schema/vehicle.schema.json` (JSON Schema format).

## Retention Policy

(Detailed in a future ADR, but outlined here for schema planning.)

- Vehicle records are never hard-deleted by the app. A resident can mark a vehicle "cleared", but the record remains.
- Sightings within a vehicle record are retained indefinitely by default, but:
  - Sightings older than 14 days are hidden from nearby search (ADR-011).
  - A future ADR will define hard-deletion for sightings (e.g., after 1 year) with an explicit retention policy and operator script.
- Hard deletion of records or sightings is a manual repository action, preserving Git history for audit.

## Related

- [[ADR-009 Vehicle as Primary Entity]]
- [[ADR-010 Multiple Photos Per Vehicle Record]]
- [[ADR-011 Confirmed Vehicle Local Search Retention]]
- [[schema/vehicle.schema.json]] — JSON Schema definition
- [[schema/plate.schema.json]] — JSON Schema definition
