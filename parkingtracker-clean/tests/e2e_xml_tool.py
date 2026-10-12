"""Browser test for tools/import.html (XML side).

The page is a port of scripts/migrate_xml_to_json.py. This test runs both on the
same XML and requires byte-identical vehicle, plate and index files, so the two
cannot drift apart. It also checks the ZIP, geocoding (mocked), media, merging
with existing repo data, and error handling.

Run: python3 tests/e2e_xml_tool.py   (needs: pip install playwright pillow)
"""
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TOOL = (ROOT / "tools" / "import.html").as_uri()
FIXTURE = ROOT / "tests" / "fixtures" / "sample_export.xml"
SCRIPT = ROOT / "scripts" / "migrate_xml_to_json.py"

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


def rec(token, plate="ABC1234", make="Black Ford Explorer", stamp="FRI JAN 2 2026 10:00:00 PST", media="",
        comments="seen", address="1 MAIN ST", extra="", tag="record", token_tag="alert_token"):
    tok = f"<{token_tag}>{token}</{token_tag}>" if token is not None else ""
    return (f"<{tag}>{tok}<media>{media}</media><vehicle_license>{plate}</vehicle_license><address>{address}</address>"
            f"<guest>1</guest><vehicle_make>{make}</vehicle_make><month>JAN</month><day>2</day><year>2026</year>"
            f"<comments>{comments}</comments><datestamp>{stamp}</datestamp>{extra}</{tag}>")

def wrap(*groups, decl='<?xml version="1.0" encoding="utf-16" standalone="yes" ?>'):
    return decl + "<db>" + "".join(f"<plate_file_{n}>{''.join(r)}</plate_file_{n}>" for n, r in groups) + "</db>"

CORPUS = {
    "plain.xml": wrap(("A", [rec("1"), rec("2", stamp="SUN JAN 4 2026 18:30:00 PST")]), ("B", [rec("3", plate="ZZZ999", make="Silver Chevy Tahoe")])),
    "variants.xml": wrap(
        ("C", [rec("10", plate="NOPLATE", make="dark blue honda civic"), rec("11", plate="NOPLATE", make="BMW 3 Series"),
               rec("12", plate="", make="Gray Land Rover Defender 90"), rec("13", plate="TOOLONG1234", make=""),
               rec("14", plate="TENCHARS10", make="White Dodge Ram")]),
        ("D", [rec("20", stamp="2026-01-02T10:00:00-08:00"), rec("21", stamp="2026-01-02 10:00:00"), rec("22", stamp="1767380400"),
               rec("23", stamp="1767380400123"), rec("24", stamp="garbage"), rec("25", stamp="FRI FEB 30 2026 10:00:00 PST"),
               rec("26", stamp="FRI JAN 2 2026 10:00:00 XYZ"), rec("27", stamp="Jan 2, 2026 10:00 PDT"), rec("28", stamp="2026-02-30")], ),
    ),
    "extras.xml": ('<?xml version="1.0"?><root xmlns:x="urn:x"><grp><Record id="r1" x:flag="y">'
                   '<ALERT_TOKEN>30</ALERT_TOKEN><Plate>aaa-111</Plate><Make>Red Honda Civic</Make><Date>2026-01-05T08:00:00Z</Date>'
                   '<Notes>café \U0001F697 &amp; <b>bold</b></Notes><mystery>x</mystery><tags><t>a</t><t>b</t></tags></Record>'
                   '<sighting><vehicle_license>BBB222</vehicle_license><comments>no token</comments></sighting></grp></root>'),
    "dupes.xml": wrap(("E", [rec("40"), rec("40", comments="again"), rec(None, plate="CCC333", comments="no token here")])),
    "broken.xml": ('<?xml version="1.0"?><db><plate_file_X>'
                   + rec("90", comments="Driver said <State: CA> & left <b>fast</b> \x01 x < y")
                   + rec("91", plate="BRK0091", comments="AT&T van; 5 < 6 &amp; ok &#169; &bogus;")
                   + '</plate_file_X></db>'),
    "states.xml": wrap(
        ("S", [rec("200", plate="STA0001", extra="<state>nv</state>"), rec("201", plate="STA0002", extra="<plate_state>Nevada</plate_state>"),
               rec("202", plate="STA0003", comments="Parked twice. State: California, white sticker"),
               rec("203", plate="STA0004", extra="<st>Atlantis</st>"), rec("204", plate="STA0005", comments="state=Calif."),
               rec("205", plate="STA0006", extra="<state>ON</state>", comments="State: CA"),
               rec("206", plate="SAME001", extra="<state>CA</state>"), rec("207", plate="SAME001", extra="<state>NV</state>"),
               rec("208", plate="SAME001"), rec("209", plate="STA0007", extra="<province>British Columbia</province>"),
               rec("210", plate="STA0008", comments="no state here"), rec("211", plate="STA0009", comments="State: Oregon and more words")]),
    ),
    "states2.xml": wrap(
        ("M", [rec("400", plate="MEX0001", extra="<state>Sonora</state>"), rec("401", plate="MEX0002", extra="<state>SON</state>"),
               rec("402", plate="MEX0003", extra="<state>Nuevo León</state>"), rec("403", plate="MEX0004", comments="State: Baja California Sur."),
               rec("404", plate="GOV0001", extra="<state>GOV DHS</state>"), rec("405", plate="GOV0002", extra="<state>usg-g42</state>"),
               rec("406", plate="GOV0003", extra="<state>GOV</state>"), rec("407", plate="GOV0004", comments="State: USG G42 parked"),
               rec("408", plate="GOV0005", extra="<state>GOVERNMENT</state>"), rec("409", plate="GOV0006", comments="State: GOV Plate seen"),
               rec("410", plate="NFL0001", extra="<province>Newfoundland and Labrador</province>")]),
    ),
    "html.xml": ('<?xml version="1.0"?>\n<db>\n<plate_file_H>\n'
                 + rec("300", comments="x <State: CA> y <b class=x>bold</b> and <br> then <i>kept</i> 1 < 2 AT&T <!-- <ok> & --> <![CDATA[ <raw & > ]]> end")
                 + "\n" + rec("301", plate="HTM0002", comments='<a href=http://x.y/z?a=1&b=2>link</a> <input disabled> <p>para<p>para2 </div>', extra="<state>NV</state>")
                 + "\n" + rec("302", plate="HTM0003", comments="plain")
                 + "\n</plate_file_H>\n</db>"),
    "media.xml": wrap(("F", [rec("50", media="media/F/50/preview.png,media/F/50/index.html,media/F/50/one.png,media/F/50/two.PNG,"),
                             rec("51", plate="NOPLATE", media="media/F/51/preview.jpeg,media/F/51/index.html,")])),
}


def run_python(xml_files, root, extra=(), default_state=None):
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "schema").exists():
        (root / "schema").symlink_to(ROOT / "schema")
    cmd = [sys.executable, str(SCRIPT), "--root", str(root), "--geocode", "none", "--coarsen", "3"]
    for f in xml_files:
        cmd += ["--in", str(f)]
    if default_state:
        cmd += ["--default-state", default_state]
    out = subprocess.run(cmd + list(extra), capture_output=True, text=True)
    return out


def read_tree(root, subdirs=("data/vehicles", "data/plates")):
    files = {}
    for sub in subdirs:
        for p in sorted((Path(root) / sub).glob("*.json")):
            files[f"{sub}/{p.name}"] = p.read_text(encoding="utf-8")
    return files


def zip_files(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    assert z.testzip() is None, "ZIP failed its CRC check"
    return {n: z.read(n) for n in z.namelist()}


def convert(page, files, tmp, name="out.zip", **opts):
    """Drive the page: choose files, set options, convert, return (zip files, report)."""
    page.goto(TOOL)
    if not opts.get("keep_cache"):
        page.evaluate("localStorage.clear()")
    page.set_input_files("#xml-input", [str(f) for f in files])
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    page.select_option("#geocode", opts.get("geocode", "none"))
    if "flag" in opts: page.select_option("#flag", opts["flag"])
    if "default_state" in opts: page.select_option("#default-state", opts["default_state"])
    if "debug" in opts: page.set_checked("#debug", opts["debug"])
    if "area" in opts: page.fill("#area", opts["area"])
    if "coarsen" in opts: page.fill("#coarsen", opts["coarsen"])
    if "tz" in opts: page.fill("#tz", opts["tz"])
    if "repo" in opts: page.set_input_files("#repo-input", str(opts["repo"]))
    if "media" in opts: page.set_input_files("#media-input", str(opts["media"]))
    if "overrides" in opts: page.set_input_files("#overrides-input", str(opts["overrides"]))
    page.click("#convert")
    page.wait_for_selector("#results:not([hidden])", timeout=60000)
    with page.expect_download() as d:
        page.click("#download-zip")
    zpath = Path(tmp) / name
    d.value.save_as(zpath)
    with page.expect_download() as d2:
        page.click("#download-report")
    rpath = Path(tmp) / (name + ".report.json")
    d2.value.save_as(rpath)
    with page.expect_download() as d3:
        page.click("#download-debug")
    dpath = Path(tmp) / (name + ".debug.txt")
    d3.value.save_as(dpath)
    report = json.loads(rpath.read_text())
    report["_debug_text"] = dpath.read_text(encoding="utf-8")
    return zip_files(zpath.read_bytes()), report


def utf8_files(zf):
    return {n: v.decode("utf-8") for n, v in zf.items() if n.endswith(".json")}


with tempfile.TemporaryDirectory() as t, sync_playwright() as p:
    tmp = Path(t)
    xml_dir = tmp / "xml"; xml_dir.mkdir()
    for name, text in CORPUS.items():
        (xml_dir / name).write_text(text, encoding="utf-8")
    shutil_fixture = xml_dir / "fixture.xml"; shutil_fixture.write_bytes(FIXTURE.read_bytes())

    browser = p.chromium.launch()
    ctx = browser.new_context(accept_downloads=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)

    # ---- 1. parity with the Python tool, file by file ----
    for xml_name in list(CORPUS) + ["fixture.xml"]:
        xml = xml_dir / xml_name
        py_root = tmp / ("py-" + xml_name)
        out = run_python([xml], py_root)
        if out.returncode not in (0, 1):
            check(f"python tool ran on {xml_name}", False, out.stderr[-300:])
            continue
        expected = read_tree(py_root)
        kwargs = {"media": None} if False else {}
        zf, report = convert(page, [xml], tmp, name=xml_name + ".zip")
        got = utf8_files(zf)
        got = {k: v for k, v in got.items() if k.startswith(("data/vehicles", "data/plates"))}
        same = got == expected
        detail = ""
        if not same:
            for k in sorted(set(got) | set(expected)):
                if got.get(k) != expected.get(k):
                    import difflib
                    detail = k + "\n" + "\n".join(list(difflib.unified_diff((expected.get(k) or "").splitlines(), (got.get(k) or "").splitlines(), "py", "js", lineterm="", n=1))[:30])
                    break
        check(f"identical to the Python tool: {xml_name} ({len(expected)} files)", same, detail)

    zf, report = convert(page, [xml_dir / "broken.xml"], tmp, name="broken.zip")
    allv = " ".join(v for k, v in utf8_files(zf).items() if k.startswith("data/vehicles"))
    check("malformed XML (stray < and &) is repaired and reported", report["files"][0].get("repaired_characters", 0) >= 5 and not report["files_failed"], str(report["files"]))
    check("repaired text is kept in the notes", "<State: CA>" in allv and "AT&T" in allv and "5 < 6" in allv)
    py = run_python([xml_dir / "broken.xml"], tmp / "py-broken-rep")
    check("Python tool repairs it too (exit 0)", py.returncode == 0 and "repaired" in py.stderr, py.stderr[-200:])

    # ---- plate state ----
    expect_state = {"STA0001": "NV", "STA0002": "NV", "STA0003": "CA", "STA0004": "XX", "STA0005": "CA", "STA0006": "ON",
                    "STA0007": "BC", "STA0008": "XX", "STA0009": "OR"}
    zf, report = convert(page, [xml_dir / "states.xml"], tmp, name="states.zip")
    zf_xx = zf
    plates = {json.loads(v)["plate"] + "/" + json.loads(v)["plateState"] for k, v in utf8_files(zf).items() if k.startswith("data/plates")}
    got_state = {p.split("/")[0]: p.split("/")[1] for p in plates if not p.startswith("SAME")}
    check("state: element, alias element, full name, text, abbreviation, province, unknown", got_state == expect_state, str(got_state))
    check("state: same plate in three states is three plates", {p for p in plates if p.startswith("SAME001")} == {"SAME001/CA", "SAME001/NV", "SAME001/XX"})
    check("state: plate files are named <ST>-<PLATE>.json", all(re.match(r"data/plates/[A-Z]{2}-[A-Z0-9]+\.json$", k) for k in zf if k.startswith("data/plates")))
    check("state: element wins over text (ON, not CA)", got_state["STA0006"] == "ON")
    check("state: unrecognised value reported", report["states"]["unrecognised"] == {"Atlantis": 1}, str(report["states"]["unrecognised"]))
    check("state: ambiguity reported", report["state_ambiguous"] == [{"plate": "SAME001", "states": ["CA", "NV", "XX"]}])
    check("state: 'st' element understood as a state field mapping", report["debug"]["field_map"]["st"]["becomes"] == "vehicle_state")
    py = tmp / "py-states"
    out = run_python([xml_dir / "states.xml"], py, ["--debug"])
    pyrep = json.loads((py / "reports" / "xml-import-debug.json").read_text())
    check("state summary matches the Python tool", pyrep["states"] == report["states"] and pyrep["state_ambiguous"] == report["state_ambiguous"], f"{pyrep['states']} vs {report['states']}")
    check("field map matches the Python tool", {k: (v["becomes"], v["count"], v["empty"]) for k, v in pyrep["debug"]["field_map"].items()} ==
          {k: (v["becomes"], v["count"], v["empty"]) for k, v in report["debug"]["field_map"].items()})
    check("element census matches the Python tool", pyrep["debug"]["elements"] == report["debug"]["elements"])
    heads = lambda txt: re.findall(r"#(\d+) \S+?:(\d+|\?) token=(\S+) group=(\S+)", txt)
    check("record numbers, line numbers and tokens match the Python tool", heads(report["_debug_text"]) == heads((py / "reports" / "xml-import-debug.txt").read_text()) and len(heads(report["_debug_text"])) == 12,
          str(heads(report["_debug_text"])[:3]))
    stateline = lambda txt: re.findall(r"state (\w\w) from ([^;\[]+?)(?: \[|;)", txt)
    check("state decisions match the Python tool", stateline(report["_debug_text"]) == stateline((py / "reports" / "xml-import-debug.txt").read_text()) and len(stateline(report["_debug_text"])) == 12)
    # Mexican states, USG / GOV with a code
    zf, report = convert(page, [xml_dir / "states2.xml"], tmp, name="states2.zip")
    got2 = {json.loads(v)["plate"]: json.loads(v)["plateState"] for k, v in utf8_files(zf).items() if k.startswith("data/plates")}
    check("states: Mexican states, federal plates with codes, provinces", got2 == {"MEX0001": "SON", "MEX0002": "SON", "MEX0003": "NLE", "MEX0004": "BCS",
          "GOV0001": "GOV-DHS", "GOV0002": "USG-G42", "GOV0003": "GOV", "GOV0004": "USG-G42", "GOV0005": "XX", "GOV0006": "GOV", "NFL0001": "NL"}, str(got2))
    check("states: plate files for coded states are named <STATE>-<PLATE>.json", "data/plates/GOV-DHS-GOV0001.json" in zf and "data/plates/SON-MEX0001.json" in zf)
    # default state, both tools
    py2 = tmp / "py-states-ca"; run_python([xml_dir / "states.xml"], py2, default_state="CA")
    zf, report = convert(page, [xml_dir / "states.xml"], tmp, name="states-ca.zip", default_state="CA")
    got = {k: v for k, v in utf8_files(zf).items() if k.startswith(("data/vehicles", "data/plates"))}
    check("default state matches the Python tool and fills only the gaps", got == read_tree(py2) and "data/plates/CA-STA0008.json" in got and "data/plates/ON-STA0006.json" in got)
    # debug off
    zf2, rep2 = convert(page, [xml_dir / "states.xml"], tmp, name="states-nodebug.zip", debug=False)
    check("debug off: identical records to debug on", {k: v for k, v in utf8_files(zf2).items() if k.startswith("data/")} == {k: v for k, v in utf8_files(zf_xx).items() if k.startswith("data/")})
    check("debug off: no RECORDS section", "\nRECORDS" not in rep2["_debug_text"] and "PLATE STATE" in rep2["_debug_text"])
    # the page shows it
    page.goto(TOOL); page.set_input_files("#xml-input", [str(xml_dir / "states.xml")]); page.select_option("#geocode", "none"); page.click("#convert")
    page.wait_for_selector("#results:not([hidden])", timeout=60000)
    check("page shows a state warning for plates without a state", "no state" in page.inner_text("#state-summary"))
    check("page lists the records with line numbers", page.locator("#debug-records tr").count() == 12 and page.inner_text("#debug-records tr:first-child").split("\t")[1].strip().isdigit())
    page.fill("#debug-filter", "STA0006")
    check("record filter works", page.locator("#debug-records tr").count() == 1)
    page.click("#debug-records tr")
    check("clicking a record shows its explanation and XML", "plate_key" in page.inner_text("#debug-record-detail") and "<record>" in page.inner_text("#debug-record-detail").replace("&lt;", "<"))
    zf, report = convert(page, [xml_dir / "broken.xml"], tmp, name="broken2.zip")
    check("repair details give line numbers in the debug text", re.search(r"line \d+, col \d+: stray <", report["_debug_text"]) is not None)

    # ---- 2. several files at once + folder input ----
    py_root = tmp / "py-all"
    run_python(sorted(xml_dir.glob("*.xml")), py_root)
    zf, report = convert(page, sorted(xml_dir.glob("*.xml")), tmp, name="all.zip")
    got = {k: v for k, v in utf8_files(zf).items() if k.startswith(("data/vehicles", "data/plates"))}
    check("several XML files together match the Python tool", got == read_tree(py_root))
    check("no index.json without the repo data folder", "data/index.json" not in zf)
    check("no photos without a media folder", not any(n.startswith("photos/") for n in zf))
    check("zip root layout is data/...", all(n.startswith("data/") for n in zf))

    # ---- 3. merge with existing repo data (+ index) matches Python importing twice ----
    first = xml_dir / "plain.xml"
    second = tmp / "second.xml"
    second.write_text(wrap(("A", [rec("1"), rec("99", stamp="MON JAN 5 2026 08:00:00 PST", comments="later")]),
                           ("Z", [rec("98", plate="YYY777", make="Blue Honda Accord")])), encoding="utf-8")
    repo_root = tmp / "repo"
    run_python([first], repo_root)
    # simulate a sighting added by the app after the first import
    veh = sorted((repo_root / "data" / "vehicles").glob("*.json"))[0]
    v = json.loads(veh.read_text())
    v["sightings"].append({"id": "S_deadbeef", "timestamp": "2026-03-01T00:00:00.000Z", "location": {"lat": 34.1, "lng": -118.1},
                           "photos": [], "flag": "suspected", "notes": "added in app", "source": None, "observer": "Pat"})
    v["flag"] = "suspected"; v["lastSeen"] = "2026-03-01T00:00:00.000Z"
    veh.write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n")
    py_merge = tmp / "py-merge"
    import shutil
    shutil.copytree(repo_root, py_merge, symlinks=True)
    run_python([second], py_merge)
    zf, report = convert(page, [second], tmp, name="merge.zip", repo=repo_root / "data")
    got = utf8_files(zf)
    expected = read_tree(py_merge, ("data/vehicles", "data/plates"))
    expected["data/index.json"] = (py_merge / "data" / "index.json").read_text(encoding="utf-8")
    before_tree = read_tree(repo_root, ("data/vehicles", "data/plates"))
    changed = {k for k, v in expected.items() if k != "data/index.json" and before_tree.get(k) != v}
    bad = [k for k in expected if k in got and got[k] != expected[k]]
    check("merging into existing repo data matches the Python tool", not bad and changed <= set(got), f"differs: {bad}; missing: {changed - set(got)}")
    check("zip holds only new or changed records (plus the index)", set(got) <= changed | {"data/index.json"}, str(sorted(set(got) - changed)))
    mk = f"data/vehicles/{veh.name}"
    check("sighting added in the app survives a re-import", mk not in got or any(s["id"] == "S_deadbeef" for s in json.loads(got[mk])["sightings"]))
    check("index.json included when repo data is given", "data/index.json" in zf)

    # ---- 3b. old + new records after the data was edited (plate state changed, notes edited, plate type set) ----
    edited = tmp / "edited"
    shutil.copytree(repo_root, edited, symlinks=True)
    vf = sorted((edited / "data" / "vehicles").glob("*.json"))[0]
    ev = json.loads(vf.read_text())
    name = ev["plateAliases"][0]; st, _, pl = name.partition("-")
    pf = edited / "data" / "plates" / f"{name}.json"
    pd = json.loads(pf.read_text()); pf.unlink()
    pd["plateState"] = "CA"; pd["plateType"] = "vanity"
    (edited / "data" / "plates" / f"CA-{pl}.json").write_text(json.dumps(pd, indent=2) + "\n")
    ev["plateAliases"] = [f"CA-{pl}"]; ev["sightings"][0]["notes"] = "edited by hand"
    vf.write_text(json.dumps(ev, indent=2, ensure_ascii=False) + "\n")
    mixed = tmp / "mixed.xml"
    mixed.write_text(wrap(("A", [rec("1"), rec("2", stamp="SUN JAN 4 2026 18:30:00 PST"), rec("77", stamp="TUE JAN 6 2026 09:00:00 PST", comments="brand new")]),
                          ("B", [rec("3", plate="ZZZ999", make="Silver Chevy Tahoe")])), encoding="utf-8")
    py_edit = tmp / "py-edit"
    shutil.copytree(edited, py_edit, symlinks=True)
    run_python([mixed], py_edit)
    zf, report = convert(page, [mixed], tmp, name="edited.zip", repo=edited / "data")
    got = utf8_files(zf)
    expected = read_tree(py_edit, ("data/vehicles", "data/plates"))
    expected["data/index.json"] = (py_edit / "data" / "index.json").read_text(encoding="utf-8")
    before_tree = read_tree(edited, ("data/vehicles", "data/plates"))
    changed = {k for k, v in expected.items() if k != "data/index.json" and before_tree.get(k) != v}
    bad = [k for k in expected if k in got and got[k] != expected[k]]
    check("edited data + old and new XML: output matches the Python tool", not bad and changed <= set(got) and set(got) <= changed | {"data/index.json"}, f"differs: {bad}; missing: {changed - set(got)}; extra: {set(got) - changed}")
    check("edited data: no vehicle or plate duplicated", len(read_tree(py_edit, ("data/vehicles",))) == len(before_tree) - len(read_tree(edited, ("data/plates",))), "")
    evk = f"data/vehicles/{vf.name}"
    check("edited data: hand edits survive", evk not in got or ("edited by hand" in got[evk] and f"CA-{pl}" in got[evk]))
    check("edited data: plate type set by hand is kept", f"data/plates/XX-{pl}.json" not in got)
    check("report counts old records as already imported", report["counts"]["already_imported"] >= 2, str(report["counts"]))
    panel = page.inner_text("#check-panel")
    check("result shows a passed completeness check", "Check passed" in panel and "already in your data" in panel and "brand new" not in panel, panel)
    check("result shows the date range of the file", "dated 2026-01-0" in panel, panel)
    with page.expect_download() as dl:
        page.click("#download-records")
    csv_path = Path(tmp) / "records.csv"; dl.value.save_as(csv_path)
    lines = csv_path.read_text().strip().splitlines()
    check("record-by-record CSV has one line per XML record", len(lines) == 1 + report["counts"]["records_read"] and lines[0].startswith("alert_token,result"), f"{len(lines)} lines")
    check("CSV marks old and new records", any(",already imported," in l for l in lines) and any(",new," in l for l in lines))
    # verification run: the same file again against the data it produced -> nothing new
    out_dir = tmp / "applied"; shutil.copytree(edited, out_dir, symlinks=True)
    for name_, text_ in utf8_files(zf).items():
        (out_dir / name_).parent.mkdir(parents=True, exist_ok=True); (out_dir / name_).write_text(text_, encoding="utf-8")
    zf2, report2 = convert(page, [mixed], tmp, name="again.zip", repo=out_dir / "data")
    check("re-running a fully imported file reports nothing new", "Nothing new" in page.inner_text("#check-panel") and report2["check"]["new"] == 0 and report2["check"]["complete"], page.inner_text("#check-panel"))
    check("re-run changes no files except the index", not [k for k in zf2 if k != "data/index.json"], str(list(zf2)))
    zf3, report3 = convert(page, [mixed], tmp, name="norepo.zip")
    check("choosing no data folder is called out", "did not choose" in page.inner_text("#check-panel"))

    # ---- 4. options ----
    zf, report = convert(page, [xml_dir / "plain.xml"], tmp, name="flag.zip", flag="suspected")
    vs = [json.loads(v) for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")]
    check("flag option applies", all(x["flag"] == "suspected" for x in vs))
    zf, _ = convert(page, [xml_dir / "variants.xml"], tmp, name="tz.zip", tz="XYZ=3")
    xs = [json.loads(v) for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")]
    check("extra time zone is used", any(s["timestamp"] == "2026-01-02T07:00:00.000Z" for x in xs for s in x["sightings"]))

    # ---- 5. geocoding (service mocked; JSONP for Census, fetch for OSM) ----
    calls = []
    def census(route):
        url = route.request.url
        calls.append(url)
        cb = re.search(r"callback=([^&]+)", url).group(1)
        addr = re.search(r"address=([^&]+)", url).group(1)
        if "NOWHERE" in addr.upper():
            body = {"result": {"addressMatches": []}}
        else:
            body = {"result": {"addressMatches": [{"coordinates": {"x": -118.1445012, "y": 34.1478012}}]}}
        route.fulfill(status=200, content_type="application/javascript", body=f"{cb}({json.dumps(body)})")
    ctx.route("https://geocoding.geo.census.gov/**", census)
    geo_xml = tmp / "geo.xml"
    geo_xml.write_text(wrap(("G", [rec("60", address="1 Main St"), rec("61", plate="HHH888", address="NOWHERE LN"),
                                   rec("62", plate="III999", address="")])), encoding="utf-8")
    zf, report = convert(page, [geo_xml], tmp, name="geo.zip", geocode="census", area="Pasadena CA")
    vs = {json.loads(v)["plateAliases"][0] if json.loads(v)["plateAliases"] else "": json.loads(v) for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")}
    loc = vs["XX-ABC1234"]["sightings"][0]["location"]
    check("address becomes a coarsened location", loc == {"lat": 34.1478, "lng": -118.1445}, str(loc))
    check("default area is appended to the lookup", any("Pasadena" in c for c in calls), str(calls[:1]))
    check("unmatched address leaves location unknown and keeps the address", vs["XX-HHH888"]["sightings"][0]["location"] is None and "NOWHERE LN" in vs["XX-HHH888"]["sightings"][0]["notes"])
    check("no address, no lookup", vs["XX-III999"]["sightings"][0]["location"] is None)
    check("report counts the unmatched address", report["geocoding"]["unmatched"] == ["NOWHERE LN"])
    before = len(calls)
    zf, _ = convert(page, [geo_xml], tmp, name="geo2.zip", geocode="census", area="Pasadena CA", keep_cache=True)
    check("addresses are cached between conversions", len(calls) == before)
    csv_path = tmp / "fix.csv"; csv_path.write_text("address,lat,lng\n1 main st,10.5,20.5\n")
    zf, _ = convert(page, [geo_xml], tmp, name="geo3.zip", geocode="census", overrides=csv_path, coarsen="none")
    vs = [json.loads(v) for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")]
    check("override CSV wins and coarsening can be turned off", any(s["location"] == {"lat": 10.5, "lng": 20.5} for x in vs for s in x["sightings"]))

    page.evaluate("localStorage.clear()")
    ctx.unroute("https://geocoding.geo.census.gov/**")
    down = []
    ctx.route("https://geocoding.geo.census.gov/**", lambda r: (down.append(1), r.abort()))
    many = tmp / "many.xml"
    many.write_text(wrap(("M", [rec(str(100 + i), plate="PLATE%d" % i, address=f"{i} A ST") for i in range(7)])), encoding="utf-8")
    zf, report = convert(page, [many], tmp, name="down.zip", geocode="census")
    vs = [json.loads(v) for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")]
    check("service down: every record still imported with unknown locations", len(vs) == 7 and all(s["location"] is None for x in vs for s in x["sightings"]))
    check("service down: stops asking after three failures", len(down) == 3, str(len(down)))
    ctx.unroute("https://geocoding.geo.census.gov/**")

    def osm(route):
        route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"}, body=json.dumps([{"lat": "34.5", "lon": "-118.5"}]))
    ctx.route("https://nominatim.openstreetmap.org/**", osm)
    one = tmp / "one.xml"; one.write_text(wrap(("O", [rec("70")])), encoding="utf-8")
    zf, _ = convert(page, [one], tmp, name="osm.zip", geocode="nominatim")
    vs = [json.loads(v) for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")]
    check("OpenStreetMap provider works", vs[0]["sightings"][0]["location"] == {"lat": 34.5, "lng": -118.5})

    # ---- 6. media ----
    from PIL import Image
    media_root = tmp / "export"; (media_root / "media" / "F" / "50").mkdir(parents=True); (media_root / "media" / "F" / "51").mkdir(parents=True)
    Image.new("RGB", (3000, 2000), (200, 30, 30)).save(media_root / "media" / "F" / "50" / "one.png")
    Image.new("RGB", (800, 600), (30, 30, 200)).save(media_root / "media" / "F" / "51" / "preview.jpeg")
    Image.effect_noise((2400, 1800), 80).convert("RGB").save(media_root / "media" / "F" / "50" / "two.PNG")
    py_media = tmp / "py-media"
    run_python([xml_dir / "media.xml"], py_media, ["--media-root", str(media_root)])
    zf, report = convert(page, [xml_dir / "media.xml"], tmp, name="media.zip", media=media_root)
    got = {k: v for k, v in utf8_files(zf).items() if k.startswith("data/vehicles")}
    exp_m = read_tree(py_media, ("data/vehicles",))
    import difflib
    md = next((k for k in exp_m if got.get(k) != exp_m[k]), None)
    check("with media: records identical to the Python tool (photo names, notes)", md is None,
          md and "\n".join(list(difflib.unified_diff(exp_m[md].splitlines(), (got.get(md) or "").splitlines(), "py", "js", lineterm="", n=1))[:25]))
    photos = sorted(n for n in zf if n.startswith("photos/"))
    check("with media: photos are JPEGs under 500 KB", len(photos) == 3 and all(zf[n][:3] == b"\xff\xd8\xff" and len(zf[n]) <= 500 * 1024 for n in photos), str(photos))
    check("with media: every referenced photo is in the zip", all(ph in zf for v in got.values() for s in json.loads(v)["sightings"] for ph in s["photos"]))
    check("zip root has photos/ too", all(n.startswith(("data/", "photos/")) for n in zf))

    # ---- 7. problems ----
    bad = tmp / "bad.xml"; bad.write_text("<db><record>", encoding="utf-8")
    evil = tmp / "evil.xml"; evil.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaa">]><db>&a;</db>', encoding="utf-8")
    zf, report = convert(page, [bad, xml_dir / "plain.xml"], tmp, name="partial.zip")
    check("one broken file is reported, the other still converts", len(report["files_failed"]) == 1 and len(zf) >= 3, str(report["files_failed"]))
    page.goto(TOOL); page.set_input_files("#xml-input", [str(bad), str(evil)]); page.click("#convert")
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Error')", timeout=10000) if False else None
    for _ in range(50):
        if page.inner_text("#status").startswith("Error"): break
        page.wait_for_timeout(100)
    check("all files broken: clear error and no result", page.inner_text("#status").startswith("Error") and page.is_hidden("#results"), page.inner_text("#status"))
    page.goto(TOOL)
    check("Convert is disabled until a file is chosen", page.is_disabled("#convert"))
    page.set_input_files("#xml-input", [str(tmp / "one.xml")])
    check("Convert enables once a file is chosen", not page.is_disabled("#convert"))

    # UTF-16 with BOM and declared-wrong encodings
    u16 = tmp / "u16.xml"; u16.write_bytes(wrap(("U", [rec("80")])).encode("utf-16"))
    zf, _ = convert(page, [u16], tmp, name="u16.zip")
    check("UTF-16 file with a BOM converts", any(k.startswith("data/vehicles") for k in zf))

    check("no page errors", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
