#!/usr/bin/env python3
"""Generate (or remove) a deterministic sample data set for phone testing.

The set is built to exercise every branch of the app: each ranking tier, the
14-day hiding rule, the radius cut-off, a vehicle with no location, a vehicle
with no plate, a multi-plate vehicle, a vehicle that has moved, and record text
containing HTML. Every record is placed relative to a centre point and to "now",
so the expected Local-search results are the same wherever and whenever you
generate it (see "09 Testing/Phone Test with Sample Data.md").

All plates are obviously fake (TST*/DLRTST*). Every record is tagged
lastUpdatedBy = "sample-data", which is how --clean finds and removes them
without touching real data.

Usage:
  python3 scripts/generate_sample_data.py                      # Pasadena, now
  python3 scripts/generate_sample_data.py --center 40.71,-74.0 # test elsewhere
  python3 scripts/generate_sample_data.py --clean              # remove sample data

Regenerating first removes the previous sample set, so it never accumulates.
Photos are placeholder JPEGs and need Pillow (pip install pillow); without it
the records are generated with no photos.
"""

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_index  # noqa: E402
from plate_states import plate_key  # noqa: E402

TAG = "sample-data"
DEFAULT_CENTER = "34.1478,-118.1445"  # Pasadena City Hall
HOUR, DAY = timedelta(hours=1), timedelta(days=1)

# slug, colour, make, model, body, plates [(plate, type)] (state: see PLATE_STATE, default CA), distinguishing, sightings
# sighting: (age before now, distance m, bearing deg or None for no location, flag, notes)
# The LAST sighting listed is the newest. Distances are from the centre point.
# Not every sample plate is from California, so state handling gets exercised.
PLATE_STATE = {"DLRTST1": "NV", "TST1002": "XX"}  # NV: out of state; XX: state not known
VEHICLES = [
    ("recent-confirmed", "red", "Honda", "Civic", "sedan", [("TST1001", "standard")],
     ["cracked taillight", "bumper sticker"],
     [(26 * HOUR, 120, 0, "unknown", "First noticed overnight."),
      (2 * HOUR, 120, 0, "confirmed", "Still here, same spot.")]),
    ("recent-suspected-a", "white", "Ford", "F-150", "truck", [("TST1002", "standard")],
     ["ladder rack", "toolbox"],
     [(20 * HOUR, 400, 90, "suspected", "Parked facing the wrong way.")]),
    ("recent-suspected-b", "black", "Tesla", "Model 3", "sedan", [("TST1003", "standard")],
     ["tinted windows"],
     [(40 * HOUR, 850, 180, "suspected", "Near the edge of the search area.")]),
    ("older-confirmed", "silver", "Toyota", "Camry", "sedan", [("TST2001", "standard")],
     ["dented rear bumper"],
     [(5 * DAY, 300, 270, "unknown", None), (4 * DAY, 300, 270, "confirmed", "Confirmed by neighbour.")]),
    ("older-suspected", "blue", "Subaru", "Outback", "suv", [("TST2002", "standard")],
     ["roof rack", "kayak mount"],
     [(10 * DAY, 700, 45, "suspected", "Seen once.")]),
    ("unknown-recent", "green", "Jeep", "Wrangler", "suv", [("TST3001", "standard")],
     ["soft top", "spare tire cover"],
     [(1 * DAY, 200, 135, "unknown", "Flag not set yet.")]),
    ("unknown-older", "grey", "Nissan", "Pathfinder", "suv", [("TST3002", "standard")],
     ["roof rack", "dented rear bumper"],
     [(6 * DAY, 500, 315, "unknown", None)]),
    ("cleared-recent", "yellow", "Mini", "Cooper", "hatchback", [("TST4001", "standard")],
     ["black roof"],
     [(4 * DAY, 150, 225, "suspected", "Looked odd."), (3 * DAY, 150, 225, "cleared", "Resident's guest.")]),
    ("cleared-old", "white", "Chevrolet", "Express", "van", [("TST4002", "standard")],
     ["company logo removed"],
     [(30 * DAY, 600, 20, "cleared", "Delivery contractor.")]),
    ("pigs-recent", "black", "Dodge", "Charger", "sedan", [("TST4101", "standard")],
     ["push bar", "roof light bar"],
     [(2 * DAY, 250, 160, "pigs", "Marked unit parked at the corner.")]),
    ("pigs-old", "white", "Chevrolet", "Tahoe", "suv", [("TST4102", "standard")],
     ["push bar"],
     [(25 * DAY, 900, 300, "pigs", "Older than 14 days: still listed, only confirmed vehicles age out.")]),
    ("hidden-old", "orange", "Dodge", "Challenger", "coupe", [("TST5001", "standard")],
     ["racing stripes"],
     [(20 * DAY, 250, 90, "confirmed", "Confirmed and older than 14 days: must NOT appear in Local.")]),
    ("out-of-radius", "purple", "Kia", "Soul", "hatchback", [("TST6001", "standard")],
     ["fuzzy dice"],
     [(3 * HOUR, 2500, 0, "confirmed", "2.5 km away: outside the 1 km radius.")]),
    ("no-location", "black", "BMW", "3 Series", "sedan", [("TST7001", "standard")],
     ["aftermarket wheels"],
     [(1 * HOUR, None, None, "suspected", "Saved without location: findable by plate only.")]),
    ("no-plate", "brown", "Ford", "Transit", "van", [],
     ["scaffolding on roof"],
     [(5 * HOUR, 300, 200, "unknown", "Photo-first capture, plate not visible.")]),
    ("multi-plate", "silver", "Honda", "Accord", "sedan", [("TST8001", "standard"), ("DLRTST1", "dealer")],
     ["dealer frame"],
     [(30 * HOUR, 350, 330, "unknown", "Showed a dealer plate."), (6 * HOUR, 350, 330, "suspected", "Now on a standard plate.")]),
    ("moved", "tan", "Toyota", "Tacoma", "truck", [("TST9001", "standard")],
     ["lift kit"],
     [(3 * DAY, 2200, 0, "unknown", "Earlier sighting far away (outside radius)."),
      (8 * HOUR, 450, 200, "suspected", "Now nearby: the index must use THIS location.")]),
    ("html-text", "teal", "Hyundai", "Elantra <i>GT</i>", "sedan", [("TST9002", "standard")],
     ['<b>bold</b> sticker', '"quoted" decal'],
     [(12 * HOUR, 280, 15, "unknown", "<script>alert(1)</script> & ampersand")]),
]

COLORS = {
    "red": (200, 50, 50), "white": (235, 235, 235), "black": (40, 40, 45), "silver": (170, 175, 180),
    "blue": (50, 90, 190), "green": (50, 140, 80), "grey": (130, 130, 135), "yellow": (235, 200, 40),
    "orange": (230, 120, 30), "purple": (130, 70, 160), "brown": (110, 75, 50), "tan": (200, 175, 130),
    "teal": (30, 140, 140),
}


def digest(text):
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def offset(center, meters, bearing_deg):
    """Move `meters` from `center` along a compass bearing."""
    lat0, lng0 = center
    d_north = meters * math.cos(math.radians(bearing_deg))
    d_east = meters * math.sin(math.radians(bearing_deg))
    lat = lat0 + d_north / 111_320
    lng = lng0 + d_east / (111_320 * math.cos(math.radians(lat0)))
    return round(lat, 5), round(lng, 5)


def photo_path(key, when, n):
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"photos/{key}_{stamp}_{n:03d}.jpg"


def display_name(color, make, model):
    return " ".join(p for p in (color.capitalize(), make, model) if p)


def make_photo(path, name, plate, color):
    """Placeholder JPEG: a flat colour with the car's name and a SAMPLE banner."""
    from PIL import Image, ImageDraw, ImageFont  # imported lazily: optional dependency

    def font(size):
        try:
            return ImageFont.load_default(size=size)  # Pillow >= 10.1
        except TypeError:
            return ImageFont.load_default()
    img = Image.new("RGB", (640, 480), COLORS.get(color, (120, 120, 120)))
    d = ImageDraw.Draw(img)
    light = sum(COLORS.get(color, (120, 120, 120))) > 400
    ink = (20, 20, 20) if light else (245, 245, 245)
    d.rectangle([0, 0, 640, 70], fill=(180, 20, 20))
    d.text((20, 18), "SAMPLE DATA - NOT A REAL VEHICLE", fill=(255, 255, 255), font=font(26))
    d.text((20, 190), name, fill=ink, font=font(48))
    d.text((20, 260), plate or "(no plate visible)", fill=ink, font=font(36))
    img.save(path, "JPEG", quality=70, optimize=True)


def clean(root):
    """Remove every record tagged as sample data, with its plates and photos."""
    removed = {"vehicles": 0, "plates": 0, "photos": 0}
    vehicles_dir = root / "data" / "vehicles"
    keys = set()
    for path in sorted(vehicles_dir.glob("*.json")):
        try:
            vehicle = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if vehicle.get("lastUpdatedBy") != TAG:
            continue
        keys.add(vehicle["vehicleKey"])
        for sighting in vehicle.get("sightings", []):
            for photo in sighting.get("photos", []):
                target = root / photo
                if target.is_file():
                    target.unlink()
                    removed["photos"] += 1
        path.unlink()
        removed["vehicles"] += 1
    for path in sorted((root / "data" / "plates").glob("*.json")):
        try:
            plate = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if plate.get("currentVehicleKey") in keys:
            path.unlink()
            removed["plates"] += 1
    return removed


def generate(root, center, now, with_photos=True):
    clean(root)
    (root / "data" / "vehicles").mkdir(parents=True, exist_ok=True)
    (root / "data" / "plates").mkdir(parents=True, exist_ok=True)
    (root / "photos").mkdir(parents=True, exist_ok=True)

    try:
        import PIL  # noqa: F401
        photos_ok = with_photos
    except ImportError:
        photos_ok = False
        if with_photos:
            print("Pillow not installed: generating records without photos", file=sys.stderr)

    count_photos = 0
    for slug, color, make, model, body, plates, features, sightings in VEHICLES:
        key = f"VEH_{digest('sample:' + slug)}"
        built = []
        for i, (age, dist, bearing, flag, notes) in enumerate(sightings):
            when = now - age
            is_newest = i == len(sightings) - 1
            location = None
            if dist is not None:
                lat, lng = offset(center, dist, bearing)
                location = {"lat": lat, "lng": lng}
            photos = []
            if photos_ok and (is_newest or i == 0) and slug != "no-location":
                path = photo_path(key, when, 1)
                make_photo(root / path, display_name(color, make, model), plates[0][0] if plates else None, color)
                photos.append(path)
                count_photos += 1
            built.append({
                "id": f"S_{digest(f'{slug}:{i}')}",
                "timestamp": iso(when),
                "location": location,
                "photos": photos,
                "flag": flag,
                "notes": notes,
                "source": TAG,
            })

        vehicle = {
            "vehicleKey": key,
            "displayName": display_name(color, make, model),
            "color": color,
            "make": make,
            "model": model,
            "bodyStyle": body,
            "distinguishing": features,
            "plateAliases": [plate_key(PLATE_STATE.get(p, "CA"), p) for p, _ in plates],
            "flag": built[-1]["flag"],
            "sightings": built,
            "firstSeen": built[0]["timestamp"],
            "lastSeen": built[-1]["timestamp"],
            "possibleDuplicate": False,
            "lastUpdatedBy": TAG,
        }
        (root / "data" / "vehicles" / f"{key}.json").write_text(
            json.dumps(vehicle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        for plate, plate_type in plates:
            record = {
                "plate": plate,
                "plateState": PLATE_STATE.get(plate, "CA"),
                "plateType": plate_type,
                "currentVehicleKey": key,
                "firstSeen": vehicle["firstSeen"],
                "updated": vehicle["lastSeen"],
            }
            (root / "data" / "plates" / f"{plate_key(PLATE_STATE.get(plate, 'CA'), plate)}.json").write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8")

    build_index.main(["--root", str(root)])
    return len(VEHICLES), count_photos


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    parser.add_argument("--center", default=DEFAULT_CENTER, help="'lat,lng' to build the set around")
    parser.add_argument("--now", help="ISO timestamp to treat as 'now' (default: current time)")
    parser.add_argument("--no-photos", action="store_true")
    parser.add_argument("--clean", action="store_true", help="remove sample data and exit")
    args = parser.parse_args(argv)

    if args.clean:
        removed = clean(args.root)
        build_index.main(["--root", str(args.root)])
        print(f"removed {removed['vehicles']} vehicles, {removed['plates']} plates, {removed['photos']} photos")
        return 0

    try:
        lat, lng = (float(x) for x in args.center.split(","))
    except ValueError:
        parser.error("--center must look like 34.1478,-118.1445")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        parser.error("--center is out of range")
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)

    n_vehicles, n_photos = generate(args.root, (lat, lng), now, with_photos=not args.no_photos)
    print(f"generated {n_vehicles} sample vehicles and {n_photos} photos around {lat},{lng}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
