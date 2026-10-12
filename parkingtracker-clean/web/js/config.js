export const APP_NAME = 'ParkingTracker';

// GitHub backend
export const REPO_OWNER = 'FranklyAbagnale';
export const REPO_NAME = 'ParkingTracker-Clean';
export const REPO_BRANCH = 'main';

// Local search + ranking
export const DEFAULT_RADIUS_METERS = 1000;
export const HIDDEN_AFTER_DAYS = 14; // only 'confirmed' vehicles age out of the nearby list
export const INDEX_MAX_AGE_HOURS = 24;

// Live nearby list on the new home screen
export const HOME_REFRESH_MINUTES = 5;   // re-read data/index.json this often while the home screen is open
export const HOME_MIN_MOVE_METERS = 25;  // redraw the list only after the device has moved this far

// Photos (stored as files under photos/, see ADR-008)
export const PHOTO_MAX_BYTES = 500 * 1024;
export const PHOTO_MAX_EDGE = 1600;
export const MAX_PHOTOS_PER_SIGHTING = 6;

// A "previous sighting" (entered after the fact) may be backdated this many days at most.
export const PREVIOUS_SIGHTING_MAX_DAYS = 30;

// A person may edit their own sightings for this long after saving them.
export const SIGHTING_EDIT_WINDOW_HOURS = 24;

// Location privacy (ADR-007). Decimal places kept when a location is stored:
// 4 ~= 11 m, 3 ~= 110 m. Use null for full precision (private repo + trusted group only).
// The repo is currently public, so locations are still rounded. Existing records keep their old precision.
export const COARSEN_DECIMALS = 4;

// Shown on every screen when non-empty. The repo is public while testing, so
// everything saved (photos included) is world-readable. Set to '' once private.
export const BANNER_TEXT = 'TEST MODE: everything you save is publicly visible. Use test data only.';

// Plate lookup (optional): year/make/model for a plate, through the proxy in api/. An empty LOOKUP_URL turns
// the feature off. When set, also add its origin to connect-src in index.html. See "07 Operations/Runbook - Plate Lookup.md".
export const LOOKUP_URL = '';
export const LOOKUP_STATES = ['CA']; // only these plate states are looked up (the proxy enforces its own list too)
export const LOOKUP_TIMEOUT_MS = 8000;

// Sync
export const MAX_RETRIES = 3;

// Vocabulary (kept in sync with schema/vehicle.schema.json)
// Public plate-lookup sites offered when a plate has no result. {state} and {plate} in a url are filled in.
// tracked: true gives the vehicle form a Verified / Not found / Wrong choice for that site; the year is
// entered only after a tracked site is marked Verified. Add a site here to try it; no other change is needed.
export const PLATE_SITES = [
  { id: 'faxvin', name: 'FaxVIN', url: 'https://www.faxvin.com/license-plate-lookup', tracked: true },
  { id: 'carfax', name: 'Carfax', url: 'https://www.carfax.com/', tracked: true },
  { id: 'epicvin', name: 'EpicVIN', url: 'https://epicvin.com/license-plate-lookup' },
  { id: 'findbyplate', name: 'FindByPlate', url: 'https://findbyplate.com/US/{state}/{plate}/', fallback: 'https://findbyplate.com/' }
];
export const SITE_CHECK_STATUSES = ['verified', 'not_found', 'wrong'];

export const FLAGS = ['unknown', 'suspected', 'confirmed', 'cleared', 'pigs'];
export const BODY_STYLES = ['sedan', 'suv', 'truck', 'van', 'coupe', 'hatchback', 'unknown'];
export const PLATE_MAX_LENGTH = 20; // keep in sync with schema/plate.schema.json
export const PLATE_TYPES = ['standard', 'dealer', 'temporary', 'vanity'];

// Plates are identified by state + plate. XX = state not known. Keep in sync with scripts/plate_states.py
// and tools/import.html (tests/fixtures/state_cases.json is checked against all three).
// A state is a US state or territory or Canadian province (2 letters), a Mexican state (3 letters, ISO 3166-2:MX),
// USG or GOV (federal / government plates, optionally with a code: USG-G42, GOV-DHS), or XX.
export const UNKNOWN_STATE = 'XX';
export const FEDERAL_STATES = ['USG', 'GOV'];
export const FEDERAL_CODE_MAX = 8; // longest optional code after USG- / GOV-
export const MX_STATES = [
  'AGU', 'BCN', 'BCS', 'CAM', 'CHP', 'CHH', 'CMX', 'COA', 'COL', 'DUR', 'GUA', 'GRO', 'HID', 'JAL', 'MEX', 'MIC',
  'MOR', 'NAY', 'NLE', 'OAX', 'PUE', 'QUE', 'ROO', 'SLP', 'SIN', 'SON', 'TAB', 'TAM', 'TLA', 'VER', 'YUC', 'ZAC'
];
// Names for the pickers (Mexican states are listed by name because their codes are not well known)
export const STATE_LABELS = {
  AGU: 'Aguascalientes', BCN: 'Baja California', BCS: 'Baja California Sur', CAM: 'Campeche', CHP: 'Chiapas', CHH: 'Chihuahua',
  CMX: 'Ciudad de México', COA: 'Coahuila', COL: 'Colima', DUR: 'Durango', GUA: 'Guanajuato', GRO: 'Guerrero', HID: 'Hidalgo',
  JAL: 'Jalisco', MEX: 'Estado de México', MIC: 'Michoacán', MOR: 'Morelos', NAY: 'Nayarit', NLE: 'Nuevo León', OAX: 'Oaxaca',
  PUE: 'Puebla', QUE: 'Querétaro', ROO: 'Quintana Roo', SLP: 'San Luis Potosí', SIN: 'Sinaloa', SON: 'Sonora', TAB: 'Tabasco',
  TAM: 'Tamaulipas', TLA: 'Tlaxcala', VER: 'Veracruz', YUC: 'Yucatán', ZAC: 'Zacatecas',
  USG: 'US Government (federal)', GOV: 'Government'
};
// Full names for the glossary page and anywhere a code needs explaining.
export const STATE_NAMES = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming', PR: 'Puerto Rico', GU: 'Guam', VI: 'Virgin Islands', AS: 'American Samoa', MP: 'Northern Mariana Islands', AB: 'Alberta', BC: 'British Columbia', MB: 'Manitoba', NB: 'New Brunswick', NL: 'Newfoundland and Labrador', NS: 'Nova Scotia', NT: 'Northwest Territories', NU: 'Nunavut', ON: 'Ontario', PE: 'Prince Edward Island', QC: 'Quebec', SK: 'Saskatchewan', YT: 'Yukon',
  ...STATE_LABELS,
  XX: 'State not known'
};
// How the glossary groups the states (codes are listed in STATES order).
export const STATE_GROUPS = [
  { title: 'US states', codes: ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'] },
  { title: 'District of Columbia and US territories', codes: ['DC', 'AS', 'GU', 'MP', 'PR', 'VI'] },
  { title: 'Canadian provinces and territories', codes: ['AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT'] },
  { title: 'Mexican states (ISO 3166-2:MX)', codes: MX_STATES },
  { title: 'Federal and government plates', codes: FEDERAL_STATES },
  { title: 'Not known', codes: [UNKNOWN_STATE] }
];
export const STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA',
  'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR',
  'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
  'AS', 'GU', 'MP', 'PR', 'VI',
  'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT',
  ...MX_STATES,
  ...FEDERAL_STATES,
  UNKNOWN_STATE
];
export const DEFAULT_STATE = 'CA'; // first-run default; the app remembers the last one used
