import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import migrate_xml_to_json as m  # noqa: E402
import validate_records  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "sample_export.xml"


def record(token, plate="ABC1234", make="Black Ford Explorer", stamp="FRI JAN 2 2026 10:00:00 PST",
           media="", comments="seen", address="1 MAIN ST", extra=""):
    return (f"<record><alert_token>{token}</alert_token><media>{media}</media>"
            f"<vehicle_license>{plate}</vehicle_license><address>{address}</address><guest>1</guest>"
            f"<vehicle_make>{make}</vehicle_make><month>JAN</month><day>2</day><year>2026</year>"
            f"<comments>{comments}</comments><datestamp>{stamp}</datestamp>{extra}</record>")


def xml_of(*groups, decl='<?xml version="1.0" encoding="utf-16" standalone="yes" ?>'):
    body = "".join(f"<plate_file_{name}>{''.join(recs)}</plate_file_{name}>" for name, recs in groups)
    return f"{decl}<db>{body}</db>"


class FakeProvider:
    """Stands in for the geocoding service; records what was asked."""
    def __init__(self, table=None, down=False):
        self.table, self.down, self.calls = table or {}, down, []

    def __call__(self, query):
        self.calls.append(query)
        if self.down:
            raise m.GeocodeUnavailable("offline")
        return self.table.get(query.upper())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        (self.root / "schema").symlink_to(ROOT / "schema")
        self.media = Path(self.tmp.name) / "media"
        self.media.mkdir()

    def write(self, text, name="in.xml"):
        path = Path(self.tmp.name) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return path

    def run_xml(self, text, **kw):
        return m.convert(self.write(text), self.root, **kw)

    def vehicles(self):
        return [json.loads(p.read_text()) for p in sorted((self.root / "data" / "vehicles").glob("*.json"))]

    def validate(self):
        errors, warnings, *_ = validate_records.validate(self.root)
        return errors, warnings


class ParsingTests(unittest.TestCase):
    def rows(self, text):
        return list(m.parse_xml(m.read_xml_text(text.encode("utf-8"))))

    def test_declared_utf16_but_plain_ascii_still_parses(self):
        self.assertEqual(len(self.rows(xml_of(("A", [record("1")])))), 1)

    def test_real_utf16_with_bom_parses(self):
        data = xml_of(("A", [record("1")])).encode("utf-16")
        self.assertEqual(len(list(m.parse_xml(m.read_xml_text(data)))), 1)

    def test_entities_and_doctype_are_refused(self):
        with self.assertRaises(m.ImportErrorXml):
            m.read_xml_text(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><db>&a;</db>')

    def test_malformed_xml_is_a_clean_error(self):
        with self.assertRaises(m.ImportErrorXml):
            list(m.parse_xml("<db><record><alert_token>1</alert_token>"))  # cut off

    def test_any_layout_is_found(self):
        flat = "<db><record><alert_token>1</alert_token></record><record><alert_token>2</alert_token></record></db>"
        deep = "<a><b><c><sighting><vehicle_license>XYZ1</vehicle_license></sighting></c></b></a>"
        bare = "<record><alert_token>9</alert_token></record>"
        self.assertEqual(len(self.rows(flat)), 2)
        self.assertEqual(len(self.rows(deep)), 1)
        self.assertEqual(len(self.rows(bare)), 1)

    def test_names_are_case_insensitive_and_aliases_work(self):
        (_, fields, extras), = self.rows("<DB><Record><ALERT_TOKEN>5</ALERT_TOKEN><Plate>abc1</Plate>"
                                        "<Make>Red Honda Civic</Make><Date>2026-01-02T10:00:00Z</Date></Record></DB>")
        self.assertEqual((fields["alert_token"], fields["vehicle_license"], fields["vehicle_make"]), ("5", "abc1", "Red Honda Civic"))
        self.assertEqual(extras, [])

    def test_unknown_elements_attributes_and_nesting_become_extras(self):
        (_, fields, extras), = self.rows('<db><record id="x7"><alert_token>1</alert_token><guest>1</guest>'
                                        '<tags><t>a</t><t>b</t></tags><empty></empty></record></db>')
        self.assertIn(("id", "x7"), extras)
        self.assertIn(("guest", "1"), extras)
        self.assertIn(("tags", "a b"), extras)
        self.assertNotIn("empty", dict(extras))

    def test_make_split(self):
        self.assertEqual(m.parse_make("Black Ford Explorer"), ("black", "Ford", "Explorer"))
        self.assertEqual(m.parse_make("Dark Blue Honda Civic"), ("dark blue", "Honda", "Civic"))
        self.assertEqual(m.parse_make("Gray Land Rover Defender 90"), ("grey", "Land Rover", "Defender 90"))
        self.assertEqual(m.parse_make("Toyota"), ("unknown", "Toyota", None))
        self.assertEqual(m.parse_make(""), ("unknown", "Unknown", None))

    def test_timestamps(self):
        t = lambda stamp, **extra: m.parse_timestamp({"datestamp": stamp, **extra}, m.TZ_OFFSETS)
        self.assertEqual((m.iso(t("FRI JAN 2 2026 10:00:00 PST")[0]), t("FRI JAN 2 2026 10:00:00 PST")[1]), ("2026-01-02T18:00:00.000Z", None))
        self.assertEqual(m.iso(t("SAT JUL 4 2026 10:00:00 PDT")[0]), "2026-07-04T17:00:00.000Z")
        self.assertEqual(m.iso(t("2026-01-02T10:00:00-08:00")[0]), "2026-01-02T18:00:00.000Z")
        self.assertEqual(m.iso(t("2026-01-02 10:00:00")[0]), "2026-01-02T10:00:00.000Z")
        self.assertEqual(m.iso(t("1767380400")[0]), "2026-01-02T19:00:00.000Z")
        self.assertEqual(m.iso(t("1767380400000")[0]), "2026-01-02T19:00:00.000Z")

    def test_timestamp_fallbacks_never_raise(self):
        when, note = m.parse_timestamp({"datestamp": "garbage", "month": "JAN", "day": "6", "year": "2026"}, m.TZ_OFFSETS)
        self.assertEqual(m.iso(when), "2026-01-06T12:00:00.000Z")
        self.assertIn("time of day unknown", note)
        when, note = m.parse_timestamp({"datestamp": "garbage"}, m.TZ_OFFSETS)
        self.assertEqual(when, m.EPOCH)
        self.assertIn("date unknown", note)
        when, _ = m.parse_timestamp({"datestamp": "FRI FEB 30 2026 10:00:00 PST"}, m.TZ_OFFSETS)  # impossible date
        self.assertEqual(when, m.EPOCH)

    def test_unknown_zone_reads_as_utc_with_a_note(self):
        when, note = m.parse_timestamp({"datestamp": "FRI JAN 2 2026 10:00:00 XYZ"}, m.TZ_OFFSETS)
        self.assertEqual(m.iso(when), "2026-01-02T10:00:00.000Z")
        self.assertIn("XYZ", note)

    def test_media_selection(self):
        self.assertEqual(m.pick_media("a/preview.png,a/index.html,a/1.png,a/2.jpeg,"), (["a/1.png", "a/2.jpeg"], ["a/index.html"]))
        self.assertEqual(m.pick_media("a/preview.jpeg,a/index.html,")[0], ["a/preview.jpeg"])
        self.assertEqual(m.pick_media(""), ([], []))

    def test_plate_pattern_matches_the_schema(self):
        schema = json.loads((ROOT / "schema" / "plate.schema.json").read_text())
        self.assertEqual(m.PLATE_RE.pattern, schema["properties"]["plate"]["pattern"])


class ConversionTests(Base):
    def test_fixture_maps_validates_and_is_confirmed(self):
        counts, report = m.convert(FIXTURE, self.root)
        self.assertEqual((counts["records_read"], counts["vehicles"], counts["sightings"], counts["plates"]), (6, 4, 6, 3))
        self.assertEqual(self.validate(), ([], []))
        by_name = {v["displayName"]: v for v in self.vehicles()}
        highlander = by_name["Grey Toyota Highlander"]
        self.assertEqual(len(highlander["sightings"]), 2)
        self.assertEqual(highlander["plateAliases"], ["XX-SAMPLE003"])  # 9 characters is now fine; the fixture has no state
        self.assertEqual(by_name["White Dodge Ram"]["bodyStyle"], "truck")
        self.assertEqual(by_name["White Dodge Ram"]["plateAliases"], [])
        for v in by_name.values():
            self.assertEqual(v["flag"], "confirmed")
            self.assertTrue(all(s["flag"] == "confirmed" for s in v["sightings"]))
        self.assertIn("guest", report["unmapped_fields"])

    def test_twenty_character_plate_ok_twentyone_goes_to_notes(self):
        ok, too_long = "ABCDEFGHIJKLMNOPQRST", "ABCDEFGHIJKLMNOPQRSTU"
        _, report = self.run_xml(xml_of(("A", [record("1", plate=ok)]), ("B", [record("2", plate=too_long)])))
        vs = {v["plateAliases"] and v["plateAliases"][0] or "none": v for v in self.vehicles()}
        self.assertIn("XX-" + ok, vs)
        self.assertEqual(self.validate(), ([], []))
        self.assertIn(too_long, report["plates_not_storable"])
        self.assertIn(too_long, vs["none"]["sightings"][0]["notes"])

    def test_missing_or_failed_fields_become_unknown(self):
        self.run_xml("<db><record><alert_token>1</alert_token></record></db>")
        (v,) = self.vehicles()
        self.assertEqual((v["color"], v["make"], v["model"], v["bodyStyle"], v["distinguishing"]),
                         ("unknown", "Unknown", None, "unknown", ["unknown"]))
        self.assertEqual(v["sightings"][0]["timestamp"], "1970-01-01T00:00:00.000Z")
        self.assertIsNone(v["sightings"][0]["location"])
        self.assertEqual(v["flag"], "confirmed")
        self.assertEqual(self.validate(), ([], []))

    def test_unmatched_model_has_unknown_body_style(self):
        self.run_xml(xml_of(("A", [record("1", make="Blue Zorblax Q9")])))
        self.assertEqual(self.vehicles()[0]["bodyStyle"], "unknown")

    def test_data_without_a_field_goes_into_notes(self):
        _, report = self.run_xml(xml_of(("A", [record("1", extra='<mystery>x</mystery><tags><t>a</t><t>b</t></tags>')])))
        notes = self.vehicles()[0]["sightings"][0]["notes"]
        for expected in ("seen", "Address: 1 MAIN ST", "guest: 1", "mystery: x", "tags: a b"):
            self.assertIn(expected, notes)
        self.assertEqual(report["unmapped_fields"]["mystery"][0]["value"], "x")

    def test_valid_plate_creates_linked_plate_record(self):
        self.run_xml(xml_of(("ABC1234", [record("1"), record("2", stamp="SUN JAN 4 2026 18:30:00 PST")])))
        (vehicle,) = self.vehicles()
        plate = json.loads((self.root / "data" / "plates" / "XX-ABC1234.json").read_text())
        self.assertEqual(plate["currentVehicleKey"], vehicle["vehicleKey"])
        self.assertEqual((vehicle["firstSeen"], vehicle["lastSeen"]), ("2026-01-02T18:00:00.000Z", "2026-01-05T02:30:00.000Z"))
        self.assertEqual(self.validate(), ([], []))

    def test_noplate_records_stay_separate_vehicles(self):
        self.run_xml(xml_of(("N1", [record("1", plate="NOPLATE")]), ("N2", [record("2", plate="NOPLATE")])))
        self.assertEqual(len(self.vehicles()), 2)

    def test_rerun_is_idempotent_and_merges(self):
        text = xml_of(("ABC1234", [record("1")]))
        self.run_xml(text)
        first = {p.name: p.read_bytes() for p in (self.root / "data").rglob("*.json")}
        self.run_xml(text)
        self.assertEqual(first, {p.name: p.read_bytes() for p in (self.root / "data").rglob("*.json")})
        self.run_xml(xml_of(("ABC1234", [record("1"), record("2", stamp="SUN JAN 4 2026 18:30:00 PST")])))
        self.assertEqual(len(self.vehicles()[0]["sightings"]), 2)

    def test_dry_run_writes_nothing(self):
        counts, _ = self.run_xml(xml_of(("ABC1234", [record("1")])), dry_run=True)
        self.assertEqual(counts["vehicles"], 1)
        self.assertFalse((self.root / "data").exists())

    def test_custom_time_zone_offset(self):
        self.run_xml(xml_of(("A", [record("1", stamp="FRI JAN 2 2026 10:00:00 AEST")])), offsets={"AEST": 10})
        self.assertEqual(self.vehicles()[0]["sightings"][0]["timestamp"], "2026-01-02T00:00:00.000Z")

    def test_flag_option(self):
        self.run_xml(xml_of(("A", [record("1")])), flag="suspected")
        self.assertEqual(self.vehicles()[0]["flag"], "suspected")

    def test_duplicate_alert_tokens_are_merged_and_reported(self):
        counts, report = self.run_xml(xml_of(("A", [record("1"), record("1")])))
        self.assertEqual(len(self.vehicles()[0]["sightings"]), 1)
        self.assertEqual(report["duplicate_records"], ["1"])


class MultipleFilesTests(Base):
    def test_folder_is_searched_recursively_and_files_combined(self):
        self.write(xml_of(("ABC1234", [record("1")])), "in/a.xml")
        self.write(xml_of(("ABC1234", [record("2", stamp="SUN JAN 4 2026 18:30:00 PST")]), ("ZZZ999", [record("3", plate="ZZZ999")])), "in/sub/b.XML")
        self.write("not xml", "in/readme.txt")
        counts, report = m.convert([Path(self.tmp.name) / "in"], self.root)
        self.assertEqual((counts["files_read"], counts["records_read"], counts["vehicles"]), (2, 3, 2))
        self.assertEqual(self.validate(), ([], []))

    def test_one_broken_file_does_not_stop_the_rest(self):
        self.write(xml_of(("ABC1234", [record("1")])), "in/good.xml")
        self.write("<db><record>", "in/bad.xml")
        counts, report = m.convert([Path(self.tmp.name) / "in"], self.root)
        self.assertEqual(counts["vehicles"], 1)
        self.assertEqual(len(report["files_failed"]), 1)
        self.assertIn("bad.xml", report["files_failed"][0]["file"])

    def test_cli_exit_codes(self):
        good = self.write(xml_of(("ABC1234", [record("1")])), "in/good.xml")
        bad = self.write("<db><record>", "in/bad.xml")
        args = ["--root", str(self.root), "--geocode", "none"]
        self.assertEqual(m.main(["--in", str(good)] + args), 0)
        self.assertEqual(m.main(["--in", str(bad)] + args), 2)
        self.assertEqual(m.main(["--in", str(good), "--in", str(bad)] + args), 1)
        self.assertEqual(m.main(["--in", str(Path(self.tmp.name) / "missing.xml")] + args), 2)


class GeocodingTests(Base):
    def geocoder(self, provider, **kw):
        return m.Geocoder(provider=provider, **kw)

    def test_address_becomes_a_coarsened_location(self):
        provider = FakeProvider({"1 MAIN ST": (34.1478012, -118.1445012)})
        counts, _ = self.run_xml(xml_of(("ABC1234", [record("1")])), geocoder=self.geocoder(provider, coarsen=3))
        self.assertEqual(self.vehicles()[0]["sightings"][0]["location"], {"lat": 34.148, "lng": -118.145})
        self.assertEqual(counts["located"], 1)
        self.assertEqual(self.validate(), ([], []))

    def test_no_coarsening_when_disabled(self):
        provider = FakeProvider({"1 MAIN ST": (34.1478012, -118.1445012)})
        self.run_xml(xml_of(("ABC1234", [record("1")])), geocoder=self.geocoder(provider, coarsen=None))
        self.assertEqual(self.vehicles()[0]["sightings"][0]["location"], {"lat": 34.1478012, "lng": -118.1445012})

    def test_unmatched_address_leaves_location_unknown_but_keeps_the_address(self):
        provider = FakeProvider({})
        geo = self.geocoder(provider)
        self.run_xml(xml_of(("ABC1234", [record("1", address="NOWHERE LN")])), geocoder=geo)
        sighting = self.vehicles()[0]["sightings"][0]
        self.assertIsNone(sighting["location"])
        self.assertIn("Address: NOWHERE LN", sighting["notes"])
        self.assertEqual(geo.stats["unmatched"], ["NOWHERE LN"])

    def test_default_area_is_appended_only_when_missing(self):
        provider = FakeProvider({})
        geo = self.geocoder(provider, default_area="Pasadena CA")
        geo.locate("12 OAK ST")
        geo.locate("34 ELM AVE PASADENA CA")
        self.assertEqual(provider.calls, ["12 OAK ST Pasadena CA", "34 ELM AVE PASADENA CA"])

    def test_service_down_never_fails_the_import_and_stops_after_three(self):
        provider = FakeProvider(down=True)
        geo = self.geocoder(provider)
        recs = [record(str(i), address=f"{i} A ST") for i in range(6)]
        self.run_xml(xml_of(("ABC1234", recs)), geocoder=geo)
        self.assertEqual(len(self.vehicles()[0]["sightings"]), 6)
        self.assertTrue(all(s["location"] is None for s in self.vehicles()[0]["sightings"]))
        self.assertEqual(len(provider.calls), 3)

    def test_cache_survives_between_runs_and_outages_are_not_cached(self):
        cache = Path(self.tmp.name) / "cache.json"
        first = FakeProvider({"1 MAIN ST": (34.0, -118.0)})
        geo = self.geocoder(first, cache_path=cache)
        geo.locate("1 MAIN ST"); geo.save()
        second = FakeProvider({})
        geo2 = self.geocoder(second, cache_path=cache)
        self.assertEqual(geo2.locate("1 MAIN ST"), {"lat": 34.0, "lng": -118.0})
        self.assertEqual(second.calls, [])
        down = self.geocoder(FakeProvider(down=True), cache_path=Path(self.tmp.name) / "c2.json")
        down.locate("9 X ST"); down.save()
        self.assertFalse((Path(self.tmp.name) / "c2.json").exists())

    def test_overrides_win_over_the_service(self):
        csv_path = Path(self.tmp.name) / "o.csv"
        csv_path.write_text("address,lat,lng\n1 main st,10.0,20.0\nbad,x,y\n")
        provider = FakeProvider({"1 MAIN ST": (1.0, 2.0)})
        geo = self.geocoder(provider, overrides=m.load_overrides(csv_path))
        self.assertEqual(geo.locate("1 Main St"), {"lat": 10.0, "lng": 20.0})
        self.assertEqual(provider.calls, [])

    def test_census_response_is_read_as_lat_y_lng_x(self):
        original = m._fetch_json
        m._fetch_json = lambda url: {"result": {"addressMatches": [{"coordinates": {"x": -117.19562823275, "y": 34.05680790487}}]}}
        self.addCleanup(setattr, m, "_fetch_json", original)
        self.assertEqual(m.census_geocode("380 New York St Redlands CA"), (34.05680790487, -117.19562823275))
        m._fetch_json = lambda url: {"result": {"addressMatches": []}}
        self.assertIsNone(m.census_geocode("nowhere"))

    def test_coarsening_follows_the_app_config(self):
        (self.root / "web" / "js").mkdir(parents=True)
        cfg = self.root / "web" / "js" / "config.js"
        cfg.write_text("export const COARSEN_DECIMALS = 2;")
        self.assertEqual(m.configured_coarsening(self.root), 2)
        cfg.write_text("export const COARSEN_DECIMALS = null;")
        self.assertIsNone(m.configured_coarsening(self.root))
        self.assertEqual(m.configured_coarsening(ROOT / "nowhere"), 4)


class PhotoTests(Base):
    def make_image(self, rel, size=(3000, 2000), mode="RGB", fmt="PNG"):
        from PIL import Image
        path = self.media / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.effect_noise(size, 80).convert(mode) if mode == "L" else Image.new(mode, size, (200, 30, 30))
        img.save(path, format=fmt)
        return path

    def test_media_is_skipped_by_default_but_remembered_in_notes(self):
        counts, report = self.run_xml(xml_of(("A", [record("1", media="m/preview.png,m/index.html,m/1.png,m/2.png,")])))
        sighting = self.vehicles()[0]["sightings"][0]
        self.assertEqual((sighting["photos"], counts["photos"]), ([], 0))
        self.assertIn("Legacy media (not imported): m/1.png, m/2.png", sighting["notes"])
        self.assertFalse((self.root / "photos").exists())

    def test_later_run_with_media_root_attaches_the_photos_to_the_same_sighting(self):
        text = xml_of(("A", [record("1", media="media/A/1.png")]))
        self.run_xml(text)
        before = self.vehicles()[0]["sightings"][0]["id"]
        self.make_image("media/A/1.png", size=(4000, 3000))
        self.run_xml(text, media_root=self.media)
        (vehicle,) = self.vehicles()
        self.assertEqual(len(vehicle["sightings"]), 1)
        sighting = vehicle["sightings"][0]
        self.assertEqual(sighting["id"], before)
        self.assertEqual(len(sighting["photos"]), 1)
        self.assertNotIn("Legacy media", sighting["notes"])
        self.assertEqual(self.validate(), ([], []))

    def test_photos_become_small_jpegs(self):
        from PIL import Image
        self.make_image("media/A/preview.png")
        self.make_image("media/A/100.png", size=(4000, 3000))
        self.run_xml(xml_of(("A", [record("1", media="media/A/preview.png,media/A/index.html,media/A/100.png,")])), media_root=self.media)
        photos = self.vehicles()[0]["sightings"][0]["photos"]
        self.assertEqual(len(photos), 1)  # preview skipped because a real image exists
        out = self.root / photos[0]
        self.assertLessEqual(out.stat().st_size, m.PHOTO_MAX_BYTES)
        with Image.open(out) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), m.PHOTO_MAX_EDGE)

    def test_noisy_photo_is_shrunk_below_the_limit(self):
        self.make_image("media/A/noise.png", size=(2400, 1800), mode="L")
        self.run_xml(xml_of(("A", [record("1", media="media/A/noise.png")])), media_root=self.media)
        out = self.root / self.vehicles()[0]["sightings"][0]["photos"][0]
        self.assertLessEqual(out.stat().st_size, m.PHOTO_MAX_BYTES)

    def test_missing_media_is_reported_and_noted(self):
        _, report = self.run_xml(xml_of(("A", [record("1", media="media/A/missing.png,media/A/index.html,")])), media_root=self.media)
        self.assertEqual(sorted(x["reason"] for x in report["media_not_imported"]),
                         ["file not found under --media-root", "not an image"])
        self.assertIn("Media not imported: media/A/missing.png", self.vehicles()[0]["sightings"][0]["notes"])

    def test_media_paths_cannot_escape_media_root(self):
        self.make_image("../secret.png")
        _, report = self.run_xml(xml_of(("A", [record("1", media="../secret.png")])), media_root=self.media)
        self.assertEqual(self.vehicles()[0]["sightings"][0]["photos"], [])
        self.assertEqual(report["media_not_imported"][0]["reason"], "file not found under --media-root")

    def test_corrupt_image_is_reported_not_fatal(self):
        (self.media / "bad.png").write_bytes(b"not an image")
        counts, report = self.run_xml(xml_of(("A", [record("1", media="bad.png")])), media_root=self.media)
        self.assertEqual(counts["vehicles"], 1)
        self.assertIn("could not convert", report["media_not_imported"][0]["reason"])



class StateTests(Base):
    def plates(self):
        return {p.stem: json.loads(p.read_text()) for p in sorted((self.root / "data" / "plates").glob("*.json"))}

    def one(self, extra="", comments="seen", default_state="XX", **kw):
        return self.run_xml(xml_of(("A", [record("1", extra=extra, comments=comments)])), default_state=default_state, **kw)

    def test_state_element_sets_state_in_alias_plate_file_and_name(self):
        self.one(extra="<state>nv</state>")
        (v,) = self.vehicles()
        self.assertEqual(v["plateAliases"], ["NV-ABC1234"])
        self.assertEqual(self.plates()["NV-ABC1234"]["plateState"], "NV")
        self.assertEqual(self.validate(), ([], []))
        self.assertNotIn("state", v["sightings"][0]["notes"])  # it has a field now, so it is not repeated as extra data

    def test_names_and_abbreviations_are_understood(self):
        for raw, code in (("Nevada", "NV"), ("Calif.", "CA"), ("new york", "NY"), ("ON", "ON"), ("British Columbia", "BC")):
            self.assertEqual(m.parse_state(raw)[0], code, raw)

    def test_state_written_in_the_comments_is_found_and_kept_in_the_notes(self):
        self.one(comments="Parked twice. State: California, white sticker")
        (v,) = self.vehicles()
        self.assertEqual(v["plateAliases"], ["CA-ABC1234"])
        self.assertIn("State: California", v["sightings"][0]["notes"])

    def test_element_beats_text(self):
        self.one(extra="<plate_state>AZ</plate_state>", comments="State: CA")
        self.assertEqual(self.vehicles()[0]["plateAliases"], ["AZ-ABC1234"])

    def test_unrecognised_state_becomes_xx_and_is_reported(self):
        _, report = self.one(extra="<state>Atlantis</state>")
        self.assertEqual(self.vehicles()[0]["plateAliases"], ["XX-ABC1234"])
        self.assertEqual(report["states"]["unrecognised"], {"Atlantis": 1})
        self.assertEqual(self.validate(), ([], []))

    def test_no_state_is_xx_unless_a_default_is_given(self):
        _, report = self.one()
        self.assertEqual(self.vehicles()[0]["plateAliases"], ["XX-ABC1234"])
        self.assertEqual(report["states"]["plates_without_state"], 1)
        self.assertEqual(report["states"]["by_source"], {"none found": 1})

    def test_default_state_fills_gaps_only(self):
        self.run_xml(xml_of(("A", [record("1", plate="AAA111"), record("2", plate="BBB222", extra="<state>NV</state>")])), default_state="CA")
        self.assertEqual(sorted(self.plates()), ["CA-AAA111", "NV-BBB222"])

    def test_same_plate_in_two_states_is_two_vehicles(self):
        _, report = self.run_xml(xml_of(("A", [record("1", extra="<state>CA</state>"), record("2", extra="<state>NV</state>"),
                                               record("3")])))
        self.assertEqual(sorted(p for v in self.vehicles() for p in v["plateAliases"]), ["CA-ABC1234", "NV-ABC1234", "XX-ABC1234"])
        self.assertEqual(report["state_ambiguous"], [{"plate": "ABC1234", "states": ["CA", "NV", "XX"]}])

    def test_rerun_is_idempotent_with_state(self):
        text = xml_of(("A", [record("1", extra="<state>NV</state>")]))
        self.run_xml(text)
        before = {p.name: p.read_text() for p in self.root.rglob("*.json") if "reports" not in p.parts}
        self.run_xml(text)
        self.assertEqual(before, {p.name: p.read_text() for p in self.root.rglob("*.json") if "reports" not in p.parts})

    def test_debug_trace_explains_each_record(self):
        _, report = self.run_xml(xml_of(("A", [record("7", extra="<state>nv</state>")])), debug=True)
        (rec,) = report["debug"]["records"]
        self.assertEqual((rec["alert_token"], rec["plate_key"], rec["state"]["source"], rec["state"]["raw"]), ("7", "NV-ABC1234", "element", "nv"))
        self.assertTrue(rec["source"]["line"] >= 1 and rec["source"]["xml"].startswith("<record>"))
        names = {k for d in rec["decisions"] for k in d}
        self.assertTrue({"timestamp", "address", "media", "vehicle"} <= names)
        self.assertEqual(report["debug"]["field_map"]["state"]["becomes"], "vehicle_state")
        self.assertIn("record", report["debug"]["elements"])
        self.assertIn("debug", m.debug_text(report).lower())

    def test_debug_off_has_no_record_trace_but_keeps_the_summary(self):
        _, report = self.one()
        self.assertIsNone(report["debug"]["records"])
        self.assertIn("vehicle_license", report["debug"]["field_map"])

    def test_record_lines_point_at_the_file(self):
        text = "<?xml version='1.0'?>\n<db>\n<plate_file_A>\n" + record("1") + "\n</plate_file_A>\n<plate_file_B>\n" + record("2", plate="ZZZ") + "\n</plate_file_B>\n</db>"
        _, report = self.run_xml(text, debug=True)
        self.assertEqual([r["source"]["line"] for r in report["debug"]["records"]], [4, 7])

    def test_repair_details_are_in_the_debug_files_section(self):
        bad = "<db>\n<record><alert_token>1</alert_token><vehicle_license>A1</vehicle_license>\n<comments>x <State: CA> y</comments></record></db>"
        _, report = self.run_xml(bad)
        (f,) = report["debug"]["files"]
        self.assertEqual((f["repaired"], f["repairs"][0]["line"], f["repairs"][0]["kind"]), (1, 3, "stray <"))
        self.assertIn("<State: CA>", self.vehicles()[0]["sightings"][0]["notes"])


class RepairTests(unittest.TestCase):
    def test_stray_lt_and_amp_are_repaired(self):
        xml = "<db><record><alert_token>1</alert_token><comments>State: <State: CA> AT&T 5 < 6 &amp; &#169;</comments></record></db>"
        info = {}
        rows = list(m.parse_xml(xml, info))
        self.assertEqual(len(rows), 1)
        self.assertIn("<State: CA>", rows[0][1]["comments"])
        self.assertIn("AT&T", rows[0][1]["comments"])
        self.assertEqual(info["repaired"], 3)
        self.assertEqual([(x["kind"], x["line"]) for x in info["repairs"]], [("stray <", 1), ("stray &", 1), ("stray <", 1)])

    def test_html_style_markup_in_text_is_repaired(self):
        xml = ("<db>\n<record><alert_token>1</alert_token>\n<comments>a <b class=x>bold</b> b <br> c <State: CA> "
               "d <a href=http://x?a=1&b=2>l</a> e <input disabled> f <p>g<p>h </div> 1 < 2</comments></record></db>")
        info = {}
        rows = list(m.parse_xml(xml, info))
        text = rows[0][1]["comments"]
        for piece in ("<b class=x>bold</b>", "<br>", "<State: CA>", "<a href=http://x?a=1&b=2>l</a>", "<input disabled>", "<p>g<p>h", "</div>", "1 < 2"):
            self.assertIn(piece, text)
        kinds = {x["kind"].split(" ")[0] for x in info["repairs"]}
        self.assertTrue({"stray", "closing", "unclosed"} <= kinds, kinds)
        self.assertTrue(all(x["line"] == 3 for x in info["repairs"]))

    def test_comments_and_cdata_are_left_alone(self):
        rows = list(m.parse_xml("<db><record><alert_token>1</alert_token><comments>a < b <!-- < & --> <![CDATA[ <x & ]]></comments></record></db>"))
        self.assertIn("<x &", rows[0][1]["comments"])

    def test_final_error_names_the_line_and_text(self):
        with self.assertRaises(m.ImportErrorXml) as cm:
            list(m.parse_xml("<db>\n<record>\n<alert_token>1</alert_token>\n"))
        self.assertIn("line", str(cm.exception))

    def test_unrepairable_still_fails(self):
        with self.assertRaises(m.ImportErrorXml):
            list(m.parse_xml("<db><record>"))


if __name__ == "__main__":
    unittest.main()
