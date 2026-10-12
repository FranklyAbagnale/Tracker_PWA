import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load("generate_sample_data")
validate_records = load("validate_records")
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
CENTER = (34.1478, -118.1445)


class SampleDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "schema", self.tmp / "schema")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def files(self, pattern):
        return sorted(p.name for p in self.tmp.glob(pattern))

    def test_generated_set_passes_validation(self):
        gen.generate(self.tmp, CENTER, NOW)
        errors, warnings, nv, np_ = validate_records.validate(self.tmp)
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(nv, len(gen.VEHICLES))

    def test_generation_is_deterministic(self):
        gen.generate(self.tmp, CENTER, NOW, with_photos=False)
        first = {p.name: p.read_text() for p in self.tmp.glob("data/vehicles/*.json")}
        gen.generate(self.tmp, CENTER, NOW, with_photos=False)
        second = {p.name: p.read_text() for p in self.tmp.glob("data/vehicles/*.json")}
        self.assertEqual(first, second)

    def test_regenerating_replaces_rather_than_accumulates(self):
        gen.generate(self.tmp, CENTER, NOW)
        n_photos = len(self.files("photos/*.jpg"))
        later = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        gen.generate(self.tmp, CENTER, later)
        self.assertEqual(len(self.files("data/vehicles/*.json")), len(gen.VEHICLES))
        self.assertEqual(len(self.files("photos/*.jpg")), n_photos)  # old timestamps removed

    def test_clean_removes_only_sample_records(self):
        gen.generate(self.tmp, CENTER, NOW)
        real = json.loads((ROOT / "data/samples/vehicle-example.json").read_text())
        (self.tmp / "data/vehicles" / "VEH_7a3f9c2b.json").write_text(json.dumps(real))
        (self.tmp / "data/plates" / "ABC1234.json").write_text((ROOT / "data/samples/plate-example.json").read_text())
        (self.tmp / "photos" / "real.jpg").write_bytes(b"\xff\xd8real")

        removed = gen.clean(self.tmp)
        self.assertEqual(removed["vehicles"], len(gen.VEHICLES))
        self.assertEqual(self.files("data/vehicles/*.json"), ["VEH_7a3f9c2b.json"])
        self.assertEqual(self.files("data/plates/*.json"), ["ABC1234.json"])
        self.assertEqual(self.files("photos/*.jpg"), ["real.jpg"])

    def test_covers_each_ranking_case(self):
        gen.generate(self.tmp, CENTER, NOW, with_photos=False)
        vehicles = [json.loads(p.read_text()) for p in self.tmp.glob("data/vehicles/*.json")]
        by_name = {v["displayName"]: v for v in vehicles}
        ages = {n: (NOW - datetime.fromisoformat(v["lastSeen"].replace("Z", "+00:00"))).total_seconds() / 3600
                for n, v in by_name.items()}
        flags = {v["flag"] for v in vehicles}
        self.assertEqual(flags, {"confirmed", "suspected", "unknown", "cleared", "pigs"})
        self.assertTrue(any(f == "confirmed" and a > 14 * 24 for (f, a) in ((by_name[n]["flag"], ages[n]) for n in by_name)))
        self.assertTrue(any(v["flag"] == "pigs" and ages[v["displayName"]] > 14 * 24 for v in vehicles))
        self.assertTrue(any(v["flag"] == "cleared" and ages[v["displayName"]] > 14 * 24 for v in vehicles))
        self.assertTrue(any(not v["plateAliases"] for v in vehicles))
        self.assertTrue(any(len(v["plateAliases"]) > 1 for v in vehicles))
        self.assertTrue(any(all(s["location"] is None for s in v["sightings"]) for v in vehicles))
        self.assertTrue(all(v["lastUpdatedBy"] == "sample-data" for v in vehicles))

    def test_offsets_land_at_the_requested_distance(self):
        import math
        lat, lng = gen.offset(CENTER, 850, 180)
        dlat = (lat - CENTER[0]) * 111_320
        dlng = (lng - CENTER[1]) * 111_320 * math.cos(math.radians(CENTER[0]))
        self.assertAlmostEqual(math.hypot(dlat, dlng), 850, delta=2)
        self.assertLess(lat, CENTER[0])  # bearing 180 = south

    def test_index_uses_newest_located_sighting_for_moved_vehicle(self):
        gen.generate(self.tmp, CENTER, NOW, with_photos=False)
        index = json.loads((self.tmp / "data/index.json").read_text())
        moved = next(e for e in index if e["displayName"] == "Tan Toyota Tacoma")
        self.assertLess(abs(moved["location"]["lat"] - CENTER[0]), 0.01)  # ~450 m, not the 2.2 km sighting


if __name__ == "__main__":
    unittest.main()
