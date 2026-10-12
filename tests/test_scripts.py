import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_index = load("build_index")
validate_records = load("validate_records")


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "schema", self.tmp / "schema")
        for d in ("data/vehicles", "data/plates", "data/samples", "photos"):
            (self.tmp / d).mkdir(parents=True)
        self.sample_vehicle = json.loads((ROOT / "data/samples/vehicle-example.json").read_text())
        self.sample_plate = json.loads((ROOT / "data/samples/plate-example.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel, data):
        (self.tmp / rel).write_text(json.dumps(data), encoding="utf-8")

    def install_pair(self):
        self.write("data/vehicles/VEH_7a3f9c2b.json", self.sample_vehicle)
        self.write("data/plates/CA-ABC1234.json", self.sample_plate)

    def test_repo_samples_and_committed_data_validate(self):
        errors, _, _, _ = validate_records.validate(ROOT)
        self.assertEqual(errors, [])

    def test_samples_are_actually_checked(self):
        bad = dict(self.sample_vehicle, flag="pig")
        self.write("data/samples/vehicle-bad.json", bad)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("vehicle-bad.json" in e for e in errors), errors)

    def test_valid_pair_passes(self):
        self.install_pair()
        errors, warnings, nv, np_ = validate_records.validate(self.tmp)
        self.assertEqual((errors, nv, np_), ([], 1, 1))
        self.assertEqual(warnings, [])

    def pair_with_state(self, state, plate="ABC1234"):
        key = f"{state}-{plate}"
        for old in (self.tmp / "data" / "plates").glob("*.json"):
            old.unlink()
        self.write("data/vehicles/VEH_7a3f9c2b.json", dict(self.sample_vehicle, plateAliases=[key]))
        self.write(f"data/plates/{key}.json", dict(self.sample_plate, plate=plate, plateState=state))
        return validate_records.validate(self.tmp)

    def test_mexican_federal_and_coded_states_validate(self):
        for state, plate in (("SON", "ABC1234"), ("BCN", "1ABC"), ("GOV", "12345"), ("USG", "G42"), ("GOV-DHS", "12345"), ("USG-G42", "X1")):
            errors, warnings, nv, np_ = self.pair_with_state(state, plate)
            self.assertEqual((errors, warnings, nv, np_), ([], [], 1, 1), state)

    def test_unknown_state_codes_are_errors(self):
        for state in ("ZZZ", "GOVX", "GOV-", "GOV-TOOLONGCODE", "gov-dhs", "C"):
            errors, _, _, _ = self.pair_with_state(state)
            self.assertTrue(errors, state)

    def test_alias_with_unknown_state_is_an_error(self):
        self.write("data/vehicles/VEH_7a3f9c2b.json", dict(self.sample_vehicle, plateAliases=["CA-ABC1234", "ZZZ-ABC1234"]))
        self.write("data/plates/CA-ABC1234.json", self.sample_plate)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("known state code" in e for e in errors), errors)

    def test_filename_must_match_key(self):
        self.write("data/vehicles/VEH_00000000.json", self.sample_vehicle)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("does not match filename" in e for e in errors), errors)

    def test_plate_pointing_at_missing_vehicle_is_an_error(self):
        self.write("data/plates/CA-ABC1234.json", self.sample_plate)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("missing vehicle" in e for e in errors), errors)

    def test_plate_not_listed_in_aliases_is_an_error(self):
        self.write("data/vehicles/VEH_7a3f9c2b.json", dict(self.sample_vehicle, plateAliases=[]))
        self.write("data/plates/CA-ABC1234.json", self.sample_plate)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("plateAliases" in e for e in errors), errors)

    def test_missing_photo_is_a_warning_not_an_error(self):
        v = json.loads(json.dumps(self.sample_vehicle))
        v["sightings"][0]["photos"] = ["photos/VEH_7a3f9c2b_20261009T091500_001.jpg"]
        self.write("data/vehicles/VEH_7a3f9c2b.json", v)
        self.write("data/plates/CA-ABC1234.json", self.sample_plate)
        errors, warnings, _, _ = validate_records.validate(self.tmp)
        self.assertEqual(errors, [])
        self.assertTrue(any("missing photo" in w for w in warnings), warnings)

    def test_observer_is_accepted_but_capped(self):
        v = json.loads(json.dumps(self.sample_vehicle))
        v["sightings"][0]["observer"] = "Alex Kim"
        v["lastUpdatedBy"] = "Alex Kim"
        self.write("data/vehicles/VEH_7a3f9c2b.json", v)
        self.write("data/plates/CA-ABC1234.json", self.sample_plate)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertEqual(errors, [])

        v["sightings"][0]["observer"] = "x" * 41
        self.write("data/vehicles/VEH_7a3f9c2b.json", v)
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("observer" in e for e in errors), errors)

    def test_unknown_field_is_rejected(self):
        self.write("data/vehicles/VEH_7a3f9c2b.json", dict(self.sample_vehicle, surprise=1))
        errors, _, _, _ = validate_records.validate(self.tmp)
        self.assertTrue(any("surprise" in e for e in errors), errors)

    def test_build_index_projects_entries_and_is_idempotent(self):
        self.install_pair()
        self.assertEqual(build_index.main(["--root", str(self.tmp)]), 0)
        index = json.loads((self.tmp / "data/index.json").read_text())
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["vehicleKey"], "VEH_7a3f9c2b")
        self.assertEqual(index[0]["location"], {"lat": 34.148, "lng": -118.145})  # newest located sighting
        self.assertEqual(index[0]["lastSeen"], "2026-10-10T14:32:00.000Z")
        self.assertEqual(index[0]["plateAliases"], ["CA-ABC1234"])
        v = self.sample_vehicle
        for k in ("color", "make", "model", "bodyStyle"):   # description fields for the app's search
            if v.get(k) and v.get(k) != "unknown":
                self.assertEqual(index[0][k], v[k])
            else:
                self.assertNotIn(k, index[0])
        self.assertNotIn("unknown", [index[0].get(k) for k in ("color", "make", "model", "bodyStyle")])

        before = (self.tmp / "data/index.json").read_text()
        build_index.main(["--root", str(self.tmp)])
        self.assertEqual((self.tmp / "data/index.json").read_text(), before)

    def test_build_index_skips_corrupt_records(self):
        self.install_pair()
        (self.tmp / "data/vehicles/VEH_deadbeef.json").write_text("{not json")
        entries, skipped = build_index.build(self.tmp)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(skipped), 1)


if __name__ == "__main__":
    unittest.main()


class AuditTests(unittest.TestCase):
    def test_summary_and_by_person(self):
        audit = load("audit_observers")
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "data/vehicles").mkdir(parents=True)
            v = json.loads((ROOT / "data/samples/vehicle-example.json").read_text())
            v["sightings"][0]["observer"] = "Alex"
            v["sightings"][1]["observer"] = "Sam"
            v["sightings"].append(dict(v["sightings"][1], id="S_aaaaaaaa", observer="sam", notes="again"))
            (tmp / "data/vehicles/VEH_7a3f9c2b.json").write_text(json.dumps(v))

            stats = audit.summarise(tmp)
            self.assertEqual(stats["Alex"]["sightings"], 1)
            self.assertEqual(stats["Sam"]["sightings"], 1)
            self.assertEqual(stats["sam"]["sightings"], 1)   # names are kept as typed
            self.assertEqual(len(audit.by_person(tmp, "SAM")), 2)  # lookup ignores case
            self.assertEqual(audit.main(["--root", str(tmp), "--who", "nobody"]), 1)
        finally:
            shutil.rmtree(tmp)


class MigratePlateStateTests(unittest.TestCase):
    def test_legacy_records_are_upgraded_and_current_ones_left_alone(self):
        mp = load("migrate_plate_state")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for d in ("data/vehicles", "data/plates"):
                (root / d).mkdir(parents=True)
            (root / "schema").symlink_to(ROOT / "schema")
            vehicle = json.loads((ROOT / "data/samples/vehicle-example.json").read_text())
            vehicle["plateAliases"] = ["ABC1234", "NV-DLR0001"]
            (root / "data/vehicles/VEH_7a3f9c2b.json").write_text(json.dumps(vehicle))
            plate = {"plate": "ABC1234", "plateType": "standard", "currentVehicleKey": "VEH_7a3f9c2b",
                     "firstSeen": vehicle["firstSeen"], "updated": vehicle["lastSeen"]}
            (root / "data/plates/ABC1234.json").write_text(json.dumps(plate))
            moved, aliased = mp.migrate(root, "CA")
            self.assertEqual((len(moved), len(aliased)), (1, 1))
            self.assertTrue((root / "data/plates/CA-ABC1234.json").exists())
            self.assertFalse((root / "data/plates/ABC1234.json").exists())
            self.assertEqual(json.loads((root / "data/plates/CA-ABC1234.json").read_text())["plateState"], "CA")
            self.assertEqual(json.loads((root / "data/vehicles/VEH_7a3f9c2b.json").read_text())["plateAliases"], ["CA-ABC1234", "NV-DLR0001"])
            self.assertEqual(mp.migrate(root, "CA"), ([], []))  # idempotent
