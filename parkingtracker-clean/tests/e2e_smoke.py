"""End-to-end smoke test: drives the real app in Chromium against an in-memory
fake of the GitHub contents API (no network, no token needed).

Covers: token setup, camera + photo flow, photos stored as files, location
coarsening, plate lookup/update, a forced 409 merge, local search, XSS
escaping, offline queue + auto-flush, service worker, CSP violations.

Not part of `npm test` (needs Playwright + Chromium):
    pip install playwright && python3 tests/e2e_smoke.py
"""
import os
import datetime, base64, json, re, subprocess, sys, time, hashlib
from playwright.sync_api import sync_playwright

from pathlib import Path
WEB = str(Path(__file__).resolve().parent.parent / "web")
PORT = 8765
BASE = f"http://localhost:{PORT}/index.html"
server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", WEB, "--bind", "127.0.0.1"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

# ---- fake GitHub repo ----
repo = {}          # path -> {"b64": str, "sha": str}
deletes = []
puts = []          # (path, had_sha)
state = {"conflict_on": None, "offline": False}

def sha_of(b64): return hashlib.sha1(b64.encode()).hexdigest()

def handle(route, request):
    if state["offline"]:
        return route.abort("internetdisconnected")
    url = request.url
    m = re.match(r"https://api\.github\.com/repos/([^/]+)/([^/?]+)(/contents/([^?]+))?(\?.*)?$", url)
    if not m:
        return route.fulfill(status=404, body="{}")
    cors = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"}
    if request.method == "OPTIONS":
        return route.fulfill(status=204, headers=cors)
    path = m.group(4)
    def ok(body, status=200):
        route.fulfill(status=status, content_type="application/json", headers=cors, body=json.dumps(body))
    if path is None:
        return ok({"full_name": "x/y", "permissions": {"push": True}})
    path = re.sub(r"%2F", "/", path)
    if request.method == "GET":
        if path not in repo:
            return ok({"message": "Not Found"}, 404)
        accept = request.headers.get("accept", "")
        if "raw" in accept:
            return route.fulfill(status=200, headers=cors, body=base64.b64decode(repo[path]["b64"]))
        return ok({"content": repo[path]["b64"], "sha": repo[path]["sha"], "encoding": "base64"})
    if request.method == "PUT":
        body = json.loads(request.post_data)
        existing = repo.get(path)
        puts.append((path, "sha" in body))
        if state["conflict_on"] and path.startswith(state["conflict_on"]) and existing:
            # another device wins the race: mutate the remote, then reject this write
            rec = json.loads(base64.b64decode(existing["b64"]))
            other = json.loads(json.dumps(rec["sightings"][-1]))
            t = rec["sightings"][-1]["timestamp"]
            from datetime import datetime, timedelta
            bumped = (datetime.fromisoformat(t.replace("Z", "+00:00")) + timedelta(milliseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            other.update({"id": "S_0badc0de", "notes": "from another device", "timestamp": bumped, "observer": "Other Device"})
            rec["sightings"].append(other)
            nb = base64.b64encode(json.dumps(rec).encode()).decode()
            repo[path] = {"b64": nb, "sha": sha_of(nb)}
            state["conflict_on"] = None
            return ok({"message": "sha does not match"}, 409)
        if existing and body.get("sha") != existing["sha"]:
            return ok({"message": "sha mismatch"}, 409)
        if existing and "sha" not in body:
            return ok({"message": "\"sha\" wasn't supplied."}, 422)
        repo[path] = {"b64": body["content"], "sha": sha_of(body["content"])}
        return ok({"content": {"sha": repo[path]["sha"]}}, 200 if existing else 201)
    if request.method == "DELETE":
        body = json.loads(request.post_data)
        if path not in repo: return ok({"message": "Not Found"}, 404)
        if body.get("sha") != repo[path]["sha"]: return ok({"message": "sha mismatch"}, 409)
        del repo[path]
        deletes.append(path)
        return ok({"commit": {}}, 200)
    ok({}, 405)

def load(path): return json.loads(base64.b64decode(repo[path]["b64"]))
def vehicles(): return [p for p in repo if p.startswith("data/vehicles/")]


def wait_js(page, expr, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => !!(" + expr + ")"):
            return
        time.sleep(0.2)
    raise TimeoutError("condition never true: " + expr)

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = browser.new_context(permissions=["geolocation", "camera"], geolocation={"latitude": 34.14812, "longitude": -118.14449},
                              viewport={"width": 390, "height": 844})
    ctx.add_init_script("localStorage.setItem('pt-classic-home','1');")  # these tests drive the classic home; e2e_sample_data.py covers the new one
    ctx.route("https://api.github.com/**", handle)
    ctx.route("https://nominatim.openstreetmap.org/**", lambda r: r.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"}, body=json.dumps([{"lat": "34.2000", "lon": "-118.3000", "display_name": "Test Street"}])))
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))
    page.on("dialog", lambda d: d.accept())

    # 1. token setup (a name is mandatory: with a shared token it is the only audit trail)
    page.goto(BASE)
    page.wait_for_selector("#token-input")
    page.fill("#token-input", "github_pat_test")
    page.click("[data-action=save-token]")
    page.wait_for_selector("#notice:not([hidden])")
    check("sign-in is refused without a name", "name" in page.inner_text("#notice").lower() and page.locator("#observer-input").count() == 1)
    page.fill("#observer-input", "Test Person")
    page.fill("#token-input", "github_pat_test")
    page.click("[data-action=save-token]")
    page.wait_for_selector("[data-action=start-vehicle]")
    check("token saved -> home screen", True)

    # 2. new vehicle with a photo via the camera screen (draft must survive the trip)
    page.click("[data-action=start-vehicle]")
    page.fill("#color", "Grey"); page.fill("#make", "nissan"); page.fill("#model", "pathfinder")
    page.select_option("#bodyStyle", "suv"); page.fill("#distinguishing", "roof rack, dented bumper")
    page.fill("#plate", "abc-123"); page.select_option("#flag", "suspected"); page.fill("#notes", "first sighting")
    page.click("[data-action=add-photos]")
    page.wait_for_selector("#camera-video")
    wait_js(page, "document.getElementById('camera-video').videoWidth > 0")
    page.click("[data-action=capture-photo]")
    page.wait_for_selector("#photo-preview img")
    page.click("[data-action=accept-photo]")
    check("accepted photo appears as thumbnail", page.locator("#photo-list .thumb").count() == 1)
    page.click("[data-action=finish-photos]")
    page.wait_for_selector("#color")
    check("form draft survives the camera screen", page.input_value("#color") == "Grey" and page.input_value("#plate") == "abc-123")
    check("photo count shown on form", "1 photo" in page.inner_text("body"))
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden])")
    notice = page.inner_text("#notice")
    check("save confirmation shown", "saved" in notice.lower(), notice)

    vks = vehicles()
    check("vehicle file written", len(vks) == 1, str(vks))
    v = load(vks[0]) if vks else {}
    check("plate record written", "data/plates/CA-ABC123.json" in repo)
    check("plate points at vehicle", repo.get("data/plates/CA-ABC123.json") and load("data/plates/CA-ABC123.json")["currentVehicleKey"] == v.get("vehicleKey"))
    photo_paths = [k for k in repo if k.startswith("photos/")]
    check("photo uploaded as a file under photos/", len(photo_paths) == 1 and photo_paths[0] in v["sightings"][0]["photos"], str(photo_paths))
    if photo_paths:
        raw = base64.b64decode(repo[photo_paths[0]]["b64"])
        check("photo is a JPEG under 500 KB", raw[:2] == b"\xff\xd8" and len(raw) <= 500 * 1024, f"{len(raw)} bytes")
    check("no base64 image embedded in record", "base64" not in json.dumps(v))
    check("location coarsened to 4 decimals", v["sightings"][0]["location"] == {"lat": 34.1481, "lng": -118.1445}, str(v["sightings"][0]["location"]))
    check("display name tidy-cased", v["displayName"] == "Grey Nissan Pathfinder", v["displayName"])
    check("home shows all synced", "All synced" in page.inner_text("#sync-status"))
    idx = load("data/index.json") if "data/index.json" in repo else []
    mine = [x for x in idx if x["vehicleKey"] == v["vehicleKey"]]
    check("app wrote data/index.json itself (no workflow needed)", len(mine) == 1, str(idx))
    check("index entry carries coarsened location, flag and plate",
          mine and mine[0]["location"] == {"lat": 34.1481, "lng": -118.1445} and mine[0]["flag"] == "suspected" and mine[0]["plateAliases"] == ["CA-ABC123"], str(mine))
    check("menu is closed by default", not page.is_visible("#menu"))
    page.click(".menu-btn")
    check("hamburger opens the menu", page.is_visible("#menu"))
    check("menu shows who is signed in", "Signed in as Test Person" in page.inner_text("#menu"))
    check("menu holds sync and log out", page.is_visible("[data-action=sync-now]") and page.is_visible("[data-action=logout]"))
    page.keyboard.press("Escape")
    check("Escape closes the menu", not page.is_visible("#menu"))
    page.click(".menu-btn")
    page.mouse.click(200, 400)
    check("tapping outside closes the menu", not page.is_visible("#menu"))
    check("logo is at the top", page.is_visible(".topbar .logo"))
    check("four main actions on home", page.locator(".main-grid button").count() == 4)
    check("sighting is stamped with the observer", v["sightings"][0].get("observer") == "Test Person", str(v["sightings"][0]))
    check("vehicle records lastUpdatedBy", v.get("lastUpdatedBy") == "Test Person", str(v.get("lastUpdatedBy")))

    # 2b. a plate is state + plate: the same characters under another state are a different plate
    page.click("[data-action=start-plate]")
    page.select_option("#state-input", "NV"); page.fill("#plate-input", "ABC 123")
    page.click("[data-action=search-plate]")
    page.wait_for_selector("#plate-results .plate-hit, [data-action=create-with-plate]")
    res = page.inner_text("#plate-results")
    check("same plate, other state: not an exact match", "No vehicle found for NV ABC123" in res, res[:120])
    check("same plate, other state: the CA plate is offered as a hint", "CA ABC123" in res, res[:200])
    page.click("[data-action=create-with-plate]")
    page.wait_for_selector("#plateState")
    check("create-with-plate carries the state and plate into the form", page.input_value("#plateState") == "NV" and page.input_value("#plate") == "ABC123")
    page.click("[data-action=go-home]") if page.locator("[data-action=go-home]").count() else None
    page.wait_for_selector("[data-action=start-plate]")

    # 3. plate lookup -> update, with a forced 409 from 'another device'
    page.click("[data-action=start-plate]")
    page.fill("#plate-input", "ABC 123")
    check("search defaults to Any state", page.input_value("#state-input") == "ANY")
    page.select_option("#state-input", "CA")
    page.click("[data-action=search-plate]")
    page.wait_for_selector("#flag")
    check("plate search opens update form", "Update: Grey Nissan Pathfinder" in page.inner_text("h2"))
    page.select_option("#flag", "confirmed"); page.fill("#notes", "back again")
    state["conflict_on"] = "data/vehicles/"
    page.click("[data-action=update-vehicle]")
    page.wait_for_selector("[data-action=start-local]")
    wait_js(page, "document.getElementById('notice') && !document.getElementById('notice').hidden")
    v = load(vks[0])
    notes = [s["notes"] for s in v["sightings"]]
    check("409 retry merged both devices' sightings", notes == ["first sighting", "from another device", "back again"] or set(notes) == {"first sighting", "from another device", "back again"}, str(notes))
    check("both devices' sightings keep their own observers", [x.get("observer") for x in v["sightings"]] == ["Test Person", "Other Device", "Test Person"], str([x.get("observer") for x in v["sightings"]]))
    idx = load("data/index.json")
    entry = next(x for x in idx if x["vehicleKey"] == vks[0].split("/")[-1][:-5])
    check("index entry follows the merged record (flag, lastSeen)", entry["flag"] == v["flag"] and entry["lastSeen"] == v["lastSeen"], str(entry))
    check("flag updated to confirmed", v["flag"] == "confirmed" or v["sightings"][-1]["flag"] == "confirmed", v["flag"])
    check("exactly one retry (2 vehicle PUTs for this update)", sum(1 for pth, _ in puts if pth == vks[0]) == 3, str([x for x in puts if x[0] == vks[0]]))

    # 4. local search from manual coordinates (index.json absent -> overlay from this device)
    page.click("[data-action=start-local]")
    page.fill("#lat", "34.1481"); page.fill("#lng", "-118.1445")
    page.click("[data-action=search-local]")
    page.wait_for_selector(".result-card")
    card = page.inner_text(".result-card")
    check("local result shows the saved vehicle", "Grey Nissan Pathfinder" in card and "confirmed" in card, card)
    check("local result shows distance + recency", "m" in card and "ago" in card or "just now" in card, card)
    page.fill("#lat", "40.0"); page.fill("#lng", "-100.0")
    page.click("[data-action=search-local]")
    wait_js(page, "document.getElementById('local-results').innerText.includes('No vehicles')")
    check("far-away search returns nothing", True)
    page.click("[data-action=go-home]")

    # 5. XSS attempt in record fields must render as text
    page.click("[data-action=start-vehicle]")
    page.fill("#color", "red"); page.fill("#make", "<img src=x onerror=window.__xss=1>")
    page.select_option("#bodyStyle", "sedan"); page.fill("#distinguishing", "\"><script>window.__xss=2</script>")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("[data-action=start-local]")
    page.click("[data-action=start-local]")
    page.fill("#lat", "34.1481"); page.fill("#lng", "-118.1445")
    page.click("[data-action=search-local]")
    page.wait_for_selector(".result-card")
    page.locator(".result-card", has_text="<img").click()
    page.wait_for_selector("#flag")
    check("injected markup rendered as text, not executed", page.evaluate("window.__xss") is None)
    check("injected markup visible literally", "<img src=x" in page.inner_text("h2"))
    page.click("[data-action=go-home]")

    # 6. offline save -> queue -> auto flush on reconnect
    before = len(vehicles())
    state['offline'] = True; ctx.set_offline(True)
    page.click("[data-action=start-vehicle]")
    page.fill("#color", "blue"); page.fill("#make", "Toyota"); page.select_option("#bodyStyle", "truck")
    page.fill("#distinguishing", "ladder rack"); page.fill("#plate", "OFF1234")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("[data-action=start-local]")
    notice = page.inner_text("#notice")
    check("offline save reports queued-on-device", "device" in notice and "online" in notice, notice)
    check("nothing reached GitHub while offline", len(vehicles()) == before)
    wait_js(page, "document.getElementById('sync-status').innerText.includes('Waiting')")
    check("pending indicator shown", "pending" in page.inner_text("#sync-status"))
    state['offline'] = False; ctx.set_offline(False)
    wait_js(page, "document.getElementById('sync-status').innerText.includes('All synced')")
    check("auto-flush on reconnect uploaded the record", len(vehicles()) == before + 1 and "data/plates/CA-OFF1234.json" in repo)

    # 7. service worker + manifest
    page.reload(); page.wait_for_selector("[data-action=start-vehicle]")
    sw = page.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r)")
    check("service worker registered", sw)
    mf = page.evaluate("fetch('manifest.json').then(r => r.json()).then(j => j.icons.length)")
    check("manifest has icons", mf >= 2)

    # 8. permissions card, logo, and the home layout (fresh contexts, no permissions pre-granted)
    signed_in = "localStorage.setItem('parkingtracker-clean.token','github_pat_test');localStorage.setItem('parkingtracker-clean.observer','Test Person');localStorage.setItem('pt-classic-home','1');"
    allow = """window.__asked = [];
      navigator.geolocation.getCurrentPosition = (ok) => { window.__asked.push('location'); ok({coords: {latitude: 1, longitude: 2}}); };
      navigator.mediaDevices.getUserMedia = async () => { window.__asked.push('camera'); return {getTracks: () => [{stop() {}}]}; };"""
    deny = """window.__asked = [];
      navigator.geolocation.getCurrentPosition = (ok, err) => { window.__asked.push('location'); err({code: 1}); };
      navigator.mediaDevices.getUserMedia = async () => { window.__asked.push('camera'); const e = new Error('no'); e.name = 'NotAllowedError'; throw e; };"""

    def fresh(script):
        c = browser.new_context(viewport={"width": 390, "height": 780})
        c.add_init_script(signed_in + script)
        c.route("https://api.github.com/**", handle)
        pg = c.new_page()
        pg.goto(BASE)
        pg.wait_for_selector(".main-grid")
        return c, pg

    c2, p2 = fresh(allow)
    wait_js(p2, "!document.getElementById('permissions-card').hidden")
    check("permission card offered while using the app", "location and camera" in p2.inner_text("#permissions-card"))
    p2.click("[data-action=request-permissions]")
    wait_js(p2, "window.__asked.length === 2")
    check("Allow asks for location then camera", p2.evaluate("window.__asked") == ["location", "camera"])
    wait_js(p2, "document.getElementById('permissions-card').hidden")
    check("card goes away once allowed", True)

    p2.reload(); p2.wait_for_selector(".main-grid")
    wait_js(p2, "!document.getElementById('permissions-card').hidden")
    p2.click("[data-action=dismiss-permissions]")
    p2.reload(); p2.wait_for_selector(".main-grid"); time.sleep(0.5)
    check("Not now hides the card for the session", p2.evaluate("document.getElementById('permissions-card').hidden"))

    # layout: the four buttons own most of the screen, with large type and a 3D look
    box = p2.evaluate("(() => { const r = document.querySelector('.main-grid').getBoundingClientRect(); return [r.height, innerHeight]; })()")
    check("main buttons fill most of the screen", box[0] >= 0.5 * box[1], str(box))
    style = p2.evaluate("(() => { const s = getComputedStyle(document.querySelector('.main-grid button')); return [parseFloat(s.fontSize), s.boxShadow, s.backgroundImage, parseFloat(s.borderBottomWidth)]; })()")
    check("button text is large", style[0] >= 26, str(style))
    check("buttons have depth (gradient, shadow, thick lower edge)", "gradient" in style[2] and style[1] != "none" and style[3] >= 6, str(style))
    p2.hover("[data-action=start-plate]")

    # logo: home from anywhere; asks first when a form has been filled in
    p2.click("[data-action=logo-home]")
    check("logo on home is harmless", p2.locator(".main-grid").count() == 1)
    p2.click("[data-action=start-plate]"); p2.wait_for_selector("#plate-input")
    p2.click("[data-action=logo-home]"); p2.wait_for_selector(".main-grid")
    check("logo returns home from plate search", True)
    p2.click("[data-action=start-vehicle]"); p2.wait_for_selector("#color")
    p2.click("[data-action=logo-home]"); p2.wait_for_selector(".main-grid")
    check("logo returns home from an empty form without asking", True)
    p2.click("[data-action=start-vehicle]"); p2.wait_for_selector("#color"); p2.fill("#color", "red")
    asked = []
    p2.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
    p2.click("[data-action=logo-home]"); time.sleep(0.3)
    check("filled form: logo asks and Cancel keeps the form", asked and "not been saved" in asked[0] and p2.locator("#color").count() == 1 and p2.input_value("#color") == "red", str(asked))
    p2.once("dialog", lambda d: d.accept())
    p2.click("[data-action=logo-home]"); p2.wait_for_selector(".main-grid")
    check("filled form: OK discards and goes home", True)
    c2.close()

    c3, p3 = fresh(deny)
    wait_js(p3, "!document.getElementById('permissions-card').hidden")
    p3.click("[data-action=request-permissions]")
    wait_js(p3, "document.getElementById('permissions-card').innerText.includes('blocked')")
    check("denied permissions explain what still works", "location" in p3.inner_text("#permissions-card") and "camera" in p3.inner_text("#permissions-card"))
    c3.close()

    # ---- location switch (pin, top left) ----
    page.goto(BASE); page.wait_for_selector(".loc-btn")
    g = page.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
        return { pin: r('.loc-btn'), logo: r('.logo-btn .logo'), menu: r('.menu-btn'), w: innerWidth }; })()""")
    check("pin top left, logo centered, menu right", g["pin"]["right"] < g["logo"]["left"] and abs((g["logo"]["left"] + g["logo"]["right"]) / 2 - g["w"] / 2) <= 6 and g["menu"]["left"] > g["logo"]["right"], str(g))
    colour = lambda: page.evaluate("getComputedStyle(document.querySelector('.loc-btn')).color")
    check("location on by default: pin is green", colour() == "rgb(22, 163, 74)" and page.get_attribute(".loc-btn", "aria-pressed") == "true")
    page.click(".loc-btn")
    check("tap turns it off: pin is grey", colour() == "rgb(156, 163, 175)" and page.get_attribute(".loc-btn", "aria-pressed") == "false" and page.evaluate("localStorage.getItem('pt-location')") == "off")
    page.reload(); page.wait_for_selector(".loc-btn")
    check("off survives a reload and nothing asks about location", colour() == "rgb(156, 163, 175)" and page.locator("#permissions-card:not([hidden])").count() == 0)
    # ---- back arrow: returns to the last screen, hidden on first open ----
    check("no back arrow on first open", page.locator(".back-btn").count() == 0)
    check("space for the arrow is reserved so the pin does not move", page.locator(".back-slot").count() == 1)
    pin_x = page.evaluate("document.querySelector('.loc-btn').getBoundingClientRect().left")
    page.click("[data-action=start-plate]"); page.wait_for_selector("#plate-input")
    check("back arrow appears after leaving home, left of the pin", page.locator(".back-btn").count() == 1 and page.evaluate("document.querySelector('.back-btn').getBoundingClientRect().right <= document.querySelector('.loc-btn').getBoundingClientRect().left + 1"))
    check("pin stays put when the arrow appears", abs(page.evaluate("document.querySelector('.loc-btn').getBoundingClientRect().left") - pin_x) < 1)
    page.click(".back-btn"); page.wait_for_selector("[data-action=start-plate]")
    check("arrow goes back to home and is hidden again", page.locator(".screen.home-screen").count() == 1 and page.locator(".back-btn").count() == 0)
    page.click("[data-action=start-plate]"); page.wait_for_selector("#plate-input")
    page.click("[data-action=logo-home]"); page.wait_for_selector("[data-action=start-plate]")
    check("after the logo, the arrow leads to the last screen viewed", page.locator(".back-btn").count() == 1)
    page.click(".back-btn"); page.wait_for_selector("#plate-input")
    check("arrow reopened the search", page.locator(".screen.plate-search").count() == 1)
    page.click("[data-action=logo-home]"); page.wait_for_selector("[data-action=start-plate]")

    def start_vehicle(plate):
        page.click("[data-action=start-vehicle]")
        page.fill("#color", "Blue"); page.fill("#make", "mazda"); page.fill("#model", "three")
        page.select_option("#bodyStyle", "sedan"); page.fill("#plate", plate)
    def find(plate):
        for k in vehicles():
            v = load(k)
            if any(a.endswith("-" + plate) for a in v["plateAliases"]): return v
        return None

    start_vehicle("LOCOFF1")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector(".modal")
    check("saving with location off asks, with three choices", "Location is off" in page.inner_text(".modal") and page.locator(".modal [data-choice]").count() == 3)
    page.click(".modal [data-choice=cancel]")
    check("Cancel returns to the form, nothing saved", page.locator(".modal").count() == 0 and page.input_value("#plate") == "LOCOFF1" and find("LOCOFF1") is None)
    page.click("[data-action=save-vehicle]"); page.wait_for_selector(".modal")
    page.click(".modal [data-choice=skip]")
    page.wait_for_selector("#notice:not([hidden])")
    v = find("LOCOFF1")
    check("Save without location: saved with no location, switch stays off", v and v["sightings"][0]["location"] is None and colour() == "rgb(156, 163, 175)", str(v and v["sightings"][0]["location"]))
    start_vehicle("LOCON1")
    page.click("[data-action=save-vehicle]"); page.wait_for_selector(".modal")
    page.click(".modal [data-choice=on]")
    page.wait_for_selector("#notice:not([hidden])")
    v = find("LOCON1")
    check("Turn on and add: location saved and pin is green", v and v["sightings"][0]["location"] == {"lat": 34.1481, "lng": -118.1445} and colour() == "rgb(22, 163, 74)", str(v and v["sightings"][0]["location"]))
    start_vehicle("LOCON2")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden])")
    v = find("LOCON2")
    check("with location on, saving does not ask", page.locator(".modal").count() == 0 and v and v["sightings"][0]["location"] is not None)

    # ---- sharing a record: button, link, and opening a link ----
    key2 = find("LOCON2")["vehicleKey"]; key1 = find("LOCON1")["vehicleKey"]
    btn = page.locator("#notice-actions [data-action=share-vehicle]")
    check("the save confirmation offers Share this record", btn.count() == 1 and btn.get_attribute("data-key") == key2)
    page.evaluate("window.__shared = null; Object.defineProperty(navigator, 'share', {value: async (d) => { window.__shared = d; }, configurable: true})")
    btn.click()
    wait_js(page, "window.__shared")
    shared = page.evaluate("window.__shared")
    check("Share opens the phone's share sheet with a link to that record", shared["url"] == BASE.split("#")[0].rstrip("/") + "/#v=" + key2 or shared["url"].endswith("#v=" + key2), str(shared))
    check("the link carries only the record key, no token", "github_pat" not in shared["url"] and shared["url"].count("#") == 1)
    page.evaluate("""Object.defineProperty(navigator, 'share', {value: undefined, configurable: true});
        window.__copied = null; Object.defineProperty(navigator, 'clipboard', {value: {writeText: async (t) => { window.__copied = t; }}, configurable: true})""")
    page.click("[data-action=start-vehicle]"); page.click("[data-action=go-home]")  # any screen change; share from a vehicle screen next
    pl = ctx.new_page()
    pl.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))
    pl.goto(BASE + "#v=" + key1)
    pl.wait_for_selector("#flag")
    check("a shared link opens that vehicle", "Update: Blue Mazda Three" in pl.inner_text("h2") and pl.evaluate("location.hash") == "")
    if os.environ.get("SHOT"): pl.screenshot(path=os.environ["SHOT"] + "-navigate.png")
    nav = pl.locator("a[data-navigate]")
    href = nav.get_attribute("href") or ""
    check("vehicle screen has a Navigate button that opens directions to the last seen location",
          nav.count() == 1 and href.startswith("https://www.google.com/maps/dir/?api=1&destination=34.1481%2C-118.1445") and nav.get_attribute("target") == "_blank" and "noopener" in nav.get_attribute("rel"), href)
    check("each sighting with a location has its own Map link", pl.locator(".history a.maplink").count() == 1 and pl.locator(".history a.maplink").get_attribute("href") == href, pl.locator(".history").inner_text())
    pl.evaluate("Object.defineProperty(navigator, 'share', {value: undefined, configurable: true}); window.__copied = null; Object.defineProperty(navigator, 'clipboard', {value: {writeText: async (t) => { window.__copied = t; }}, configurable: true})")
    check("the vehicle screen has Share this record", pl.locator("[data-action=share-vehicle]").count() == 1)
    pl.click("[data-action=share-vehicle]")
    wait_js(pl, "window.__copied")
    check("no share sheet: the link is copied and the person is told", pl.evaluate("window.__copied").endswith("#v=" + key1) and "Link copied" in pl.inner_text("#notice"))
    pl.goto(BASE + "#v=VEH_00000000")
    pl.wait_for_selector("#notice:not([hidden])")
    check("a link to a record not on the server explains what to do", "not on the server yet" in pl.inner_text("#notice"), pl.inner_text("#notice"))
    pl.close()
    cs = browser.new_context(viewport={"width": 390, "height": 780})
    cs.route("https://api.github.com/**", handle)
    ps = cs.new_page()
    ps.goto(BASE + "#v=" + key1)
    ps.wait_for_selector("#token-input")
    check("signed out: the link waits for sign-in and is cleared from the address", ps.evaluate("location.hash") == "")
    ps.fill("#observer-input", "Desk Person"); ps.fill("#token-input", "github_pat_test")
    ps.click("[data-action=save-token]")
    ps.wait_for_selector("#flag")
    check("after signing in, the shared vehicle opens", "Update: Blue Mazda Three" in ps.inner_text("h2"))
    cs.close()

    # ---- nothing is required: save the little that is known ----
    def start_empty():
        page.click("[data-action=start-vehicle]")
        page.uncheck("#attachLocation")
    n0 = len(vehicles())
    start_empty()
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden])")
    check("completely empty (and no location) is not saved, with a friendly hint", "Add anything you know" in page.inner_text("#notice") and len(vehicles()) == n0, page.inner_text("#notice"))
    page.fill("#notes", "white van by gate B")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=saved")
    mine = [load(k) for k in vehicles() if load(k)["sightings"][0].get("notes") == "white van by gate B"]
    check("a note alone saves a record with unknown color, make and body style", len(mine) == 1 and (mine[0]["color"], mine[0]["make"], mine[0]["bodyStyle"], mine[0]["displayName"]) == ("unknown", "unknown", "unknown", "Unknown vehicle"), str(mine))
    check("no plate is fine", mine and mine[0]["plateAliases"] == [])
    start_empty(); page.fill("#plate", "ONLY999"); page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=saved")
    check("a plate alone saves a vehicle and its plate record", find("ONLY999") is not None and any(k.endswith("-ONLY999.json") and k.startswith("data/plates/") for k in repo))
    start_empty(); page.select_option("#plateState", "GOV"); page.fill("#plateStateCode", "dhs"); page.fill("#plate", "gv 1234"); page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=saved")
    gv = find("GV1234")
    check("a government plate with a code is saved as <STATE>-<PLATE> with the code in the state", gv is not None and load("data/plates/GOV-DHS-GV1234.json")["plateState"] == "GOV-DHS" and load("data/plates/GOV-DHS-GV1234.json")["plate"] == "GV1234" and "GOV-DHS-GV1234" in gv["plateAliases"], str(sorted(k for k in repo if "GV1234" in k)))
    start_empty(); page.select_option("#plateState", "SON"); page.fill("#plate", "son 777"); page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=saved")
    check("a Mexican state is saved with its 3-letter code", "data/plates/SON-SON777.json" in repo and load("data/plates/SON-SON777.json")["plateState"] == "SON")
    # ---- previous sighting: set an earlier time and a chosen place ----
    page.click("[data-action=start-vehicle]"); page.uncheck("#attachLocation")
    check("previous-sighting fields start hidden", not page.is_visible("#prevWhen"))
    page.check("#prevOn")
    check("ticking previous sighting shows time and place", page.is_visible("#prevWhen") and not page.is_visible("#attachLocation"))
    page.fill("#plate", "PREV111")
    page.select_option("#prevLoc", "picked")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=Find place")
    check("a chosen place that was never found is refused with a hint", find("PREV111") is None)
    page.fill("#prevPlace", "1 Test Street"); page.click("[data-action=find-place]")
    page.wait_for_selector("#prev-result >> text=Pinned")
    check("address search pins coordinates and offers a map check", "34.2, -118.3" in page.inner_text("#prev-result").replace("34.20000", "34.2").replace("-118.30000", "-118.3") and page.locator("#prev-result a").count() == 1, page.inner_text("#prev-result"))
    page.evaluate("() => { const d = new Date(Date.now() - 20*3600*1000); const p = n => String(n).padStart(2,'0'); document.getElementById('prevWhen').value = `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; }")
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=saved")
    pv = find("PREV111")
    ps = pv["sightings"][0] if pv else {}
    age_h = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(ps.get("timestamp", "1970-01-01T00:00:00+00:00").replace("Z", "+00:00"))).total_seconds() / 3600 if pv else 0
    check("previous sighting is stored at the earlier time with the chosen place", pv is not None and 19 < age_h < 21 and ps["location"] == {"lat": 34.2, "lng": -118.3, "manual": True} and "recordedAt" in ps, str(ps))
    check("firstSeen and lastSeen follow the sighting time", pv["firstSeen"] == ps["timestamp"] == pv["lastSeen"])

    # ---- find by description ----
    page.goto(BASE); page.wait_for_selector("[data-action=start-plate]")
    page.click("[data-action=toggle-menu]"); page.click("#menu [data-action=start-describe]")
    page.wait_for_selector("#desc-q")
    page.fill("#desc-q", "pathfind")
    page.wait_for_selector("#desc-results .result-card")
    check("description search lists a vehicle by part of its name", "Pathfinder" in page.inner_text("#desc-results"), page.inner_text("#desc-results"))
    page.fill("#desc-q", "pathfind zzzz")
    check("all words must match", page.locator("#desc-results .result-card").count() == 0 and "No vehicles match" in page.inner_text("#desc-results"))
    page.fill("#desc-q", "pathfind"); page.click("#desc-results .result-card")
    page.wait_for_selector("#flag")
    check("tapping a result opens the vehicle", "Pathfinder" in page.inner_text("h2"))

    # ---- edit your own sighting (24 h window, honor system) ----
    first_key = vks[0].split("/")[-1][:-5]
    _r = load(vks[0])
    for _x in _r["sightings"][1:]: _x["photos"] = []   # the other device's copy shared the photo; unshare it so removal can delete the file
    _nb = base64.b64encode(json.dumps(_r).encode()).decode(); repo[vks[0]] = {"b64": _nb, "sha": sha_of(_nb)}
    v0 = load(vks[0]); s0 = v0["sightings"][0]
    photo0 = s0["photos"][0]
    page.goto(BASE + "#v=" + first_key); page.wait_for_selector("#flag")
    check("Edit shows only on my own recent sightings", page.locator(f"[data-action=edit-sighting][data-id='{s0['id']}']").count() == 1 and page.locator("[data-action=edit-sighting][data-id=S_0badc0de]").count() == 0)
    page.click(f"[data-action=edit-sighting][data-id='{s0['id']}']"); page.wait_for_selector("[data-action=save-sighting-edit]")
    page.fill("#notes", "edited note"); page.fill("#color", "red")
    page.check(".rm-photo"); page.select_option("#prevLoc", "none")
    page.click("[data-action=save-sighting-edit]"); page.wait_for_selector("#notice:not([hidden]) >> text=updated")
    v1 = load(vks[0]); e0 = next(x for x in v1["sightings"] if x["id"] == s0["id"])
    check("edit changes notes, clears the location and stamps editedAt", e0["notes"] == "edited note" and e0["location"] is None and "editedAt" in e0 and v1["color"] == "red", str(e0))
    check("removed photo leaves the sighting and the file is deleted from the repo", photo0 not in e0["photos"] and photo0 in deletes and photo0 not in repo, str((e0["photos"], deletes)))
    check("other sightings are untouched", [x["id"] for x in v1["sightings"]] == [x["id"] for x in v0["sightings"]])
    ientry = next(x for x in load("data/index.json") if x["vehicleKey"] == first_key)
    check("index entry matches the edited record", ientry["lastSeen"] == v1["lastSeen"] and ientry["displayName"] == v1["displayName"], str(ientry))

    page.click("[data-action=start-vehicle]")   # location is on and ticked by default: the location alone is enough
    page.click("[data-action=save-vehicle]")
    page.wait_for_selector("#notice:not([hidden]) >> text=saved")
    located = [load(k) for k in vehicles() if load(k)["displayName"] == "Unknown vehicle" and load(k)["sightings"][0]["location"] and not load(k)["plateAliases"] and not load(k)["sightings"][0].get("notes")]
    check("location alone saves a record", len(located) == 1 and located[0]["sightings"][0]["location"] == {"lat": 34.1481, "lng": -118.1445}, str(located))
    # a handoff: the teammate opens it and completes it
    page.goto(BASE + "#v=" + located[0]["vehicleKey"]); page.wait_for_selector("#flag")
    check("a vehicle with unknown details opens for completion", "Update: Unknown vehicle" in page.inner_text("h2"))
    page.fill("#make", "ford"); page.fill("#color", "white"); page.select_option("#bodyStyle", "van")
    page.uncheck("#attachLocation")
    page.click("[data-action=update-vehicle]"); page.wait_for_selector("#notice:not([hidden]) >> text=updated")
    v = load("data/vehicles/" + located[0]["vehicleKey"] + ".json")
    check("the teammate's details complete the record and rename it", (v["color"], v["make"], v["bodyStyle"], v["displayName"]) == ("white", "Ford", "van", "White Ford"), str(v["displayName"]))
    check("the original location is still there to navigate to", v["sightings"][0]["location"] is not None and len(v["sightings"]) == 2)

    # every file the app wrote still passes the repository's own validator
    import subprocess, tempfile, pathlib
    tree = pathlib.Path(tempfile.mkdtemp())
    for path_, f in repo.items():
        if path_.startswith(("data/", "photos/")):
            (tree / path_).parent.mkdir(parents=True, exist_ok=True)
            (tree / path_).write_bytes(base64.b64decode(f["b64"]))
    (tree / "schema").symlink_to(pathlib.Path(__file__).resolve().parent.parent / "schema")
    r = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "validate_records.py"), "--root", str(tree)], capture_output=True, text=True)
    check("records saved with blank fields pass validate_records.py", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    bad = [e for e in console_errors if "Failed to load resource" not in e]
    check("no console/page errors (incl. CSP violations)", not bad, "; ".join(bad[:5]))
    browser.close()

server.terminate()
failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
