"""Re-importing an XML that holds old and new records, after the data was edited."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_migrate_xml import Base, record, xml_of, m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def tok(n):
    return f"S_{m.digest('xml:' + n)}"


class Reimport(Base):
    def first(self, *recs):
        return self.run_xml(xml_of(("A", list(recs))))

    def vfile(self, key):
        return self.root / "data" / "vehicles" / f"{key}.json"

    def read(self, path):
        return json.loads(Path(path).read_text())

    def only_vehicle(self):
        (v,) = self.vehicles()
        return v

    def second(self, *recs, **kw):
        return self.run_xml(xml_of(("A", list(recs))), **kw)

    def test_untouched_data_gets_only_new_records(self):
        self.first(record("1"), record("2", plate="ZZZ999"))
        before = {p.name: p.read_text() for p in (self.root / "data").rglob("*.json")}
        counts, report = self.second(record("1"), record("2", plate="ZZZ999"), record("3", stamp="SAT JAN 3 2026 10:00:00 PST"))
        self.assertEqual(counts["already_imported"], 2)
        self.assertEqual([r["alert_token"] for r in report["new_records"]], ["3"])
        after = {p.name: p.read_text() for p in (self.root / "data").rglob("*.json")}
        changed = {n for n in after if before.get(n) != after[n]}
        self.assertEqual(len(changed), 2, changed)  # the ABC1234 vehicle and its plate, nothing else
        self.assertEqual(len(self.vehicles()), 2)

    def test_identical_reimport_writes_nothing(self):
        self.first(record("1"), record("2", plate="ZZZ999"))
        before = {str(p): p.read_text() for p in (self.root / "data").rglob("*.json")}
        counts, report = self.second(record("1"), record("2", plate="ZZZ999"))
        self.assertEqual((counts["vehicles"], counts["sightings"], counts["already_imported"]), (0, 0, 2))
        self.assertEqual(before, {str(p): p.read_text() for p in (self.root / "data").rglob("*.json")})

    def test_edited_sighting_and_vehicle_survive(self):
        self.first(record("1"))
        v = self.only_vehicle()
        v["sightings"][0]["notes"] = "my edit"
        v["sightings"][0]["flag"] = "cleared"
        v["flag"] = "cleared"
        v["color"] = "teal"
        self.vfile(v["vehicleKey"]).write_text(json.dumps(v, indent=2) + "\n")
        self.second(record("1"), record("9", stamp="SAT JAN 3 2025 10:00:00 PST"))  # older new sighting
        v = self.only_vehicle()
        s = {x["id"]: x for x in v["sightings"]}
        self.assertEqual(s[tok("1")]["notes"], "my edit")
        self.assertEqual(s[tok("1")]["flag"], "cleared")
        self.assertEqual((v["color"], v["flag"]), ("teal", "cleared"))  # older sighting does not move the flag
        self.assertIn(tok("9"), s)

    def test_newer_sighting_moves_flag_and_is_reported(self):
        self.first(record("1"))
        v = self.only_vehicle(); v["flag"] = "cleared"
        self.vfile(v["vehicleKey"]).write_text(json.dumps(v, indent=2) + "\n")
        _, report = self.second(record("1"), record("9", stamp="SAT JAN 3 2027 10:00:00 PST"))
        self.assertEqual(self.only_vehicle()["flag"], "confirmed")
        self.assertEqual(report["flag_changed"][0]["from"], "cleared")

    def test_plate_state_changed_in_data_tool_does_not_duplicate(self):
        self.first(record("1"))
        v = self.only_vehicle(); key = v["vehicleKey"]
        # data tool: XX-ABC1234 becomes CA-ABC1234 (new plate file, old one removed, alias updated)
        old = self.root / "data" / "plates" / "XX-ABC1234.json"
        plate = json.loads(old.read_text()); old.unlink()
        plate["plateState"] = "CA"
        (self.root / "data" / "plates" / "CA-ABC1234.json").write_text(json.dumps(plate, indent=2) + "\n")
        v["plateAliases"] = ["CA-ABC1234"]
        self.vfile(key).write_text(json.dumps(v, indent=2) + "\n")
        _, report = self.second(record("1"), record("5", stamp="SAT JAN 3 2026 10:00:00 PST"))
        self.assertEqual(len(self.vehicles()), 1)
        self.assertEqual(sorted(p.name for p in (self.root / "data" / "plates").glob("*.json")), ["CA-ABC1234.json"])
        v = self.only_vehicle()
        self.assertEqual(v["plateAliases"], ["CA-ABC1234"])
        self.assertEqual(len(v["sightings"]), 2)

    def test_vehicle_merged_into_another_gets_new_sightings_there(self):
        self.first(record("1"), record("2", plate="ZZZ999"))
        by_plate = {v["plateAliases"][0]: v for v in self.vehicles()}
        keep, drop = by_plate["XX-ABC1234"], by_plate["XX-ZZZ999"]
        keep["sightings"] += drop["sightings"]
        keep["plateAliases"] = sorted(keep["plateAliases"] + drop["plateAliases"])
        self.vfile(keep["vehicleKey"]).write_text(json.dumps(keep, indent=2) + "\n")
        self.vfile(drop["vehicleKey"]).unlink()
        (self.root / "data" / "plates" / "XX-ZZZ999.json").unlink()
        self.second(record("1"), record("2", plate="ZZZ999"), record("7", plate="ZZZ999", stamp="SAT JAN 3 2026 10:00:00 PST"))
        (v,) = self.vehicles()
        self.assertEqual(len(v["sightings"]), 3)
        self.assertFalse((self.root / "data" / "plates" / "XX-ZZZ999.json").exists())

    def test_xml_without_state_joins_the_plate_that_has_one_now(self):
        self.first(record("1"))
        v = self.only_vehicle()
        old = self.root / "data" / "plates" / "XX-ABC1234.json"
        plate = json.loads(old.read_text()); old.unlink(); plate["plateState"] = "CA"
        (self.root / "data" / "plates" / "CA-ABC1234.json").write_text(json.dumps(plate, indent=2) + "\n")
        v["plateAliases"] = ["CA-ABC1234"]
        self.vfile(v["vehicleKey"]).write_text(json.dumps(v, indent=2) + "\n")
        self.vfile(v["vehicleKey"]).unlink()
        v["vehicleKey"] = "VEH_00000001"
        (self.root / "data" / "vehicles" / "VEH_00000001.json").write_text(json.dumps(v, indent=2) + "\n")
        plate["currentVehicleKey"] = "VEH_00000001"
        (self.root / "data" / "plates" / "CA-ABC1234.json").write_text(json.dumps(plate, indent=2) + "\n")
        self.second(record("1"), record("5", stamp="SAT JAN 3 2026 10:00:00 PST"))
        self.assertEqual(len(self.vehicles()), 1)
        self.assertEqual(len(self.only_vehicle()["sightings"]), 2)

    def test_plate_type_edit_survives(self):
        self.first(record("1"))
        p = self.root / "data" / "plates" / "XX-ABC1234.json"
        d = json.loads(p.read_text()); d["plateType"] = "vanity"; p.write_text(json.dumps(d, indent=2) + "\n")
        self.second(record("1"), record("5", stamp="SAT JAN 3 2026 10:00:00 PST"))
        self.assertEqual(json.loads(p.read_text())["plateType"], "vanity")

    def test_known_records_are_not_geocoded_again(self):
        self.first(record("1"))
        geocoder = m.Geocoder(provider=lambda q: (_ for _ in ()).throw(AssertionError("geocoded " + q)))
        self.second(record("1"), geocoder=geocoder)

    def test_media_added_later_keeps_edits(self):
        self.first(record("1", media="media/a/one.png"))
        v = self.only_vehicle()
        v["sightings"][0]["notes"] = v["sightings"][0]["notes"] + "\nmy line"
        self.vfile(v["vehicleKey"]).write_text(json.dumps(v, indent=2) + "\n")
        from PIL import Image
        (self.media / "media" / "a").mkdir(parents=True)
        Image.new("RGB", (40, 30), "red").save(self.media / "media" / "a" / "one.png")
        self.second(record("1", media="media/a/one.png"), media_root=self.media)
        s = self.only_vehicle()["sightings"][0]
        self.assertEqual(len(s["photos"]), 1)
        self.assertTrue((self.root / s["photos"][0]).is_file())
        self.assertIn("my line", s["notes"])
        self.assertNotIn("Legacy media", s["notes"])

    def test_check_accounts_for_every_record(self):
        counts, report = self.first(record("1"), record("1", comments="again"), record("2", plate="ZZZ999"))
        c = report["check"]
        self.assertTrue(c["complete"])
        self.assertEqual((c["records_read"], c["new"], c["already_imported"], c["repeated_in_file"]), (3, 2, 0, 1))
        counts, report = self.second(record("1"), record("2", plate="ZZZ999"), record("3", stamp="SAT JAN 3 2026 10:00:00 PST"))
        c = report["check"]
        self.assertTrue(c["complete"])
        self.assertEqual((c["records_read"], c["new"], c["already_imported"]), (3, 1, 2))
        self.assertEqual(c["new_date_range"][0][:10], "2026-01-03")
        self.assertEqual(sorted(r["result"] for r in report["records"]), ["already imported", "already imported", "new"])
        counts, report = self.second(record("1"), record("2", plate="ZZZ999"), record("3", stamp="SAT JAN 3 2026 10:00:00 PST"))
        self.assertEqual((report["check"]["new"], report["check"]["already_imported"]), (0, 3))

    def test_repo_validators_pass_after_reimport(self):
        self.first(record("1"))
        self.second(record("1"), record("5", stamp="SAT JAN 3 2026 10:00:00 PST"), record("6", plate="NOPLATE"))
        for script in ("build_index.py", "validate_records.py"):
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--root", str(self.root)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
