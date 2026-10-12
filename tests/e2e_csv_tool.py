"""Browser test for the CSV side of tools/import.html (and the XML/CSV switching).

Drives the page in Chromium with made-up CSV files (no real plates), then checks the
records it writes with the repository's own validator and index builder, that a
re-run says "Nothing new", that new sightings join vehicles that already exist
(including ones imported from XML), and that odd spreadsheets (quotes, other
delimiters, other encodings, day-first dates, missing columns) are read correctly.

Run: python3 tests/e2e_csv_tool.py   (needs: pip install playwright jsonschema pillow)
"""
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TOOL = (ROOT / "tools" / "import.html").as_uri()
TEMPLATE = ROOT / "tools" / "csv-template.csv"
XML_SCRIPT = ROOT / "scripts" / "migrate_xml_to_json.py"
VALIDATE = ROOT / "scripts" / "validate_records.py"
BUILD_INDEX = ROOT / "scripts" / "build_index.py"

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


HEAD = "License Plate,State,Color,Make,Model,Type,Earliest Seen,Last Seen,City,NOTES"

def csv_file(tmp, name, text, encoding="utf-8"):
    p = Path(tmp) / name
    p.write_bytes(text.encode(encoding))
    return p

def new_root(tmp, name):
    root = Path(tmp) / name
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "schema").exists():
        (root / "schema").symlink_to(ROOT / "schema")
    return root

def unzip_into(zf, root):
    for name, data in zf.items():
        dest = Path(root) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

def run_script(script, root, *args):
    return subprocess.run([sys.executable, str(script), "--root", str(root), *args], capture_output=True, text=True)

def zip_files(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    assert z.testzip() is None, "ZIP failed its CRC check"
    return {n: z.read(n) for n in z.namelist()}

def records(zf, prefix):
    return {n: json.loads(b) for n, b in zf.items() if n.startswith(prefix)}

def vehicles_by_plate(zf):
    out = {}
    for v in records(zf, "data/vehicles/").values():
        for alias in v["plateAliases"]:
            out[alias] = v
    return out


def convert(page, files, tmp, name="out.zip", **opts):
    """Drive the page; returns (zip files, report, result-panel text)."""
    page.goto(TOOL)
    if not opts.get("keep_storage"):
        page.evaluate("localStorage.clear()")
    page.set_input_files("#csv-input", [str(f) for f in files])
    page.wait_for_selector("#map-rows tr", timeout=10000)
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    page.select_option("#geocode", opts.get("geocode", "none"))
    for key, sel in (("flag", "#flag"), ("default_state", "#default-state"), ("date_order", "#date-order"), ("tz", "#csv-tz")):
        if key in opts: page.select_option(sel, opts[key])
    if "skip_same_day" in opts: page.set_checked("#skip-same-day", opts["skip_same_day"])
    if "area" in opts: page.fill("#area", opts["area"])
    if "coarsen" in opts: page.fill("#coarsen", opts["coarsen"])
    if "header" in opts: page.set_checked("#has-header", opts["header"])
    for col, target in opts.get("map", {}).items():
        rows = page.query_selector_all("#map-rows tr")
        rows[col].query_selector("select").select_option(target)
    if "repo" in opts: page.set_input_files("#repo-input", str(opts["repo"]))
    page.click("#convert")
    page.wait_for_selector("#results:not([hidden])", timeout=60000)
    panel = page.inner_text("#check-panel") + "\n" + page.inner_text("#validation-panel")
    zpath = Path(tmp) / name
    if page.is_enabled("#download-zip"):
        with page.expect_download() as d:
            page.click("#download-zip")
        d.value.save_as(zpath)
        zf = zip_files(zpath.read_bytes())
    else:
        zf = {}
    with page.expect_download() as d2:
        page.click("#download-report")
    rpath = Path(tmp) / (name + ".report.json")
    d2.value.save_as(rpath)
    report = json.loads(rpath.read_text())
    return zf, report, panel


with tempfile.TemporaryDirectory() as tmpdir, sync_playwright() as p:
    tmp = Path(tmpdir)
    browser = p.chromium.launch()
    ctx = browser.new_context(accept_downloads=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    # ---------- the template ships with the tool and converts cleanly ----------
    zf, report, panel = convert(page, [TEMPLATE], tmp, name="template.zip")
    check("template: check passed and format check passed", "Check passed" in panel and "Format check passed" in panel, panel)
    veh = vehicles_by_plate(zf)
    check("template: two vehicles and two plates", len(records(zf, "data/vehicles/")) == 2 and len(records(zf, "data/plates/")) == 2, str(sorted(zf)))
    check("template: Earliest and Last Seen make two sightings", len(veh["CA-DEMO001"]["sightings"]) == 2 and len(veh["NV-DEMO002"]["sightings"]) == 1)
    check("template: same dates make one sighting", veh["NV-DEMO002"]["firstSeen"] == veh["NV-DEMO002"]["lastSeen"])
    check("template: type guessed from the model when blank, read from Type when given", veh["CA-DEMO001"]["bodyStyle"] == "suv" and veh["NV-DEMO002"]["bodyStyle"] == "van", f'{veh["CA-DEMO001"]["bodyStyle"]} {veh["NV-DEMO002"]["bodyStyle"]}')
    check("template: City is kept in the notes with its column name", "City: Exampleville" in veh["CA-DEMO001"]["sightings"][0]["notes"])
    check("template: imported sightings are confirmed by default", all(s["flag"] == "confirmed" for v in veh.values() for s in v["sightings"]))
    check("template: no index.json without the data folder", "data/index.json" not in zf)
    check("template: source and observer say csv-import", all(s["source"].startswith("csv-import:") and s["observer"] == "csv-import" for v in veh.values() for s in v["sightings"]))

    # the repository's own validator accepts what the tool wrote
    root = new_root(tmp, "repo1")
    unzip_into(zf, root)
    out = run_script(VALIDATE, root)
    check("template: scripts/validate_records.py passes on the output", out.returncode == 0, out.stdout[-400:] + out.stderr[-400:])
    run_script(BUILD_INDEX, root)

    # ---------- re-run against the imported data: nothing new ----------
    zf2, report2, panel2 = convert(page, [TEMPLATE], tmp, name="again.zip", repo=root / "data")
    check("re-run: 'Nothing new' and the check passes", "Nothing new" in panel2 and "Check passed" in panel2, panel2)
    check("re-run: no vehicle or plate files written", not [n for n in zf2 if n.startswith(("data/vehicles", "data/plates"))], str(sorted(zf2)))
    check("re-run: every sighting counted as already imported", report2["check"]["already_imported"] == 3 and report2["check"]["new"] == 0, json.dumps(report2["check"]))
    idx_tool = zf2["data/index.json"].decode()
    check("index.json from the tool equals scripts/build_index.py", idx_tool == (root / "data" / "index.json").read_text(), "differs")

    # ---------- the sheet grows: a later Last Seen adds exactly one sighting to the same vehicle ----------
    grown = csv_file(tmp, "grown.csv", HEAD + "\nDEMO001,CA,Silver,Ford,Explorer,,01/08/26,03/15/26,Exampleville,made-up example row\n"
                                              "DEMO002,NV,White,Chrysler,Pacifica,Minivan,02/06/26,02/06/26,Exampleville,\n"
                                              "DEMO004,AZ,Green,Subaru,Outback,,04/01/26,04/01/26,Exampleville,new car\n")
    zf3, report3, panel3 = convert(page, [grown], tmp, name="grown.zip", repo=root / "data")
    check("grown sheet: 2 new sightings (one on the old vehicle, one on a new one)", report3["check"]["new"] == 2 and report3["check"]["already_imported"] == 2 and "Check passed" in panel3, json.dumps(report3["check"]))
    v1 = vehicles_by_plate(zf3)["CA-DEMO001"]
    check("grown sheet: the old vehicle keeps its key and gains the sighting", v1["vehicleKey"] == veh["CA-DEMO001"]["vehicleKey"] and len(v1["sightings"]) == 3 and v1["lastSeen"].startswith("2026-03-15"), v1["vehicleKey"])
    check("grown sheet: only the changed and new vehicles are written", len(records(zf3, "data/vehicles/")) == 2, str(sorted(zf3)))
    unzip_into(zf3, root)
    out = run_script(VALIDATE, root); run_script(BUILD_INDEX, root)
    check("grown sheet: validator passes after merging", out.returncode == 0, out.stdout[-400:])
    check("grown sheet: index.json equals build_index.py", zf3["data/index.json"].decode() == (root / "data" / "index.json").read_text())

    # ---------- overlap with records imported earlier from XML ----------
    xml_root = new_root(tmp, "xmlrepo")
    xml = tmp / "legacy.xml"
    xml.write_text('<?xml version="1.0"?><db><plate_file_A><record><alert_token>7001</alert_token><media></media>'
                   '<vehicle_license>DEMO010</vehicle_license><address></address><vehicle_make>Blue Honda Civic</vehicle_make>'
                   '<month>JAN</month><day>8</day><year>2026</year><comments>from the app</comments>'
                   '<datestamp>THU JAN 8 2026 18:30:00 PST</datestamp><state>CA</state></record></plate_file_A></db>', encoding="utf-8")
    out = run_script(XML_SCRIPT, xml_root, "--in", str(xml), "--geocode", "none")
    check("overlap: XML import for the setup succeeded", out.returncode == 0, out.stdout[-300:] + out.stderr[-300:])
    xml_key = json.loads(next((xml_root / "data" / "vehicles").glob("VEH_*.json")).read_text())["vehicleKey"]
    overlap = csv_file(tmp, "overlap.csv", HEAD + "\nDEMO010,CA,Blue,Honda,Civic,,01/08/26,02/20/26,Exampleville,seen again\n")
    zf4, report4, panel4 = convert(page, [overlap], tmp, name="overlap.zip", repo=xml_root / "data")
    v4 = vehicles_by_plate(zf4)["CA-DEMO010"]
    check("overlap: joins the vehicle the XML import created (no duplicate vehicle)", v4["vehicleKey"] == xml_key and len(records(zf4, "data/vehicles/")) == 1, v4["vehicleKey"])
    check("overlap: the 8 Jan sighting is skipped (already recorded that day), 20 Feb is added", report4["check"]["new"] == 1 and report4["check"]["same_date_skipped"] == 1 and len(v4["sightings"]) == 2, json.dumps(report4["check"]))
    check("overlap: the XML sighting is untouched", any(s["source"] == "xml-import:7001" and s["notes"] == "from the app" for s in v4["sightings"]))
    zf5, report5, _ = convert(page, [overlap], tmp, name="overlap2.zip", repo=xml_root / "data", skip_same_day=False)
    check("overlap: with the same-date skip off, the 8 Jan sighting is added", report5["check"]["new"] == 2, json.dumps(report5["check"]))

    # ---------- the data has the plate with no state (legacy XML had none): join it, never duplicate ----------
    ns_root = new_root(tmp, "nostate")
    def legacy(tok, plate, make, day):
        return (f"<record><alert_token>{tok}</alert_token><media></media><vehicle_license>{plate}</vehicle_license><address></address>"
                f"<vehicle_make>{make}</vehicle_make><month>JAN</month><day>{day}</day><year>2026</year><comments>legacy</comments>"
                f"<datestamp>THU JAN {day} 2026 12:00:00 PST</datestamp></record>")
    xml2 = tmp / "nostate.xml"
    xml2.write_text('<?xml version="1.0"?><db><plate_file_A>' + legacy(8001, "DEMO020", "Ford Explorer", 8) + legacy(8002, "DEMO021", "Black Ford Focus", 9) + '</plate_file_A></db>', encoding="utf-8")
    out = run_script(XML_SCRIPT, ns_root, "--in", str(xml2), "--geocode", "none")
    legacy_keys = {json.loads(f.read_text())["plateAliases"][0]: json.loads(f.read_text())["vehicleKey"] for f in (ns_root / "data" / "vehicles").glob("VEH_*.json")}
    check("no-state data: setup shows XX plates", out.returncode == 0 and set(legacy_keys) == {"XX-DEMO020", "XX-DEMO021"}, str(legacy_keys))
    ns_csv = csv_file(tmp, "nostate.csv", HEAD + "\nDEMO020,CA,Silver,Ford,Explorer,SUV,01/08/26,02/20/26,Exampleville,\nDEMO021,CA,Silver,Ford,Focus,,03/01/26,03/01/26,Exampleville,\n")
    zf12, report12, panel12 = convert(page, [ns_csv], tmp, name="nostate.zip", repo=ns_root / "data")
    vs = records(zf12, "data/vehicles/")
    check("no-state data: the CSV joins the XX vehicles instead of creating CA ones", {v["vehicleKey"] for v in vs.values()} == set(legacy_keys.values()), str([v["plateAliases"] for v in vs.values()]))
    check("no-state data: no plate record is created or renamed", not [n for n in zf12 if n.startswith("data/plates/")], str(sorted(zf12)))
    e20 = next(v for v in vs.values() if v["plateAliases"] == ["XX-DEMO020"]); e21 = next(v for v in vs.values() if v["plateAliases"] == ["XX-DEMO021"])
    check("no-state data: unknown details are filled in, name follows", e20["color"] == "silver" and e20["displayName"] == "Silver Ford Explorer" and e20["bodyStyle"] == "suv", f'{e20["color"]} {e20["displayName"]}')
    check("no-state data: a known color is never replaced", e21["color"] == "black" and e21["displayName"] == "Black Ford Focus", f'{e21["color"]} {e21["displayName"]}')
    check("no-state data: new sightings carry the CSV's state in their notes", any("State: CA" in s["notes"] for s in e20["sightings"] if s["source"].startswith("csv-import")))
    check("no-state data: plates needing a state are listed in the report", sorted(x["plate"] for x in report12["state_to_set"]) == ["DEMO020", "DEMO021"], str(report12["state_to_set"]))
    check("no-state data: 8 Jan skipped as same date, 20 Feb and 1 Mar added", report12["check"]["new"] == 2 and report12["check"]["same_date_skipped"] == 1 and "Check passed" in panel12 and "Format check passed" in panel12, json.dumps(report12["check"]))
    unzip_into(zf12, ns_root); run_script(BUILD_INDEX, ns_root)
    out = run_script(VALIDATE, ns_root)
    check("no-state data: validator passes after merging", out.returncode == 0, out.stdout[-400:])
    zf13, report13, panel13 = convert(page, [ns_csv], tmp, name="nostate2.zip", repo=ns_root / "data")
    check("no-state data: re-run says Nothing new and writes no records", "Nothing new" in panel13 and not [n for n in zf13 if n.startswith(("data/vehicles", "data/plates"))], panel13)
    off_root = new_root(tmp, "nostate_off"); run_script(XML_SCRIPT, off_root, "--in", str(xml2), "--geocode", "none")
    page.goto(TOOL); page.evaluate("localStorage.clear()")
    page.set_input_files("#csv-input", [str(ns_csv)]); page.wait_for_selector("#map-rows tr")
    page.set_checked("#fill-unknown", False); page.select_option("#geocode", "none"); page.set_input_files("#repo-input", str(off_root / "data"))
    page.click("#convert"); page.wait_for_selector("#results:not([hidden])")
    with page.expect_download() as d: page.click("#download-zip")
    d.value.save_as(tmp / "fill_off.zip")
    off_vs = records(zip_files((tmp / "fill_off.zip").read_bytes()), "data/vehicles/")
    check("fill-in option off: details stay unknown", next(v for v in off_vs.values() if v["plateAliases"] == ["XX-DEMO020"])["color"] == "unknown")
    # only details to fill, no new sightings: the ZIP still carries the vehicle, and the page does not claim "Nothing new"
    fill_root = new_root(tmp, "fill_only"); run_script(XML_SCRIPT, fill_root, "--in", str(xml2), "--geocode", "none")
    fill_csv = csv_file(tmp, "fill_only.csv", HEAD + "\nDEMO020,CA,Silver,Ford,Explorer,SUV,01/08/26,01/08/26,,\n")
    zf14, report14, panel14 = convert(page, [fill_csv], tmp, name="fill_only.zip", repo=fill_root / "data")
    check("details only: vehicle written, no new sightings, not reported as 'Nothing new'",
          report14["check"]["new"] == 0 and len(records(zf14, "data/vehicles/")) == 1 and "No new sightings, but 1 vehicle" in panel14 and "nothing to push" not in panel14 and next(iter(records(zf14, "data/vehicles/").values()))["color"] == "silver", panel14)

    # ---------- a messy spreadsheet ----------
    messy = (
        '﻿Plate;State;Color;Make;Model;Type;Date;Notes;Latitude;Longitude;Flag;Year\r\n'
        'abc-123;California;dark blue;TOYOTA;"Land Cruiser, 80";SUV;25/01/26 6:30 PM;"saw it twice,\nonce at night";34.14567;-118.14567;suspected;1995\r\n'
        ';;;Honda;Civic;;26/01/2026;no plate here;;;;\r\n'
        'NOPLATE;;Red;Mazda;3;wagon;27 Jan 2026;;;;;\r\n'
        'TOOLONGPLATE1234567890X;NV;Black;BMW;M3;coupe;2026-01-28;;;;;\r\n'
        'abc-123;CA;dark blue;Toyota;Land Cruiser, 80;SUV;25/01/26 6:30 PM;"saw it twice,\nonce at night";;;;\r\n'
        'SAME001;CA;Gray;Ford;Focus;Hatch;01/02/2026;;;;;\r\n'
        'SAME001;NV;Gray;Ford;Focus;Hatch;01/02/2026;other state, same text;;;;\r\n'
        'BADDATE;Atlantis;White;Kia;Soul;;garbage;;;;nonsense;1850\r\n'
        '\r\n;;;;;;;;;;;\r\n'
    )
    mp = csv_file(tmp, "messy.csv", messy)
    zf6, report6, panel6 = convert(page, [mp], tmp, name="messy.zip")
    veh6 = vehicles_by_plate(zf6)
    check("messy: BOM + semicolons read; check and format check pass", "Check passed" in panel6 and "Format check passed" in panel6, panel6)
    check("messy: day-first detected from 25/01/26 and applied to every date", report6["options"]["date_order"] == "dmy" and veh6["CA-ABC123"]["firstSeen"].startswith("2026-01-26T02:30"), report6["options"]["date_order"])
    v = veh6["CA-ABC123"]
    check("messy: state name and dash in plate normalised; quoted comma and newline kept", v["sightings"][0]["notes"].startswith("saw it twice,\nonce at night"), repr(v["sightings"][0]["notes"]))
    check("messy: time of day respected (6:30 PM PST = 02:30 UTC next day)", v["sightings"][0]["timestamp"] == "2026-01-26T02:30:00.000Z", v["sightings"][0]["timestamp"])
    check("messy: lat/lng become the location, rounded to 4 decimals", v["sightings"][0]["location"] == {"lat": 34.1457, "lng": -118.1457}, str(v["sightings"][0]["location"]))
    check("messy: flag column and year used", v["flag"] == "suspected" and v["year"] == 1995, f'{v["flag"]} {v.get("year")}')
    check("messy: repeated row merged into one sighting", len(v["sightings"]) == 1 and report6["check"]["repeated_in_file"] == 1)
    check("messy: all-caps make title-cased like the XML tool", v["make"] == "Toyota" and v["model"] == "Land Cruiser, 80" and v["color"] == "dark blue", f'{v["make"]} {v["model"]} {v["color"]}')
    check("messy: same plate text in another state stays a separate vehicle", "CA-SAME001" in veh6 and "NV-SAME001" in veh6 and veh6["CA-SAME001"]["vehicleKey"] != veh6["NV-SAME001"]["vehicleKey"])
    check("messy: gray becomes grey; Hatch becomes hatchback", veh6["CA-SAME001"]["color"] == "grey" and veh6["CA-SAME001"]["bodyStyle"] == "hatchback")
    noplate = [x for x in records(zf6, "data/vehicles/").values() if not x["plateAliases"]]
    check("messy: rows with no plate or NOPLATE become plate-less vehicles", len(noplate) == 3, f"{len(noplate)} plate-less vehicles: {[x['displayName'] for x in noplate]}")
    wagon = next(x for x in noplate if x["make"] == "Mazda")
    check("messy: unrecognised body type kept in notes, style unknown", wagon["bodyStyle"] == "unknown" and "wagon" in wagon["sightings"][0]["notes"], wagon["sightings"][0]["notes"])
    check("messy: text month date read", wagon["firstSeen"].startswith("2026-01-27"))
    long_plate = next(x for x in noplate if x["make"] == "Bmw")
    check("messy: over-long plate not stored, kept in notes", "TOOLONGPLATE1234567890X" in long_plate["sightings"][0]["notes"] and not any(n.startswith("data/plates/NV-TOOLONG") for n in zf6))
    bad = veh6["XX-BADDATE"]
    check("messy: unreadable date -> 1970 and listed", bad["firstSeen"].startswith("1970-01-01") and any(n["why"].startswith("date unknown") for n in report6["needs_review"]))
    check("messy: unrecognised state -> XX, bad flag/year ignored, all kept in notes", all(t in bad["sightings"][0]["notes"] for t in ("Atlantis", "nonsense", "1850", "garbage")) and "year" not in bad, bad["sightings"][0]["notes"])
    check("messy: blank lines are not rows", report6["check"]["rows_read"] == 8, str(report6["check"]["rows_read"]))
    root6 = new_root(tmp, "repo6"); unzip_into(zf6, root6)
    out = run_script(VALIDATE, root6)
    check("messy: scripts/validate_records.py passes", out.returncode == 0, out.stdout[-500:])

    # ---------- single combined vehicle column, single date, default state, flag option, Windows-1252 ----------
    comb = csv_file(tmp, "comb.csv", "Tag,Vehicle,Seen,Remarks\nQQQ111,Dark Blue Honda Civic,3/4/2026,façade café\nQQQ222,Silver Land Rover Defender 90,Mar 5 2026,\n", encoding="cp1252")
    zf7, report7, panel7 = convert(page, [comb], tmp, name="comb.zip", default_state="NV", flag="suspected")
    veh7 = vehicles_by_plate(zf7)
    check("combined column: color, make, model split like the XML tool", veh7["NV-QQQ111"]["color"] == "dark blue" and veh7["NV-QQQ111"]["make"] == "Honda" and veh7["NV-QQQ111"]["model"] == "Civic" and veh7["NV-QQQ222"]["make"] == "Land Rover", json.dumps(veh7["NV-QQQ222"]["make"]))
    check("combined column: default state and chosen flag applied", all(s["flag"] == "suspected" for v in veh7.values() for s in v["sightings"]))
    check("combined column: month-first date 3/4/2026 is 4 March", veh7["NV-QQQ111"]["firstSeen"].startswith("2026-03-04"), veh7["NV-QQQ111"]["firstSeen"])
    check("windows-1252 file: accents survive", "façade café" in veh7["NV-QQQ111"]["sightings"][0]["notes"], veh7["NV-QQQ111"]["sightings"][0]["notes"])
    zf7b, report7b, _ = convert(page, [comb], tmp, name="comb2.zip", date_order="dmy", default_state="NV")
    check("date order option: day-first reads 3/4/2026 as 3 April", vehicles_by_plate(zf7b)["NV-QQQ111"]["firstSeen"].startswith("2026-04-03"))

    # ---------- every date format the README promises ----------
    from datetime import date, datetime, timezone
    serial = (date(2026, 1, 8) - date(1899, 12, 30)).days
    epoch = int(datetime(2026, 1, 8, 12, 0, tzinfo=timezone.utc).timestamp())
    cases = [  # text, order, expected stamp (None = not a date)
        ("01/08/26", "mdy", "2026-01-08"), ("01/08/26", "dmy", "2026-08-01"), ("13/01/26", "dmy", "2026-01-13"), ("13/01/26", "mdy", None),
        ("1/8/2026", "mdy", "2026-01-08"), ("2026-01-08", "mdy", "2026-01-08"), ("2026/1/8", "mdy", "2026-01-08"), ("Jan 8, 2026", "mdy", "2026-01-08"),
        ("January 8th, 2026", "mdy", "2026-01-08"), ("8 Jan 2026", "mdy", "2026-01-08"), ("8-Jan-26", "mdy", "2026-01-08"), ("1/8/99", "mdy", "1999-01-08"),
        ("1/8/69", "mdy", "2069-01-08"), ("1/8/70", "mdy", "1970-01-08"), ("01/08/26 10:30 PM", "mdy", "2026-01-08T22:30"), ("01/08/26 12:15 AM", "mdy", "2026-01-08T00:15"),
        ("01/08/26 12:15 PM", "mdy", "2026-01-08T12:15"), ("2026-01-08 10:00", "mdy", "2026-01-08T10:00"), ("2026-01-08T10:00:00Z", "mdy", "2026-01-08T10:00"),
        (str(serial), "mdy", "2026-01-08"), (str(epoch), "mdy", "2026-01-08T12:00"), (str(epoch * 1000), "mdy", "2026-01-08T12:00"),
        ("02/30/26", "mdy", None), ("garbage", "mdy", None), ("01/08/26 25:00", "mdy", None), ("13:45", "mdy", None),
    ]
    got = page.evaluate("(cases) => cases.map(([t, o]) => { const r = PTImport.csv.parseCsvDate(t, o, -8); return r.bad ? null : r.stamp; })", [[c[0], c[1]] for c in cases])
    wrong = [(c, g) for c, g in zip(cases, got) if g != c[2]]
    check("dates: every documented format is read as documented", not wrong, str(wrong))
    check("dates: blank is empty, not an error", page.evaluate("PTImport.csv.parseCsvDate('  ', 'mdy', -8).empty === true"))
    check("dates: 12:00 placeholder is in the chosen time zone; ISO Z and explicit times keep their own", page.evaluate(
        "[PTImport.csv.parseCsvDate('01/08/26','mdy',-8).ms, PTImport.csv.parseCsvDate('01/08/26','mdy',0).ms, PTImport.csv.parseCsvDate('2026-01-08T10:00:00Z','mdy',-8).ms]")
        == [1767902400000, 1767873600000, 1767866400000])

    # ---------- other file shapes ----------
    u16 = tmp / "u16.csv"; u16.write_bytes((HEAD + "\nUTF0001,CA,Red,Ford,Focus,,01/01/26,01/01/26,,caf\u00e9\n").encode("utf-16"))
    zf10, _, _ = convert(page, [u16], tmp, name="u16.zip")
    check("UTF-16 file with a byte order mark converts", "CA-UTF0001" in vehicles_by_plate(zf10) and "caf\u00e9" in vehicles_by_plate(zf10)["CA-UTF0001"]["sightings"][0]["notes"])
    tabbed = csv_file(tmp, "tabbed.tsv", HEAD.replace(",", "\t") + "\nTAB0001\tCA\tRed\tFord\tFocus\t\t01/01/26\t01/01/26\t\t\n")
    zf11, _, _ = convert(page, [tabbed], tmp, name="tab.zip")
    check("tab-separated file converts", "CA-TAB0001" in vehicles_by_plate(zf11))

    # ---------- changing a column's meaning, and remembering it ----------
    oddhead = csv_file(tmp, "odd.csv", "Col A,Col B,Col C\nODD0001,Red Ford Focus,5/6/2026\n")
    page.goto(TOOL); page.evaluate("localStorage.clear()")
    page.set_input_files("#csv-input", [str(oddhead)]); page.wait_for_selector("#map-rows tr")
    guessed = [r.query_selector("select").input_value() for r in page.query_selector_all("#map-rows tr")]
    check("unknown headings default to 'add to notes', so nothing is lost", guessed == ["note_labeled"] * 3, str(guessed))
    check("warns when no plate, date or vehicle column is chosen", all(t in page.inner_text("#map-warnings") for t in ("No column is the plate", "No column is a date", "No column describes the vehicle")))
    for i, t in enumerate(["plate", "vehicle", "date"]):
        page.query_selector_all("#map-rows tr")[i].query_selector("select").select_option(t)
    check("preview updates after changing columns", "NV-" not in page.inner_text("#preview-rows") and "XX-ODD0001" in page.inner_text("#preview-rows") and "2026-05-06" in page.inner_text("#preview-rows"), page.inner_text("#preview-rows"))
    page.goto(TOOL); page.set_input_files("#csv-input", [str(oddhead)]); page.wait_for_selector("#map-rows tr")
    remembered = [r.query_selector("select").input_value() for r in page.query_selector_all("#map-rows tr")]
    check("the column choices are remembered for the same layout", remembered == ["plate", "vehicle", "date"], str(remembered))

    # ---------- no header row ----------
    zf8, report8, _ = convert(page, [csv_file(tmp, "nohead.csv", "NOH0001,CA,Red,Ford,Focus\n")], tmp, name="nohead.zip", header=False, map={0: "plate", 1: "state", 2: "color", 3: "make", 4: "model"}, keep_storage=False)
    check("no header row: first line is data", "CA-NOH0001" in vehicles_by_plate(zf8) and report8["check"]["rows_read"] == 1)

    # ---------- bad input ----------
    page.goto(TOOL); page.evaluate("localStorage.clear()")
    a = csv_file(tmp, "a.csv", HEAD + "\nAAA1,CA,Red,Ford,Focus,,01/01/26,01/01/26,,\n")
    b = csv_file(tmp, "b.csv", "Plate,Color\nBBB2,Blue\n")
    page.set_input_files("#csv-input", [str(a), str(b)]); page.wait_for_selector("#map-rows tr")
    check("files with different columns: clear message and Convert disabled", "different column headings" in page.inner_text("#file-status") and page.is_disabled("#convert"), page.inner_text("#file-status"))
    page.goto(TOOL); page.evaluate("localStorage.clear()")
    page.set_input_files("#csv-input", [str(csv_file(tmp, "q.csv", HEAD + '\nAAA1,CA,"Red,Ford,Focus,,01/01/26,01/01/26,,\n'))]); page.wait_for_selector("#map-rows tr")
    check("an unclosed quote is reported", "never closed" in page.inner_text("#file-status"), page.inner_text("#file-status"))
    page.goto(TOOL)
    check("Convert is disabled until a file is chosen", page.is_disabled("#convert"))
    page.set_input_files("#csv-input", [str(csv_file(tmp, "empty.csv", ""))])
    page.wait_for_timeout(300)
    check("an empty file keeps Convert disabled", page.is_disabled("#convert"))

    # two files with the same layout are combined
    zf9, report9, _ = convert(page, [csv_file(tmp, "m1.csv", HEAD + "\nMUL1,CA,Red,Ford,Focus,,01/01/26,01/01/26,,\n"), csv_file(tmp, "m2.csv", HEAD + "\nMUL2,CA,Blue,Ford,Focus,,02/01/26,02/01/26,,\n")], tmp, name="multi.zip")
    check("two files with the same columns convert together", report9["check"]["rows_read"] == 2 and len(records(zf9, "data/vehicles/")) == 2)

    # the page's own format check catches a record that breaks the schema
    bad_problems = page.evaluate("""() => PTImport.csv.validateFiles(new Map([
      ['data/plates/CA-X.json', JSON.stringify({plate:'x', plateState:'CA'})],
      ['data/vehicles/VEH_00000000.json', JSON.stringify({vehicleKey:'VEH_00000000', sightings: []})]]))""")
    check("format check reports records that break the schema", len(bad_problems) >= 5, str(bad_problems))

    # tools never fetch anything unless an address column is mapped
    requests = []
    ctx.on("request", lambda r: requests.append(r.url) if r.url.startswith("http") else None)
    convert(page, [TEMPLATE], tmp, name="net.zip", geocode="census")
    check("no network requests when there is no address column", not requests, str(requests))

    # ---------- states: Mexican states, Canadian provinces, USG / GOV with a code ----------
    cases = json.loads((ROOT / "tests" / "fixtures" / "state_cases.json").read_text(encoding="utf-8"))
    got = page.evaluate("(cases) => cases.map(([t]) => PTImport.xml.parseState(t))", cases["parse"])
    bad = [(c[0], g, c[1:]) for c, g in zip(cases["parse"], got) if g != c[1:]]
    check("states: the page parses every case in tests/fixtures/state_cases.json like the Python tool", not bad, str(bad[:3]))
    page.goto(TOOL)
    st_csv = csv_file(tmp, "states.csv", HEAD + "\n".join(["",
        "MXA0001,Sonora,White,Toyota,Tacoma,,01/05/26,01/05/26,,",
        "MXA0002,SON,Red,Ford,F-150,,01/06/26,01/06/26,,",
        "MXA0003,Nuevo León,Black,Chevrolet,Tahoe,,01/07/26,01/07/26,,",
        "CAN0001,Quebec,Blue,Honda,Civic,,01/08/26,01/08/26,,",
        "FED0001,GOV DHS,Black,Chevrolet,Suburban,,01/09/26,01/09/26,,",
        "FED0002,usg-g42,Gray,Ford,Expedition,,01/10/26,01/10/26,,",
        "FED0003,GOV,White,Dodge,Charger,,01/11/26,01/11/26,,",
        "FED0004,Government,White,Dodge,Charger,,01/12/26,01/12/26,,",
        "FED0001,GOV DHS,Black,Chevrolet,Suburban,,02/09/26,02/09/26,,"]) + "\n")
    zfs, reps, panels = convert(page, [st_csv], tmp, name="states.zip")
    plates_s = {n.rsplit("/", 1)[-1][:-5]: json.loads(b) for n, b in zfs.items() if n.startswith("data/plates/")}
    check("states: plate files for Mexican, Canadian and federal plates", sorted(plates_s) == sorted(["SON-MXA0001", "SON-MXA0002", "NLE-MXA0003", "QC-CAN0001", "GOV-DHS-FED0001", "USG-G42-FED0002", "GOV-FED0003", "XX-FED0004"]), str(sorted(plates_s)))
    check("states: plateState holds the code, plate holds the number", plates_s["GOV-DHS-FED0001"]["plateState"] == "GOV-DHS" and plates_s["GOV-DHS-FED0001"]["plate"] == "FED0001" and plates_s["SON-MXA0001"]["plateState"] == "SON")
    check("states: the same GOV-DHS plate seen twice is one vehicle with two sightings", len(vehicles_by_plate(zfs)["GOV-DHS-FED0001"]["sightings"]) == 2)
    check("states: format check passed with the new states", "Format check passed" in panels, panels)
    root_s = new_root(tmp, "repo-states")
    unzip_into(zfs, root_s)
    out = run_script(VALIDATE, root_s)
    check("states: scripts/validate_records.py passes on the output", out.returncode == 0, out.stdout[-400:] + out.stderr[-400:])
    run_script(BUILD_INDEX, root_s)
    zfs2, reps2, panels2 = convert(page, [st_csv], tmp, name="states-again.zip", repo=root_s / "data")
    check("states: re-run says Nothing new and finds the coded plates again", "Nothing new" in panels2 and reps2["check"]["new"] == 0, panels2)
    page.goto(TOOL)
    page.set_input_files("#csv-input", [str(st_csv)]); page.wait_for_selector("#map-rows tr")
    check("states: the preview shows GOV-DHS-FED0001 and SON-MXA0001", "GOV-DHS-FED0001" in page.inner_text("#preview-rows") and "SON-MXA0001" in page.inner_text("#preview-rows"), page.inner_text("#preview-rows")[:300])

    # ---------- ignore conflicts: a failed format check holds the ZIP back unless the person overrides it ----------
    zf_ok, _, _ = convert(page, [TEMPLATE], tmp, name="ic-ok.zip")
    check("ignore conflicts: the button is hidden when the format check passes", page.is_hidden("#download-anyway") and page.is_enabled("#download-zip"))
    root_bad = new_root(tmp, "repo-bad")
    unzip_into(zf_ok, root_bad)
    bad_path = next(p_ for p_ in (root_bad / "data" / "vehicles").glob("*.json") if "DEMO001" in p_.read_text())
    bad_rec = json.loads(bad_path.read_text()); bad_rec["bodyStyle"] = "spaceship"; bad_path.write_text(json.dumps(bad_rec))
    grown_ic = csv_file(tmp, "grown-ic.csv", HEAD + "\nDEMO001,CA,Silver,Ford,Explorer,,01/08/26,04/20/26,Exampleville,made-up example row\n")
    zf_bad, rep_bad, panel_bad = convert(page, [grown_ic], tmp, name="ic-bad.zip", repo=root_bad / "data")
    check("ignore conflicts: a record that breaks the format holds the ZIP back", zf_bad == {} and page.is_disabled("#download-zip") and "held back" in panel_bad and ("bodyStyle" in panel_bad or "spaceship" in panel_bad.lower()), panel_bad[-300:])
    check("ignore conflicts: the button is offered", page.is_visible("#download-anyway") and "Ignore conflicts" in page.inner_text("#download-anyway"))
    page.once("dialog", lambda d_: d_.dismiss())
    page.click("#download-anyway")
    check("ignore conflicts: declining the warning downloads nothing and keeps the hold", page.is_disabled("#download-zip") and "Conflicts ignored" not in page.inner_text("#validation-panel"))
    page.once("dialog", lambda d_: d_.accept())
    with page.expect_download() as d_ic:
        page.click("#download-anyway")
    ic_path = Path(tmp) / "ic-forced.zip"; d_ic.value.save_as(ic_path)
    forced = zip_files(ic_path.read_bytes())
    check("ignore conflicts: accepting downloads the ZIP as it is", any("DEMO001" in json.dumps(v_) for v_ in records(forced, "data/vehicles/").values()) and "Conflicts ignored" in page.inner_text("#validation-panel"))
    with page.expect_download() as d_rep:
        page.click("#download-report")
    rep_ic = json.loads(d_rep.value.path().read_text() if hasattr(d_rep.value.path(), "read_text") else Path(d_rep.value.path()).read_text())
    check("ignore conflicts: the report says the conflicts were ignored", rep_ic["conflicts_ignored"] is True and len(rep_ic["validation_problems"]) >= 1, str(rep_ic.get("conflicts_ignored")))

    # one page, two sources: the file type picks the steps
    XMLFILE = ROOT / "tests" / "fixtures" / "sample_export.xml"
    page.goto(TOOL)
    check("before a file is added neither source's steps are shown", page.is_hidden("#map-wrap") and page.is_hidden("#debug") and page.is_disabled("#convert"))
    page.set_input_files("#csv-input", [str(TEMPLATE)]); page.wait_for_selector("#map-rows tr")
    check("a CSV shows the column steps and hides the XML options", page.is_visible("#preview-rows") and page.is_visible("#fill-unknown") and page.is_hidden("#debug") and page.is_hidden("#media-input"))
    page.set_input_files("#xml-input", [str(XMLFILE)])
    check("adding an XML file switches to XML and drops the CSV files", page.is_visible("#debug") and page.is_hidden("#fill-unknown") and page.locator("#file-list li").count() == 1 and "Switched to XML" in page.inner_text("#file-status"), page.inner_text("#file-status"))
    page.set_input_files("#csv-input", [str(TEMPLATE)]); page.wait_for_selector("#map-rows tr")
    check("and back to CSV", page.is_visible("#fill-unknown") and page.is_hidden("#debug") and "Switched to CSV" in page.inner_text("#file-status"))
    page.set_input_files("#csv-input", [str(TEMPLATE)])
    check("the same CSV added twice is listed once", page.locator("#file-list li").count() == 1)

    check("no page errors", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
