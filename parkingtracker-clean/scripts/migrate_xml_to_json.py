#!/usr/bin/env python3
"""Convert legacy plate-tracker XML exports into ParkingTracker JSON records.

Writes into the repository, where the app reads it (nothing else to configure):

  data/vehicles/VEH_xxxxxxxx.json   one file per vehicle (sightings inside)
  data/plates/<ST>-<PLATE>.json     one file per plate (state + plate, e.g. CA-7ABC123; XX = state not known)
  photos/VEH_..._..._001.jpg        photos (only when --media-root is given)
  data/index.json                   rebuilt at the end

Rules (see "07 Operations/Runbook - XML Import.md"):
  * Every record is imported. A field that is missing, unmatched or fails to
    convert becomes "unknown" (colour, make, body style, features) or empty
    (model, location); it never drops the record.
  * Every imported sighting is flagged "confirmed" (override with --flag).
  * Any data that has no field in the schema goes into the sighting's notes
    (and is listed in reports/xml-import.json): unrecognised XML elements and
    attributes, the street address, an unusable plate, media that could not be
    attached.
  * Every plate has a state. It is read from a state element (state, plate_state,
    license_state, province, ...), else from "State: CA" written in the comments,
    address or other text, else --default-state, else XX (unknown). The same
    plate in two states is two plates.
  * The street address is converted to a location by geocoding (--geocode).
  * Existing legacy media is NOT imported unless you pass --media-root.

Input: one or more files or folders (--in, repeatable; folders are searched
recursively for *.xml). Any wrapper layout works: a record is any <record>
element, or any element that has an alert_token or vehicle_license child.
Element names are case-insensitive. A file that cannot be read is reported and
the rest are still imported.

Re-running is safe: ids and keys come from the XML and existing records are
merged, never duplicated.

Usage:
  python3 scripts/migrate_xml_to_json.py --in import/ --dry-run
  python3 scripts/migrate_xml_to_json.py --in import/export.xml --default-area "Pasadena CA"
  python3 scripts/migrate_xml_to_json.py --in import/ --media-root import/   # with photos
  python3 scripts/migrate_xml_to_json.py --in import/ --dry-run --debug      # explain every decision
"""

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_index  # noqa: E402
from plate_states import STATES, STATE_NAMES, UNKNOWN_STATE, parse_state, _fold  # noqa: E402
import validate_records  # noqa: E402

TAG = "xml-import"
UNKNOWN = "unknown"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)  # stands in for "date unknown"
PHOTO_MAX_BYTES = 500 * 1024  # keep in sync with web/js/config.js
PHOTO_MAX_EDGE = 1600
MAX_PHOTOS_PER_SIGHTING = 6
PLATE_RE = re.compile(r"^[A-Z0-9]{1,20}$")  # schema/plate.schema.json (a test keeps these in sync)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic"}

COLORS = {
    "black", "white", "silver", "grey", "gray", "blue", "red", "green", "brown", "tan",
    "beige", "gold", "orange", "yellow", "purple", "maroon", "teal", "burgundy", "charcoal",
    "pink", "bronze", "cream",
}
COLOR_MODIFIERS = {"dark", "light"}
TWO_WORD_MAKES = {"land rover", "alfa romeo", "mercedes benz", "aston martin", "rolls royce"}

BODY_STYLE_BY_MODEL = {
    "explorer": "suv", "tahoe": "suv", "highlander": "suv", "suburban": "suv", "expedition": "suv",
    "pathfinder": "suv", "wrangler": "suv", "cr-v": "suv", "rav4": "suv", "escape": "suv",
    "4runner": "suv", "pilot": "suv", "durango": "suv", "equinox": "suv", "traverse": "suv",
    "ram": "truck", "f-150": "truck", "f150": "truck", "silverado": "truck", "tacoma": "truck",
    "tundra": "truck", "sierra": "truck", "ranger": "truck", "colorado": "truck",
    "civic": "sedan", "accord": "sedan", "camry": "sedan", "corolla": "sedan", "altima": "sedan",
    "sentra": "sedan", "elantra": "sedan", "malibu": "sedan", "fusion": "sedan",
    "odyssey": "van", "sienna": "van", "caravan": "van", "transit": "van",
    "mustang": "coupe", "camaro": "coupe", "challenger": "coupe",
    "golf": "hatchback", "fit": "hatchback", "soul": "hatchback",
}

TZ_OFFSETS = {  # hours from UTC; extend with --tz-offset NAME=HOURS
    "PST": -8, "PDT": -7, "MST": -7, "MDT": -6, "CST": -6, "CDT": -5, "EST": -5, "EDT": -4,
    "AKST": -9, "AKDT": -8, "HST": -10, "UTC": 0, "GMT": 0, "Z": 0,
}
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# Element names this tool understands, with the spellings other exports use.
FIELD_ALIASES = {
    "alert_token": {"alert_token", "token", "id", "record_id"},
    "media": {"media", "photos", "images"},
    "vehicle_license": {"vehicle_license", "license", "license_plate", "plate", "vehicle_plate"},
    "address": {"address", "street_address", "location_text"},
    "vehicle_state": {"vehicle_state", "state", "plate_state", "license_state", "lic_state", "st", "province",
                      "region", "vehicle_license_state", "plate_st", "issuing_state", "registration_state", "reg_state"},
    "vehicle_make": {"vehicle_make", "make", "vehicle", "vehicle_description"},
    "month": {"month"}, "day": {"day"}, "year": {"year"},
    "comments": {"comments", "comment", "notes", "note", "description"},
    "datestamp": {"datestamp", "date", "timestamp", "datetime", "date_time"},
}
CANONICAL = {alias: field for field, aliases in FIELD_ALIASES.items() for alias in aliases}


class ImportErrorXml(Exception):
    pass


# ---------- reading ----------

def read_xml_text(data: bytes, info=None) -> str:
    """Decode by BOM or content, not by the XML declaration (which often lies:
    one export declares utf-16 but is plain ASCII). DTDs and entities are
    refused outright: the file is untrusted and ElementTree would expand them."""
    used = "utf-8"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text, used = data.decode("utf-16"), "utf-16 (byte order mark)"
    elif data.startswith(b"\xef\xbb\xbf"):
        text, used = data[3:].decode("utf-8"), "utf-8 (byte order mark)"
    elif b"\x00" in data[:200]:
        text, used = data.decode("utf-16-le" if data[1:2] == b"\x00" else "utf-16-be"), "utf-16 (no byte order mark)"
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text, used = data.decode("latin-1"), "latin-1 (not valid UTF-8)"
            print("warning: not valid UTF-8; decoded as latin-1", file=sys.stderr)
    if info is not None:
        declared = re.match(r"^\s*<\?xml[^>]*?encoding=[\"']([^\"']+)", text)
        info.update({"bytes": len(data), "encoding_used": used, "encoding_declared": declared.group(1) if declared else None,
                     "lines": text.count("\n") + 1})
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise ImportErrorXml("refusing XML with a DOCTYPE or ENTITY declaration")
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def element_text(el):
    """Text of an element including nested elements, whitespace collapsed."""
    return re.sub(r"\s+", " ", " ".join(t.strip() for t in el.itertext() if t.strip())).strip()


def is_record(el):
    if local_name(el.tag) == "record":
        return True
    return bool({local_name(c.tag) for c in el} & {"alert_token", "vehicle_license"})


_NAME = r"[A-Za-z_][A-Za-z0-9_.\-]*(?::[A-Za-z_][A-Za-z0-9_.\-]*)?"
_ATTR = _NAME + r"\s*=\s*(?:\"[^\"<]*\"|'[^'<]*')"
# Every kind of markup, strictly. Anything else that starts with '<' is text.
_TOKEN = re.compile(
    r"<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<\?[\s\S]*?\?>"
    r"|</(" + _NAME + r")\s*>"
    r"|<(" + _NAME + r")((?:\s+" + _ATTR + r")*)\s*(/?)>"
    r"|<")
_STRAY_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9A-Fa-f]+);)")
_BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def repair_xml(text: str, details=None):
    """Fix the usual damage in exported XML. Returns (text, number_of_fixes).

    Text with a literal '<' or '&' in it is the common case ("<State: CA>", "a < b", "AT&T"),
    and so is HTML-style markup typed into a comment (<b class=x>, <br>). The file is walked
    tag by tag: a tag that is not strictly valid XML, a closing tag with no opening tag, or an
    opening tag that is never closed is turned into plain text; bare '&' becomes '&amp;';
    control characters are dropped. Only used after a strict parse has failed.
    `details`, when given, receives one entry per fix: where it was and what it looked like."""
    count = 0
    newlines = [m.start() for m in re.finditer("\n", text)]
    out, stack, pos = [], [], 0

    def note(kind, at):
        if details is not None and len(details) < 200:
            line = bisect_right(newlines, at) + 1
            col = at - (newlines[line - 2] if line > 1 else -1)
            details.append({"line": line, "column": col, "kind": kind,
                            "context": text[max(0, at - 30):at + 50].replace("\n", " ")})

    def amps(chunk, at):
        nonlocal count

        def fix(m):
            nonlocal count
            count += 1
            note("stray &", at + m.start())
            return "&amp;"

        return _STRAY_AMP.sub(fix, chunk)

    def as_text(token, at, kind):
        nonlocal count
        count += 1
        note(kind, at)
        return "&lt;" + amps(token[1:], at + 1)

    for m in _TOKEN.finditer(text):
        out.append(amps(text[pos:m.start()], pos))
        pos, tok = m.end(), m.group(0)
        if tok.startswith(("<!--", "<![CDATA[", "<?")):
            out.append(tok)
        elif m.group(1):  # closing tag
            name = m.group(1)
            if stack and stack[-1][0] == name:
                stack.pop()
                out.append(tok)
            elif any(n == name for n, _, _ in stack):
                while stack[-1][0] != name:  # tags opened but never closed: they were text
                    _, idx, at = stack.pop()
                    out[idx] = as_text(out[idx], at, f"unclosed <{_}>")
                stack.pop()
                out.append(tok)
            else:
                out.append(as_text(tok, m.start(), f"closing </{name}> with no opening tag"))
        elif m.group(2):  # opening tag
            out.append(amps(tok, m.start()))
            if not m.group(4):
                stack.append((m.group(2), len(out) - 1, m.start()))
        else:
            out.append(as_text(tok, m.start(), "stray <"))
    out.append(amps(text[pos:], pos))
    text = "".join(out)
    cleaned = _BAD_CHARS.sub("", text)
    count += len(text) - len(cleaned)
    if details is not None:
        details.sort(key=lambda d: (d["line"], d["column"]))
    return cleaned, count


def describe_parse_error(exc, text):
    """'line 59232, column 151: ...the text there...' for an ElementTree ParseError."""
    line, col = getattr(exc, "position", (None, None)) or (None, None)
    if not line:
        return str(exc)
    lines = text.split("\n")
    src = lines[line - 1] if line <= len(lines) else ""
    return f"{exc} | line {line}: ...{src[max(0, col - 60):col + 60]}..."


def parse_xml(text: str, info=None):
    """Yield (group_name, fields, extras) for every record, wherever it sits in the tree.

    fields maps canonical field names to text; extras lists (name, value) for
    everything that is not a known field (elements, attributes, repeats).
    `info`, when given, is filled with what happened while reading: repairs,
    an element census, and one entry per record (line, raw child elements, snippet)."""
    repaired, details, first_error = 0, [], None
    try:
        root = ET.fromstring(text)
    except ET.ParseError as first:
        first_error = describe_parse_error(first, text)
        text, repaired = repair_xml(text, details)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ImportErrorXml(f"XML is not well formed (even after repair): {describe_parse_error(exc, text)}; first error: {first_error}") from exc
    newlines = [m.start() for m in re.finditer("\n", text)]
    cursor = 0

    def line_of(el):
        """Line of the next opening tag with this name, in document order (records are visited in order)."""
        nonlocal cursor
        name = re.escape(local_name(el.tag))
        m = re.compile(r"<(?:[A-Za-z0-9_.\-]+:)?" + name + r"(?=[\s/>])", re.IGNORECASE).search(text, cursor)
        if not m:
            return None
        cursor = m.end()
        return bisect_right(newlines, m.start()) + 1

    def read_record(el):
        fields, extras = {}, []
        for name, value in el.attrib.items():
            extras.append((local_name(name), value.strip()))
        for sub in el:
            name, value = local_name(sub.tag), element_text(sub)
            canon = CANONICAL.get(name)
            if canon and canon not in fields:
                fields[canon] = value
            else:
                extras.append((name, value))
        return fields, [(n, v) for n, v in extras if v]

    def note_record(el, group):
        if info is None:
            return
        info["records"].append({
            "line": line_of(el), "group": group, "element": local_name(el.tag),
            "children": [(local_name(sub.tag), element_text(sub)) for sub in el]
                        + [("@" + local_name(n), v.strip()) for n, v in el.attrib.items()],
            "snippet": re.sub(r"\s+", " ", ET.tostring(el, encoding="unicode"))[:600],
        })

    def walk(node, group):
        for child in node:
            if is_record(child):
                fields, extras = read_record(child)
                note_record(child, group)
                yield group, fields, extras
            else:
                yield from walk(child, local_name(child.tag))

    if info is not None:
        info.setdefault("records", [])
        info["repaired"] = repaired
        info["repairs"] = details
        info["first_error"] = first_error
        info["elements"] = dict(Counter(local_name(el.tag) for el in root.iter()))
    if is_record(root):
        fields, extras = read_record(root)
        note_record(root, local_name(root.tag))
        yield local_name(root.tag), fields, extras
    else:
        yield from walk(root, local_name(root.tag))


def find_xml_files(paths):
    files = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".xml"))
        else:
            files.append(path)
    return files


# ---------- field mapping ----------

def digest(text):
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def normalize_plate(raw):
    plate = re.sub(r"[^A-Z0-9]", "", (raw or "").upper())
    if not plate or plate in {"NOPLATE", "NONE", "UNKNOWN", "NA", "NULL"}:
        return None
    return plate


_STATE_TEXT = re.compile(r"\bstate\s*[:=]\s*([^\W\d_][\w .\-]*)", re.IGNORECASE)
_FEDERAL_TEXT = re.compile(r"(USG|GOV)(?:[ \-/]+([A-Z0-9]{1,4}))?(?![A-Z0-9])")
_STATE_NAMES_LONGEST_FIRST = sorted(STATE_NAMES, key=len, reverse=True)


def state_from_text(text):
    """Find 'State: CA' / 'state=California' in free text. Returns (code, matched_text) or None."""
    m = _STATE_TEXT.search(text or "")
    if not m:
        return None
    candidate = _fold(m.group(1)).rstrip(". ")  # "Baja California Sur." still names the state
    for name in _STATE_NAMES_LONGEST_FIRST:
        if candidate == name or candidate.startswith(name + " "):
            return STATE_NAMES[name], m.group(0).strip()
    fed = _FEDERAL_TEXT.match(candidate)
    if fed:  # USG / GOV, with a short code after it (the free-text form is stricter than a state column)
        return (f"{fed.group(1)}-{fed.group(2)}" if fed.group(2) else fed.group(1)), m.group(0).strip()
    word = re.match(r"[A-Z]{2,6}", candidate)
    raw = word.group(0) if word else candidate.split(" ")[0]
    return parse_state(raw)[0], m.group(0).strip()


def resolve_state(fields, extras, default_state=UNKNOWN_STATE):
    """Decide a plate's state. Returns {"code", "source", "raw"}.

    Order: a state element; "State: XX" in the comments, address or other text; the
    default; unknown. A value that is not a real state/province becomes XX."""
    raw = fields.get("vehicle_state")
    if raw:
        code, how = parse_state(raw)
        return {"code": code, "source": "element" if code != UNKNOWN_STATE else "element (unrecognised)", "raw": raw}
    texts = [("comments", fields.get("comments")), ("address", fields.get("address"))] + [(f"{n}", v) for n, v in extras]
    for where, text in texts:
        found = state_from_text(text)
        if found:
            code, matched = found
            return {"code": code, "source": f"text in {where}" if code != UNKNOWN_STATE else f"text in {where} (unrecognised)",
                    "raw": matched}
    if default_state != UNKNOWN_STATE:
        return {"code": default_state, "source": "default", "raw": None}
    return {"code": UNKNOWN_STATE, "source": "none found", "raw": None}


def parse_make(text):
    """'Black Ford Explorer' -> ('black', 'Ford', 'Explorer'); anything missing -> unknown."""
    words = (text or "").split()
    color_words = []
    while words and (words[0].lower() in COLORS or (words[0].lower() in COLOR_MODIFIERS and len(words) > 1)):
        color_words.append(words.pop(0).lower())
        if len(color_words) == 2:
            break
    color = " ".join(color_words).replace("gray", "grey") or UNKNOWN
    if len(words) >= 2 and " ".join(words[:2]).lower() in TWO_WORD_MAKES:
        make, model_words = " ".join(words[:2]), words[2:]
    elif words:
        make, model_words = words[0], words[1:]
    else:
        make, model_words = "Unknown", []
    return color, make.title() if make.isupper() or make.islower() else make, " ".join(model_words) or None


def guess_body_style(model):
    return BODY_STYLE_BY_MODEL.get((model or "").lower().split(" ")[0], UNKNOWN)


def _month_number(value):
    value = (value or "").strip()
    if value.isdigit() and 1 <= int(value) <= 12:
        return int(value)
    return MONTHS.get(value.upper()[:3])


def parse_timestamp(fields, offsets):
    """Return (UTC datetime, note or None). Never raises: the worst case is the
    1970 'unknown' date, which sorts oldest and is never shown as recent."""
    stamp = (fields.get("datestamp") or "").strip()

    m = re.match(r"^(?:[A-Za-z]{3,9},?\s+)?([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([A-Za-z]+)?$", stamp)
    if m and _month_number(m.group(1)):
        mon, day, year, hh, mm, ss, zone = m.groups()
        zone = (zone or "UTC").upper()
        note = None
        if zone not in offsets:
            note, zone = f"time zone {zone} not recognised; read as UTC; add its offset to correct", "UTC"
        try:
            local = datetime(int(year), _month_number(mon), int(day), int(hh), int(mm), int(ss or 0),
                             tzinfo=timezone(timedelta(hours=offsets[zone])))
            return local.astimezone(timezone.utc), note
        except ValueError:
            pass

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$", stamp)
    if m:
        y, mo, d, hh, mm, ss, tz = m.groups()
        try:
            tzinfo = timezone.utc
            if tz and tz != "Z":
                sign = -1 if tz[0] == "-" else 1
                digits = tz[1:].replace(":", "")
                tzinfo = timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))
            when = datetime(int(y), int(mo), int(d), int(hh or 12), int(mm or 0), int(ss or 0), tzinfo=tzinfo)
            return when.astimezone(timezone.utc), (None if hh else "time of day unknown; set to 12:00 UTC")
        except ValueError:
            pass

    if re.fullmatch(r"\d{9,13}", stamp):
        seconds = int(stamp) / (1000 if len(stamp) > 10 else 1)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc), None
        except (OverflowError, OSError, ValueError):
            pass

    month = _month_number(fields.get("month"))
    try:
        if month:
            return datetime(int(fields["year"]), month, int(fields["day"]), 12, 0, 0, tzinfo=timezone.utc), \
                "time of day unknown (no usable datestamp); set to 12:00 UTC"
    except (KeyError, ValueError):
        pass
    return EPOCH, "date unknown (no usable date in the XML); set to 1970-01-01"


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def pick_media(media_field):
    """Split the media list; drop index.html; keep preview.* only if nothing else is an image."""
    paths = [p.strip() for p in re.split(r"[,;\n]", media_field or "") if p.strip()]
    images = [p for p in paths if Path(p).suffix.lower() in IMAGE_EXTENSIONS]
    real = [p for p in images if not Path(p).stem.lower().startswith("preview")]
    skipped = [p for p in paths if p not in images]
    return (real or images)[:MAX_PHOTOS_PER_SIGHTING], skipped


# ---------- geocoding ----------

class GeocodeUnavailable(Exception):
    """The geocoding service could not be reached (not cached; retried on the next run)."""


def normalize_address(address):
    return re.sub(r"\s+", " ", (address or "").upper()).strip()


def census_geocode(address):
    """US Census one-line geocoder (free, no key, US addresses). -> (lat, lng) | None"""
    url = ("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?"
           + urllib.parse.urlencode({"address": address, "benchmark": "Public_AR_Current", "format": "json"}))
    data = _fetch_json(url)
    matches = (data.get("result") or {}).get("addressMatches") or []
    if not matches:
        return None
    c = matches[0]["coordinates"]
    return float(c["y"]), float(c["x"])  # the Census API calls longitude x and latitude y


def nominatim_geocode(address):
    """OpenStreetMap Nominatim: worldwide, but limited to 1 request/second by policy. -> (lat, lng) | None"""
    time.sleep(1.1)
    url = ("https://nominatim.openstreetmap.org/search?"
           + urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1}))
    data = _fetch_json(url)
    return (float(data[0]["lat"]), float(data[0]["lon"])) if data else None


def _fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ParkingTracker-import/1.0", "Accept": "application/json"})
    last = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code < 500:  # a 4xx will not get better on retry
                break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last = exc
        time.sleep(1.5)
    raise GeocodeUnavailable(str(last))


class Geocoder:
    """Overrides, then cache, then the provider. Any failure leaves the location unknown (None)."""

    def __init__(self, provider=None, cache_path=None, overrides=None, default_area="", coarsen=4, max_failures=3):
        self.provider = provider
        self.cache_path = cache_path
        self.overrides = overrides or {}
        self.default_area = default_area.strip()
        self.coarsen = coarsen
        self.max_failures = max_failures
        self.failures = 0
        self.disabled = False
        self.cache = {}
        self.stats = {"matched": 0, "unmatched": [], "unavailable": 0, "from_cache": 0, "from_overrides": 0}
        if cache_path and Path(cache_path).is_file():
            try:
                self.cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            except ValueError:
                self.cache = {}

    def query_for(self, address):
        address = re.sub(r"\s+", " ", address or "").strip()
        if self.default_area and self.default_area.split()[0].upper() not in address.upper():
            return f"{address} {self.default_area}"
        return address

    def locate(self, address):
        """-> {'lat', 'lng'} or None"""
        key = normalize_address(address)
        if not key:
            return None
        if key in self.overrides:
            self.stats["from_overrides"] += 1
            return self._result(self.overrides[key])
        query = self.query_for(address)
        qkey = normalize_address(query)
        if qkey in self.cache:
            self.stats["from_cache"] += 1
            return self._result(self.cache[qkey])
        if self.provider is None or self.disabled:
            return None
        try:
            found = self.provider(query)
        except GeocodeUnavailable:
            self.stats["unavailable"] += 1
            self.failures += 1
            if self.failures >= self.max_failures:
                self.disabled = True
                print(f"warning: geocoding service unreachable {self.failures} times in a row; skipping the rest "
                      "(locations stay unknown; re-run later, the cache keeps what worked)", file=sys.stderr)
            return None
        self.failures = 0
        self.cache[qkey] = list(found) if found else None  # only definite answers are cached
        if found is None:
            self.stats["unmatched"].append(address)
        return self._result(found)

    def _result(self, pair):
        if not pair:
            return None
        lat, lng = pair
        if self.coarsen is not None:
            lat, lng = round(lat, self.coarsen), round(lng, self.coarsen)
        self.stats["matched"] += 1
        return {"lat": lat, "lng": lng}

    def save(self):
        if self.cache_path and self.cache:
            Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.cache_path).write_text(json.dumps(self.cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def load_overrides(path):
    """CSV with columns address,lat,lng -> {normalized address: (lat, lng)}"""
    overrides = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                overrides[normalize_address(row["address"])] = (float(row["lat"]), float(row["lng"]))
            except (KeyError, ValueError, TypeError):
                print(f"warning: skipped bad row in {path}: {row}", file=sys.stderr)
    return overrides


def configured_coarsening(root):
    """COARSEN_DECIMALS from web/js/config.js, so imports follow the app's privacy setting."""
    try:
        text = (root / "web" / "js" / "config.js").read_text(encoding="utf-8")
        m = re.search(r"COARSEN_DECIMALS\s*=\s*(\d+|null)", text)
        if m:
            return None if m.group(1) == "null" else int(m.group(1))
    except OSError:
        pass
    return 4


# ---------- photos ----------

def convert_photo(src: Path, dest: Path):
    """Write src as a JPEG no larger than PHOTO_MAX_BYTES; raises on unreadable images."""
    from PIL import Image, ImageOps  # imported lazily: only needed when photos exist

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        im.thumbnail((PHOTO_MAX_EDGE, PHOTO_MAX_EDGE))
        for quality in (82, 72, 62, 52, 42, 32):
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            if buf.tell() <= PHOTO_MAX_BYTES:
                break
        else:
            while buf.tell() > PHOTO_MAX_BYTES and min(im.size) > 200:
                im = im.resize((int(im.width * 0.8), int(im.height * 0.8)))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=32, optimize=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(buf.getvalue())


def find_media_file(media_root: Path, rel: str):
    """Resolve a media path under media_root, refusing anything that escapes it."""
    if not media_root:
        return None
    root = media_root.resolve()
    candidate = (root / rel.replace("\\", "/")).resolve()
    if root != candidate and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


# ---------- building records ----------

def reconcile(read, counts, report):
    """Did every record in the XML end up somewhere? read = already in data + new + repeated within the file."""
    new, already, repeated = counts["sightings"], counts["already_imported"], counts["duplicates"]
    dated = [r["timestamp"] for r in report["records"] if r["timestamp"] and not r["timestamp"].startswith("1970")]
    newdated = [r["timestamp"] for r in report["records"] if r["result"] == "new" and not r["timestamp"].startswith("1970")]
    return {"records_read": read, "new": new, "already_imported": already, "repeated_in_file": repeated,
            "accounted_for": new + already + repeated, "complete": new + already + repeated == read,
            "date_range": [min(dated), max(dated)] if dated else None,
            "new_date_range": [min(newdated), max(newdated)] if newdated else None,
            "no_date": sum(1 for r in report["records"] if r["timestamp"] and r["timestamp"].startswith("1970")),
            "with_location_new": sum(1 for r in report["records"] if r["result"] == "new" and r["located"]),
            "without_location_new": sum(1 for r in report["records"] if r["result"] == "new" and not r["located"])}


def load_existing(root):
    """Read the vehicles and plates already in data/. Returns ({key: vehicle}, {"ST-PLATE": plate})."""
    vehicles, plates = {}, {}
    for folder, target in (("vehicles", vehicles), ("plates", plates)):
        for path in sorted((root / "data" / folder).glob("*.json")):
            try:
                target[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
    return vehicles, plates


def find_target(identity, key, plate, state, vehicles, plates):
    """Which existing vehicle should new sightings for this identity join?

    The vehicle derived from the XML (`key`) if it still exists. Otherwise, because records may have
    been edited since the first import: the vehicle that now owns this state+plate (plate file, then
    alias); and, when the XML gives no state, the one vehicle holding that plate under a known state.
    Returns (key, how) where how is None when nothing was redirected."""
    if key in vehicles or not identity.startswith("plate:") or not plate:
        return key, None
    name = f"{state}-{plate}"
    owner = (plates.get(name) or {}).get("currentVehicleKey")
    if owner in vehicles:
        return owner, "plate record"
    holders = sorted(k for k, v in vehicles.items() if name in v.get("plateAliases", []))
    if len(holders) == 1:
        return holders[0], "alias"
    if state == UNKNOWN_STATE:
        others = {(p.get("currentVehicleKey")) for n, p in plates.items()
                  if n.endswith("-" + plate) and n != name and p.get("currentVehicleKey") in vehicles}
        if len(others) == 1:
            return others.pop(), "same plate, state set since import"
    return key, None


def backfill_media(item, owner, sid, vehicle, media_root, root, offsets, dry_run, counts, report):
    """A sighting that is already imported keeps everything, but gets its photos if it has none yet."""
    _plate, token, fields, _extras, _state, _entry = item
    target = next((s for s in vehicle["sightings"] if s["id"] == sid or s.get("source") == f"{TAG}:{token}"), None)
    if target is None or target.get("photos"):
        return
    paths, _skipped = pick_media(fields.get("media"))
    when, _note = parse_timestamp(fields, offsets)
    added = []
    for n, rel in enumerate(paths, 1):
        src = find_media_file(media_root, rel)
        if src is None:
            report["media_not_imported"].append({"alert_token": token, "path": rel, "reason": "file not found under --media-root"})
            continue
        dest_rel = f"photos/{owner}_{when.strftime('%Y%m%dT%H%M%S')}_{n:03d}.jpg"
        try:
            if not dry_run:
                convert_photo(src, root / dest_rel)
            added.append(dest_rel)
        except Exception as exc:
            report["media_not_imported"].append({"alert_token": token, "path": rel, "reason": f"could not convert: {exc}"})
    if not added:
        return
    target["photos"] = added
    if target.get("notes"):
        lines = [ln for ln in target["notes"].split("\n") if not ln.startswith("Legacy media (not imported):")]
        target["notes"] = "\n".join(lines) or None
    counts["photos"] += len(added)
    if not dry_run:
        (root / "data" / "vehicles" / f"{owner}.json").write_text(json.dumps(vehicle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_vehicles(rows, offsets, media_root, root, dry_run, report, flag, geocoder, default_state=UNKNOWN_STATE, trace=None):
    """Group rows into vehicles and write them. Returns counts."""
    groups = {}
    states = report["states"] = {"by_source": Counter(), "by_code": Counter(), "unrecognised": {}, "plates_without_state": 0}
    for index, (group_name, fields, extras) in enumerate(rows):
        plate = normalize_plate(fields.get("vehicle_license"))
        token = fields.get("alert_token") or digest(group_name + json.dumps([fields, extras], sort_keys=True))
        state = resolve_state(fields, extras, default_state) if plate else {"code": UNKNOWN_STATE, "source": "no plate", "raw": None}
        key_text = f"{state['code']}-{plate}" if plate else None
        identity = f"plate:{key_text}" if plate else f"noplate:{token}"
        if plate:
            states["by_source"][state["source"]] += 1
            states["by_code"][state["code"]] += 1
            if state["code"] == UNKNOWN_STATE:
                states["plates_without_state"] += 1
            if "unrecognised" in state["source"]:
                states["unrecognised"][state["raw"]] = states["unrecognised"].get(state["raw"], 0) + 1
        if plate and not PLATE_RE.match(plate):
            report["plates_not_storable"].setdefault(plate, []).append(token)
        for name, value in extras:
            report["unmapped_fields"].setdefault(name, []).append({"alert_token": token, "value": value})
        entry = None
        if trace is not None:
            entry = {"record": index + 1, "alert_token": token, "group": group_name,
                     "plate": {"raw": fields.get("vehicle_license"), "normalized": plate,
                               "storable": bool(plate and PLATE_RE.match(plate))},
                     "state": state, "plate_key": key_text, "identity": identity,
                     "fields": dict(fields), "extras": [list(e) for e in extras], "decisions": []}
            trace.append(entry)
        groups.setdefault(identity, []).append((plate, token, fields, extras, state["code"], entry))
    by_plate = {}
    for identity in groups:
        if identity.startswith("plate:"):
            code, _, plate = identity[len("plate:"):].partition("-")
            by_plate.setdefault(plate, set()).add(code)
    report["state_ambiguous"] = [
        {"plate": p, "states": sorted(c)} for p, c in sorted(by_plate.items()) if UNKNOWN_STATE in c and len(c) > 1]

    counts = {"vehicles": 0, "sightings": 0, "photos": 0, "plates": 0, "located": 0, "duplicates": 0, "already_imported": 0}
    report["already_imported"], report["redirected"], report["flag_changed"], report["new_records"] = [], [], [], []
    report["records"] = []  # one line per XML record: what happened to it
    vehicles_mem, plates_mem = load_existing(root)
    known = {}
    for vk, v in vehicles_mem.items():
        for s in v.get("sightings", []):
            known[s["id"]] = vk
            if s.get("source"):
                known[s["source"]] = vk
    for identity, all_items in sorted(groups.items()):
        base_key = f"VEH_{digest('xml:' + identity)}"
        items = []
        for it in all_items:
            token, entry = it[1], it[5]
            sid = f"S_{digest('xml:' + token)}"
            owner = known.get(sid) or known.get(f"{TAG}:{token}")
            if owner is None:
                items.append(it)
                continue
            # Already in the data (possibly edited since): never touched again, except photos.
            counts["already_imported"] += 1
            report["already_imported"].append(token)
            report["records"].append({"alert_token": token, "result": "already imported", "vehicle": owner,
                                      "plate": f"{it[4]}-{it[0]}" if it[0] else None, "timestamp": iso(parse_timestamp(it[2], offsets)[0]),
                                      "located": None})
            if entry is not None:
                entry["vehicle_key"], entry["sighting_id"] = owner, sid
                entry["decisions"].append({"skipped": "already in the data; left as it is"})
            if media_root is not None:
                backfill_media(it, owner, sid, vehicles_mem[owner], media_root, root, offsets, dry_run, counts, report)
        if not items:
            continue
        plate, state_code = items[0][0], items[0][4]
        key, how = find_target(identity, base_key, plate, state_code, vehicles_mem, plates_mem)
        if how:
            report["redirected"].append({"identity": identity, "joined_vehicle": key, "because": how})
        storable = bool(plate and PLATE_RE.match(plate))
        # The plate is only (re)written for a new vehicle or one that still lists it: if the vehicle was
        # edited since import (plate state changed), its plate records are left as the data tool set them.
        keep_plates = bool(how) or (key in vehicles_mem and f"{state_code}-{plate}" not in vehicles_mem[key].get("plateAliases", []))
        sightings, newest = {}, None

        for _, token, fields, extras, _state, entry in items:
            sid = f"S_{digest('xml:' + token)}"
            if sid in sightings:
                counts["duplicates"] += 1
                report["duplicate_records"].append(token)
                report["records"].append({"alert_token": token, "result": "repeated in this file", "vehicle": key,
                                          "plate": f"{state_code}-{plate}" if plate else None,
                                          "timestamp": iso(parse_timestamp(fields, offsets)[0]), "located": None})
            when, time_note = parse_timestamp(fields, offsets)
            if entry is not None:
                entry["vehicle_key"], entry["sighting_id"] = key, sid
                entry["decisions"].append({"timestamp": {"raw": [fields.get("datestamp"), fields.get("month"), fields.get("day"), fields.get("year")],
                                                          "result": iso(when), "note": time_note or None}})
            if when == EPOCH:
                report["needs_review"].append({"alert_token": token, "why": "date unknown; set to 1970-01-01"})
            elif time_note:
                report["assumptions"].append({"alert_token": token, "note": time_note})

            notes = []
            if fields.get("comments"):
                notes.append(fields["comments"])
            if fields.get("address"):
                notes.append(f"Address: {fields['address']}")
            if plate and not storable:
                notes.append(f"Plate: {plate} (not stored as a plate: 1-20 letters/digits only)")
            if entry is not None and plate and not storable:
                entry["decisions"].append({"plate": "too long or invalid; kept in notes"})
            for name, value in extras:  # data without a field of its own
                notes.append(f"{name}: {value}")
            if time_note:
                notes.append(f"[{time_note}]")

            photos = []
            media_paths, skipped_media = pick_media(fields.get("media"))
            if media_root is None:
                if media_paths:
                    notes.append("Legacy media (not imported): " + ", ".join(media_paths))
            else:
                for n, rel in enumerate(media_paths, 1):
                    src = find_media_file(media_root, rel)
                    reason = None
                    if src is None:
                        reason = "file not found under --media-root"
                    else:
                        dest_rel = f"photos/{key}_{when.strftime('%Y%m%dT%H%M%S')}_{n:03d}.jpg"
                        try:
                            if not dry_run:
                                convert_photo(src, root / dest_rel)
                            photos.append(dest_rel)
                            counts["photos"] += 1
                        except Exception as exc:  # unreadable or unsupported image
                            reason = f"could not convert: {exc}"
                    if reason:
                        report["media_not_imported"].append({"alert_token": token, "path": rel, "reason": reason})
                        notes.append(f"Media not imported: {rel} ({reason})")
            for rel in skipped_media:
                report["media_not_imported"].append({"alert_token": token, "path": rel, "reason": "not an image"})

            location = geocoder.locate(fields.get("address")) if fields.get("address") else None
            if location:
                counts["located"] += 1
            if entry is not None:
                entry["decisions"].append({"address": {"raw": fields.get("address"), "location": location,
                                                       "lookup_query": geocoder.query_for(fields["address"]) if fields.get("address") else None}})
                entry["decisions"].append({"media": {"raw": fields.get("media"), "photos": photos, "legacy_paths": media_paths}})
            sightings[sid] = {
                "id": sid,
                "timestamp": iso(when),
                "location": location,
                "photos": photos,
                "flag": flag,
                "notes": "\n".join(notes) or None,
                "source": f"{TAG}:{token}",
                "observer": TAG,
            }
            if newest is None or iso(when) >= newest[0]:
                newest = (iso(when), fields)

        color, make, model = parse_make(newest[1].get("vehicle_make"))
        for _, _t, _f, _e, _s, entry in items:
            if entry is not None:
                entry["decisions"].append({"vehicle": {"raw": newest[1].get("vehicle_make"), "color": color, "make": make, "model": model,
                                                       "bodyStyle": guess_body_style(model)}})
        incoming = {
            "vehicleKey": key,
            "displayName": " ".join(p for p in (color.title(), make, model) if p),
            "color": color,
            "make": make,
            "model": model,
            "bodyStyle": guess_body_style(model),
            "distinguishing": [UNKNOWN],
            "distinguishingNotes": None,
            "plateAliases": [f"{state_code}-{plate}"] if storable and not keep_plates else [],
            "possibleDuplicate": False,
            "lastUpdatedBy": TAG,
        }
        before = vehicles_mem.get(key)
        vehicle = merge_with_existing(before, incoming, list(sightings.values()))
        if before and before.get("flag") != vehicle["flag"]:
            report["flag_changed"].append({"vehicle": key, "from": before.get("flag"), "to": vehicle["flag"],
                                           "because": "newer sighting than any already recorded"})
        vehicles_mem[key] = vehicle
        for s in sightings.values():
            report["new_records"].append({"alert_token": s["source"].split(":", 1)[1], "vehicle": key,
                                          "plate": f"{state_code}-{plate}" if plate else None, "timestamp": s["timestamp"],
                                          "new_vehicle": before is None})
            report["records"].append({"alert_token": s["source"].split(":", 1)[1], "result": "new", "vehicle": key,
                                      "plate": f"{state_code}-{plate}" if plate else None, "timestamp": s["timestamp"],
                                      "located": s["location"] is not None})
        counts["vehicles"] += 1
        counts["sightings"] += len(sightings)

        if not dry_run:
            path = root / "data" / "vehicles" / f"{key}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(vehicle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if storable and not keep_plates:
            counts["plates"] += write_plate(root, plate, state_code, key, vehicle, dry_run, report)
    report["check"] = reconcile(len(rows), counts, report)
    return counts


def merge_with_existing(existing, incoming, sightings):
    """Add new sightings to an existing vehicle record (or start one). Existing sightings and
    fields are never changed. The flag follows the new sightings only when they are newer than
    everything already recorded."""
    by_id = {s["id"]: s for s in (existing or {}).get("sightings", [])}
    previous_last = max((s["timestamp"] for s in by_id.values()), default=None)
    for s in sightings:
        by_id.setdefault(s["id"], s)
    merged = sorted(by_id.values(), key=lambda s: s["timestamp"])
    base = dict(existing) if existing else dict(incoming)
    if existing:
        base["plateAliases"] = sorted(set(existing.get("plateAliases", [])) | set(incoming["plateAliases"]))
    base["sightings"] = merged
    if not existing or previous_last is None or merged[-1]["timestamp"] > previous_last:
        base["flag"] = merged[-1]["flag"]
    base["firstSeen"] = merged[0]["timestamp"]
    base["lastSeen"] = merged[-1]["timestamp"]
    return base


def write_plate(root, plate, state, key, vehicle, dry_run, report):
    path = root / "data" / "plates" / f"{state}-{plate}.json"
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            current = {}
        if current.get("currentVehicleKey") not in (None, key):
            report["plate_conflicts"].append({
                "plate": f"{state}-{plate}", "existing_vehicle": current.get("currentVehicleKey"), "imported_vehicle": key,
                "action": "kept existing plate record; imported vehicle still lists the plate as an alias"})
            return 0
    plate_type = "standard"
    if path.is_file():
        plate_type = (current.get("plateType") or "standard") if current.get("currentVehicleKey") == key else "standard"
    record = {
        "plate": plate, "plateState": state, "plateType": plate_type, "currentVehicleKey": key,
        "firstSeen": vehicle["firstSeen"], "updated": vehicle["lastSeen"],
    }
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 1


# ---------- main ----------

def convert(sources, root: Path, media_root=None, dry_run=False, offsets=None, flag="confirmed", geocoder=None,
            default_state=UNKNOWN_STATE, debug=False):
    """Convert every XML file in `sources` (files or folders). Returns (counts, report).

    report["debug"] always holds the cheap diagnostics (per-file facts, element census, how each
    element was mapped). With debug=True it also holds a trace of every record."""
    offsets = {**TZ_OFFSETS, **(offsets or {})}
    geocoder = geocoder or Geocoder(provider=None)
    sources = [sources] if isinstance(sources, Path) else list(sources)
    report = {
        "files": [], "files_failed": [], "unmapped_fields": {}, "needs_review": [], "assumptions": [],
        "duplicate_records": [], "media_not_imported": [], "plate_conflicts": [], "plates_not_storable": {},
    }
    dbg = report["debug"] = {"files": [], "elements": {}, "field_map": {}, "record_shapes": {}, "records": None}
    rows = []
    for path in find_xml_files(sources):
        info = {"file": str(path)}
        try:
            text = read_xml_text(path.read_bytes(), info)
            found = list(parse_xml(text, info))
        except (ImportErrorXml, OSError, UnicodeError) as exc:
            report["files_failed"].append({"file": str(path), "reason": str(exc)})
            dbg["files"].append({**{k: v for k, v in info.items() if k != "records"}, "failed": str(exc)})
            continue
        entry = {"file": str(path), "records": len(found)}
        if info.get("repaired"):
            entry["repaired_characters"] = info["repaired"]
            print(f"warning: {path.name}: not well formed; repaired {info['repaired']} stray '<', '&' or control characters", file=sys.stderr)
        report["files"].append(entry)
        rows.extend(found)

        dbg["files"].append({k: v for k, v in info.items() if k not in ("records", "elements")} | {"records": len(found)})
        for name, n in info.get("elements", {}).items():
            dbg["elements"][name] = dbg["elements"].get(name, 0) + n
        for rec in info.get("records", []):
            shape = ", ".join(sorted({n for n, _ in rec["children"]}))
            dbg["record_shapes"][shape] = dbg["record_shapes"].get(shape, 0) + 1
            for name, value in rec["children"]:
                bare = name.lstrip("@")
                target = CANONICAL.get(bare)
                slot = dbg["field_map"].setdefault(name, {"becomes": target or "notes (no field of its own)", "count": 0, "empty": 0, "examples": []})
                slot["count"] += 1
                if not value:
                    slot["empty"] += 1
                elif len(slot["examples"]) < 3 and value not in slot["examples"]:
                    slot["examples"].append(value[:80])
        if debug:
            dbg.setdefault("_meta", []).extend({"file": path.name, **rec} for rec in info.get("records", []))

    trace = [] if debug else None
    counts = build_vehicles(rows, offsets, media_root, root, dry_run, report, flag, geocoder, default_state, trace)
    counts["records_read"] = len(rows)
    counts["files_read"] = len(report["files"])
    report["counts"] = counts
    report["geocoding"] = geocoder.stats
    report["states"] = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in report["states"].items()}
    if debug:
        meta = dbg.pop("_meta", [])
        for entry, m in zip(trace, meta):
            entry["source"] = {"file": m["file"], "line": m["line"], "xml": m["snippet"]}
        dbg["records"] = trace
    return counts, report


def debug_text(report):
    """The debug report as plain text, for reading top to bottom."""
    d, out = report["debug"], []
    add = out.append
    add("XML IMPORT DEBUG REPORT")
    add("=" * 60)
    add("\nFILES")
    for f in d["files"]:
        bits = [f"{f['file']}", f"{f.get('bytes', '?')} bytes", f"{f.get('lines', '?')} lines",
                f"encoding {f.get('encoding_used', '?')} (declared {f.get('encoding_declared') or 'none'})",
                f"{f.get('records', 0)} records"]
        add("  " + "; ".join(bits))
        if f.get("failed"):
            add(f"    FAILED: {f['failed']}")
        if f.get("first_error"):
            add(f"    strict parse error: {f['first_error']}")
        if f.get("repaired"):
            add(f"    repaired {f['repaired']} character(s); first {len(f.get('repairs', []))} listed:")
            for x in f.get("repairs", []):
                add(f"      line {x['line']}, col {x['column']}: {x['kind']}  ...{x['context']}...")
    st = report.get("states", {})
    add("\nPLATE STATE")
    add(f"  where the state came from: {st.get('by_source', {})}")
    add(f"  states found: {st.get('by_code', {})}")
    add(f"  plates left with unknown state (XX): {st.get('plates_without_state', 0)}")
    if st.get("unrecognised"):
        add(f"  state values that are not a real state/province (became XX): {st['unrecognised']}")
    for a in report.get("state_ambiguous", []):
        add(f"  same plate with and without a state: {a['plate']} -> {a['states']}")
    add("\nXML ELEMENTS (all files; name: count)")
    for name, n in sorted(d["elements"].items(), key=lambda kv: -kv[1]):
        add(f"  {name}: {n}")
    add("\nHOW EACH ELEMENT WAS USED (inside records)")
    for name, m in sorted(d["field_map"].items(), key=lambda kv: -kv[1]["count"]):
        add(f"  {name:24} -> {m['becomes']:34} x{m['count']} ({m['empty']} empty)  e.g. {m['examples']}")
    add("\nRECORD SHAPES (the set of elements a record has -> how many)")
    for shape, n in sorted(d["record_shapes"].items(), key=lambda kv: -kv[1]):
        add(f"  x{n}: {shape}")
    if d.get("records"):
        add("\nRECORDS")
        for e in d["records"]:
            src = e.get("source", {})
            add(f"  #{e['record']} {src.get('file', '')}:{src.get('line', '?')} token={e['alert_token']} group={e['group']}")
            pl = e["plate"]
            add(f"      plate {pl['raw']!r} -> {pl['normalized']!r} (storable={pl['storable']}); state {e['state']['code']} from {e['state']['source']}"
                + (f" [{e['state']['raw']!r}]" if e["state"]["raw"] else "") + f"; key {e['plate_key']}")
            add(f"      vehicle {e.get('vehicle_key')} sighting {e.get('sighting_id')} identity {e['identity']}")
            for dec in e["decisions"]:
                for k, v in dec.items():
                    add(f"      {k}: {json.dumps(v, ensure_ascii=False)}")
            if e["extras"]:
                add(f"      no field of its own (-> notes): {e['extras']}")
            add(f"      xml: {src.get('xml', '')[:300]}")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--in", dest="inputs", action="append", required=True, type=Path,
                        help="XML file or folder (repeatable; folders are searched for *.xml)")
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path, help="repository root")
    parser.add_argument("--media-root", type=Path,
                        help="folder the XML's media/... paths are relative to. Omit to skip legacy media (the default)")
    parser.add_argument("--flag", default="confirmed", choices=["unknown", "suspected", "confirmed", "cleared", "pigs"],
                        help="flag for every imported sighting (default: confirmed)")
    parser.add_argument("--geocode", default="census", choices=["census", "nominatim", "none"],
                        help="turn addresses into locations (default: census, US only; nominatim is worldwide but slow)")
    parser.add_argument("--default-area", default="", metavar="'CITY ST'",
                        help="added to addresses that do not already mention it, e.g. 'Pasadena CA'")
    parser.add_argument("--geocode-overrides", type=Path, metavar="CSV",
                        help="CSV with columns address,lat,lng that wins over the service")
    parser.add_argument("--geocode-cache", type=Path, help="default: <root>/import/geocode-cache.json")
    parser.add_argument("--coarsen", help="decimal places for locations, or 'none'. Default: COARSEN_DECIMALS from web/js/config.js")
    parser.add_argument("--tz-offset", action="append", default=[], metavar="NAME=HOURS",
                        help="extra time zone, e.g. AEST=10 (PST/PDT/EST etc. are built in)")
    parser.add_argument("--default-state", default="", metavar="ST",
                        help="state for plates with no state in the XML, e.g. CA (default: XX = unknown)")
    parser.add_argument("--debug", action="store_true",
                        help="explain every decision: writes reports/xml-import-debug.json and .txt (with --dry-run: prints the text)")
    parser.add_argument("--dry-run", action="store_true", help="report what would be written; write nothing")
    args = parser.parse_args(argv)

    offsets = {}
    for item in args.tz_offset:
        name, _, hours = item.partition("=")
        try:
            offsets[name.upper()] = float(hours)
        except ValueError:
            print(f"error: bad --tz-offset {item!r}; use NAME=HOURS", file=sys.stderr)
            return 2
    for path in args.inputs:
        if not path.exists():
            print(f"error: {path} not found", file=sys.stderr)
            return 2
    if args.media_root is not None and not args.media_root.is_dir():
        print(f"error: --media-root {args.media_root} is not a folder", file=sys.stderr)
        return 2
    if args.coarsen is None:
        coarsen = configured_coarsening(args.root)
    elif args.coarsen.lower() == "none":
        coarsen = None
    else:
        try:
            coarsen = int(args.coarsen)
        except ValueError:
            print("error: --coarsen must be a number or 'none'", file=sys.stderr)
            return 2

    default_state = UNKNOWN_STATE
    if args.default_state:
        default_state, how = parse_state(args.default_state)
        if default_state == UNKNOWN_STATE:
            print(f"error: --default-state {args.default_state!r} is not a US state or Canadian province", file=sys.stderr)
            return 2

    provider = {"census": census_geocode, "nominatim": nominatim_geocode, "none": None}[args.geocode]
    cache_path = args.geocode_cache or (args.root / "import" / "geocode-cache.json")
    geocoder = Geocoder(
        provider=provider, cache_path=cache_path,
        overrides=load_overrides(args.geocode_overrides) if args.geocode_overrides else {},
        default_area=args.default_area, coarsen=coarsen)

    counts, report = convert(args.inputs, args.root, args.media_root, args.dry_run, offsets, args.flag, geocoder,
                             default_state, args.debug)
    if not args.dry_run:
        geocoder.save()

    verb = "would write" if args.dry_run else "wrote"
    print(f"read {counts['records_read']} records from {counts['files_read']} file(s); {verb} {counts['vehicles']} vehicles, "
          f"{counts['plates']} plates, {counts['photos']} photos ({counts['sightings']} sightings, "
          f"{counts['located']} with a location)")
    print(f"  {counts['already_imported']} record(s) already in the data were left as they are; "
          f"{len(report['new_records'])} new sighting(s) added to {sum(1 for r in report['new_records'] if r['new_vehicle'])} new "
          f"and {len({r['vehicle'] for r in report['new_records'] if not r['new_vehicle']})} existing vehicle(s)")
    c = report["check"]
    print(("CHECK OK: " if c["complete"] else "CHECK FAILED: ") + f"{c['records_read']} records read = {c['already_imported']} already in the data "
          f"+ {c['new']} new + {c['repeated_in_file']} repeated within the file"
          + ("" if c["complete"] else f" (only {c['accounted_for']} accounted for)"))
    if c["date_range"]:
        print(f"  records dated {c['date_range'][0][:10]} to {c['date_range'][1][:10]}"
              + (f"; new ones {c['new_date_range'][0][:10]} to {c['new_date_range'][1][:10]}" if c["new_date_range"] else "; none are new")
              + (f"; {c['no_date']} with no usable date" if c["no_date"] else ""))
    if c["records_read"] and not c["new"] and c["complete"]:
        print("  Nothing new: everything in this file is already in your data.")
    g = report["geocoding"]
    if g["unmatched"]:
        print(f"  {len(g['unmatched'])} address(es) not found: location left unknown")
    if g["unavailable"]:
        print(f"  geocoding service unreachable for {g['unavailable']} lookup(s): those locations are unknown (re-run later)")
    for label, key in (("file(s) failed", "files_failed"), ("need review", "needs_review"),
                       ("assumption(s) made", "assumptions"), ("duplicate record(s)", "duplicate_records"),
                       ("media not imported", "media_not_imported"), ("plate conflict(s)", "plate_conflicts"),
                       ("joined a vehicle that was edited or renamed since import", "redirected"),
                       ("vehicle flag(s) changed by a newer sighting", "flag_changed")):
        if report[key]:
            print(f"  {len(report[key])} {label} (see reports/xml-import.json)")
    st = report["states"]
    if st["by_code"]:
        print("  plate states: " + ", ".join(f"{k} x{v}" for k, v in sorted(st["by_code"].items(), key=lambda kv: -kv[1]))
              + (f"  ({st['plates_without_state']} with no state found: XX; run with --debug to see why)" if st["plates_without_state"] else ""))
    if report["state_ambiguous"]:
        print(f"  {len(report['state_ambiguous'])} plate(s) appear both with and without a state (kept as separate plates)")
    if report["plates_not_storable"]:
        print("  plates not stored (1-20 letters/digits only; text kept in notes): "
              + ", ".join(sorted(report["plates_not_storable"])))
    if report["unmapped_fields"]:
        print("  data with no field, added to notes: "
              + ", ".join(f"{k} (x{len(v)})" for k, v in sorted(report["unmapped_fields"].items())))
    for item in report["files_failed"]:
        print(f"  FAILED {item['file']}: {item['reason']}", file=sys.stderr)

    if args.dry_run:
        if args.debug:
            print(debug_text(report))
        return 0 if counts["files_read"] else 2

    reports_dir = args.root / "reports"
    reports_dir.mkdir(exist_ok=True)
    if args.debug:
        (reports_dir / "xml-import-debug.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (reports_dir / "xml-import-debug.txt").write_text(debug_text(report), encoding="utf-8")
        print("  debug detail: reports/xml-import-debug.txt (read) and .json (data)")
        report["debug"]["records"] = None  # the main report stays small
    with open(reports_dir / "xml-import-records.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["alert_token", "result", "vehicle", "plate", "timestamp", "location_found"])
        for r in report["records"]:
            w.writerow([r["alert_token"], r["result"], r["vehicle"], r["plate"] or "", r["timestamp"],
                        "" if r["located"] is None else ("yes" if r["located"] else "no")])
    print("  record-by-record log: reports/xml-import-records.csv")
    (reports_dir / "xml-import.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if counts["files_read"] == 0:
        print("error: no XML file could be read", file=sys.stderr)
        return 2
    build_index.main(["--root", str(args.root)])
    status = validate_records.main(["--root", str(args.root)])
    return status or (1 if report["files_failed"] else 0)


if __name__ == "__main__":
    sys.exit(main())
