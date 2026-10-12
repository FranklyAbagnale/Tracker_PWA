"""scripts/plate_states.py against tests/fixtures/state_cases.json.

The same cases are checked against the web app (tests/states.test.mjs) and against
tools/import.html (tests/e2e_csv_tool.py), so the three implementations cannot drift apart.
"""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("plate_states", ROOT / "scripts" / "plate_states.py")
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)
CASES = json.loads((ROOT / "tests" / "fixtures" / "state_cases.json").read_text(encoding="utf-8"))


class PlateStateTests(unittest.TestCase):
    def test_parse_cases(self):
        for text, code, how in CASES["parse"]:
            self.assertEqual(ps.parse_state(text), (code, how), text)

    def test_normalize_cases(self):
        for text, code in CASES["normalize"]:
            self.assertEqual(ps.normalize_state(text), code, text)

    def test_key_cases(self):
        for key, parts in CASES["keys"]:
            self.assertEqual(ps.split_plate_key(key), tuple(parts) if parts else None, key)

    def test_plate_key(self):
        self.assertEqual(ps.plate_key("GOV-DHS", "12 345"), "GOV-DHS-12345")
        self.assertEqual(ps.plate_key("SON", "abc-1"), "SON-ABC1")
        self.assertEqual(ps.plate_key("Atlantis", "ABC1"), "XX-ABC1")
        self.assertEqual(ps.plate_key("CA", ""), "")

    def test_lists(self):
        self.assertEqual(len(ps.MX_STATES), 32)
        self.assertEqual(len(set(ps.STATES)), len(ps.STATES), "no duplicate codes")
        self.assertTrue(all(re.fullmatch(r"[A-Z]{3}", c) for c in ps.MX_STATES))
        self.assertTrue({"SON", "USG", "GOV", "XX", "CA", "BC", "QC"} <= set(ps.STATES))
        for name, code in ps.STATE_NAMES.items():
            self.assertIn(code, ps.STATES, name)
        for alias, code in ps.STATE_ALIASES.items():
            self.assertIn(code, ps.STATES, alias)


if __name__ == "__main__":
    unittest.main()


class XmlStateTextTests(unittest.TestCase):
    """The importer's free-text "State: ..." reader knows the new states."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        spec2 = importlib.util.spec_from_file_location("migrate_xml_to_json", ROOT / "scripts" / "migrate_xml_to_json.py")
        cls.m = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(cls.m)

    def test_text_forms(self):
        for text, code in (("State: Sonora", "SON"), ("State: Baja California Sur.", "BCS"), ("state=Nuevo León", "NLE"),
                           ("State: USG G42", "USG-G42"), ("State: gov-dhs.", "GOV-DHS"), ("State: GOV", "GOV"),
                           ("State: GOVERNMENT", "XX"), ("State: GOV Plate seen", "GOV"), ("State: CA 7ABC", "CA")):
            self.assertEqual(self.m.state_from_text(text)[0], code, text)
