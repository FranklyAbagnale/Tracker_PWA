#!/usr/bin/env python3
"""Validate data records against the schemas and check cross-references.

Checks:
  * data/vehicles/*.json  -> schema/vehicle.schema.json
  * data/plates/*.json    -> schema/plate.schema.json
  * data/samples/*.json   -> the matching schema (vehicle-* / plate-*)
  * filename matches vehicleKey / <plateState>-<plate>
  * every plate record points at an existing vehicle, and that vehicle lists
    the plate in plateAliases
  * every photo path a sighting references exists under photos/ (warning only,
    because the app uploads photos before the record that references them but
    a partial upload can still leave a dangling reference)
  * data/index.json is well-formed (staleness is not an error: the index is
    rebuilt after each push)

Exit status is 1 if any error is found. Requires: pip install jsonschema

Usage: python3 scripts/validate_records.py [--root PATH]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plate_states import is_valid_state, split_plate_key  # noqa: E402

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover
    sys.exit("jsonschema is required: pip install jsonschema")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def schema_errors(validator, data):
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]


def validate(root: Path):
    errors, warnings = [], []

    def make_validator(name):
        return Draft202012Validator(load_json(root / "schema" / name), format_checker=FormatChecker())

    vehicle_v = make_validator("vehicle.schema.json")
    plate_v = make_validator("plate.schema.json")

    vehicles, plates = {}, {}

    def read(path: Path, validator, label):
        try:
            data = load_json(path)
        except ValueError as exc:
            errors.append(f"{path.relative_to(root)}: invalid JSON ({exc})")
            return None
        for msg in schema_errors(validator, data):
            errors.append(f"{path.relative_to(root)}: {msg}")
        return data

    for path in sorted((root / "data" / "vehicles").glob("*.json")):
        data = read(path, vehicle_v, "vehicle")
        if isinstance(data, dict):
            if data.get("vehicleKey") != path.stem:
                errors.append(f"{path.relative_to(root)}: vehicleKey {data.get('vehicleKey')!r} does not match filename")
            vehicles[path.stem] = data

    for path in sorted((root / "data" / "plates").glob("*.json")):
        data = read(path, plate_v, "plate")
        if isinstance(data, dict):
            if not is_valid_state(data.get("plateState")):
                errors.append(f"{path.relative_to(root)}: plateState {data.get('plateState')!r} is not a known state code")
            expected = f"{data.get('plateState')}-{data.get('plate')}"
            if expected != path.stem:
                errors.append(f"{path.relative_to(root)}: plateState + plate ({expected}) does not match filename")
            plates[path.stem] = data

    for path in sorted((root / "data" / "samples").glob("*.json")):
        validator = plate_v if path.name.startswith("plate") else vehicle_v
        read(path, validator, "sample")

    for plate, record in plates.items():
        key = record.get("currentVehicleKey")
        vehicle = vehicles.get(key)
        if vehicle is None:
            errors.append(f"data/plates/{plate}.json: points at missing vehicle {key}")
        elif plate not in vehicle.get("plateAliases", []):
            errors.append(f"data/plates/{plate}.json: {key} does not list {plate} in plateAliases")

    for key, vehicle in vehicles.items():
        for alias in vehicle.get("plateAliases", []):
            if split_plate_key(alias) is None:
                errors.append(f"data/vehicles/{key}.json: alias {alias!r} does not start with a known state code")
            elif alias not in plates:
                warnings.append(f"data/vehicles/{key}.json: alias {alias} has no plate record")
        for sighting in vehicle.get("sightings", []):
            for photo in sighting.get("photos", []):
                if not (root / photo).is_file():
                    warnings.append(f"data/vehicles/{key}.json: missing photo {photo}")

    index_path = root / "data" / "index.json"
    if index_path.exists():
        try:
            index = load_json(index_path)
            if not isinstance(index, list) or not all(isinstance(e, dict) and "vehicleKey" in e for e in index):
                errors.append("data/index.json: must be an array of objects with a vehicleKey")
        except ValueError as exc:
            errors.append(f"data/index.json: invalid JSON ({exc})")

    return errors, warnings, len(vehicles), len(plates)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    args = parser.parse_args(argv)

    errors, warnings, n_vehicles, n_plates = validate(args.root)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"checked {n_vehicles} vehicles, {n_plates} plates: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
