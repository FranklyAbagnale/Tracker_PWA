"""Browser test: registration-data lookup, end to end in Chromium.

The GitHub API and the lookup proxy are both faked. The app is served with LOOKUP_URL pointed at /api/lookup
(config.js is rewritten on the way in; the file on disk stays off).

Checks the rule "look at what is on file first": a lookup runs only for a California plate that is not listed,
a vehicle whose make or model is unknown, a plate typed into the new-vehicle form that is not on file, or when
asked for. It also checks what gets stored (year/make/model only, and only when make and model agree; no VIN).

    pip install playwright && python3 tests/e2e_lookup.py
"""
import base64, hashlib, json, re, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8767
BASE = f"http://localhost:{PORT}/index.html"
NOW = "2026-10-10T12:00:00.000Z"

def b64(obj):
    return base64.b64encode(json.dumps(obj).encode()).decode()

def vehicle(key, make, model, plate_key, color="grey"):
    return {
        "vehicleKey": key, "displayName": " ".join(x for x in (color, make, model) if x), "color": color, "make": make,
        "model": model, "bodyStyle": "sedan", "distinguishing": ["unknown"], "plateAliases": [plate_key], "flag": "confirmed",
        "sightings": [{"id": "S_" + key[-8:], "timestamp": NOW, "location": None, "photos": [], "flag": "confirmed", "notes": None, "source": "field-app"}],
        "firstSeen": NOW, "lastSeen": NOW,
    }

def plate_rec(plate, state, vkey):
    return {"plate": plate, "plateState": state, "plateType": "standard", "currentVehicleKey": vkey, "firstSeen": NOW, "updated": NOW}

repo, writes = {}, {}
def put_repo(path, obj):
    enc = b64(obj)
    repo[path] = {"b64": enc, "sha": hashlib.sha1(enc.encode()).hexdigest()}

put_repo("data/vehicles/VEH_aaaa0001.json", vehicle("VEH_aaaa0001", "Unknown", None, "CA-UNK0001", color="unknown"))
put_repo("data/plates/CA-UNK0001.json", plate_rec("UNK0001", "CA", "VEH_aaaa0001"))
put_repo("data/vehicles/VEH_bbbb0002.json", vehicle("VEH_bbbb0002", "Honda", "Civic", "CA-TST1001", color="red"))
put_repo("data/plates/CA-TST1001.json", plate_rec("TST1001", "CA", "VEH_bbbb0002"))

CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"}

def github(route, request):
    m = re.match(r"https://api\.github\.com/repos/[^/]+/[^/?]+(/contents/([^?]+))?", request.url)
    def ok(body, status=200):
        route.fulfill(status=status, content_type="application/json", headers=CORS, body=json.dumps(body))
    if request.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    if not m or m.group(2) is None:
        return ok({"permissions": {"push": True}})
    path = m.group(2).replace("%2F", "/")
    if request.method == "PUT":
        body = json.loads(request.post_data)
        sha = hashlib.sha1(body["content"].encode()).hexdigest()
        repo[path] = {"b64": body["content"], "sha": sha}
        if path.endswith(".json"):
            writes[path] = json.loads(base64.b64decode(body["content"]))
        return ok({"content": {"sha": sha}})
    if path not in repo:
        return ok({"message": "Not Found"}, 404)
    if "raw" in request.headers.get("accept", ""):
        return route.fulfill(status=200, headers=CORS, body=base64.b64decode(repo[path]["b64"]))
    return ok({"content": repo[path]["b64"], "sha": repo[path]["sha"]})

# What the fake proxy knows (a real proxy returns exactly these three fields)
ANSWERS = {
    "NEW1234": {"year": 2021, "make": "Kia", "model": "Soul"},
    "MIS5555": {"year": 2017, "make": "Honda", "model": "Civic"},
    "UNK0001": {"year": 2018, "make": "Toyota", "model": "Camry"},
    "TST1001": {"year": 2019, "make": "Honda", "model": "Civic LX"},
    "HON7777": {"year": 2015, "make": "Honda", "model": "Civic"},
}
calls = []

def proxy(route, request):
    body = json.loads(request.post_data)
    calls.append(f'{body["state"]}-{body["plate"]}')
    assert request.headers.get("authorization") == "Bearer github_pat_test", request.headers
    answer = ANSWERS.get(body["plate"])
    payload = {"status": "found", "vehicle": answer} if answer else {"status": "not_found"}
    route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(payload))

CONFIG = (ROOT / "web/js/config.js").read_text()
assert "export const LOOKUP_URL = '';" in CONFIG
ENABLED_CONFIG = CONFIG.replace("export const LOOKUP_URL = '';", "export const LOOKUP_URL = '/api/lookup';")

results = []
def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

def wait_js(page, expr, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => !!(" + expr + ")"):
            return
        time.sleep(0.2)
    raise TimeoutError(expr)

SIGNED_IN = ("localStorage.setItem('parkingtracker-clean.token','github_pat_test');localStorage.setItem('parkingtracker-clean.observer','Test Person');"
             "localStorage.setItem('pt-classic-home','1');")

server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT / "web"), "--bind", "127.0.0.1"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

def new_page(browser, enabled):
    ctx = browser.new_context(permissions=["geolocation"], geolocation={"latitude": 34.1478, "longitude": -118.1445},
                              viewport={"width": 390, "height": 844}, service_workers="block")
    ctx.add_init_script(SIGNED_IN)
    ctx.route("https://api.github.com/**", github)
    ctx.route("**/api/lookup", proxy)
    ctx.route(re.compile(r"https://(www\.)?(faxvin|carfax|epicvin|findbyplate)\.com/.*"), lambda route, req: route.fulfill(status=200, content_type="text/html", body="<title>stub</title>"))
    if enabled:
        ctx.route("**/js/config.js", lambda route, req: route.fulfill(status=200, content_type="text/javascript", body=ENABLED_CONFIG))
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto(BASE)
    page.wait_for_selector("[data-action=start-plate]")
    return ctx, page, errors

def search(page, plate, state):
    page.click("[data-action=start-plate]")
    page.select_option("#state-input", state)
    page.fill("#plate-input", plate)
    page.click("[data-action=search-plate]")
    page.wait_for_selector("#flag, #plate-results [data-action=create-with-plate]")

def last_written(prefix):
    return [v for k, v in writes.items() if k.startswith(prefix)]

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------- feature off (the shipped default): no lookup UI, no calls ----------
        ctx0, pg0, err0 = new_page(browser, enabled=False)
        search(pg0, "NEW1234", "CA")
        check("lookup off: a CA plate that is not listed shows no lookup", pg0.locator("#lookup-box").count() == 0 and not calls, str(calls))
        pg0.click("[data-action=create-with-plate]"); pg0.wait_for_selector("#color")
        check("lookup off: the form has no lookup text", pg0.inner_text("#form-lookup") == "")
        check("lookup off: no errors", not err0, "; ".join(err0[:3]))
        ctx0.close()

        ctx, page, errors = new_page(browser, enabled=True)

        # ---------- 1. not listed + California: looked up automatically ----------
        search(page, "NEW1234", "CA")
        page.wait_for_function("document.getElementById('lookup-box') && document.getElementById('lookup-box').innerText.includes('Registration data')")
        check("not listed (CA): registration data appears by itself", "2021 Kia Soul" in page.inner_text("#lookup-box"), page.inner_text("#plate-results"))
        check("the lookup ran once, for that plate", calls == ["CA-NEW1234"], str(calls))
        page.click("[data-action=create-with-plate]"); page.wait_for_selector("#color")
        check("creating from it fills make and model", page.input_value("#make") == "Kia" and page.input_value("#model") == "Soul")
        wait_js(page, "document.getElementById('form-lookup').innerText.includes('Matches what you entered')")
        check("the form says it matches and will be saved", True)
        check("the same plate was not looked up twice", calls == ["CA-NEW1234"], str(calls))
        page.fill("#color", "blue"); page.select_option("#bodyStyle", "suv"); page.fill("#distinguishing", "dent")
        page.click("[data-action=save-vehicle]")
        wait_js(page, "document.querySelector('.notice') && !document.querySelector('.notice').hidden")
        saved = last_written("data/vehicles/")
        check("saved vehicle carries the lookup answer", len(saved) == 1 and saved[0].get("plateLookup", {}).get("plate") == "CA-NEW1234"
              and saved[0]["plateLookup"]["year"] == 2021 and saved[0]["plateLookup"]["make"] == "Kia" and saved[0]["plateLookup"]["model"] == "Soul", str(saved))
        check("no VIN or owner anywhere in what was written", not re.search(r"vin|owner", json.dumps(writes), re.I))
        page.wait_for_selector("[data-action=start-plate]")

        # ---------- 2. new-vehicle form: typed plate not on file, details disagree ----------
        page.click("[data-action=start-vehicle]"); page.wait_for_selector("#color")
        page.fill("#make", "Ford"); page.fill("#model", "F-150")
        page.fill("#plate", "MIS5555"); page.press("#plate", "Tab")
        wait_js(page, "document.getElementById('form-lookup').innerText.includes('Registration data')")
        note = page.inner_text("#form-lookup")
        check("typed plate: looked up after the on-file check", calls == ["CA-NEW1234", "CA-MIS5555"], str(calls))
        check("typed details are not overwritten", page.input_value("#make") == "Ford" and page.input_value("#model") == "F-150")
        check("a disagreement is called out and not saved", "differs" in note and "will not be saved" in note, note)
        page.fill("#color", "white"); page.select_option("#bodyStyle", "truck"); page.fill("#distinguishing", "ladder rack")
        page.click("[data-action=save-vehicle]")
        wait_js(page, "Object.values(window).length >= 0 && document.querySelector('[data-action=start-plate]')")
        mismatched = [v for v in last_written("data/vehicles/") if v["make"] == "Ford"]
        check("mismatch: saved without a lookup field", len(mismatched) == 1 and "plateLookup" not in mismatched[0], str(mismatched))

        # make agrees but the model does not: still not stored
        page.click("[data-action=start-vehicle]"); page.wait_for_selector("#color")
        page.fill("#make", "Honda"); page.fill("#model", "Accord")
        page.fill("#plate", "HON7777"); page.press("#plate", "Tab")
        wait_js(page, "document.getElementById('form-lookup').innerText.includes('Registration data')")
        check("model differs: called out as a difference", "differs" in page.inner_text("#form-lookup"), page.inner_text("#form-lookup"))
        page.fill("#color", "grey"); page.select_option("#bodyStyle", "sedan"); page.fill("#distinguishing", "scratch")
        page.click("[data-action=save-vehicle]")
        page.wait_for_selector("[data-action=start-plate]")
        accord = [v for v in last_written("data/vehicles/") if v.get("model") == "Accord"]
        check("make agrees, model differs: saved without a lookup field", len(accord) == 1 and "plateLookup" not in accord[0], str(accord))
        del calls[calls.index("CA-HON7777")]  # keep the later call-count checks about the other flows

        # a plate that IS on file is not looked up
        page.click("[data-action=start-vehicle]"); page.wait_for_selector("#color")
        page.fill("#plate", "TST1001"); page.press("#plate", "Tab")
        wait_js(page, "document.getElementById('form-lookup').innerText.includes('already on file')")
        check("plate already on file: told so, and no lookup spent", calls == ["CA-NEW1234", "CA-MIS5555"], str(calls))
        page.click("[data-action=go-home]"); page.wait_for_selector("[data-action=start-plate]")

        # ---------- 3. listed vehicle with unknown make/model: looked up automatically ----------
        search(page, "UNK0001", "CA")
        page.wait_for_selector("#form-lookup")
        wait_js(page, "document.getElementById('form-lookup').innerText.includes('Registration data')")
        check("unknown details (CA plate): looked up automatically", calls[-1] == "CA-UNK0001" and len(calls) == 3, str(calls))
        check("blank make and model are filled in", page.input_value("#make") == "Toyota" and page.input_value("#model") == "Camry")
        check("the form says it filled in what was blank", "Filled in what was blank" in page.inner_text("#form-lookup"))
        page.click("[data-action=update-vehicle]")
        page.wait_for_selector("[data-action=start-plate]")
        wait_js(page, "true")
        updated = writes.get("data/vehicles/VEH_aaaa0001.json", {})
        check("update stores make, model and the lookup answer", updated.get("make") == "Toyota" and updated.get("model") == "Camry"
              and updated.get("plateLookup", {}).get("year") == 2018 and updated["plateLookup"]["plate"] == "CA-UNK0001", str(updated))

        # ---------- 4. known vehicle: listed and complete, so no automatic lookup; manual check on request ----------
        search(page, "TST1001", "CA")
        page.wait_for_selector("#form-lookup")
        page.wait_for_selector("[data-action=check-lookup]")
        check("listed vehicle with known details: no automatic lookup", len(calls) == 3, str(calls))
        page.click("[data-action=check-lookup]")
        wait_js(page, "document.getElementById('form-lookup').innerText.includes('Registration data')")
        check("manual check runs the lookup", calls[-1] == "CA-TST1001" and len(calls) == 4, str(calls))
        check("it reports a match", "2019 Honda Civic LX" in page.inner_text("#form-lookup") and "Matches" in page.inner_text("#form-lookup"), page.inner_text("#form-lookup"))
        page.click("[data-action=update-vehicle]")
        page.wait_for_selector("[data-action=start-plate]")
        known = writes.get("data/vehicles/VEH_bbbb0002.json", {})
        check("matching check is stored on the vehicle", known.get("plateLookup", {}).get("model") == "Civic LX" and known["plateLookup"]["plate"] == "CA-TST1001", str(known))

        # ---------- 5. states and searches that must not look anything up ----------
        before = len(calls)
        search(page, "ZZZ9999", "NV")
        check("not listed but not California: no lookup", page.locator("#lookup-box").count() == 0 and len(calls) == before, str(calls))
        page.click("[data-action=go-home]"); page.wait_for_selector("[data-action=start-plate]")
        search(page, "ZZZ9999", "ANY")
        check("any-state search: no lookup (the state is unknown)", page.locator("#lookup-box").count() == 0 and len(calls) == before, str(calls))
        page.click("[data-action=go-home]"); page.wait_for_selector("[data-action=start-plate]")
        search(page, "NOSUCH1", "CA")
        page.wait_for_function("document.getElementById('lookup-box') && document.getElementById('lookup-box').innerText.length > 0")
        check("not found by the provider: says so and still offers to create", "No registration data" in page.inner_text("#lookup-box")
              and page.locator("[data-action=create-with-plate]").count() == 1)

        # ---------- 6. manual sites and a hand-entered year ----------
        page.click("[data-action=go-home]"); page.wait_for_selector("[data-action=start-plate]")
        search(page, "HAND001", "CA")
        page.wait_for_selector("[data-action=create-with-plate]")
        check("no result: FaxVIN and Carfax buttons sit under the create button",
              page.locator("[data-action=create-with-plate] ~ [data-action=open-plate-site]").count() == 4)
        with page.context.expect_page() as popup:
            page.click("[data-site=faxvin]")
        check("FaxVIN button opens FaxVIN in a new tab", popup.value.url.startswith("https://www.faxvin.com/"), popup.value.url)
        popup.value.close()
        check("the page says the plate was copied", "HAND001" in page.inner_text("#site-note"), page.inner_text("#site-note"))
        with page.context.expect_page() as popup:
            page.click("[data-site=carfax]")
        check("Carfax button opens Carfax in a new tab", popup.value.url.startswith("https://www.carfax.com/"), popup.value.url)
        popup.value.close()
        with page.context.expect_page() as popup:
            page.click("[data-site=findbyplate]")
        check("FindByPlate opens the report page for this state and plate", popup.value.url.startswith("https://findbyplate.com/US/CA/HAND001/"), popup.value.url)
        popup.value.close()
        page.click("[data-action=create-with-plate]"); page.wait_for_selector("#site-checks")
        check("only FaxVIN and Carfax get a status choice", page.locator("#site-checks select").count() == 2)
        check("year is hidden until a site is Verified", not page.is_visible("#year"))
        page.select_option("#check-faxvin", "not_found")
        check("Not found does not unlock the year", not page.is_visible("#year"))
        page.select_option("#check-carfax", "verified")
        check("Verified unlocks the year", page.is_visible("#year"))
        page.fill("#color", "green"); page.fill("#make", "Subaru"); page.fill("#model", "Outback"); page.fill("#year", "20x9")
        page.select_option("#bodyStyle", "suv"); page.fill("#distinguishing", "roof box")
        page.click("[data-action=save-vehicle]")
        check("a bad year is refused", page.locator("#year").count() == 1 and not [v for v in last_written("data/vehicles/") if v.get("make") == "Subaru"], "")
        page.fill("#year", "2019")
        page.click("[data-action=save-vehicle]")
        page.wait_for_selector("[data-action=start-plate]")
        hand = [v for v in last_written("data/vehicles/") if v.get("make") == "Subaru"]
        check("year, make, model and site checks saved; no lookup answer",
              len(hand) == 1 and hand[0].get("year") == 2019 and hand[0]["model"] == "Outback" and "plateLookup" not in hand[0]
              and hand[0]["siteChecks"]["faxvin"]["status"] == "not_found" and hand[0]["siteChecks"]["carfax"]["status"] == "verified", str(hand))
        page.wait_for_selector("[data-action=start-plate]")
        search(page, "HAND001", "CA")
        page.wait_for_selector("#year")
        check("update form shows the saved year and checks", page.input_value("#year") == "2019" and page.input_value("#check-carfax") == "verified")
        page.select_option("#check-carfax", "wrong")
        page.select_option("#check-faxvin", "verified")
        page.fill("#year", "2020")
        page.click("[data-action=update-vehicle]")
        page.wait_for_selector("[data-action=start-plate]")
        again = [v for v in last_written("data/vehicles/") if v.get("make") == "Subaru"]
        check("update changes the year and the checks", len(again) == 1 and again[0].get("year") == 2020
              and again[0]["siteChecks"]["carfax"]["status"] == "wrong" and again[0]["siteChecks"]["faxvin"]["status"] == "verified", str(again))
        search(page, "HAND001", "CA")
        page.wait_for_selector("#year")
        page.select_option("#check-faxvin", "wrong"); page.select_option("#check-carfax", "")
        page.fill("#year", "2021")
        page.click("[data-action=update-vehicle]")
        check("changing the year without a Verified site is refused", page.locator("#year").count() == 1)

        check("no console or page errors", not errors, "; ".join(errors[:3]))
        browser.close()
finally:
    server.terminate()

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
