#!/usr/bin/env python3
"""Bring records written before plates had a state up to the current format.

Older versions of the app (and any phone still running one) wrote:
  data/plates/ABC1234.json              with no plateState
  "plateAliases": ["ABC1234"]           in the vehicle

Now a plate is state + plate:
  data/plates/XX-ABC1234.json           with "plateState": "XX"
  "plateAliases": ["XX-ABC1234"]

XX means the state is not known; pass --state CA if every legacy plate is from one state.
Safe to run any time: records that are already current are left alone.

Usage: python3 scripts/migrate_plate_state.py [--root PATH] [--state ST] [--dry-run]
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_index  # noqa: E402
from plate_states import KEY_RE, UNKNOWN_STATE, is_valid_state  # noqa: E402

LEGACY_PLATE = re.compile(r"^[A-Z0-9]{1,20}$")
CURRENT_KEY = KEY_RE


def migrate(root: Path, state=UNKNOWN_STATE, dry_run=False):
    moved, aliased = [], []
    for path in sorted((root / "data" / "plates").glob("*.json")):
        if not LEGACY_PLATE.match(path.stem):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        record = {"plate": record["plate"], "plateState": record.get("plateState") or state,
                  **{k: v for k, v in record.items() if k not in ("plate", "plateState")}}
        target = path.with_name(f"{record['plateState']}-{record['plate']}.json")
        if not dry_run:
            if target.exists():
                path.unlink()  # a current record already exists; the legacy one is a duplicate
            else:
                target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                path.unlink()
        moved.append(f"{path.name} -> {target.name}")
    for path in sorted((root / "data" / "vehicles").glob("*.json")):
        vehicle = json.loads(path.read_text(encoding="utf-8"))
        old = vehicle.get("plateAliases", [])
        new = [a if CURRENT_KEY.match(a) else f"{state}-{a}" for a in old]
        if new != old:
            vehicle["plateAliases"] = sorted(set(new))
            if not dry_run:
                path.write_text(json.dumps(vehicle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            aliased.append(path.name)
    if not dry_run and (moved or aliased):
        build_index.main(["--root", str(root)])
    return moved, aliased


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    parser.add_argument("--state", default=UNKNOWN_STATE, help="state to give legacy plates (default XX = unknown)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not is_valid_state(args.state):
        print(f"error: {args.state!r} is not a US state, Canadian province, Mexican state (3 letters), USG/GOV (optionally with a code, GOV-DHS) or XX", file=sys.stderr)
        return 2
    moved, aliased = migrate(args.root, args.state, args.dry_run)
    for line in moved:
        print(("would move " if args.dry_run else "moved ") + line)
    print(f"{len(moved)} plate file(s) and {len(aliased)} vehicle(s) {'would be ' if args.dry_run else ''}updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
