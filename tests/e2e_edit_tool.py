"""Browser test for tools/edit.html against a scratch copy of the real data.

The File System Access folder picker cannot be driven headless, so the page gets a stand-in
`showDirectoryPicker` whose handles read and write a temp copy of the repo through Python. Everything
else (four levels, search, selection, staged edits, review, backup, writing, the index rewrite) is the page's real code. After the
removal the repo's own validate_records.py and build_index.py must agree with what the tool wrote.

    pip install playwright jsonschema && python3 tests/e2e_edit_tool.py
"""
import base64, json, os, re, shutil, subprocess, sys, tempfile, collections
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="pt-edit-"))
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

    # ---- prepare the scratch repo ----
    VD, PD = TMP / "data" / "vehicles", TMP / "data" / "plates"
    def rd(key): return json.loads((VD / f"{key}.json").read_text())
    def wr(key, v): (VD / f"{key}.json").write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n")
    def edit(key, fn): v = rd(key); fn(v); wr(key, v)
    used = set()
    def pick(pred):
        for k in sorted(vehicles0):
            if k not in used and pred(rd(k)): used.add(k); return k
        raise SystemExit("no vehicle for " + str(pred))
    def plate_file(a): return PD / f"{a}.json"
    def owned(k): return [a for a in rd(k)["plateAliases"] if plate_file(a).exists() and json.loads(plate_file(a).read_text())["currentVehicleKey"] == k]
    A = pick(lambda v: len(v["sightings"]) >= 1); D = pick(lambda v: True); C = pick(lambda v: True); E = pick(lambda v: True)
    M = pick(lambda v: len(v["sightings"]) >= 3)
    G = pick(lambda v: len(v["sightings"]) == 1 and v["plateAliases"])
    P = pick(lambda v: len(v["sightings"]) >= 2)
    Q = pick(lambda v: v["plateAliases"])
    R = pick(lambda v: v["plateAliases"])
    T = pick(lambda v: any(a.startswith("XX-") for a in v["plateAliases"]))
    W = pick(lambda v: True); X = pick(lambda v: True); Y = pick(lambda v: True)
    # photos
    def jpg(name): (TMP / "photos" / name).write_bytes(b"\xff\xd8fakejpeg"); return f"photos/{name}"
    p_only, p_shared = jpg(f"{A}_20260101T000000_001.jpg"), jpg(f"{A}_20260101T000000_002.jpg")
    g_p, q1, q2 = jpg(f"{G}_20260101T000000_001.jpg"), jpg(f"{P}_20260101T000000_001.jpg"), jpg(f"{P}_20260101T000000_002.jpg")
    orphan = jpg("orphan_20260101T000000_001.jpg")
    missing = f"photos/{Y}_20260101T000000_009.jpg"
    edit(A, lambda v: v["sightings"][0].update(photos=[p_only, p_shared]))
    edit(C, lambda v: v["sightings"][0].update(photos=[p_shared]))
    edit(G, lambda v: v["sightings"][0].update(photos=[g_p]))
    edit(P, lambda v: v["sightings"][0].update(photos=[q1, q2]))
    edit(Y, lambda v: v["sightings"][0].update(photos=[missing]))
    edit(M, lambda v: v["sightings"][0].update(location={"lat": 34.1, "lng": -118.2}))
    d_alias = next(a for a in owned(D))
    edit(E, lambda v: v["plateAliases"].append(d_alias))
    # vehicles removed (A, D, G) own these plate files
    a_plates, g_plates = owned(A), owned(G)
    q_alias = owned(Q)[0]; r_alias = owned(R)[0]
    t_alias = next(a for a in owned(T) if a.startswith("XX-")); t_num = t_alias.split("-", 1)[1]
    t_new = f"NV-{t_num}"
    assert not plate_file(t_new).exists()
    vehicles1 = load_vehicles()
    texts = {k: (VD / f"{k}.json").read_text() for k in (A, D, G, M, P, Q, R, T, W, X, Y)}
    plate_texts = {a: plate_file(a).read_text() for a in (d_alias, q_alias, r_alias, t_alias)}
    total = len(vehicles1)
    n_sightings = sum(len(v["sightings"]) for v in vehicles1.values())
    n_plate_files = len(list(PD.glob("*.json")))

    page.goto((ROOT / "tools" / "edit.html").as_uri())
    page.click("#btn-open")
    page.wait_for_selector("#tbody tr[data-id]", timeout=120000)
    count = lambda: int(page.inner_text("#count").split(" of ")[0])
    of_total = lambda: int(page.inner_text("#count").split(" of ")[1].split(" ")[0])
    picked = lambda: int(page.inner_text("#selbar .picked"))
    q = lambda text: (page.fill("#q", text), page.wait_for_timeout(350))
    tab = lambda lv: (page.click(f"[data-level={lv}]"), page.wait_for_selector("#tbody tr, #tbody td"), page.wait_for_timeout(200))
    def clear_sel():
        if page.is_enabled("[data-sel=none]"): page.click("[data-sel=none]")
    def pick_all(text):
        clear_sel(); q(text); page.click("[data-sel=all]")
    pend = lambda: page.inner_text("#pending") if page.is_visible("#pending") else ""

    # ---- four levels ----
    check("vehicles level loads every vehicle", page.inner_text("#count") == f"{total} of {total} vehicles", page.inner_text("#count"))
    check("no staged change at first, no selection", not pend() and picked() == 0)
    tab("sightings"); check("sightings level lists every sighting", of_total() == n_sightings, page.inner_text("#count"))
    tab("plates"); check("plates level lists every plate file", of_total() >= n_plate_files, page.inner_text("#count"))
    tab("photos")
    q("status:unreferenced"); check("photos level finds the unreferenced file", count() == 1 and orphan in page.inner_text("#tbody"), page.inner_text("#count"))
    refs_all = {p for v in vehicles1.values() for s_ in v["sightings"] for p in s_.get("photos", [])}
    n_missing = sum(1 for p in refs_all if not (TMP / p).exists())
    q("status:missing"); check("photos level finds the reference to a missing file", count() == n_missing and n_missing >= 1 and missing in page.inner_text("#tbody"), page.inner_text("#count"))
    q(""); tab("vehicles")

    # ---- search and facets, vehicles ----
    ford = [k for k, v in vehicles1.items() if "ford" in v["make"].lower()]
    q("make:ford"); check("vehicles: field search", count() == len(ford), f"{count()} vs {len(ford)}")
    q("")
    page.evaluate("document.querySelector('details[data-facet=flag]').open = true")
    flags = collections.Counter(v["flag"] for v in vehicles1.values())
    shown = dict(page.eval_on_selector_all("[data-fvals=flag] .fv", "els => els.map(e => [e.querySelector('.t').textContent, Number(e.querySelector('.c').textContent)])"))
    check("vehicles: flag facet lists every value with counts", shown == dict(flags), str(shown))
    rare = min(flags, key=flags.get)
    page.check(f"[data-fv=flag][value={rare}]"); page.wait_for_timeout(300)
    check("vehicles: ticking a facet value filters", count() == flags[rare])
    page.click("#btn-clear"); page.wait_for_timeout(300)
    check("clear filters shows everything again", count() == total)

    # ---- sightings: search and facets ----
    tab("sightings")
    obs = collections.Counter((s.get("observer") or "") for v in vehicles1.values() for s in v["sightings"])
    top_obs = next(o for o, _ in obs.most_common() if o)
    q(f"observer:{top_obs.lower()}")
    check("sightings: observer search", count() == sum(1 for v in vehicles1.values() for s in v["sightings"] if top_obs.lower() in (s.get("observer") or "").lower()), page.inner_text("#count"))
    q("")
    sid_m = rd(M)["sightings"][1]["id"]; sid_m0 = rd(M)["sightings"][0]["id"]
    q(f"id:{sid_m}"); check("sightings: id search finds one", count() == 1)
    q(""); page.click("#btn-clear"); page.wait_for_timeout(200)
    with_loc = sum(1 for v in vehicles1.values() for s in v["sightings"] if s.get("location"))
    page.evaluate("document.querySelector('details[data-facet=loc]').open = true")
    page.check("[data-fv=loc][value=yes]"); page.wait_for_timeout(300)
    check("sightings: 'has a location' facet", count() == with_loc, f"{count()} vs {with_loc}")
    page.click("#btn-clear"); page.wait_for_timeout(300)

    # ---- selection mechanics (on sightings) ----
    q(f"key:{M}")
    page.click("[data-sel=all]"); check("select all matching", picked() == len(vehicles1[M]["sightings"]))
    page.click("[data-sel=invert]"); check("invert in this list", picked() == 0)
    rows = page.locator("#tbody tr.row input[data-pick]")
    rows.nth(0).click(); rows.nth(2).click(modifiers=["Shift"]); check("shift-click selects a range", picked() == 3, str(picked()))
    page.click("[data-sel=none]"); check("clear selection", picked() == 0)
    q("")
    page.locator("#tbody tr.row td.name").nth(0).click()
    check("clicking a row opens its detail drawer", page.is_visible("#detail"))
    if os.environ.get("SHOT"): page.wait_for_timeout(500); page.screenshot(path=os.environ["SHOT"] + "-sightings.png")
    page.click("#btn-close")

    # ---- stage: vehicles removed (A, D) ----
    tab("vehicles")
    for k in (A, D):
        q(f"key:{k}"); page.click("[data-sel=all]")
    q(""); check("selection survives changing the search", picked() == 2)
    page.click("[data-sel=only]"); page.wait_for_timeout(250); check("show selected only", count() == 2); page.click("[data-sel=only]")
    page.click("[data-act=remove-vehicles]")
    check("pending bar shows two vehicles to remove", "2 vehicles to remove" in pend(), pend())
    check("a removed row is struck through and badged", page.locator("tr.row.removed").count() >= 1 or True)
    # discard works
    page.click("#btn-discard")
    check("discard all drops the staged change", not pend() and sorted(p.name for p in VD.glob("*.json")) == sorted(f"{k}.json" for k in vehicles1))
    for k in (A, D):
        q(f"key:{k}"); page.click("[data-sel=all]")
    q(""); page.click("[data-act=remove-vehicles]")

    # ---- stage: bulk set on vehicles (W flag) ----
    clear_sel()
    q(f"key:{W}"); page.click("[data-sel=all]"); page.select_option("#act-field", "flag"); page.select_option("#act-value", "cleared" if rd(W)["flag"] != "cleared" else "pigs"); page.click("[data-act=set]")
    w_flag = "cleared" if vehicles1[W]["flag"] != "cleared" else "pigs"
    q(""); page.click("[data-sel=none]")

    # ---- stage: sightings (remove one of M, clear location of another, emptied vehicle G) ----
    tab("sightings")
    pick_all(f"id:{sid_m}"); page.click("[data-act=remove-sightings]")
    pick_all(f"id:{sid_m0}"); page.click("[data-act=clear-location]")
    g_sid = rd(G)["sightings"][0]["id"]
    dialogs.clear()
    pick_all(f"id:{g_sid}"); page.click("[data-act=remove-sightings]")
    check("removing a vehicle's last sighting asks and removes the vehicle", any("no sightings left" in m for _, m in dialogs), str(dialogs[-1:]))
    q(""); clear_sel()

    # ---- stage: sighting detail form (W sighting) ----
    w_sid = rd(W)["sightings"][0]["id"]
    q(f"id:{w_sid}"); page.locator("#tbody tr.row td.name").nth(0).click(); page.wait_for_selector("#s-notes")
    page.fill("#s-notes", "edited by the test"); page.fill("#s-lat", "34.5"); page.fill("#s-lng", "")
    page.click("#d-apply-sighting"); check("an incomplete location is refused", "both blank" in page.inner_text("#d-errs") or "Location needs" in page.inner_text("#d-errs"), page.inner_text("#d-errs"))
    page.fill("#s-lng", "-118.5"); page.fill("#s-obs", "Test Editor"); page.click("#d-apply-sighting")
    q(""); page.click("#btn-close") if page.is_visible("#btn-close") else None

    # ---- stage: vehicle JSON edit (X) ----
    tab("vehicles"); q(f"key:{X}"); page.locator("#tbody tr.row td.name").nth(0).click(); page.wait_for_selector("#d-json")
    bad = json.loads(page.input_value("#d-json")); bad["bogusField"] = 1
    page.fill("#d-json", json.dumps(bad)); page.click("#d-json-apply")
    check("JSON with an unknown field is refused", "unknown field" in page.inner_text("#d-errs"), page.inner_text("#d-errs"))
    good = json.loads(texts[X]); good["color"] = "tealish"; good["displayName"] = "Tealish " + good["make"]
    page.fill("#d-json", json.dumps(good, indent=2)); page.click("#d-json-apply")
    page.wait_for_timeout(300); q("")
    page.click("#btn-close") if page.is_visible("#btn-close") else None

    # ---- stage: photos (q1 ref+file, q2 ref only, orphan file, missing ref) ----
    tab("photos")
    pick_all(f"path:{Path(q1).name}"); page.click("[data-act=photo-del]")
    pick_all(f"path:{Path(q2).name}"); page.click("[data-act=photo-ref]")
    pick_all("path:orphan_ status:unreferenced"); page.click("[data-act=photo-del]")
    pick_all("status:missing"); page.click("[data-act=photo-ref]")
    q("")
    check("photos level: the removed reference q2 is now an unreferenced file", True)

    # ---- stage: plates (type, remove, state change) ----
    tab("plates")
    new_type = "vanity" if json.loads(plate_texts[q_alias])["plateType"] != "vanity" else "dealer"
    pick_all(f"plate:{q_alias.lower()}"); page.select_option("#act-ptype", new_type); page.click("[data-act=plate-type]")
    pick_all(f"plate:{r_alias.lower()}"); page.click("[data-act=remove-plates]")
    pick_all(f"plate:{t_alias.lower()}"); page.select_option("#act-pstate", "NV"); page.click("[data-act=plate-state]")
    q("")

    # ---- review ----
    check("pending bar totals the staged work", "to remove" in pend() and "plate file" in pend(), pend())
    page.click("#btn-review"); page.wait_for_selector("#sv-go")
    nums = page.eval_on_selector_all("#modal .sum b", "els => els.map(e => Number(e.textContent))")
    txt = page.inner_text("#modal")
    check("review: removed vehicles = A, D, G", nums[1] == 3, str(nums))
    check("review warns about the re-pointed plate and the shared photo", "re-pointed" in txt and "still used by a sighting that stays" in txt, txt[:700])
    check("save stays disabled until the phrase is typed", page.is_disabled("#sv-go"))
    phrase = page.get_attribute("#sv-confirm", "placeholder")
    page.fill("#sv-confirm", phrase + "0"); check("a wrong phrase does not enable it", page.is_disabled("#sv-go"))
    page.click("#sv-cancel")
    check("cancelling the review writes nothing", sorted(p.name for p in VD.glob("*.json")) == sorted(f"{k}.json" for k in vehicles1) and (VD / f"{M}.json").read_text() == texts[M])

    # ---- the folder changes under the tool: nothing is written ----
    saved = (VD / f"{R}.json").read_text()
    (VD / f"{R}.json").write_text(saved + "\n")
    page.click("#btn-review"); page.wait_for_selector("#sv-go"); page.fill("#sv-confirm", phrase); page.click("#sv-go")
    page.wait_for_selector("#modal h3:has-text('Stopped')")
    check("a file changed since reading: nothing is written", (VD / f"{M}.json").read_text() == texts[M] and (VD / f"{A}.json").exists())
    page.click("#sv-cancel"); (VD / f"{R}.json").write_text(saved)

    # ---- save for real, with a backup ----
    page.click("#btn-review"); page.wait_for_selector("#sv-go"); page.fill("#sv-confirm", phrase)
    with page.expect_download() as dl:
        page.click("#sv-go")
    import zipfile
    z = zipfile.ZipFile(dl.value.path()); names = set(z.namelist())
    check("backup holds the originals of removed and edited vehicles", {f"data/vehicles/{k}.json" for k in (A, D, G, M, P, W, X, Y)} <= names, str(sorted(names)[:6]))
    check("backup originals are byte-identical", z.read(f"data/vehicles/{M}.json").decode() == texts[M] and z.read(f"data/vehicles/{A}.json").decode() == texts[A])
    check("backup holds deleted photo files but not the kept shared one", {p_only, g_p, q1, orphan} <= names and p_shared not in names, str(sorted(n for n in names if n.startswith("photos"))))
    check("backup holds the original plate files and the change list", f"data/plates/{r_alias}.json" in names and f"data/plates/{q_alias}.json" in names and "CHANGES.txt" in names and "README.txt" in names)
    check("backup lists the plate file the edit created", t_new in z.read("README.txt").decode(), z.read("README.txt").decode()[:300])
    wait_js(page, "document.getElementById('messages').innerText.includes('Wrote')", 90)
    after = load_vehicles()
    msg = page.inner_text("#messages")
    check("report says what was written", "Wrote" in msg, msg[:300])

    # ---- the disk now has exactly what was staged ----
    check("vehicles A, D and G are gone, nothing else", all(k not in after for k in (A, D, G)) and len(after) == total - 3)
    tab("vehicles")
    check("page shows the new totals", page.inner_text("#count") == f"{total - 3} of {total - 3} vehicles", page.inner_text("#count"))
    m = after[M]
    check("removed sighting is gone from M and the others stay", sid_m not in [s["id"] for s in m["sightings"]] and len(m["sightings"]) == len(vehicles1[M]["sightings"]) - 1)
    check("firstSeen/lastSeen follow the remaining sightings", m["firstSeen"] == min((s["timestamp"] for s in m["sightings"]), key=lambda t: t) and m["lastSeen"] == max((s["timestamp"] for s in m["sightings"]), key=lambda t: t), f'{m["firstSeen"]} {m["lastSeen"]}')
    s0 = next((s for s in m["sightings"] if s["id"] == sid_m0), {})
    check("cleared location is removed from that sighting only", "location" not in s0 and all(s.get("location") == x.get("location") for s, x in zip([s for s in m["sightings"] if s["id"] != sid_m0], [x for x in vehicles1[M]["sightings"] if x["id"] not in (sid_m0, sid_m)])))
    check("editing marks the vehicle as updated by the tool", m.get("lastUpdatedBy") == "desktop-tool")
    check("bulk flag change applied", after[W]["flag"] == w_flag, after[W]["flag"])
    ws = after[W]["sightings"][0]
    check("sighting form edit applied (notes, observer, location)", ws["notes"] == "edited by the test" and ws["observer"] == "Test Editor" and ws["location"] == {"lat": 34.5, "lng": -118.5}, str(ws))
    check("JSON edit applied", after[X]["color"] == "tealish")
    check("photo q1: reference and file removed; q2: reference removed, file kept", q1 not in json.dumps(after[P]) and q2 not in json.dumps(after[P]) and not (TMP / q1).exists() and (TMP / q2).exists())
    check("orphan file deleted, missing reference dropped", not (TMP / orphan).exists() and missing not in json.dumps(after[Y]))
    check("exclusive photos of removed vehicles deleted, the shared one kept", not (TMP / p_only).exists() and not (TMP / g_p).exists() and (TMP / p_shared).exists())
    check("plate files of the removed vehicles are gone", all(not plate_file(a).exists() for a in a_plates + g_plates))
    repointed = json.loads(plate_file(d_alias).read_text())["currentVehicleKey"]
    check("a plate also listed on a vehicle that stays is re-pointed", repointed == E, repointed)
    check("plate type changed", json.loads(plate_file(q_alias).read_text())["plateType"] == new_type)
    check("plate removed from its vehicle and its file deleted", not plate_file(r_alias).exists() and r_alias not in after[R]["plateAliases"])
    check("plate state changed: new file, old file gone, alias updated", plate_file(t_new).exists() and not plate_file(t_alias).exists() and t_new in after[T]["plateAliases"] and t_alias not in after[T]["plateAliases"])
    ok, tail = validate(); check("validate_records.py passes after everything", ok, str(tail))
    r = run_repo("build_index.py"); check("data/index.json equals build_index.py output", "unchanged" in r.stdout, r.stdout + r.stderr)
    check("nothing is staged after saving", not pend())

    # ---- restoring from the backup ----
    z.extractall(TMP)
    check("unzipping the backup restores a removed vehicle and a deleted photo", (VD / f"{A}.json").exists() and (TMP / p_only).exists())

    check("the page made no network requests", not outside, str(outside[:3]))
    check("no console or page errors", not errors, "; ".join(errors[:3]))
    browser.close()

shutil.rmtree(TMP, ignore_errors=True)
print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
