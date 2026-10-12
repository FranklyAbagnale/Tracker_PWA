#!/usr/bin/env python3
"""Regenerate data/index.json from data/vehicles/*.json.

The index is a derived projection used for fast local search; vehicle records
are the source of truth. The output is deterministic (sorted, no timestamps) so
a rebuild with no data changes produces no diff and no commit.

Mirrors indexEntryFromVehicle() in web/js/vehicle-manager.js.

Usage: python3 scripts/build_index.py [--root PATH]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def search_fields(vehicle):
    """Descriptive fields kept in the index so the app can search by description (mirrors searchFieldsOf in the app)."""
    out = {}
    for k in ("color", "make", "model", "bodyStyle"):
        v = vehicle.get(k)
        if isinstance(v, str) and v and v != "unknown":
            out[k] = v
    if isinstance(vehicle.get("year"), int) and not isinstance(vehicle.get("year"), bool):
        out["year"] = vehicle["year"]
    feats = [f for f in (vehicle.get("distinguishing") or []) if f and f != "unknown"]
    if feats:
        out["features"] = feats
    return out


def entry_for(vehicle):
    located = [
        s for s in vehicle.get("sightings", [])
        if isinstance(s.get("location"), dict)
        and isinstance(s["location"].get("lat"), (int, float))
        and isinstance(s["location"].get("lng"), (int, float))
    ]
    latest = max(located, key=lambda s: parse_ts(s.get("timestamp")), default=None)
    return {
        "vehicleKey": vehicle["vehicleKey"],
        "displayName": vehicle.get("displayName", ""),
        "flag": vehicle.get("flag", "unknown"),
        "lastSeen": vehicle.get("lastSeen"),
        "location": (
            {"lat": latest["location"]["lat"], "lng": latest["location"]["lng"]}
            if latest else None
        ),
        "plateAliases": vehicle.get("plateAliases", []),
        **search_fields(vehicle),
    }


def build(root: Path):
    entries, skipped = [], []
    for path in sorted((root / "data" / "vehicles").glob("*.json")):
        try:
            vehicle = json.loads(path.read_text(encoding="utf-8"))
            if vehicle.get("vehicleKey") != path.stem:
                raise ValueError(f"vehicleKey does not match filename {path.name}")
            entries.append(entry_for(vehicle))
        except (ValueError, KeyError, OSError) as exc:
            skipped.append((path.name, str(exc)))
    entries.sort(key=lambda e: e["vehicleKey"])
    return entries, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    args = parser.parse_args(argv)

    entries, skipped = build(args.root)
    for name, reason in skipped:
        print(f"skipped {name}: {reason}", file=sys.stderr)

    out = args.root / "data" / "index.json"
    text = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    if out.exists() and out.read_text(encoding="utf-8") == text:
        print(f"index unchanged ({len(entries)} vehicles)")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out.relative_to(args.root)} ({len(entries)} vehicles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
