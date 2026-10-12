"""Browser test for tools/search.html against a scratch copy of the real data.

The File System Access folder picker cannot be driven headless, so the page gets a stand-in
`showDirectoryPicker` whose handles read and write a temp copy of the repo through Python. Everything
else (parsing, filters, edits, saving, index rebuild) is the page's real code. After the edits the repo's
own validate_records.py and build_index.py must agree with what the tool wrote.

    pip install playwright jsonschema && python3 tests/e2e_search_tool.py
"""
import base64, json, os, re, shutil, subprocess, sys, tempfile, collections
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="pt-search-"))
for d in ("data", "schema", "scripts"):
    shutil.copytree(ROOT / d, TMP / d)
(TMP / "photos").mkdir()
results = []

def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

def wait_js(page, expr, timeout=120):
    # The page's CSP forbids eval, which page.wait_for_function relies on; poll with evaluate instead.
    import time
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => !!(" + expr + ")"):
            return
        time.sleep(0.25)
    raise TimeoutError(expr)

def load_vehicles():
    out = {}
    for f in (TMP / "data" / "vehicles").glob("*.json"):
        out[f.stem] = json.loads(f.read_text())
    return out

def hay(key, v):
    notes = "\n".join(s.get("notes") or "" for s in v["sightings"])
    obs = [s.get("observer") or "" for s in v["sightings"]]
    src = [str(s.get("source") or "").split(":")[0] for s in v["sightings"]]
    parts = [v["displayName"], v["color"], v["make"], v.get("model") or "", str(v.get("year") or ""), v["bodyStyle"], v["flag"],
             " ".join(v["plateAliases"]), " ".join(v["distinguishing"]), v.get("distinguishingNotes") or "", notes,
             " ".join(obs), " ".join(src), v.get("lastUpdatedBy") or "", key]
    return "\n".join(parts).lower()

def run_repo(script, *args):
    return subprocess.run([sys.executable, str(TMP / "scripts" / script), "--root", str(TMP), *args], capture_output=True, text=True)

def validate():
    r = run_repo("validate_records.py")
    return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-3:]

# ---------- the stand-in folder picker ----------
def p_(rel): return TMP / rel
def fs_list(path):
    d = p_(path)
    return json.dumps([{"name": c.name, "kind": "directory" if c.is_dir() else "file"} for c in sorted(d.iterdir())]) if d.is_dir() else "null"
def fs_read(path):
    f = p_(path)
    return base64.b64encode(f.read_bytes()).decode() if f.is_file() else None
def fs_write(path, text):
    f = p_(path); f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text, encoding="utf-8"); return True
def fs_remove(path):
    f = p_(path)
    if f.is_file(): f.unlink()
    return True
def fs_kind(path):
    f = p_(path)
    return "directory" if f.is_dir() else "file" if f.is_file() else None
def fs_mkdir(path): p_(path).mkdir(parents=True, exist_ok=True); return True

MOCK = r"""
(() => {
  const join = (a, b) => (a ? a + '/' + b : b);
  const nf = () => new DOMException('not found', 'NotFoundError');
  class F { constructor(path) { this.kind = 'file'; this.path = path; this.name = path.split('/').pop(); }
    async getFile() { const b = await window.__fs_read(this.path); if (b === null) throw nf();
      return new File([Uint8Array.from(atob(b), (c) => c.charCodeAt(0))], this.name); }
    async createWritable() { const path = this.path; let buf = ''; return { write: async (t) => { buf += t; }, close: async () => { await window.__fs_write(path, buf); } }; } }
  class D { constructor(path) { this.kind = 'directory'; this.path = path; this.name = path.split('/').pop() || 'repo-clone'; }
    async *values() { const raw = await window.__fs_list(this.path); if (raw === 'null') throw nf();
      for (const it of JSON.parse(raw)) yield it.kind === 'file' ? new F(join(this.path, it.name)) : new D(join(this.path, it.name)); }
    async getDirectoryHandle(name, o) { const p = join(this.path, name); const k = await window.__fs_kind(p);
      if (k !== 'directory') { if (o && o.create) await window.__fs_mkdir(p); else throw nf(); } return new D(p); }
    async getFileHandle(name, o) { const p = join(this.path, name); const k = await window.__fs_kind(p);
      if (k !== 'file' && !(o && o.create)) throw nf(); return new F(p); }
    async removeEntry(name) { await window.__fs_remove(join(this.path, name)); } }
  window.showDirectoryPicker = async () => new D('');
})();
"""

vehicles0 = load_vehicles()
flag_counts = collections.Counter(v["flag"] for v in vehicles0.values())
sample_xx = next(k for k, v in sorted(vehicles0.items()) if any(a.startswith("XX-") for a in v["plateAliases"]))

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    for fn in (fs_list, fs_read, fs_write, fs_remove, fs_kind, fs_mkdir):
        page.expose_function("__" + fn.__name__, fn)
    page.add_init_script(MOCK)
    outside, errors = [], []
    page.on("request", lambda r: outside.append(r.url) if not r.url.startswith(("file:", "data:", "blob:")) else None)
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    dialogs = []
    def on_dialog(d):
        dialogs.append((d.type, d.message))
        d.accept(d.default_value if d.type == "prompt" and not PROMPT[0] else PROMPT[0] or None)
    PROMPT = [None]
    page.on("dialog", on_dialog)

    page.goto((ROOT / "tools" / "search.html").as_uri())
    page.click("#btn-open")
    page.wait_for_selector("#tbody tr[data-key]", timeout=120000)
    total = len(vehicles0)
    check("loads every vehicle", page.inner_text("#count").replace(",", "") == f"{total} of {total} match", page.inner_text("#count"))
    if os.environ.get("SHOT"):
        page.screenshot(path=os.environ["SHOT"] + "-list.png")
    check("index.json formatting matches what the page would write (no 'differs' note)", "differs from what these records would produce" not in page.inner_text("#messages"))
    check("first load sets the review baseline quietly: nothing new", page.inner_text("[data-chip=new]").strip() == "New 0")

    # facets list every used value with counts
    def facet_counts(fid):
        rows = page.eval_on_selector_all(f"[data-fv={fid}] .fv", "els => els.map(e => [e.querySelector('.t').textContent, Number(e.querySelector('.c').textContent)])")
        return dict(rows)
    page.evaluate("document.querySelector('details[data-facet=flag]').open = true")
    check("flag facet shows every value with the right counts", facet_counts("flag") == dict(flag_counts), str(facet_counts("flag")))
    makes = collections.Counter(v["make"] for v in vehicles0.values())
    page.evaluate("document.querySelector('details[data-facet=make]').open = true")
    check("make facet lists all distinct makes", facet_counts("make") == dict(makes))

    # text search
    def count(): return int(page.inner_text("#count").split(" of ")[0].replace(",", ""))
    def search(q):
        page.fill("#q", q); page.wait_for_timeout(400)
    search("tahoe")
    exp = sum("tahoe" in hay(k, v) for k, v in vehicles0.items())
    check("free text finds records by any field", count() == exp and exp > 0, f"{count()} vs {exp}")
    check("matches in notes/features show a highlighted snippet", page.locator("#tbody mark").count() > 0 or exp == 0)
    search("make:chevy -tahoe")
    exp = sum("chevy" in v["make"].lower() and "tahoe" not in hay(k, v) for k, v in vehicles0.items())
    check("field:value and -exclude work", count() == exp, f"{count()} vs {exp}")
    search('"unknown chevy"')
    exp = sum("unknown chevy" in hay(k, v) for k, v in vehicles0.items())
    check('"quoted phrase" search', count() == exp and exp > 0, f"{count()} vs {exp}")
    search("")
    # facet selection narrows; counts elsewhere follow
    page.check("[data-fid=flag][data-val=confirmed]")
    check("ticking a flag value filters the list", count() == flag_counts["confirmed"], str(count()))
    page.uncheck("[data-fid=flag][data-val=confirmed]")
    # date filter
    page.fill("#first-from", "2026-01-01"); page.dispatch_event("#first-from", "change")
    exp = sum(v["firstSeen"][:10] >= "2026-01-01" for v in vehicles0.values())
    check("first-seen date filter", count() == exp, f"{count()} vs {exp}")
    page.fill("#first-from", ""); page.dispatch_event("#first-from", "change")
    check("clearing the date restores the full list", count() == total)

    # ---- new / updated records after a "git pull" ----
    src = vehicles0[sample_xx]
    newv = json.loads(json.dumps(src)); newv["vehicleKey"] = "VEH_0badf00d"; newv["displayName"] = "Teal Mini Cooper"
    newv["color"], newv["make"], newv["model"] = "teal", "Mini", "Cooper"; newv["plateAliases"] = ["CA-NEWTEST1"]
    newv["flag"] = "suspected"; newv["firstSeen"] = newv["lastSeen"] = "2026-10-11T08:00:00.000Z"
    photo = "photos/VEH_0badf00d_20261011T080000_001.jpg"
    newv["sightings"] = [{"id": "S_0badf00d", "timestamp": "2026-10-11T08:00:00.000Z", "location": {"lat": 34.1, "lng": -118.1}, "photos": [photo],
                          "flag": "suspected", "notes": "Seen outside the bakery with a roof box", "source": None, "observer": "Pat"}]
    (TMP / "data/vehicles/VEH_0badf00d.json").write_text(json.dumps(newv, indent=2) + "\n")
    (TMP / "data/plates/CA-NEWTEST1.json").write_text(json.dumps({"plate": "NEWTEST1", "plateState": "CA", "plateType": "standard",
        "currentVehicleKey": "VEH_0badf00d", "firstSeen": "2026-10-11T08:00:00.000Z", "updated": "2026-10-11T08:00:00.000Z"}, indent=2) + "\n")
    from PIL import Image
    Image.new("RGB", (60, 40), (10, 120, 160)).save(TMP / photo, "JPEG")
    upd_key = sorted(vehicles0)[5]
    upd = json.loads((TMP / f"data/vehicles/{upd_key}.json").read_text())
    upd["sightings"].append({"id": "S_0badf11d", "timestamp": "2026-10-11T09:00:00.000Z", "location": None, "photos": [], "flag": "unknown", "notes": "again", "source": None, "observer": "Pat"})
    upd["lastSeen"] = "2026-10-11T09:00:00.000Z"
    (TMP / f"data/vehicles/{upd_key}.json").write_text(json.dumps(upd, indent=2) + "\n")
    page.click("#btn-reload")
    wait_js(page, "document.getElementById('count').textContent.replace(/,/g, '').includes('%d of %d')" % (total + 1, total + 1))
    check("after a pull: 1 new and 1 updated record are flagged", page.inner_text("[data-chip=new]").strip() == "New 1" and page.inner_text("[data-chip=updated]").strip() == "Updated 1",
          page.inner_text("#status-chips"))
    page.click("[data-chip=new]")
    check("New chip lists the new vehicle with a NEW badge", count() == 1 and page.locator("#tbody .badge.new").count() == 1)
    page.click("[data-chip=new]"); page.click("[data-chip=updated]")
    check("Updated chip lists the vehicle that got a sighting", count() == 1 and page.locator(f"#tbody tr[data-key={upd_key}]").count() == 1)
    page.click("[data-chip=updated]")

    # ---- edit one record: details + photo shown ----
    search("bakery")
    check("search finds text inside sighting notes", count() == 1)
    page.click("#tbody tr[data-key=VEH_0badf00d]")
    page.wait_for_selector("#e-color")
    if os.environ.get("SHOT"):
        page.wait_for_timeout(500); page.screenshot(path=os.environ["SHOT"] + "-detail.png")
    page.wait_for_selector("#detail .thumbs img", timeout=10000)
    check("detail panel shows the sighting photo from the local photos folder", page.locator("#detail .thumbs img").count() == 1)
    page.fill("#e-year", "abc"); page.click("#btn-apply")
    check("a bad year is refused and nothing is staged", "four digits" in page.inner_text("#detail-errs") and page.locator("#pending").is_hidden())
    page.fill("#e-year", "")
    page.fill("#e-color", "Dark Teal"); page.fill("#e-make", "mini"); page.select_option("#e-flag", "confirmed")
    page.fill("#e-feats", "roof box, dented door"); page.click("#btn-apply")
    page.wait_for_selector("#pending:not([hidden])")
    check("applying stages the edit (pending bar shows 1 record)", "1 record" in page.inner_text("#pending"))
    check("the file on disk is untouched until Save", json.loads((TMP / "data/vehicles/VEH_0badf00d.json").read_text())["color"] == "teal")
    page.click("#btn-save")
    page.wait_for_selector("#pending", state="hidden")
    saved = json.loads((TMP / "data/vehicles/VEH_0badf00d.json").read_text())
    check("saved record has the edits, a rebuilt display name and the editor stamp",
          saved["color"] == "dark teal" and saved["make"] == "Mini" and saved["displayName"] == "Dark teal Mini Cooper" and saved["flag"] == "confirmed"
          and saved["distinguishing"] == ["roof box", "dented door"] and saved["lastUpdatedBy"] == "desktop-tool", json.dumps(saved)[:300])
    raw = (TMP / "data/vehicles/VEH_0badf00d.json").read_text()
    check("file keeps the app's formatting (2-space JSON, trailing newline)", raw == json.dumps(saved, indent=2, ensure_ascii=False) + "\n")
    idx = json.loads((TMP / "data/index.json").read_text())
    check("data/index.json now includes the new vehicle", any(e["vehicleKey"] == "VEH_0badf00d" and e["flag"] == "confirmed" for e in idx))
    ok, tail = validate(); check("validate_records.py passes after the edit", ok, str(tail))
    check("saving shows the git commands to run", "git push" in page.inner_text("#messages"))
    search("bakery")
    check("a record saved here is marked reviewed (no NEW badge left)", count() == 1 and page.locator("#tbody .badge.new").count() == 0)

    # ---- fix a plate state (the common cleanup) ----
    search("")
    page.click("#btn-clear")
    page.fill("#q", f"key:{sample_xx.lower()}"); page.wait_for_timeout(400)
    page.click(f"#tbody tr[data-key={sample_xx}]"); page.wait_for_selector("#e-color")
    old_alias = next(a for a in vehicles0[sample_xx]["plateAliases"] if a.startswith("XX-"))
    page.select_option(".plates .pr[data-alias] .p-state", "FL"); page.click("#btn-apply")
    page.wait_for_selector("#pending:not([hidden])")
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")
    new_alias = "FL-" + old_alias[3:]
    after = json.loads((TMP / f"data/vehicles/{sample_xx}.json").read_text())
    check("plate state change renames the plate file and updates the alias",
          (TMP / f"data/plates/{new_alias}.json").is_file() and not (TMP / f"data/plates/{old_alias}.json").exists() and new_alias in after["plateAliases"] and old_alias not in after["plateAliases"])
    plate_rec = json.loads((TMP / f"data/plates/{new_alias}.json").read_text())
    check("new plate file has the right fields", plate_rec["plateState"] == "FL" and plate_rec["plate"] == old_alias[3:] and plate_rec["currentVehicleKey"] == sample_xx)
    ok, tail = validate(); check("validate_records.py passes after the plate move", ok, str(tail))

    # ---- government plates carry a code; Mexican states are 3 letters ----
    page.select_option(".plates .pr[data-alias] .p-state", "GOV")
    check("search tool: choosing GOV shows the code box", page.locator(".plates .pr[data-alias] .p-code").is_visible())
    page.fill(".plates .pr[data-alias] .p-code", "dhs"); page.click("#btn-apply")
    page.wait_for_selector("#pending:not([hidden])")
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")
    gov_alias = "GOV-DHS-" + old_alias[3:]
    after = json.loads((TMP / f"data/vehicles/{sample_xx}.json").read_text())
    gov_rec = json.loads((TMP / f"data/plates/{gov_alias}.json").read_text()) if (TMP / f"data/plates/{gov_alias}.json").is_file() else {}
    check("search tool: GOV with a code renames the plate file to GOV-DHS-<plate>", gov_alias in after["plateAliases"] and not (TMP / f"data/plates/{new_alias}.json").exists() and gov_rec.get("plateState") == "GOV-DHS" and gov_rec.get("plate") == old_alias[3:], str(gov_rec))
    page.select_option(".plates .pr[data-alias] .p-state", "SON"); page.click("#btn-apply")
    page.wait_for_selector("#pending:not([hidden])")
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")
    son_alias = "SON-" + old_alias[3:]
    check("search tool: a Mexican state renames the plate file to SON-<plate> and drops the code", (TMP / f"data/plates/{son_alias}.json").is_file() and not (TMP / f"data/plates/{gov_alias}.json").exists())
    ok, tail = validate(); check("validate_records.py passes with GOV and SON plates", ok, str(tail))
    page.select_option(".plates .pr[data-alias] .p-state", "FL"); page.click("#btn-apply")
    page.wait_for_selector("#pending:not([hidden])")
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")

    # clash: moving another plate onto an existing alias is refused
    other = next(k for k, v in sorted(vehicles0.items()) if k != sample_xx and any(a.startswith("XX-") for a in v["plateAliases"]))
    other_alias = next(a for a in vehicles0[other]["plateAliases"] if a.startswith("XX-"))
    page.click("#btn-clear")
    page.fill("#q", f"key:{other.lower()}"); page.wait_for_timeout(400)
    page.click(f"#tbody tr[data-key={other}]"); page.wait_for_selector("#e-color")
    page.fill(".plates .pr[data-alias] .p-num", old_alias[3:]); page.select_option(".plates .pr[data-alias] .p-state", "FL"); page.click("#btn-apply")
    check("moving a plate onto one that already exists is refused", "already exists" in page.inner_text("#detail-errs") and page.locator("#pending").is_hidden(), page.inner_text("#detail"))
    page.click("#btn-close")

    # ---- rename a value everywhere ----
    page.click("#btn-clear")
    page.evaluate("document.querySelector('details[data-facet=make]').open = true")
    n_chevy = makes.get("Chevy", 0)
    PROMPT[0] = "Chevrolet"
    page.hover("[data-fv=make] .fv:has-text('Chevy')")
    page.click("[data-rename=make][data-val=Chevy]")
    page.wait_for_selector("#pending:not([hidden])")
    check("renaming a make stages every record that has it", f"{n_chevy} record" in page.inner_text("#pending"), page.inner_text("#pending"))
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")
    v_after = load_vehicles()
    check("no 'Chevy' left and display names follow", not any(v["make"] == "Chevy" for v in v_after.values())
          and all("Chevrolet" in v["displayName"] for v in v_after.values() if v["make"] == "Chevrolet" and v["displayName"] != ""))
    ok, tail = validate(); check("validate_records.py passes after the rename", ok, str(tail))
    PROMPT[0] = None

    # ---- bulk changes on the filtered list ----
    page.click("#btn-clear")
    page.fill("#q", "make:ford"); page.wait_for_timeout(400)
    n_ford = count()
    page.select_option("#bulk-flag", "cleared")
    page.wait_for_selector("#pending:not([hidden])")
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")
    v_after = load_vehicles()
    ford_flags = {v["flag"] for v in v_after.values() if "ford" in v["make"].lower()}
    check("bulk set flag applies to every matching record", n_ford > 0 and ford_flags == {"cleared"}, str(ford_flags))
    page.click("#btn-clear")
    page.fill("#q", "make:tahoe"); page.wait_for_timeout(400)
    page.fill("#q", "model:tahoe"); page.wait_for_timeout(400)
    xx_before = sum(1 for k, v in v_after.items() if "tahoe" in (v.get("model") or "").lower() for a in v["plateAliases"] if a.startswith("XX-"))
    nv_before = sum(1 for k, v in v_after.items() if "tahoe" in (v.get("model") or "").lower() for a in v["plateAliases"] if a.startswith("NV-"))
    page.select_option("#bulk-state", "NV")
    page.wait_for_selector("#pending:not([hidden])")
    page.click("#btn-save"); page.wait_for_selector("#pending", state="hidden")
    v_after = load_vehicles()
    xx_left = sum(1 for k, v in v_after.items() if "tahoe" in (v.get("model") or "").lower() for a in v["plateAliases"] if a.startswith("XX-"))
    nv = sum(1 for k, v in v_after.items() if "tahoe" in (v.get("model") or "").lower() for a in v["plateAliases"] if a.startswith("NV-"))
    check("bulk plate state moves unknown-state plates", xx_before > 0 and xx_left == 0 and nv == xx_before + nv_before, f"{xx_before} {xx_left} {nv} (NV already {nv_before})")
    ok, tail = validate(); check("validate_records.py passes after the bulk edits", ok, str(tail))

    # the index the tool maintains equals what the repo's own builder produces
    r = run_repo("build_index.py")
    check("data/index.json equals build_index.py output", "unchanged" in r.stdout, r.stdout + r.stderr)

    # ---- CSV and reload ----
    page.click("#btn-clear"); page.fill("#q", "make:mini"); page.wait_for_timeout(400)
    with page.expect_download() as dl:
        page.click("#btn-csv")
    csv_text = Path(dl.value.path()).read_text()
    check("CSV download has a header and one line per match", csv_text.splitlines()[0].startswith("vehicleKey,displayName") and len(csv_text.strip().splitlines()) == count() + 1)
    page.click("#btn-reload")
    page.wait_for_selector("#tbody tr[data-key]", timeout=120000)
    check("reload shows nothing as new after the tool's own saves", page.inner_text("[data-chip=new]").strip() == "New 0", page.inner_text("#status-chips"))

    check("the page made no network requests", not outside, str(outside[:3]))
    check("no console or page errors", not errors, "; ".join(errors[:3]))
    browser.close()

shutil.rmtree(TMP, ignore_errors=True)
print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
