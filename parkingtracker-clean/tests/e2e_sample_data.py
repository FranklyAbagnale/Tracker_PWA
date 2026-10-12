"""Browser test: run the real app in Chromium against the generated sample data.

Seeds an in-memory fake of the GitHub contents API from data/ and photos/, then
checks what the app shows. Expected values mirror the generator's design and
"09 Testing/Phone Test with Sample Data.md".

    python3 scripts/generate_sample_data.py     # first, so timestamps are fresh
    pip install playwright && python3 tests/e2e_sample_data.py
"""
import json
import os
import base64, hashlib, json, re, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

import tempfile
ROOT = Path(__file__).resolve().parent.parent
# The sample set is generated fresh into a scratch folder (it is not committed), so timestamps are current.
DATA = Path(tempfile.mkdtemp(prefix="pt-sample-"))
subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_sample_data.py"), "--root", str(DATA)], check=True, capture_output=True)
PORT = 8766
CENTER = (34.1478, -118.1445)

# ---- fake GitHub seeded from the working tree ----
repo = {}
for pattern in ("data/vehicles/*.json", "data/plates/*.json", "data/index.json", "photos/*.jpg"):
    for f in DATA.glob(pattern):
        b64 = base64.b64encode(f.read_bytes()).decode()
        repo[str(f.relative_to(DATA))] = {"b64": b64, "sha": hashlib.sha1(b64.encode()).hexdigest()}

CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"}

def handle(route, request):
    m = re.match(r"https://api\.github\.com/repos/[^/]+/[^/?]+(/contents/([^?]+))?", request.url)
    def ok(body, status=200):
        route.fulfill(status=status, content_type="application/json", headers=CORS, body=json.dumps(body))
    if request.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    if not m or m.group(2) is None:
        return ok({"permissions": {"push": True}})
    path = m.group(2).replace("%2F", "/")
    if request.method == "GET":
        if path not in repo:
            return ok({"message": "Not Found"}, 404)
        if "raw" in request.headers.get("accept", ""):
            return route.fulfill(status=200, headers=CORS, body=base64.b64decode(repo[path]["b64"]))
        return ok({"content": repo[path]["b64"], "sha": repo[path]["sha"]})
    ok({"content": {"sha": "x"}})  # writes are not under test here

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

EXPECTED_LOCAL = [  # by flag (confirmed, suspected, cleared+pigs mixed, unknown), nearest first within each
    "Red Honda Civic", "Silver Toyota Camry",
    "Silver Honda Accord", "White Ford F-150", "Tan Toyota Tacoma", "Blue Subaru Outback", "Black Tesla Model 3",
    "Yellow Mini Cooper", "Black Dodge Charger", "White Chevrolet Express", "White Chevrolet Tahoe",
    "Green Jeep Wrangler", "Teal Hyundai Elantra <i>GT</i>", "Brown Ford Transit", "Grey Nissan Pathfinder",
]
EXPECTED_FLAGS = ["confirmed"] * 2 + ["suspected"] * 5 + ["cleared", "pigs", "cleared", "pigs"] + ["unknown"] * 4
MUST_NOT_APPEAR = ["Orange Dodge Challenger", "Purple Kia Soul", "Black BMW 3 Series"]

server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT / "web"), "--bind", "127.0.0.1"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(permissions=["geolocation"], geolocation={"latitude": CENTER[0], "longitude": CENTER[1]},
                                  viewport={"width": 390, "height": 844})
        ctx.add_init_script("localStorage.setItem('pt-classic-home','1');")  # classic home for this section
        ctx.route("https://api.github.com/**", handle)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        base = f"http://localhost:{PORT}/index.html"

        page.goto(base)
        page.fill("#observer-input", "Test Person")
        page.fill("#token-input", "github_pat_test")
        page.click("[data-action=save-token]")
        page.wait_for_selector("[data-action=start-local]")

        # ---- Local search from the centre point ----
        page.click("[data-action=start-local]")
        page.click("[data-action=use-location]")
        page.wait_for_selector(".result-card")
        check("Local first shows 10 vehicles and offers the rest", page.locator(".result-card").count() == 10
              and page.locator("[data-action=view-more-local]").inner_text().strip() == "View 5 more")
        page.click("[data-action=view-more-local]")
        names = page.locator(".result-card strong").all_inner_texts()
        check("View more lists all 15 vehicles in range", len(names) == 15 and page.locator("[data-action=view-more-local]").count() == 0, f"{len(names)}: {names}")
        check("Local ranking order matches the design", names == EXPECTED_LOCAL, f"\n got      {names}\n expected {EXPECTED_LOCAL}")
        body = page.inner_text("#local-results")
        for hidden in MUST_NOT_APPEAR:
            check(f"Local hides: {hidden}", hidden not in body)
        flags = page.locator(".result-card").evaluate_all("els => els.map(e => e.className.match(/flag-(\\w+)/)[1])")
        check("flags appear in order (confirmed, suspected, cleared+pigs mixed, unknown)", flags == EXPECTED_FLAGS, str(flags))
        first = page.locator(".result-card").first.inner_text()
        check("closest card shows 120 m and recency", "120 m" in first and re.search(r"\dh ago", first) is not None, first)

        # ---- the out-of-radius vehicle appears when searching from 2.5 km north ----
        north = CENTER[0] + 2500 / 111_320
        page.fill("#lat", f"{north:.5f}"); page.fill("#lng", str(CENTER[1]))
        page.click("[data-action=search-local]")
        wait_js(page, "document.getElementById('local-results').innerText.includes('Purple Kia Soul')")
        check("moving the search point reveals the out-of-radius vehicle", True)

        # ---- 'moved' vehicle is placed by its NEWEST location ----
        page.fill("#lat", str(CENTER[0])); page.fill("#lng", str(CENTER[1]))
        page.click("[data-action=search-local]")
        wait_js(page, "document.getElementById('local-results').innerText.includes('Tan Toyota Tacoma')")
        check("moved vehicle is listed at its newest (nearby) location", True)

        # ---- Refresh uses the network and says so ----
        page.click("[data-action=refresh-local]")
        wait_js(page, "document.getElementById('local-status').innerText.includes('refreshed')")
        check("Refresh index reports a fresh fetch", True)

        # ---- tap a result: history, features, photos ----
        page.fill("#lat", str(CENTER[0])); page.fill("#lng", str(CENTER[1]))
        page.click("[data-action=search-local]")
        page.wait_for_selector(".result-card")
        page.locator(".result-card", has_text="Red Honda Civic").click()
        page.wait_for_selector("#flag")
        text = page.inner_text(".screen")
        check("detail shows features", "cracked taillight" in text and "bumper sticker" in text)
        check("detail shows sighting history, newest first",
              text.index("Still here, same spot.") < text.index("First noticed overnight."))
        wait_js(page, "document.querySelectorAll('#vehicle-photos img').length >= 1")
        loaded = page.evaluate("[...document.querySelectorAll('#vehicle-photos img')].every(i => i.complete && i.naturalWidth > 0)")
        check("sighting photos load and render", loaded)
        page.click("[data-action=go-home]")

        # ---- Plate search ----
        def plate(q, state="CA"):
            page.click("[data-action=start-plate]")
            page.select_option("#state-input", state)
            page.fill("#plate-input", q)
            page.click("[data-action=search-plate]")
            page.wait_for_selector("#flag, #plate-results .plate-hit, [data-action=create-with-plate]")
            return page.inner_text(".screen")

        t = plate("tst-1001")
        check("exact plate (lower case, hyphen) opens the vehicle", "Update: Red Honda Civic" in t)
        page.click("[data-action=go-home]")

        t = plate("DLRTST1", "NV")
        check("dealer-plate alias finds the multi-plate vehicle", "Update: Silver Honda Accord" in t and "CA TST8001, NV DLRTST1" in t, t[:200])
        page.click("[data-action=go-home]")

        t = plate("TST1002", "ANY")  # recorded with an unknown state (XX)
        check("Any state finds a plate recorded under an unknown state", "Update: White Ford F-150" in t, t[:200])
        page.click("[data-action=go-home]")

        t = plate("TST1002", "CA")
        check("wrong state: not an exact match, but the same plate is offered", "No vehicle found" in t and "Same plate under another state" in t and "White Ford F-150" in t, t[:300])
        page.click("[data-action=go-home]")

        t = plate("NOSUCH1", "ANY")
        check("Any state: nothing found says so", "No vehicle found for NOSUCH1 in any state" in t, t[:200])
        page.click("[data-action=go-home]")

        t = plate("DLRTST1", "ANY")
        check("Any state also finds a plate with a known state", "Update: Silver Honda Accord" in t, t[:200])
        page.click("[data-action=go-home]")

        t = plate("TST10", "ANY")
        check("partial plate (5 characters) lists every match", "3 plates matching TST10" in t and all(x in t for x in ("Red Honda Civic", "White Ford F-150", "Black Tesla Model 3")), t[:300])
        page.locator("#plate-results .plate-hit", has_text="Black Tesla").click()
        page.wait_for_selector("#flag")
        check("a listed match can be opened", "Black Tesla" in page.inner_text("h2"))
        page.click("[data-action=go-home]")
        t = plate("TST10", "ANY")
        plates_listed = [x.split()[-1] for x in page.locator("#plate-results .plate-hit .plate-text").all_inner_texts()]
        dots = page.locator("#plate-results .plate-hit .dot").evaluate_all("els => els.map(e => e.className.match(/dot-(\\w+)/)[1])")
        subs = page.locator("#plate-results .plate-hit .vrow-sub").all_inner_texts()
        check("each plate is listed once, with its flag circle", len(plates_listed) == len(set(plates_listed)) == 3 and sorted(dots) == ["confirmed", "suspected", "suspected"], str((plates_listed, dots)))
        check("the vehicle description is below the plate", sorted(subs) == ["Black Tesla Model 3", "Red Honda Civic", "White Ford F-150"], str(subs))
        check("no Exact/Partial text labels any more", "partial" not in t.lower() and "exact" not in t.lower(), t[:200])
        check("partial matches are in alphanumeric order", plates_listed == sorted(plates_listed), str(plates_listed))
        check("the matched characters are highlighted", page.locator("#plate-results .plate-hit .hit").first.inner_text() == "TST10")
        if os.environ.get("SHOT"): page.screenshot(path=os.environ["SHOT"] + "-plate-results.png")
        page.click("[data-action=go-home]")

        t = plate("TST", "ANY")
        chips = [c.strip() for c in page.locator(".chips .chip").all_inner_texts()]
        check("several states match: chips offer All plus each state with counts", any(c.startswith("All") for c in chips) and any(c.startswith("CA") for c in chips) and any(c.startswith("NV") for c in chips) and any(c.startswith("State unknown") for c in chips), str(chips))
        n_all = page.locator("#plate-results .plate-hit").count()
        page.click(".chips .chip[data-state=NV]")
        t = page.inner_text("#plate-results")
        check("tapping a state narrows the list (NV: the dealer-plate vehicle)", "Silver Honda Accord" in t and page.locator("#plate-results .plate-hit").count() == 1 and "in NV" in t, t[:200])
        page.click(".chips .chip[data-state=XX]")
        t = page.inner_text("#plate-results")
        check("State unknown narrows to the unknown-state plate", "White Ford F-150" in t and page.locator("#plate-results .plate-hit").count() == 1, t[:200])
        page.click(".chips .chip[data-state='']")
        check("All restores the full list", page.locator("#plate-results .plate-hit").count() == n_all and n_all > 3)
        page.click("[data-action=go-home]")

        t = plate("ST100", "CA")
        check("a state-specific search shows no state chips", page.locator(".chips").count() == 0)
        page.click("[data-action=go-home]")

        t = plate("1001", "ANY")
        check("a partial that matches one plate is listed (circle + plate), not opened", "Update:" not in t and page.locator("#plate-results .plate-hit").count() == 1 and page.locator("#plate-results .plate-hit[data-match=partial] .dot-confirmed").count() == 1 and "Red Honda Civic" in t, t[:200])
        page.locator("#plate-results .plate-hit").click()
        page.wait_for_selector("#flag")
        check("tapping that row opens the vehicle", "Red Honda Civic" in page.inner_text("h2"))
        page.click("[data-action=go-home]")

        t = plate("TST1001", "ANY")
        check("an exact plate shows its record (no list)", "Update: Red Honda Civic" in t, t[:200])
        page.click("[data-action=go-home]")

        t = plate("ST100", "CA")
        check("partial search respects the chosen state (TST1002 is XX)", "2 plates matching ST100 in CA" in t and "White Ford F-150" not in t, t[:300])
        page.click("[data-action=go-home]")

        t = plate("TS", "ANY")
        check("two characters explain the 3-character minimum", "No vehicle found" in t and "3 or more characters" in t, t[:300])
        page.click("[data-action=go-home]")

        t = plate("TST7001")
        check("vehicle saved without location is found by plate", "Update: Black BMW 3 Series" in t and "no location" in t)
        page.click("[data-action=go-home]")

        t = plate("TST1O01")  # letter O instead of zero
        check("near-miss plate suggests the similar vehicle", "No vehicle found" in t and "Red Honda Civic" in t, t[:300])
        check("near-miss offers to create a new vehicle", page.locator("[data-action=create-with-plate]").count() == 1)
        page.locator("#plate-results .plate-hit", has_text="Red Honda Civic").click()
        page.wait_for_selector("#flag")
        check("tapping a suggestion opens it", "Update: Red Honda Civic" in page.inner_text("h2"))
        page.click("[data-action=go-home]")

        t = plate("ZZZ9999")
        check("unknown plate says not found and offers create", "No vehicle found" in t and "Create new vehicle" in t)
        page.click("[data-action=go-home]")

        # ---- a plate that belongs to another vehicle cannot be attached ----
        t = plate("TST4001")
        page.fill("#plate", "TST1001")
        page.click("[data-action=update-vehicle]")
        wait_js(page, "document.getElementById('notice') && !document.getElementById('notice').hidden")
        note = page.inner_text("#notice")
        check("adding another vehicle's plate is refused", "already belongs to another vehicle" in note, note)
        check("refused update stays on the form (nothing saved)", page.locator("#flag").count() == 1)
        page.click("[data-action=go-home]")

        # ---- HTML in record text is shown literally ----
        t = plate("TST9002")
        check("HTML in a vehicle name renders as text", "Elantra <i>GT</i>" in page.inner_text("h2"))
        check("no element was injected from record text", page.locator(".screen i").count() == 0 and page.locator(".screen script").count() == 0)
        check("HTML in notes renders as text", "<script>alert(1)</script> & ampersand" in page.inner_text(".history"))
        page.click("[data-action=go-home]")

        # ================= new home screen (view B) =================
        ctx_b = browser.new_context(permissions=["geolocation"], geolocation={"latitude": CENTER[0], "longitude": CENTER[1]},
                                    viewport={"width": 390, "height": 844})
        ctx_b.route("https://api.github.com/**", handle)
        ctx_b.add_init_script("""window.__geo = {watch: 0, get: 0};
          const w = navigator.geolocation.watchPosition.bind(navigator.geolocation), g = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation);
          navigator.geolocation.watchPosition = (...a) => { window.__geo.watch++; return w(...a); };
          navigator.geolocation.getCurrentPosition = (...a) => { window.__geo.get++; return g(...a); };""")
        pb = ctx_b.new_page()
        errors_b = []
        pb.on("console", lambda m: errors_b.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        pb.on("pageerror", lambda e: errors_b.append(str(e)))
        pb.on("dialog", lambda d: d.accept())
        pb.goto(base)
        pb.wait_for_selector("#observer-input")
        check("camera bar is hidden on the sign-in screen", pb.locator("#camera-bar").is_hidden())
        pb.fill("#observer-input", "Test Person"); pb.fill("#token-input", "github_pat_test")
        pb.click("[data-action=save-token]")
        pb.wait_for_selector(".home-b-grid")
        check("new home is the default", pb.locator(".home-b-grid").count() == 1 and pb.locator(".main-grid").count() == 0)

        vh = pb.evaluate("window.innerHeight")
        box = pb.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
            return { plate: r('.hb-plate'), list: r('.hb-list'), bar: r('#camera-bar'), input: r('#plate-input'), btn: r('.camera-bar-btn') }; })()""")
        check("plate entry is on the home page", pb.locator(".hb-plate #plate-input").count() == 1 and pb.locator(".hb-plate #state-input").count() == 1)
        check("plate entry is large and at the top", box["input"]["height"] >= 60 and box["plate"]["top"] < box["list"]["top"],
              str(box["input"]))
        check("camera bar is pinned to the bottom edge, below the list",
              abs(box["bar"]["bottom"] - vh) <= 1 and box["list"]["bottom"] <= box["bar"]["top"] + 1 and box["btn"]["height"] >= 60, str(box))
        check("nearby list fills the middle", box["list"]["height"] > 150, str(box["list"]))
        cam = pb.locator("#camera-input")
        check("camera button opens the phone's camera app (capture=environment)", cam.get_attribute("capture") == "environment" and cam.get_attribute("accept") == "image/*")

        pb.wait_for_selector(".vrow")
        wait_js(pb, "document.querySelectorAll('.vrow').length === 10")
        check("nearby list starts with 10 and offers 5 more", pb.locator("#home-list [data-action=view-more-home]").inner_text().strip() == "View 5 more")
        pb.click("[data-action=view-more-home]")
        rows = pb.locator(".vrow strong").all_inner_texts()
        dots = pb.locator(".vrow .dot").evaluate_all("els => els.map(e => e.className.match(/dot-(\\w+)/)[1])")
        check("nearby list: all 15, ordered by flag then distance", rows == EXPECTED_LOCAL and dots == EXPECTED_FLAGS, f"{rows} {dots}")
        colours = pb.evaluate("""Object.fromEntries(['confirmed', 'suspected', 'cleared', 'unknown', 'pigs'].map((f) =>
            [f, getComputedStyle(document.querySelector('.dot-' + f)).backgroundColor]))""")
        check("circles: red confirmed, green cleared, yellow unknown, blue pigs (orange suspected)", colours == {
            "confirmed": "rgb(220, 38, 38)", "suspected": "rgb(249, 115, 22)", "cleared": "rgb(22, 163, 74)",
            "unknown": "rgb(234, 179, 8)", "pigs": "rgb(37, 99, 235)"}, str(colours))
        first = pb.locator(".vrow").first.inner_text()
        check("rows show distance and recency", "120 m" in first and re.search(r"\dh ago", first) is not None, first)

        # the list follows the device: move 2.5 km north and the far vehicle becomes the nearest
        wait_js(pb, "!document.getElementById('home-list').innerText.includes('Purple Kia Soul')")
        ctx_b.set_geolocation({"latitude": CENTER[0] + 2500 / 111_320, "longitude": CENTER[1]})
        wait_js(pb, "document.getElementById('home-list').innerText.includes('Purple Kia Soul')")
        check("moving the device re-ranks the nearby list", pb.locator(".vrow strong").first.inner_text() == "Purple Kia Soul")
        ctx_b.set_geolocation({"latitude": CENTER[0], "longitude": CENTER[1]})
        wait_js(pb, "document.querySelector('.vrow strong').innerText === 'Red Honda Civic'")

        # location switch: grey = the device is never read or asked; the list uses the last position used
        pin = lambda: pb.evaluate("getComputedStyle(document.querySelector('.loc-btn')).color")
        check("pin is green while on", pin() == "rgb(22, 163, 74)")
        wait_js(pb, "localStorage.getItem('pt-last-pos')")
        check("the position in use is remembered on this device", abs(json.loads(pb.evaluate("localStorage.getItem('pt-last-pos')"))["lat"] - CENTER[0]) < 0.001)
        pb.click(".loc-btn")
        wait_js(pb, "document.querySelector('.hb-list-head') && document.querySelector('.hb-list-head').innerText.includes('last position')")
        check("turning it off: pin grey, list stays, ranked from the last position", pin() == "rgb(156, 163, 175)" and pb.locator(".vrow").count() > 0 and pb.locator(".vrow strong").first.inner_text() == "Red Honda Civic")
        if os.environ.get("SHOT"): pb.screenshot(path=os.environ["SHOT"] + "-loc-off.png")
        ctx_b.set_geolocation({"latitude": CENTER[0] + 2500 / 111_320, "longitude": CENTER[1]})
        pb.wait_for_timeout(1500)
        check("while off, moving the device does not change the list", pb.locator(".vrow strong").first.inner_text() == "Red Honda Civic")
        pb.reload(); pb.wait_for_selector(".home-b-grid")
        wait_js(pb, "document.querySelectorAll('.vrow').length > 0")
        geo = pb.evaluate("window.__geo")
        check("after a reload with it off, the device position is never read or watched", geo == {"watch": 0, "get": 0} and pin() == "rgb(156, 163, 175)", str(geo))
        pb.evaluate("localStorage.removeItem('pt-last-pos')")
        pb.reload(); pb.wait_for_selector(".home-b-grid")
        wait_js(pb, "document.querySelectorAll('.vrow').length > 0")
        check("no position at all: the list opens on Recent (newest first), nothing is asked", pb.locator(".tab.on").inner_text() == "Recent" and pb.evaluate("window.__geo.get + window.__geo.watch") == 0)
        stamps = pb.locator(".vrow .vrow-meta").all_inner_texts()
        pb.click(".tab[data-tab=nearby]")
        wait_js(pb, "document.getElementById('home-list').innerText.includes('no earlier position')")
        check("Nearby tab explains there is no saved position", pb.locator(".vrow").count() == 0)
        pb.fill("#plate-input", "TST100")
        pb.wait_for_selector("#plate-results .plate-hit")
        check("plate search still works with location off", pb.locator("#plate-results .plate-hit").count() == 3)
        pb.click("[data-action=clear-plate-search]")
        pb.click(".loc-btn")
        wait_js(pb, "document.querySelectorAll('.vrow').length > 0 && document.querySelector('.vrow strong').innerText === 'Purple Kia Soul'")
        check("turning it on: pin green and nearby vehicles update by themselves from the device", pin() == "rgb(22, 163, 74)" and pb.evaluate("window.__geo.watch") >= 1)
        if os.environ.get("SHOT"): pb.screenshot(path=os.environ["SHOT"] + "-loc-on.png")
        ctx_b.set_geolocation({"latitude": CENTER[0], "longitude": CENTER[1]})
        wait_js(pb, "document.querySelector('.vrow strong').innerText === 'Red Honda Civic'")

        # Recent tab: newest first, no location needed
        pb.click(".tab[data-tab=recent]")
        wait_js(pb, "document.querySelector('.tab.on').innerText === 'Recent'")
        times = pb.evaluate("""[...document.querySelectorAll('.vrow .vrow-meta')].map(e => e.innerText)""")
        def minutes(t):
            n = int(re.match(r"(\d+)", t).group(1)) if re.match(r"\d+", t) else 0
            return n * (1 if "m ago" in t else 60 if "h ago" in t else 1440 if "d ago" in t else 0)
        mins = [minutes(t) for t in times]
        if os.environ.get("SHOT"): pb.screenshot(path=os.environ["SHOT"] + "-recent.png")
        check("Recent lists the newest sightings first", len(times) == 10 and mins == sorted(mins), str(times))
        check("Recent has a View more and a Refresh button", pb.locator("[data-action=view-more-home]").count() == 1 and pb.locator("[data-action=refresh-home]").count() == 1)
        pb.click(".tab[data-tab=nearby]")
        wait_js(pb, "document.querySelector('.tab.on').innerText.startsWith('Nearby (')")
        check("tabs switch back to Nearby", pb.locator(".vrow strong").first.inner_text() == "Red Honda Civic")

        # tapping a row opens the vehicle
        pb.locator(".vrow", has_text="Red Honda Civic").click()
        pb.wait_for_selector("#flag")
        check("tapping a nearby vehicle opens it", "Update: Red Honda Civic" in pb.inner_text("h2"))
        pb.click("[data-action=go-home]"); pb.wait_for_selector(".home-b-grid")

        # plate search happens on the home page
        pb.fill("#plate-input", "tst-1001"); pb.press("#plate-input", "Enter")
        pb.wait_for_selector("#flag")
        check("Enter in the plate box searches; an exact plate opens the vehicle", "Update: Red Honda Civic" in pb.inner_text("h2"))
        pb.click("[data-action=go-home]"); pb.wait_for_selector(".home-b-grid")

        pb.fill("#plate-input", "TST")
        pb.click("[data-action=search-plate]")
        pb.wait_for_selector("#plate-results .plate-hit")
        check("partial search lists matches in place, nearby list hidden", pb.locator("#home-list").is_hidden() and pb.locator("#plate-results .plate-hit").count() == 10
              and pb.locator("[data-action=view-more-plate]").count() == 1)
        pb.click("[data-action=view-more-plate]")
        check("plate matches: View more adds the rest", pb.locator("#plate-results .plate-hit").count() > 10)
        # plates appear while typing (no Search press)
        pb.click("[data-action=clear-plate-search]")
        pb.wait_for_selector(".vrow:not(.plate-hit)")
        pb.click("#plate-input"); pb.keyboard.type("T")
        check("1 character: still the Nearby list", pb.locator("#home-list").is_visible() and pb.locator("#plate-results .plate-hit").count() == 0)
        pb.keyboard.type("S")
        pb.wait_for_selector("#plate-results .plate-hit")
        check("2 characters: matching plates appear between the box and the photo bar, Nearby list hidden", pb.locator("#home-list").is_hidden() and pb.locator("#plate-results .plate-hit").count() > 0)
        n2 = pb.locator("#plate-results .plate-hit").count()
        pb.keyboard.type("T100"); pb.wait_for_selector("#plate-results .plate-hit .hit")
        shown = pb.locator("#plate-results .plate-hit .plate-text").all_inner_texts()
        check("list narrows as more is typed, highlight follows", pb.locator("#plate-results .plate-hit").count() < n2 or n2 <= 3, f"{n2} -> {len(shown)}")
        if os.environ.get("SHOT"): pb.screenshot(path=os.environ["SHOT"] + "-live.png")
        check("typed text is highlighted in every row", all(x == "TST100" for x in pb.locator("#plate-results .plate-hit .hit").all_inner_texts()) and len(shown) > 0, str(shown))
        pb.keyboard.type("ZZZ")
        pb.wait_for_selector("#plate-results:not([hidden]) >> text=No plate on file contains")
        check("no match says so and points at Search", "Press Search" in pb.inner_text("#plate-results"))
        for _ in range(8): pb.keyboard.press("Backspace")
        wait_js(pb, "!document.getElementById('home-list').hidden && document.getElementById('plate-results').hidden")
        check("backspacing to 1 character returns to the Nearby list", pb.input_value("#plate-input") == "T" and pb.locator("#home-list").is_visible())
        pb.fill("#plate-input", "")
        pb.fill("#plate-input", "TST")
        pb.click("[data-action=search-plate]")
        pb.wait_for_selector("#plate-results .plate-hit")
        pb.click("[data-action=clear-plate-search]")
        wait_js(pb, "document.querySelectorAll('.vrow').length > 0 && !document.getElementById('home-list').hidden")
        check("Clear returns to the nearby list and empties the box", pb.input_value("#plate-input") == "" and pb.locator("#plate-results").is_hidden())

        # photo from the phone's camera app carries the typed plate into the vehicle form
        photo = DATA / "snap.jpg"
        from PIL import Image
        Image.new("RGB", (800, 600), (120, 120, 160)).save(photo, "JPEG")
        pb.select_option("#state-input", "NV"); pb.fill("#plate-input", "pic123")
        pb.set_input_files("#camera-input", str(photo))
        pb.wait_for_selector("#color")
        check("photo from the camera app opens the vehicle form with the photo attached", "1 photo ready" in pb.inner_text(".screen"))
        check("typed plate and state carry over", pb.input_value("#plate") == "PIC123" and pb.input_value("#plateState") == "NV")
        check("pigs is offered as a flag", "pigs" in pb.locator("#flag option").evaluate_all("els => els.map(e => e.value)"))
        check("camera bar stays on the vehicle form", pb.locator("#camera-bar").is_visible())
        # mid-form: type, take another photo, nothing typed is lost and the count goes up
        pb.fill("#color", "teal"); pb.fill("#make", "Mini"); pb.fill("#notes", "paused for a photo")
        pb.set_input_files("#camera-input", str(photo))
        wait_js(pb, "document.querySelector('.screen').innerText.includes('2 photos ready')")
        check("photo taken mid-form is added and the form is kept as it was",
              pb.input_value("#color") == "teal" and pb.input_value("#make") == "Mini" and pb.input_value("#notes") == "paused for a photo"
              and pb.input_value("#plate") == "PIC123" and pb.input_value("#plateState") == "NV")
        # government plates: USG / GOV take a code, kept as part of the state
        check("the code box is hidden for an ordinary state", pb.locator("#plateStateCode").is_hidden())
        pb.select_option("#plateState", "GOV")
        check("choosing GOV shows the code box", pb.locator("#plateStateCode").is_visible())
        pb.fill("#plateStateCode", "dhs")
        pb.set_input_files("#camera-input", str(photo))
        wait_js(pb, "document.querySelector('.screen').innerText.includes('3 photos ready')")
        check("a GOV plate with a code survives the form being redrawn", pb.input_value("#plateState") == "GOV" and pb.input_value("#plateStateCode") == "DHS" and pb.locator("#plateStateCode").is_visible())
        pb.select_option("#plateState", "SON")
        check("a Mexican state is offered by name, and the code box hides again", "Sonora" in pb.locator("#plateState option[value=SON]").inner_text() and pb.locator("#plateStateCode").is_hidden())
        pb.select_option("#plateState", "NV")
        check("last form field is not hidden behind the camera bar", pb.evaluate("""(() => { const b = document.querySelector('#camera-bar').getBoundingClientRect();
            const l = document.querySelector('[data-action=go-home]').getBoundingClientRect(); window.scrollTo(0, document.body.scrollHeight);
            const l2 = document.querySelector('[data-action=go-home]').getBoundingClientRect(); return l2.bottom <= b.top + 1; })()"""))
        pb.click("[data-action=go-home]"); pb.wait_for_selector(".home-b-grid")

        # menu: no classic-home switch or manual-location entry any more; tutorial and glossary pages instead
        pb.click("[data-action=toggle-menu]")
        check("menu offers add vehicle, tutorial, glossary, sync and log out", all(pb.locator(f"#menu [data-action={a}]").count() == 1 for a in ("start-vehicle", "open-tutorial", "open-glossary", "sync-now", "logout")))
        check("menu no longer offers the classic home or Nearby (manual location)", pb.locator("#menu [data-action=toggle-home-view]").count() == 0 and pb.locator("#menu [data-action=start-local]").count() == 0)
        check("menu text lists Tutorial and Glossary", "Tutorial" in pb.inner_text("#menu") and "Glossary" in pb.inner_text("#menu") and "classic" not in pb.inner_text("#menu").lower())
        with pb.context.expect_page() as new_page:
            pb.click("#menu [data-action=open-glossary]")
        gl = new_page.value; gl.wait_for_load_state()
        gl.wait_for_selector("#state-tables table")
        check("glossary opens in its own tab and lists the states", gl.url.endswith("glossary.html") and "Sonora" in gl.inner_text("#state-tables") and "District of Columbia" in gl.inner_text("#state-tables") and "GOV" in gl.inner_text("#state-tables"))
        check("glossary has every state code", gl.locator("#state-tables tbody tr").count() == pb.evaluate("import('./js/config.js').then((c) => c.STATES.length)"), str(gl.locator("#state-tables tbody tr").count()))
        gl.fill("#filter", "sonora")
        check("glossary filter narrows to Sonora", gl.locator("#state-tables tbody tr:not([hidden])").count() == 1 and gl.locator("#flags").is_hidden())
        gl.close()
        pb.click("[data-action=toggle-menu]")
        with pb.context.expect_page() as new_page:
            pb.click("#menu [data-action=open-tutorial]")
        tu = new_page.value; tu.wait_for_load_state()
        check("tutorial opens in its own tab with a way back", tu.url.endswith("tutorial.html") and tu.locator("a[href='./']").count() >= 1 and "Tracker, step by step" in tu.inner_text("h1"))
        tu.close()
        # a phone that picked the classic home before is moved to the new one
        pb.evaluate("localStorage.setItem('pt-home-view', 'A')"); pb.reload(); pb.wait_for_selector(".home-b-grid")
        check("an old classic-home setting no longer applies", pb.locator(".home-b-grid").count() == 1 and pb.evaluate("localStorage.getItem('pt-home-view')") is None)
        check("no console or page errors on the new home", not errors_b, "; ".join(errors_b[:3]))

        check("no console or page errors", not errors, "; ".join(errors[:3]))
        browser.close()
finally:
    server.terminate()

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
