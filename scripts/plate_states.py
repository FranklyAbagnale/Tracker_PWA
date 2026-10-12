"""Plate state codes and plate keys, shared by the scripts.

A plate is identified by state + plate and written as "<STATE>-<PLATE>" (CA-7ABC123).
The state is one of:
  * a 2-letter US state/territory or Canadian province (CA, BC),
  * a 3-letter Mexican state, ISO 3166-2:MX without the country (SON = Sonora),
  * USG or GOV (federal / government plates), optionally with a code after a dash
    (USG-G42, GOV-DHS). The code is part of the state, so the plate keeps its own number.
  * XX = the state is not known.
The plate itself never contains a dash, so a key is split at its last dash.
Keep STATES in sync with web/js/config.js and tools/import.html.
"""

import re
import unicodedata

UNKNOWN_STATE = "XX"
STATES = (
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
    "PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI AB BC MB NB NL NS NT NU ON PE QC SK YT"
).split()
# Mexico: ISO 3166-2:MX codes (the part after "MX-")
MX_STATES = (
    "AGU BCN BCS CAM CHP CHH CMX COA COL DUR GUA GRO HID JAL MEX MIC MOR NAY NLE OAX PUE QUE ROO SLP SIN SON TAB TAM "
    "TLA VER YUC ZAC"
).split()
FEDERAL_STATES = ("USG", "GOV")
CODE_MAX = 8  # longest optional code after USG- / GOV-
STATES = STATES + MX_STATES + list(FEDERAL_STATES) + [UNKNOWN_STATE]
# A state as stored: a plain code, or USG/GOV with a code. Plain codes are checked against STATES by is_valid_state.
STATE_PATTERN = r"(?:[A-Z]{2,3}|(?:USG|GOV)-[A-Z0-9]{1,%d})" % CODE_MAX
KEY_RE = re.compile(r"^(%s)-([A-Z0-9]{1,20})$" % STATE_PATTERN)

STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY",
    "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "PUERTO RICO": "PR", "GUAM": "GU", "VIRGIN ISLANDS": "VI", "AMERICAN SAMOA": "AS",
    "NORTHERN MARIANA ISLANDS": "MP", "ALBERTA": "AB", "BRITISH COLUMBIA": "BC", "MANITOBA": "MB",
    "NEW BRUNSWICK": "NB", "NEWFOUNDLAND": "NL", "NOVA SCOTIA": "NS", "NORTHWEST TERRITORIES": "NT", "NUNAVUT": "NU",
    "ONTARIO": "ON", "PRINCE EDWARD ISLAND": "PE", "QUEBEC": "QC", "SASKATCHEWAN": "SK", "YUKON": "YT",
    "NEWFOUNDLAND AND LABRADOR": "NL", "NEWFOUNDLAND & LABRADOR": "NL", "NORTH WEST TERRITORIES": "NT",
    # Mexico (accents are removed before matching)
    "AGUASCALIENTES": "AGU", "BAJA CALIFORNIA": "BCN", "BAJA CALIFORNIA NORTE": "BCN",
    "BAJA CALIFORNIA SUR": "BCS", "CAMPECHE": "CAM", "CHIAPAS": "CHP", "CHIHUAHUA": "CHH",
    "CIUDAD DE MEXICO": "CMX", "MEXICO CITY": "CMX", "DISTRITO FEDERAL": "CMX", "COAHUILA": "COA",
    "COAHUILA DE ZARAGOZA": "COA", "COLIMA": "COL", "DURANGO": "DUR", "GUANAJUATO": "GUA", "GUERRERO": "GRO",
    "HIDALGO": "HID", "JALISCO": "JAL", "ESTADO DE MEXICO": "MEX", "MICHOACAN": "MIC", "MORELOS": "MOR",
    "NAYARIT": "NAY", "NUEVO LEON": "NLE", "OAXACA": "OAX", "PUEBLA": "PUE", "QUERETARO": "QUE",
    "QUINTANA ROO": "ROO", "SAN LUIS POTOSI": "SLP", "SINALOA": "SIN", "SONORA": "SON", "TABASCO": "TAB",
    "TAMAULIPAS": "TAM", "TLAXCALA": "TLA", "VERACRUZ": "VER", "YUCATAN": "YUC", "ZACATECAS": "ZAC",
}
# Common short forms seen in hand-typed data
STATE_ALIASES = {"CALIF": "CA", "CAL": "CA", "CALI": "CA", "WASH": "WA", "PENN": "PA", "PENNA": "PA", "MASS": "MA",
                 "TENN": "TN", "MICH": "MI", "MINN": "MN", "MISS": "MS", "OKLA": "OK", "ORE": "OR", "ILL": "IL",
                 "FLA": "FL", "NEV": "NV", "ARIZ": "AZ", "COLO": "CO", "CONN": "CT", "WISC": "WI", "WIS": "WI",
                 "PEI": "PE", "CDMX": "CMX", "DF": "CMX", "B.C.": "BC"}
FEDERAL_RE = re.compile(r"^(USG|GOV)(?:[\s\-_:/]+([A-Z0-9]{1,%d}))?$" % CODE_MAX)


def _fold(value):
    """Upper case, accents removed, spaces collapsed."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().upper()


def federal_state(value):
    """USG / GOV with an optional code, from text such as "USG G42", "gov-dhs" or "GOV". None if it is not one."""
    m = FEDERAL_RE.match(_fold(value))
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)


def is_valid_state(value):
    """True for a known code (CA, BC, SON, XX, USG, GOV) or USG/GOV with a code (GOV-DHS)."""
    value = str(value or "")
    if value in STATES:
        return True
    m = re.fullmatch(r"(USG|GOV)-[A-Z0-9]{1,%d}" % CODE_MAX, value)
    return bool(m)


def normalize_state(value):
    """A stored state for loose input, or XX. "gov dhs" -> GOV-DHS, " ca " -> CA, "Atlantis" -> XX."""
    fed = federal_state(value)
    if fed:
        return fed
    letters = re.sub(r"[^A-Z]", "", _fold(value))
    return letters if letters in STATES else UNKNOWN_STATE


def split_plate_key(key):
    """("GOV-DHS", "12345") from "GOV-DHS-12345"; None when the key is not valid."""
    m = KEY_RE.match(str(key or ""))
    if not m or not is_valid_state(m.group(1)):
        return None
    return m.group(1), m.group(2)


def parse_state(value):
    """Return (code, how). code is a state/province code (CA, SON), USG/GOV with optional code, or XX; how says what matched."""
    raw = _fold(value).rstrip(".")
    if not raw:
        return UNKNOWN_STATE, "empty"
    fed = federal_state(raw)
    if fed:
        return fed, "federal"
    if raw in STATES and raw != UNKNOWN_STATE:
        return raw, "code"
    if raw in STATE_NAMES:
        return STATE_NAMES[raw], "name"
    if raw in STATE_ALIASES:
        return STATE_ALIASES[raw], "abbreviation"
    return UNKNOWN_STATE, "unrecognised"


def normalize_plate(value, max_len=20):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())[:max_len]


def plate_key(state, plate):
    p = normalize_plate(plate)
    return f"{state if is_valid_state(state) else UNKNOWN_STATE}-{p}" if p else ""
