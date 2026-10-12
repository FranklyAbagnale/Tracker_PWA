#!/usr/bin/env python3
"""Who wrote what? Summarise records by the observer name stamped on each sighting.

With one shared GitHub token every commit looks the same, so the name each
person entered at sign-in is the audit trail. Use this to see who has been
active, or to list one person's sightings before reverting them.

Usage:
  python3 scripts/audit_observers.py                  # one line per observer
  python3 scripts/audit_observers.py --who "Sam"      # that person's sightings
  python3 scripts/audit_observers.py --root PATH
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_sightings(root: Path):
    for path in sorted((root / "data" / "vehicles").glob("*.json")):
        try:
            vehicle = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for s in vehicle.get("sightings", []):
            yield vehicle, s


def summarise(root: Path):
    stats = defaultdict(lambda: {"sightings": 0, "vehicles": set(), "photos": 0, "first": None, "last": None})
    for vehicle, s in load_sightings(root):
        who = s.get("observer") or "(unattributed)"
        e = stats[who]
        e["sightings"] += 1
        e["vehicles"].add(vehicle["vehicleKey"])
        e["photos"] += len(s.get("photos", []))
        ts = s.get("timestamp", "")
        e["first"] = ts if e["first"] is None or ts < e["first"] else e["first"]
        e["last"] = ts if e["last"] is None or ts > e["last"] else e["last"]
    return stats


def by_person(root: Path, who: str):
    rows = []
    for vehicle, s in load_sightings(root):
        if (s.get("observer") or "").lower() == who.lower():
            rows.append((s.get("timestamp", ""), vehicle["vehicleKey"], vehicle.get("displayName", ""),
                         s.get("flag", ""), s.get("notes") or "", s.get("photos", [])))
    return sorted(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    parser.add_argument("--who", help="list this observer's sightings (case-insensitive)")
    args = parser.parse_args(argv)

    if args.who:
        rows = by_person(args.root, args.who)
        if not rows:
            print(f"no sightings by {args.who!r}")
            return 1
        for ts, key, name, flag, notes, photos in rows:
            print(f"{ts}  {key}  {name}  [{flag}]  {notes}  {' '.join(photos)}".rstrip())
        return 0

    stats = summarise(args.root)
    if not stats:
        print("no sightings found")
        return 0
    width = max(len(w) for w in stats)
    for who, e in sorted(stats.items(), key=lambda kv: kv[1]["last"] or "", reverse=True):
        print(f"{who:<{width}}  {e['sightings']:>3} sightings  {len(e['vehicles']):>3} vehicles  "
              f"{e['photos']:>3} photos  last {e['last']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
