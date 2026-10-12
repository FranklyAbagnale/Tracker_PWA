/**
 * app.js
 * Application controller. Screens are rendered as HTML strings; every dynamic
 * value is escaped with esc(), and interaction uses data-action attributes with
 * one delegated listener (no inline handlers, so the CSP can forbid them).
 */

import { appState } from './state.js';
import {
  initDB, loadToken, saveToken, clearToken, loadObserver, saveObserver, clearObserver,
  enqueueWrite, cacheRecord, getCachedRecord
} from './storage.js';
import * as Photos from './photo-manager.js';
import {
  validateVehicleCapture, validateVehicleUpdate, hasAnyContent, createVehicleRecord, createPlateRecord, cleanObserver, OBSERVER_MAX, validPastDate, canEditSighting
} from './vehicle-manager.js';
import { searchByDescription } from './describe-search.js';
import { parseLatLng, searchAddress, osmViewUrl } from './place-finder.js';
import { normalizePlate, normalizeState, plateKey, formatPlateKey, splitPlateKey, baseState, stateCode, stateLabel } from './matching.js';
import { lookupEnabled, lookupVehicle, lookupText, lookupKeyFor, detailsUnknown, compareToLookup, buildPlateLookup } from './lookup.js';
import { lookupPlate, queueVehicleUpdate, queueSightingEdit, ANY_STATE, PARTIAL_MIN, MAX_LISTED, MAX_LISTED_MORE, LIVE_MIN, entriesWithPlate, plateMatchRows, rankPlateMatches } from './plate-manager.js';
import { rankLocalResults, formatLocalResult, formatTimeSince } from './local-manager.js';
import { loadIndex, refreshIndexIfStale } from './index-manager.js';
import { flushOutbox, retryFailed, getSyncStatus } from './sync-manager.js';
import * as GitHub from './github.js';
import { getDeviceLocation, coarsenLocation, isValidCoordinate, haversineDistanceKm, watchDeviceLocation, stopWatchingLocation, mapsDirectionsUrl, latestLocatedSighting } from './geo.js';
import * as Permissions from './permissions.js';
import { esc, options } from './ui.js';
import {
  DEFAULT_RADIUS_METERS, FLAGS, BODY_STYLES, PLATE_TYPES, REPO_OWNER, REPO_NAME,
  MAX_PHOTOS_PER_SIGHTING, COARSEN_DECIMALS, BANNER_TEXT, STATES, UNKNOWN_STATE, DEFAULT_STATE, FEDERAL_STATES, FEDERAL_CODE_MAX,
  HOME_REFRESH_MINUTES, HOME_MIN_MOVE_METERS, PLATE_SITES, SITE_CHECK_STATUSES, PREVIOUS_SIGHTING_MAX_DAYS, SIGHTING_EDIT_WINDOW_HOURS
} from './config.js';

let db = null;
let token = null;
let observer = null; // name of the person using this device, stamped on every record
let flash = null; // one-shot message shown on the next screen

// ---------- rendering helpers ----------

const container = () => document.getElementById('app-container');
const byId = (id) => document.getElementById(id);

// ---------- last screen (the arrow left of the pin) ----------
// A short history of screens that can be shown again (home, plate search, nearby search, a vehicle).
// Forms, the camera and setup are not kept: they hold unsaved input. The arrow is hidden while the history is empty.

const screenHistory = [];
let shownScreen = null;      // { id, restore } for the screen on display, or null if it can't be shown again
let goingBack = false;

function screenSnapshot(view) {
  if (view === 'home-screen') return { id: view, restore: showHomeScreen };
  if (view === 'plate-search') return { id: view, restore: showPlateSearch };
  if (view === 'local-search') return { id: view, restore: showLocalSearch };
  if (view === 'describe-search') return { id: view, restore: showDescribeSearch };
  if (view === 'vehicle-update' && appState.currentVehicle) {
    const v = appState.currentVehicle;
    return { id: `${view}:${v.vehicleKey}`, restore: () => { appState.currentVehicle = v; appState.draft = {}; showVehicleUpdateForm(); } };
  }
  return null;
}

function trackScreen(view) {
  const next = screenSnapshot(view);
  if (!goingBack && shownScreen && (!next || shownScreen.id !== next.id)) screenHistory.push(shownScreen);
  goingBack = false;
  if (next) {
    for (let i = screenHistory.length - 1; i >= 0; i--) if (screenHistory[i].id === next.id) screenHistory.splice(i, 1);
  }
  shownScreen = next;
}

function clearScreenHistory() {
  screenHistory.length = 0;
  shownScreen = null;
  goingBack = false;
}

const BACK_SVG = '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="M19 12H5m6-6-6 6 6 6"/></svg>';

function backButtonHtml() {
  if (!screenHistory.length) return '<span class="back-slot" aria-hidden="true"></span>';
  return `<button type="button" class="back-btn" data-action="go-back" aria-label="Back to the last screen" title="Back to the last screen">${BACK_SVG}</button>`;
}

function goBack() {
  const entry = screenHistory[screenHistory.length - 1];
  if (!entry) return;
  if (hasUnsavedEntry() && !confirm('Leave this screen? What you entered has not been saved.')) return;
  screenHistory.pop();
  Photos.stopCamera();
  Photos.clearCapturedPhotos();
  appState.draft = {};
  goingBack = true;
  entry.restore();
}

function render(html, view, layout = '') {
  stopHomeLive();
  trackScreen(view);
  appState.blobUrls.forEach((url) => URL.revokeObjectURL(url));
  appState.blobUrls = [];
  const banner = BANNER_TEXT ? `<div class="banner" role="note">${esc(BANNER_TEXT)}</div>` : '';
  document.body.dataset.layout = layout;
  const cameraBar = byId('camera-bar');
  if (cameraBar) cameraBar.hidden = view === 'token-setup';
  document.body.dataset.camera = view === 'token-setup' ? 'off' : 'on';
  container().innerHTML = `<div class="chrome">${banner}${topbarHtml(view)}</div><div class="screen ${view}${layout ? ` ${layout}` : ''}"><div id="notice" class="notice" role="status" hidden></div><div id="notice-actions"></div>${html}</div>`;
  appState.currentView = view;
  if (view !== 'token-setup') updateSyncStatus();
  if (flash) {
    setNotice(flash.text, flash.kind);
    if (flash.shareKey) byId('notice-actions').innerHTML = `<button type="button" class="secondary compact" data-action="share-vehicle" data-key="${esc(flash.shareKey)}">Share this record</button>`;
    flash = null;
  }
}

// Logo at the top of every screen; tapping it goes home (after a confirm if a
// form has been filled in). The menu (hamburger) holds everything that is not
// one of the four main actions.
// ---------- location on/off (the pin at the top left) ----------
// One switch for the whole app, remembered on this device. On: the Nearby list follows the device position.
// Off: nothing reads the position, and the only time the person is asked about it is when saving a record.

const LOCATION_KEY = 'pt-location';
function locationOn() {
  try { return localStorage.getItem(LOCATION_KEY) !== 'off'; } catch { return true; }
}
function storeLocation(on) {
  try { localStorage.setItem(LOCATION_KEY, on ? 'on' : 'off'); } catch { /* storage blocked: the choice lasts until reload */ }
}

// The last position the app used (read while location was on, or saved with a record) stays on this device only.
// With location off, the Nearby list is ranked from it instead of reading the device. Cleared at log out.
const LAST_POS_KEY = 'pt-last-pos';
function lastPosition() {
  try {
    const p = JSON.parse(localStorage.getItem(LAST_POS_KEY));
    return p && isValidCoordinate(p.lat, p.lng) ? p : null;
  } catch { return null; }
}
function rememberPosition(pos) {
  if (!pos || !isValidCoordinate(pos.lat, pos.lng)) return;
  const c = coarsenLocation(pos);
  const last = lastPosition();
  if (last && Date.now() - last.at < 30000 && haversineDistanceKm(last.lat, last.lng, c.lat, c.lng) * 1000 < HOME_MIN_MOVE_METERS) return; // no need to write on every fix
  try { localStorage.setItem(LAST_POS_KEY, JSON.stringify({ lat: c.lat, lng: c.lng, at: Date.now() })); } catch { /* storage blocked */ }
}
function forgetPosition() {
  try { localStorage.removeItem(LAST_POS_KEY); } catch { /* storage blocked */ }
}

const PIN_SVG = '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>';

function locationButtonHtml() {
  const on = locationOn();
  return `<button type="button" class="loc-btn ${on ? 'on' : 'off'}" data-action="toggle-location" aria-pressed="${on}"
    aria-label="Location ${on ? 'on' : 'off'}" title="Location ${on ? 'on: tap to turn off' : 'off: tap to turn on'}">${PIN_SVG}</button>`;
}

function refreshLocationButton() {
  const btn = document.querySelector('.loc-btn');
  if (!btn) return;
  const on = locationOn();
  btn.className = `loc-btn ${on ? 'on' : 'off'}`;
  btn.setAttribute('aria-pressed', String(on));
  btn.setAttribute('aria-label', `Location ${on ? 'on' : 'off'}`);
  btn.title = `Location ${on ? 'on: tap to turn off' : 'off: tap to turn on'}`;
}

async function geolocationBlocked() {
  try { return (await navigator.permissions.query({ name: 'geolocation' })).state === 'denied'; } catch { return false; }
}

const BLOCKED_TEXT = 'Location is blocked for this site in your browser settings. Allow it there, then tap the pin again.';

/** Turn location on (a tap, so the browser may ask now). Returns false and stays off if the browser has it blocked. */
async function enableLocation() {
  if (await geolocationBlocked()) {
    storeLocation(false);
    refreshLocationButton();
    setNotice(BLOCKED_TEXT, 'warn');
    return false;
  }
  storeLocation(true);
  refreshLocationButton();
  if (byId('home-list')) startHomeLive(); // the Nearby list starts following the device and updates by itself
  return true;
}

function disableLocation() {
  storeLocation(false);
  refreshLocationButton();
  if (byId('home-list')) startHomeLive(); // stops watching; the list uses the last position
}

async function toggleLocation() {
  if (locationOn()) disableLocation(); else await enableLocation();
}

/**
 * When saving with location off, ask once: this is the only place the person is asked.
 * Resolves 'on' (turn it on and add it), 'skip' (save without) or 'cancel' (back to the form).
 */
function askLocationAtSave() {
  return new Promise((resolve) => {
    const precision = COARSEN_DECIMALS === null ? 'full precision' : `rounded to about ${Math.round(111000 / 10 ** COARSEN_DECIMALS)} m`;
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="loc-modal-title">
      <h3 id="loc-modal-title">Location is off</h3>
      <p>Add this sighting's location? It is ${esc(precision)} and kept with this record only. Turning it on also shows nearby vehicles.</p>
      <button type="button" data-choice="on">Turn on and add location</button>
      <button type="button" class="secondary" data-choice="skip">Save without location</button>
      <button type="button" class="secondary" data-choice="cancel">Cancel</button></div>`;
    const done = (choice) => { document.removeEventListener('keydown', onKey, true); backdrop.remove(); resolve(choice); };
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); done('cancel'); } };
    backdrop.addEventListener('click', (e) => {
      const choice = e.target && e.target.dataset && e.target.dataset.choice;
      if (choice) done(choice);
      else if (e.target === backdrop) done('cancel');
    });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(backdrop);
    backdrop.querySelector('[data-choice="on"]').focus();
  });
}

function topbarHtml(view) {
  const img = '<img class="logo" src="icons/tracker-logo.png" alt="" width="79" height="52">';
  if (view === 'token-setup') return `<header class="topbar">${img}</header>`;
  return `<header class="topbar">
    <div class="top-left">${backButtonHtml()}${locationButtonHtml()}</div>
    <button type="button" class="logo-btn" data-action="logo-home" aria-label="Tracker home">${img}</button>
    <button type="button" class="menu-btn" data-action="toggle-menu" aria-label="Menu" aria-haspopup="true" aria-expanded="false" aria-controls="menu">
      <span aria-hidden="true">&#9776;</span><span id="menu-badge" class="badge" hidden></span>
    </button>
    <nav id="menu" class="menu" hidden>
      <div class="menu-user">Signed in as <strong>${esc(observer || '')}</strong></div>
      ${homeView() === 'B' ? '<button type="button" data-action="start-vehicle">Add vehicle (no photo)</button>' : ''}
      <button type="button" data-action="start-describe">Find by description</button>
      <button type="button" data-action="open-tutorial">Tutorial</button>
      <button type="button" data-action="open-glossary">Glossary</button>
      <button type="button" data-action="sync-now">Sync now</button>
      <button type="button" data-action="retry-failed" id="retry-btn" hidden>Retry failed</button>
      <button type="button" data-action="logout">Log out</button>
    </nav>
  </header>`;
}

function setMenu(open) {
  const menu = byId('menu');
  const btn = document.querySelector('.menu-btn');
  if (!menu || !btn) return;
  menu.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
}

function setNotice(text, kind = 'info') {
  const el = byId('notice');
  if (!el) return;
  el.textContent = text;
  el.className = `notice ${kind}`;
  el.hidden = !text;
}

async function withBusy(el, work) {
  if (el && el.disabled) return undefined;
  if (el) el.disabled = true;
  try {
    return await work();
  } finally {
    if (el) el.disabled = false;
  }
}

function flashTo(text, kind = 'info', shareKey = null) {
  flash = { text, kind, shareKey };
}

// ---------- form draft (survives the trip to the camera screen) ----------

const TRACKED_SITES = PLATE_SITES.filter((s) => s.tracked);
const FIELD_IDS = ['color', 'make', 'model', 'year', 'bodyStyle', 'distinguishing', 'plate', 'plateState', 'plateType', 'flag', 'notes', 'prevWhen', 'prevLoc', 'prevPlace', 'prevLat', 'prevLng',
  ...TRACKED_SITES.map((s) => `check-${s.id}`)];

// The last plate state used is remembered on this device (a convenience only).
const STATE_KEY = 'pt-last-state';
function lastState() {
  try { return localStorage.getItem(STATE_KEY) || DEFAULT_STATE; } catch { return DEFAULT_STATE; }
}
function rememberState(state) {
  try { if (state && state !== UNKNOWN_STATE) localStorage.setItem(STATE_KEY, state); } catch { /* optional */ }
}
function stateOptions(selected, withAny = false) {
  const base = selected === ANY_STATE ? selected : baseState(selected); // USG-G42 selects USG; the code has its own box
  return (withAny ? [`<option value="${ANY_STATE}"${base === ANY_STATE ? ' selected' : ''}>Any state</option>`] : []).concat(STATES.map((s) => `<option value="${esc(s)}"${s === base ? ' selected' : ''}>${esc(stateLabel(s))}</option>`)).join('');
}
// USG and GOV plates can carry a code (G42, DHS). It is typed in a small box next to the state and stored as part of the
// state (GOV-DHS); the box only shows while USG or GOV is chosen. Searches use the state alone, so they have no box.
function stateOf(stateId) {
  const select = byId(stateId);
  if (!select) return '';
  const code = byId(`${stateId}Code`);
  const clean = code ? code.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, FEDERAL_CODE_MAX) : '';
  return FEDERAL_STATES.includes(select.value) && clean ? `${select.value}-${clean}` : select.value;
}
function syncStateCode(select) {
  const code = byId(`${select.id}Code`);
  if (!code) return;
  code.hidden = !FEDERAL_STATES.includes(select.value);
  if (code.hidden) code.value = '';
}
function plateRow(inputId, placeholder, value, stateValue, stateId = 'plateState', withAny = false) {
  const federal = !withAny && FEDERAL_STATES.includes(baseState(stateValue));
  return `<div class="plate-row">
      <select id="${stateId}" aria-label="Plate state">${stateOptions(stateValue, withAny)}</select>
      ${withAny ? '' : `<input type="text" id="${stateId}Code" class="state-code" aria-label="Government plate code (optional)" placeholder="Code (G42)" maxlength="${FEDERAL_CODE_MAX}" value="${esc(federal ? stateCode(stateValue) : '')}" autocapitalize="characters" autocomplete="off"${federal ? '' : ' hidden'}>`}
      <input type="text" id="${inputId}" placeholder="${esc(placeholder)}" value="${esc(value)}" autocapitalize="characters" autocomplete="off">
    </div>`;
}
const keysText = (keys, empty) => (keys || []).map(formatPlateKey).join(', ') || empty;

function readForm() {
  const form = {};
  for (const id of FIELD_IDS) {
    const el = byId(id);
    if (el) form[id] = el.value;
  }
  if (form.plateState !== undefined) form.plateState = stateOf('plateState');
  const loc = byId('attachLocation');
  form.attachLocation = loc ? loc.checked : true;
  const prev = byId('prevOn');
  form.prevOn = prev ? prev.checked : false;
  if (document.querySelector('.rm-photo')) form.removePhotos = [...document.querySelectorAll('.rm-photo:checked')].map((e) => e.value);
  return form;
}

function saveDraft() {
  appState.draft = readForm();
}

const draftValue = (id, fallback = '') => (id in appState.draft ? appState.draft[id] : fallback);

// ---------- startup ----------

export async function initializeApp() {
  try {
    db = await initDB();
  } catch (err) {
    console.error('IndexedDB unavailable:', err);
    flashTo('Offline storage is unavailable in this browser, so saving requires a connection.', 'warn');
  }
  token = loadToken();
  observer = cleanObserver(loadObserver());
  registerServiceWorker();

  window.addEventListener('online', autoFlush);
  window.addEventListener('hashchange', () => { if (token && observer && LINK_KEY_RE.test(location.hash)) openPendingLink(); });

  if (!token || !observer) {
    const linked = LINK_KEY_RE.exec(location.hash);
    if (linked) { try { sessionStorage.setItem(PENDING_LINK, linked[1]); } catch { /* storage blocked */ } history.replaceState(null, '', location.pathname + location.search); }
    showTokenSetup();
  } else {
    showHomeScreen();
    autoFlush();
    refreshIndexIfStale(db, token);
    openPendingLink();
  }
}

function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('service-worker.js').catch((err) => {
      console.warn('Service worker registration failed:', err);
    });
  }
}

async function autoFlush() {
  if (!db || !token) return;
  const result = await flushOutbox(db, token);
  if (appState.currentView === 'home-screen') {
    updateSyncStatus();
    if (result.synced > 0) setNotice(`Synced ${result.synced} pending ${result.synced === 1 ? 'item' : 'items'}.`, 'ok');
  }
}

// ---------- token setup ----------

function showTokenSetup() {
  render(`
    <h1>Sign in</h1>
    <p>Enter your name, so your sightings are labelled, and the access token you were
    given for <code>${esc(REPO_OWNER)}/${esc(REPO_NAME)}</code>.</p>
    <input type="text" id="observer-input" placeholder="Your name" maxlength="${OBSERVER_MAX}"
           value="${esc(observer || '')}" autocomplete="name">
    <input type="password" id="token-input" placeholder="${token ? 'Token already saved (leave blank to keep)' : 'github_pat_...'}"
           autocomplete="off" autocapitalize="off">
    <button data-action="save-token">Sign in</button>
  `, 'token-setup');
}

async function handleTokenSubmit(btn) {
  const name = cleanObserver(byId('observer-input').value);
  const candidate = byId('token-input').value.trim() || token;
  if (!name || name.length < 2) {
    setNotice('Enter your name (at least 2 characters).', 'error');
    return;
  }
  if (!candidate) {
    setNotice('Paste the access token you were given.', 'error');
    return;
  }

  await withBusy(btn, async () => {
    try {
      await GitHub.checkAccess(candidate);
    } catch (err) {
      if (err instanceof GitHub.NetworkError) {
        flashTo('Could not verify the token (offline). It was saved; sync will confirm it.', 'warn');
      } else {
        setNotice(err.message, 'error');
        return;
      }
    }
    token = candidate;
    observer = name;
    saveToken(token);
    saveObserver(observer);
    showHomeScreen();
    autoFlush();
    refreshIndexIfStale(db, token);
    openPendingLink();
  });
}

async function logout() {
  const status = await getSyncStatus(db);
  const warning = status.total > 0
    ? `${status.total} unsynced item(s) are stored on this device and will upload after you sign in again. `
    : '';
  if (confirm(`${warning}Clear the token and your name, and log out?`)) {
    clearToken();
    clearObserver();
    forgetPosition();
    clearScreenHistory();
    token = null;
    observer = null;
    showTokenSetup();
  }
}

// ---------- home ----------

// The home screen puts plate entry on top and the live nearby list below (the photo button is the bar at the bottom
// of every screen). The original four-button grid ("classic", view A) is no longer offered in the menu; it stays in the
// code only so tests/e2e_smoke.py can keep driving it, and is switched on by the test-only key below. A phone that
// chose it earlier has its old setting removed, so it lands on the new home screen.
const CLASSIC_HOME_TEST_KEY = 'pt-classic-home';
let homeViewChoice = 'B';
try {
  localStorage.removeItem('pt-home-view');
  if (localStorage.getItem(CLASSIC_HOME_TEST_KEY) === '1') homeViewChoice = 'A';
} catch { /* optional */ }
const homeView = () => homeViewChoice;

// Tutorial and glossary are pages of their own, opened in a new tab so the screen the person is on is kept.
function openPage(name) {
  const win = window.open(name, '_blank'); // not 'noopener': that makes open() return null, which would look like a blocked popup
  if (win) win.opener = null; else window.location.href = name;
}

function showHomeScreen() {
  if (homeView() === 'B') showHomeScreenB();
  else showHomeScreenA();
}

function showHomeScreenA() {
  render(`
    <div id="permissions-card" class="permissions" hidden></div>
    <div class="main-grid">
      <button data-action="start-photo"><span class="big" aria-hidden="true">📷</span>Photo</button>
      <button data-action="start-plate"><span class="big" aria-hidden="true">🔍</span>Plate</button>
      <button data-action="start-vehicle"><span class="big" aria-hidden="true">🚗</span>Vehicle</button>
      <button data-action="start-local"><span class="big" aria-hidden="true">📍</span>Local</button>
    </div>
    <div id="sync-status"></div>
  `, 'home-screen');
  showPermissionsCard();
}

function showHomeScreenB() {
  // No permissions card here: the live list asks for location itself (the browser's own prompt), and the camera
  // button (the bar at the bottom of every screen) opens the phone's camera app, which handles its own permission.
  render(`
    <div class="home-b-grid">
      <section class="hb-plate" aria-label="Plate lookup">
        ${plateRow('plate-input', 'Enter plate', '', ANY_STATE, 'state-input', true)}
        <div class="hb-actions">
          <button data-action="search-plate">Search</button>
          <button data-action="clear-plate-search" id="clear-plate" class="secondary" hidden>Clear</button>
        </div>
      </section>
      <section class="hb-list" aria-label="Nearby vehicles">
        <div id="plate-results" hidden></div>
        <div id="home-list"></div>
      </section>
    </div>
    <div id="sync-status"></div>
  `, 'home-screen', 'home-b');
  startHomeLive();
}

// ---------- live nearby list (home screen B) ----------
// Follows the device position and re-reads data/index.json every HOME_REFRESH_MINUTES while the screen is open.
// The position is used in memory only and is never saved.

const live = { watchId: null, timer: null, pos: null, drawnPos: null, entries: [], source: '', loadError: null, locationError: null, expanded: false, showing: 'nearby', tab: 'nearby', tabChosen: false };

function stopHomeLive() {
  stopWatchingLocation(live.watchId);
  live.watchId = null;
  if (live.timer) clearInterval(live.timer);
  live.timer = null;
}

function startHomeLive() {
  stopHomeLive();
  live.savedAt = null;
  Object.assign(live, { drawnPos: null, expanded: false, showing: byId('plate-results') && !byId('plate-results').hidden ? 'plate' : 'nearby', locationError: null });
  if (!locationOn()) { // off: read no position and do not ask; rank by the last position used, if there is one
    const saved = lastPosition();
    live.pos = saved ? { lat: saved.lat, lng: saved.lng } : null;
    live.savedAt = saved ? saved.at : null;
    live.locationError = 'off';
    drawHomeList();
    loadHomeEntries(false);
    live.timer = setInterval(() => { if (document.visibilityState === 'visible') loadHomeEntries(true); }, HOME_REFRESH_MINUTES * 60 * 1000);
    return;
  }
  drawHomeList();
  loadHomeEntries(false);
  live.watchId = watchDeviceLocation(onHomePosition, onHomeLocationError);
  live.timer = setInterval(() => { if (document.visibilityState === 'visible') loadHomeEntries(true); }, HOME_REFRESH_MINUTES * 60 * 1000);
}

async function loadHomeEntries(force) {
  try {
    const result = await loadIndex(db, token, { force });
    live.entries = result.entries;
    live.source = result.source;
    live.loadError = null;
  } catch (err) {
    live.loadError = err.message || 'Could not load the vehicle list';
  }
  if (live.showing === 'nearby') drawHomeList();
}

function onHomePosition(pos) {
  live.locationError = null;
  live.pos = pos;
  rememberPosition(pos);
  if (live.showing !== 'nearby') return;
  const movedM = live.drawnPos ? haversineDistanceKm(live.drawnPos.lat, live.drawnPos.lng, pos.lat, pos.lng) * 1000 : Infinity;
  if (movedM >= HOME_MIN_MOVE_METERS) drawHomeList();
}

function onHomeLocationError(err) {
  if (err && err.code === 1) { // blocked in the browser: the pin goes grey so it shows what is really happening
    storeLocation(false);
    refreshLocationButton();
  }
  if (live.pos) return; // keep showing the last known position
  live.locationError = err && err.code === 1 ? 'denied' : 'unavailable';
  if (live.showing === 'nearby') drawHomeList();
}

function homeTab() {
  if (live.tabChosen) return live.tab;
  return !live.pos && live.locationError ? 'recent' : 'nearby'; // nothing to rank by: show what is newest instead
}

function tabsHead(tab, nearbyCount, status) {
  const t = (id, label) => `<button type="button" class="tab${tab === id ? ' on' : ''}" data-action="home-tab" data-tab="${id}" aria-pressed="${tab === id}">${label}</button>`;
  return `<div class="hb-list-head"><span class="tabs">${t('nearby', nearbyCount === null ? 'Nearby' : `Nearby (${nearbyCount})`)}${t('recent', 'Recent')}</span><span class="small">${esc(status)}</span></div>`;
}

function drawHomeList() {
  const el = byId('home-list');
  if (!el) return;
  const box = el.parentElement;
  const scroll = box.scrollTop;
  const tab = homeTab();
  const cap = capFor(live.expanded);
  const loadStatus = live.loadError ? `Could not refresh: ${live.loadError}`
    : live.source === 'stale-cache' ? 'offline, saved list'
    : live.source === 'offline-empty' ? 'offline, no saved list yet' : '';

  if (tab === 'recent') {
    // newest sighting first; needs no position, so it works for someone at a computer
    const recent = [...live.entries].filter((e) => e.lastSeen).sort((a, b) => String(b.lastSeen).localeCompare(String(a.lastSeen)));
    const row = (e) => `<div class="vrow" role="button" tabindex="0" data-action="view-vehicle" data-key="${esc(e.vehicleKey)}">
      <span class="dot dot-${esc(e.flag || 'unknown')}" role="img" aria-label="${esc(e.flag || 'unknown')}"></span>
      <span class="vrow-main"><strong>${esc(e.displayName || 'Vehicle')}</strong><span class="vrow-sub">${esc([e.flag, keysText(e.plateAliases, '')].filter(Boolean).join(' · '))}</span></span>
      <span class="vrow-meta">${esc(formatTimeSince(new Date(e.lastSeen)))}</span>
    </div>`;
    el.innerHTML = tabsHead('recent', live.pos ? rankLocalResults(live.entries, live.pos, DEFAULT_RADIUS_METERS).length : null, loadStatus || 'newest first')
      + `<div class="tab-tools"><button type="button" class="secondary compact" data-action="refresh-home">↻ Refresh</button></div>`
      + (recent.length ? recent.slice(0, cap).map(row).join('') : '<p class="small" style="padding-top:10px">No vehicles yet.</p>')
      + moreButton(recent.length, live.expanded, 'view-more-home')
      + capNote(recent.length, live.expanded, 'These are the newest.');
    box.scrollTop = scroll;
    return;
  }

  if (!live.pos) {
    const msg = live.locationError === 'off'
      ? 'Location is off and no earlier position is saved on this device, so nearby vehicles are not shown. Plate search still works. Recent shows the newest records.'
      : live.locationError === 'denied'
      ? 'Location is blocked, so nearby vehicles cannot be listed. Allow location for this site in your browser settings, or use Nearby (manual location) from the menu.'
      : live.locationError === 'unavailable'
        ? 'Could not get your location. Use Nearby (manual location) from the menu.'
        : 'Finding your location…';
    el.innerHTML = tabsHead('nearby', null, '') + `<p class="small" style="padding-top:10px">${esc(msg)}</p>`;
    return;
  }
  live.drawnPos = live.pos;
  const ranked = rankLocalResults(live.entries, live.pos, DEFAULT_RADIUS_METERS);
  const status = live.savedAt ? `off · last position ${formatTimeSince(new Date(live.savedAt))}` : loadStatus;
  const row = (item) => {
    const f = formatLocalResult(item, item.distance);
    const sub = [f.flag, keysText(f.plateAliases, '')].filter(Boolean).join(' · ');
    return `<div class="vrow" role="button" tabindex="0" data-action="view-vehicle" data-key="${esc(f.vehicleKey)}">
      <span class="dot dot-${esc(f.flag)}" role="img" aria-label="${esc(f.flag)}"></span>
      <span class="vrow-main"><strong>${esc(f.displayName)}</strong><span class="vrow-sub">${esc(sub)}</span></span>
      <span class="vrow-meta">${esc(f.distance)}<br>${esc(f.timeSince)}</span>
    </div>`;
  };
  el.innerHTML = tabsHead('nearby', ranked.length, status || `within ${DEFAULT_RADIUS_METERS / 1000} km`)
    + (ranked.length ? ranked.slice(0, cap).map(row).join('') : '<p class="small" style="padding-top:10px">No vehicles found nearby.</p>')
    + moreButton(ranked.length, live.expanded, 'view-more-home')
    + capNote(ranked.length, live.expanded, 'These are the nearest.');
  box.scrollTop = scroll;
}

function clearPlateSearch() {
  const input = byId('plate-input');
  if (input) input.value = '';
  const results = byId('plate-results');
  if (results) { results.hidden = true; results.innerHTML = ''; }
  const list = byId('home-list');
  if (list) list.hidden = false;
  const clear = byId('clear-plate');
  if (clear) clear.hidden = true;
  appState.plateSearch = null;
  live.showing = 'nearby';
  drawHomeList();
}

/**
 * The phone's camera app took a picture. The camera bar is on every screen, so whatever the person is doing is
 * paused, not abandoned: forms keep what was typed and gain the photo; anywhere else the photo starts a new vehicle.
 */
async function handleCameraPhoto(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  const view = appState.currentView;
  const inForm = view === 'vehicle-form' || view === 'vehicle-update' || view === 'sighting-edit';
  if (inForm) saveDraft(); // keep what is typed; the screen is redrawn below
  if (!inForm && view !== 'photo-capture') Photos.clearCapturedPhotos(); // a photo from a browsing screen starts fresh
  try {
    await Photos.captureFromFile(file);
  } catch (err) {
    setNotice(`Could not read that photo: ${err.message}`, 'error');
    return;
  }
  if (!Photos.acceptPendingCapture()) {
    Photos.discardPendingCapture();
    setNotice(`Up to ${MAX_PHOTOS_PER_SIGHTING} photos per sighting.`, 'warn');
    return;
  }

  if (view === 'photo-capture') { refreshPhotoUI(); return; }
  if (view === 'vehicle-form') { showVehicleForm(); return; }
  if (view === 'vehicle-update' && appState.currentVehicle) { showVehicleUpdateForm(); return; }
  if (view === 'sighting-edit' && appState.currentVehicle) { showSightingEdit(); return; }

  // Home, plate search, nearby search: carry a typed plate (and state) into a new vehicle.
  const plate = normalizePlate(byId('plate-input') ? byId('plate-input').value : '');
  const picked = byId('state-input') ? byId('state-input').value : ANY_STATE;
  appState.draft = plate ? { plate, plateState: picked === ANY_STATE ? lastState() : normalizeState(picked) } : {};
  appState.returnTo = 'vehicle-form';
  showVehicleForm();
}

// ---------- list limits: MAX_LISTED at first, then up to MAX_LISTED_MORE more ----------

const capFor = (expanded) => MAX_LISTED + (expanded ? MAX_LISTED_MORE : 0);

function moreButton(total, expanded, action) {
  return !expanded && total > MAX_LISTED
    ? `<button type="button" class="secondary compact" data-action="${action}">View ${Math.min(MAX_LISTED_MORE, total - MAX_LISTED)} more</button>`
    : '';
}

const capNote = (total, expanded, hint) => (expanded && total > capFor(true)
  ? `<p class="small">Showing ${capFor(true)} of ${total}. ${esc(hint)}</p>` : '');

// ---------- permissions ("while using the app") ----------

async function showPermissionsCard(afterRequest = null) {
  const card = byId('permissions-card');
  if (!card) return;
  const status = afterRequest || await Permissions.getPermissionStatus();
  if (!locationOn()) status.location = 'granted'; // switched off by the person: not asked, not reported as a problem
  if (!byId('permissions-card')) return; // navigated away while waiting
  const denied = [];
  if (status.location === 'denied') denied.push('location');
  if (status.camera === 'denied') denied.push('camera');
  if (denied.length) {
    card.innerHTML = `<p><strong>${esc(denied.join(' and '))} blocked.</strong> The app still works, but ${
      denied.includes('location') ? 'new sightings will have no location and Local search needs coordinates typed in' : 'you will need "Choose or take a photo" instead of the live camera'
    }. To allow it, open your phone or browser settings for this site and switch ${esc(denied.join(' and '))} to Allow.</p>
      <button type="button" data-action="dismiss-permissions" class="secondary">OK</button>`;
    card.hidden = !afterRequest && !Permissions.shouldAsk(status);
    return;
  }
  if (!Permissions.shouldAsk(status)) { card.hidden = true; return; }
  card.innerHTML = `<p><strong>Allow location and camera while you use the app.</strong>
    Location is read only when you save a sighting or search nearby, and never in the background.</p>
    <button type="button" data-action="request-permissions">Allow</button>
    <button type="button" data-action="dismiss-permissions" class="secondary">Not now</button>`;
  card.hidden = false;
}

async function requestPermissions(btn) {
  await withBusy(btn, async () => {
    const result = await Permissions.requestPermissions({ location: locationOn() });
    await showPermissionsCard(result);
  });
}

function dismissPermissions() {
  Permissions.dismissForSession();
  const card = byId('permissions-card');
  if (card) card.hidden = true;
}

async function updateSyncStatus() {
  if (!db) return;
  const s = await getSyncStatus(db);
  const badge = byId('menu-badge');
  if (badge) {
    badge.hidden = s.total === 0;
    badge.textContent = s.total ? String(s.total) : '';
    badge.className = `badge${s.failed + s.conflict ? ' bad' : ''}`;
  }
  const el = byId('sync-status');
  const retry = byId('retry-btn');
  if (retry) {
    retry.hidden = s.failed + s.conflict === 0;
    retry.textContent = `Retry failed (${s.failed + s.conflict})`;
  }
  if (!el) return;
  if (s.total === 0) {
    el.innerHTML = '<p class="ok">All synced</p>';
    return;
  }
  const parts = [];
  if (s.pending) parts.push(`${s.pending} pending`);
  if (s.failed) parts.push(`${s.failed} failed`);
  if (s.conflict) parts.push(`${s.conflict} in conflict`);
  const detail = s.items.filter((i) => i.lastError)
    .map((i) => `<div class="small">${esc(i.key)}: ${esc(i.lastError)}</div>`).join('');
  el.innerHTML = `<p class="warn">Waiting to upload: ${esc(parts.join(', '))}</p>${detail}`;
}

function describeFlush(result) {
  if (result.stopped === 'offline') return { text: 'Offline. Changes are saved on this device and will upload when you reconnect.', kind: 'warn' };
  if (result.stopped === 'auth') return { text: `${result.message || 'Token problem'}. Log out and enter a new token.`, kind: 'error' };
  if (result.conflicts) return { text: `${result.conflicts} item(s) hit an edit conflict. Tap Retry failed.`, kind: 'warn' };
  if (result.failed) return { text: `${result.failed} item(s) failed to upload. Tap Retry failed.`, kind: 'error' };
  if (result.synced) return { text: `Synced ${result.synced} item(s).`, kind: 'ok' };
  return { text: 'Nothing to sync.', kind: 'info' };
}

async function syncNow(btn) {
  await withBusy(btn, async () => {
    const note = describeFlush(await flushOutbox(db, token));
    setNotice(note.text, note.kind);
    updateSyncStatus();
  });
}

async function retryFailedItems(btn) {
  await withBusy(btn, async () => {
    const note = describeFlush(await retryFailed(db, token));
    setNotice(note.text, note.kind);
    updateSyncStatus();
  });
}

// ---------- photo capture ----------

async function startPhotoCapture(returnTo = 'vehicle-form') {
  appState.returnTo = returnTo;
  render(`
    <h2>Photos</h2>
    <video id="camera-video" playsinline muted autoplay></video>
    <div id="photo-preview"></div>
    <button data-action="capture-photo" id="btn-capture">📸 Capture</button>
    <button data-action="accept-photo" id="btn-accept" disabled>✓ Accept</button>
    <button data-action="retake-photo" id="btn-retake" class="secondary" disabled>↻ Retake</button>
    <label class="file-button secondary">Choose or take a photo
      <input type="file" id="file-input" accept="image/*" hidden>
    </label>
    <div id="photo-list" class="thumbs"></div>
    <button data-action="finish-photos" id="btn-done">Done</button>
    <button data-action="go-home" class="secondary">Cancel</button>
  `, 'photo-capture');
  refreshPhotoUI();

  try {
    await Photos.initializeCamera(byId('camera-video'));
  } catch (err) {
    console.warn('Camera unavailable:', err);
    byId('camera-video').hidden = true;
    byId('btn-capture').disabled = true;
    setNotice('Camera unavailable. Use "Choose or take a photo" instead.', 'warn');
  }
}

function refreshPhotoUI() {
  const pending = Photos.getPendingCapture();
  const photos = Photos.getCapturedPhotos();

  const preview = byId('photo-preview');
  preview.textContent = '';
  if (pending) {
    const img = document.createElement('img');
    img.src = pending;
    img.alt = 'Captured photo';
    preview.appendChild(img);
  }
  byId('btn-accept').disabled = !pending || photos.length >= MAX_PHOTOS_PER_SIGHTING;
  byId('btn-retake').disabled = !pending;

  const list = byId('photo-list');
  list.textContent = '';
  photos.forEach((src, i) => {
    const cell = document.createElement('div');
    cell.className = 'thumb';
    const img = document.createElement('img');
    img.src = src;
    img.alt = `Photo ${i + 1}`;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.dataset.action = 'remove-photo';
    remove.dataset.index = String(i);
    remove.setAttribute('aria-label', `Remove photo ${i + 1}`);
    remove.textContent = '✕';
    cell.append(img, remove);
    list.appendChild(cell);
  });
  byId('btn-done').textContent = photos.length ? `Done (${photos.length} photo${photos.length > 1 ? 's' : ''})` : 'Done';
}

function capturePhoto() {
  Photos.captureFrame(byId('camera-video'));
  refreshPhotoUI();
}

function acceptPhoto() {
  if (!Photos.acceptPendingCapture()) {
    setNotice(`Up to ${MAX_PHOTOS_PER_SIGHTING} photos per sighting.`, 'warn');
  }
  refreshPhotoUI();
}

function retakePhoto() {
  Photos.discardPendingCapture();
  refreshPhotoUI();
}

async function handleFileChosen(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  try {
    await Photos.captureFromFile(file);
    refreshPhotoUI();
  } catch (err) {
    setNotice(`Could not read that image: ${err.message}`, 'error');
  }
}

function finishPhotoCapture() {
  Photos.stopCamera();
  Photos.discardPendingCapture();
  if (appState.returnTo === 'sighting-edit' && appState.currentVehicle && appState.editingSightingId) {
    showSightingEdit();
  } else if (appState.returnTo === 'vehicle-update' && appState.currentVehicle) {
    showVehicleUpdateForm();
  } else {
    showVehicleForm();
  }
}

function addPhotosFromForm() {
  saveDraft();
  startPhotoCapture(appState.currentView);
}

function photoSummary() {
  const n = Photos.getCapturedPhotos().length;
  return n ? `📷 ${n} photo${n > 1 ? 's' : ''} ready` : 'No photos yet';
}

// ---------- vehicle form (new) ----------

function pad2(n) { return String(n).padStart(2, '0'); }
function localInputValue(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** "This happened earlier": lets the person set when and where a sighting really took place. */
function previousSightingBlock() {
  const on = draftValue('prevOn', false);
  const now = new Date();
  const min = localInputValue(new Date(now.getTime() - PREVIOUS_SIGHTING_MAX_DAYS * 86400000));
  const lat = draftValue('prevLat');
  const lng = draftValue('prevLng');
  const mode = draftValue('prevLoc', 'none');
  return `<label class="check"><input type="checkbox" id="prevOn"${on ? ' checked' : ''}> This happened earlier (previous sighting)</label>
    <div id="prev-fields"${on ? '' : ' hidden'}>
      <label class="small" for="prevWhen">When did you see it?</label>
      <input type="datetime-local" id="prevWhen" min="${min}" max="${localInputValue(now)}" value="${esc(draftValue('prevWhen', localInputValue(now)))}">
      <label class="small" for="prevLoc">Where was it?</label>
      <select id="prevLoc">
        <option value="none"${mode === 'none' ? ' selected' : ''}>No location</option>
        <option value="here"${mode === 'here' ? ' selected' : ''}>Where I am now</option>
        <option value="picked"${mode === 'picked' ? ' selected' : ''}>A place I choose</option>
      </select>
      <div id="prev-pick"${mode === 'picked' ? '' : ' hidden'}>
        <input type="text" id="prevPlace" placeholder="Address, &quot;lat, lng&quot; or a map link" value="${esc(draftValue('prevPlace'))}" autocomplete="off">
        <button type="button" class="secondary" data-action="find-place">Find place</button>
        <input type="hidden" id="prevLat" value="${esc(lat)}"><input type="hidden" id="prevLng" value="${esc(lng)}">
        <div id="prev-result" class="small" aria-live="polite">${lat !== '' && lng !== '' ? placeResultHtml(Number(lat), Number(lng), '') : ''}</div>
      </div>
    </div>`;
}

function placeResultHtml(lat, lng, label) {
  return `Pinned ${esc(`${lat.toFixed(5)}, ${lng.toFixed(5)}`)}${label ? ` (${esc(label)})` : ''}. <a href="${esc(osmViewUrl(lat, lng))}" target="_blank" rel="noopener">Check on map</a>`;
}

function syncPreviousUi() {
  const on = byId('prevOn');
  const fields = byId('prev-fields');
  if (on && fields) {
    fields.hidden = !on.checked;
    const attach = byId('attachLocation');
    if (attach && attach.closest('label')) attach.closest('label').hidden = on.checked;
  }
  const pick = byId('prev-pick');
  if (pick && byId('prevLoc')) pick.hidden = byId('prevLoc').value !== 'picked';
}

async function findPlace() {
  const text = byId('prevPlace').value;
  const out = byId('prev-result');
  out.textContent = 'Looking…';
  let hit = parseLatLng(text);
  if (!hit) hit = await searchAddress(text);
  if (!hit) {
    byId('prevLat').value = '';
    byId('prevLng').value = '';
    out.textContent = 'Not found. Try a fuller address, or paste "lat, lng" or a map link.';
    return;
  }
  const c = coarsenLocation({ lat: hit.lat, lng: hit.lng });
  byId('prevLat').value = c.lat;
  byId('prevLng').value = c.lng;
  out.innerHTML = placeResultHtml(c.lat, c.lng, hit.label || '');
  saveDraft();
}

/**
 * Where and when to record. Normal saves use the live location; a previous sighting uses the chosen time and place.
 * Returns { cancelled } | { location, when }.
 */
async function resolveWhenAndWhere(form) {
  if (!form.prevOn) return { ...(await captureLocation(form.attachLocation)), when: null };
  const when = validPastDate(form.prevWhen, new Date());
  if (!when) {
    setNotice(`Pick a time that is in the past, within the last ${PREVIOUS_SIGHTING_MAX_DAYS} days.`, 'warn');
    return { cancelled: true };
  }
  if (form.prevLoc === 'here') return { ...(await captureLocation(true)), when };
  if (form.prevLoc === 'picked') {
    const lat = Number(form.prevLat);
    const lng = Number(form.prevLng);
    if (form.prevLat === '' || form.prevLng === '' || !isValidCoordinate(lat, lng)) {
      setNotice('Tap "Find place" to pin the location, or choose another location option.', 'warn');
      return { cancelled: true };
    }
    return { location: { lat, lng, manual: true }, when };
  }
  return { location: null, when };
}

function locationCheckbox() {
  const precision = COARSEN_DECIMALS === null ? 'full precision' : `rounded to about ${Math.round(111000 / 10 ** COARSEN_DECIMALS)} m`;
  const checked = draftValue('attachLocation', true) ? ' checked' : '';
  return `<label class="check"><input type="checkbox" id="attachLocation"${checked}>
    Attach my location (${esc(precision)})</label>`;
}

const SITE_STATUS_LABELS = { verified: 'Verified', not_found: 'Not found', wrong: 'Wrong' };

/** Which lookup sites were tried, and the year once one of them is Verified. */
function siteChecksBlock(draft, vehicle) {
  const saved = vehicle?.siteChecks || {};
  const value = (site) => (draft[`check-${site.id}`] !== undefined ? draft[`check-${site.id}`] : (saved[site.id]?.status || ''));
  const yearValue = draft.year !== undefined ? draft.year : (vehicle?.year ? String(vehicle.year) : '');
  const verified = TRACKED_SITES.some((s) => value(s) === 'verified') || Boolean(vehicle?.year);
  return `<div id="site-checks">
    <div class="small">Ran the plate on a lookup site? Mark what you found.</div>
    ${TRACKED_SITES.map((s) => `<label class="check-row"><span>${esc(s.name)}</span>
      <select id="check-${esc(s.id)}"><option value="">Not checked</option>${options(SITE_CHECK_STATUSES, value(s), (v) => SITE_STATUS_LABELS[v])}</select></label>`).join('')}
    <input type="text" id="year" placeholder="Year (e.g., 2019)" value="${esc(yearValue)}" inputmode="numeric" maxlength="4" autocomplete="off"${verified ? '' : ' hidden'}>
  </div>`;
}

function toggleYearField() {
  const year = byId('year');
  if (!year) return;
  const verified = TRACKED_SITES.some((s) => byId(`check-${s.id}`)?.value === 'verified');
  year.hidden = !verified && !year.value;
}

function showVehicleForm() {
  const d = appState.draft;
  render(`
    <h2>Vehicle details</h2>
    <input type="text" id="color" placeholder="Color (optional, e.g., grey)" value="${esc(d.color)}" autocomplete="off">
    <input type="text" id="make" placeholder="Make (optional, e.g., Nissan)" value="${esc(d.make)}" autocomplete="off">
    <input type="text" id="model" placeholder="Model (optional)" value="${esc(d.model)}" autocomplete="off">
    ${siteChecksBlock(d, null)}
    <select id="bodyStyle"><option value="">Body style (optional)</option>${options(BODY_STYLES, d.bodyStyle)}</select>
    <input type="text" id="distinguishing" placeholder="Distinguishing features (optional, comma-separated)" value="${esc(d.distinguishing)}" autocomplete="off">
    ${plateRow('plate', 'License plate (optional)', d.plate, d.plateState || lastState())}
    <div id="form-lookup" class="small" aria-live="polite"></div>
    <select id="plateType">${options(PLATE_TYPES, d.plateType || 'standard')}</select>
    <select id="flag">${options(FLAGS, d.flag || 'unknown')}</select>
    <textarea id="notes" placeholder="Notes">${esc(d.notes)}</textarea>
    ${locationCheckbox()}
    ${previousSightingBlock()}
    <div class="small">${esc(photoSummary())}</div>
    <button data-action="add-photos" class="secondary">📷 Add photos</button>
    <button data-action="save-vehicle">Save vehicle</button>
    <button data-action="go-home" class="secondary">Cancel</button>
  `, 'vehicle-form');
}

/**
 * The location to save with a record. With location switched off and "Attach my location" ticked, this asks once.
 * Returns { cancelled: true } when the person goes back to the form.
 */
async function captureLocation(attach) {
  if (!attach) return { location: null };
  if (!locationOn()) {
    const choice = await askLocationAtSave();
    if (choice === 'cancel') return { cancelled: true };
    if (choice === 'skip') return { location: null };
    if (!(await enableLocation())) return { location: null }; // blocked in the browser: saved without, and the notice says why
  }
  const location = coarsenLocation(await getDeviceLocation());
  if (location) rememberPosition(location);
  return { location };
}

async function afterSave(prefix, vehicleKey = null) {
  const result = await flushOutbox(db, token);
  let note;
  if (result.stopped === 'offline') note = { text: `${prefix} saved on this device. It will upload when you're back online.`, kind: 'warn' };
  else if (result.stopped === 'auth') note = { text: `${prefix} saved on this device, but ${result.message || 'the token was rejected'}.`, kind: 'error' };
  else if (result.conflicts || result.failed) note = { text: `${prefix} saved on this device, but upload needs a retry.`, kind: 'warn' };
  else note = { text: `${prefix} saved.`, kind: 'ok' };
  Photos.clearCapturedPhotos();
  appState.draft = {};
  appState.currentVehicle = null;
  flashTo(note.text, note.kind, vehicleKey);
  showHomeScreen();
}

// ---------- editing your own sighting ----------

function editFormFields(v, s) {
  const happened = new Date(s.timestamp);
  const mode = draftValue('prevLoc', 'keep');
  const removed = new Set(draftValue('removePhotos', []));
  const photoRows = (s.photos || []).map((p) => `<label class="check"><input type="checkbox" class="rm-photo" value="${esc(p)}"${removed.has(p) ? ' checked' : ''}> Remove photo ${esc(p.split('/').pop())}</label>`).join('');
  const min = localInputValue(new Date(Date.now() - PREVIOUS_SIGHTING_MAX_DAYS * 86400000));
  const lat = draftValue('prevLat');
  const lng = draftValue('prevLng');
  return `
    <h2>Edit sighting</h2>
    <p class="small">${esc(v.displayName)}. You can edit your own sightings for ${SIGHTING_EDIT_WINDOW_HOURS} hours after saving them.</p>
    <input type="text" id="color" placeholder="Color" value="${esc(draftValue('color', v.color))}">
    <input type="text" id="make" placeholder="Make" value="${esc(draftValue('make', v.make))}">
    <input type="text" id="model" placeholder="Model" value="${esc(draftValue('model', v.model || ''))}">
    <select id="bodyStyle">${options(BODY_STYLES, draftValue('bodyStyle', v.bodyStyle))}</select>
    <input type="text" id="distinguishing" placeholder="Features (comma-separated)" value="${esc(draftValue('distinguishing', (v.distinguishing || []).join(', ')))}">
    <select id="flag">${options(FLAGS, draftValue('flag', s.flag))}</select>
    <textarea id="notes" placeholder="Sighting notes">${esc(draftValue('notes', s.notes || ''))}</textarea>
    <label class="small" for="prevWhen">When it was seen</label>
    <input type="datetime-local" id="prevWhen" min="${min}" max="${localInputValue(new Date())}" value="${esc(draftValue('prevWhen', localInputValue(happened)))}">
    <label class="small" for="prevLoc">Location</label>
    <select id="prevLoc">
      <option value="keep"${mode === 'keep' ? ' selected' : ''}>Keep as saved${s.location ? '' : ' (none)'}</option>
      <option value="none"${mode === 'none' ? ' selected' : ''}>Remove the location</option>
      <option value="here"${mode === 'here' ? ' selected' : ''}>Where I am now</option>
      <option value="picked"${mode === 'picked' ? ' selected' : ''}>A place I choose</option>
    </select>
    <div id="prev-pick"${mode === 'picked' ? '' : ' hidden'}>
      <input type="text" id="prevPlace" placeholder="Address, &quot;lat, lng&quot; or a map link" value="${esc(draftValue('prevPlace'))}" autocomplete="off">
      <button type="button" class="secondary" data-action="find-place">Find place</button>
      <input type="hidden" id="prevLat" value="${esc(lat)}"><input type="hidden" id="prevLng" value="${esc(lng)}">
      <div id="prev-result" class="small" aria-live="polite">${lat !== '' && lng !== '' ? placeResultHtml(Number(lat), Number(lng), '') : ''}</div>
    </div>
    ${photoRows}
    <div class="small">${esc(photoSummary())}</div>
    <button data-action="add-photos" class="secondary">📷 Add photos</button>
    <button data-action="save-sighting-edit">Save changes</button>
    <button data-action="go-home" class="secondary">Cancel</button>`;
}

function showSightingEdit() {
  const v = appState.currentVehicle;
  const s = (v.sightings || []).find((x) => x.id === appState.editingSightingId);
  if (!s) { setNotice('That sighting is no longer on this record.', 'warn'); return; }
  render(editFormFields(v, s), 'sighting-edit');
}

function editSighting(el) {
  appState.editingSightingId = el.dataset.id;
  appState.draft = {};
  Photos.clearCapturedPhotos();
  showSightingEdit();
}

async function saveSightingEdit(btn) {
  const form = readForm();
  const v = appState.currentVehicle;
  const s = (v.sightings || []).find((x) => x.id === appState.editingSightingId);
  if (!s || !canEditSighting(s, observer)) {
    setNotice(`You can edit your own sightings for ${SIGHTING_EDIT_WINDOW_HOURS} hours after saving them.`, 'warn');
    return;
  }
  await withBusy(btn, async () => {
    const changes = { notes: form.notes, flag: form.flag, removePhotos: form.removePhotos,
      vehicle: { color: form.color, make: form.make, model: form.model, bodyStyle: form.bodyStyle, distinguishing: form.distinguishing } };
    if (form.prevWhen && localInputValue(new Date(s.timestamp)) !== form.prevWhen) {
      const when = validPastDate(form.prevWhen, new Date());
      if (!when) { setNotice(`Pick a time that is in the past, within the last ${PREVIOUS_SIGHTING_MAX_DAYS} days.`, 'warn'); return; }
      changes.when = when;
    }
    if (form.prevLoc === 'none') changes.location = null;
    else if (form.prevLoc === 'here') {
      const captured = await captureLocation(true);
      if (captured.cancelled) return;
      if (captured.location) changes.location = captured.location;
    } else if (form.prevLoc === 'picked') {
      const lat = Number(form.prevLat);
      const lng = Number(form.prevLng);
      if (form.prevLat === '' || form.prevLng === '' || !isValidCoordinate(lat, lng)) {
        setNotice('Tap "Find place" to pin the location, or choose another location option.', 'warn');
        return;
      }
      changes.location = { lat, lng, manual: true };
    }
    await queueSightingEdit(v, s.id, changes, Photos.getCapturedPhotos(), db, observer);
    appState.editingSightingId = null;
    await afterSave(`${v.displayName} sighting updated;`, v.vehicleKey);
  });
}

async function saveVehicle(btn) {
  const form = readForm();
  const check = validateVehicleCapture(form);
  if (!check.isValid) {
    setNotice(check.errors.join('. '), 'error');
    return;
  }
  if (!hasAnyContent(form, Photos.getCapturedPhotos().length, form.attachLocation)) {
    setNotice('Add anything you know (a plate, photo, note or description) and save. Everything else can be filled in later.', 'warn');
    return;
  }

  await withBusy(btn, async () => {
    const photos = Photos.getCapturedPhotos();
    const captured = await resolveWhenAndWhere(form);
    if (captured.cancelled) return;
    const location = captured.location;
    form.when = captured.when;
    if (!hasAnyContent(form, photos.length, Boolean(location))) { // only a location was wanted, and none could be read
      setNotice('Nothing to save yet: the location could not be read. Add a plate, photo or note, or turn location on.', 'warn');
      return;
    }
    const plate = normalizePlate(form.plate);
    const state = normalizeState(form.plateState);
    const key = plateKey(state, plate);
    rememberState(state);

    // A known plate means a known vehicle: add a sighting instead of a duplicate.
    let existing = null;
    let possibleDuplicate = false;
    if (plate) {
      try {
        const plateRecord = await GitHub.getPlate(key, token);
        if (plateRecord) existing = await GitHub.getVehicle(plateRecord.currentVehicleKey, token);
      } catch (err) {
        if (!(err instanceof GitHub.NetworkError)) throw err;
        possibleDuplicate = true; // offline: could not check
      }
    }

    if (existing) {
      await queueVehicleUpdate(existing, { ...form, plateLookup: lookupRecordFor(form, existing) }, photos, location, db, observer);
      await afterSave(`Plate ${formatPlateKey(key)} was already on file. Sighting added to ${existing.displayName};`, existing.vehicleKey);
      return;
    }

    const { vehicle, photoFiles } = createVehicleRecord({ ...form, possibleDuplicate, plateLookup: lookupRecordFor(form, null) }, photos, location, new Date(), observer, form.when);
    const plateRecord = plate ? createPlateRecord(plate, state, vehicle.vehicleKey, form.plateType) : null;
    await enqueueWrite(db, { key: vehicle.vehicleKey, payload: { vehicle, plate: plateRecord, photos: photoFiles } });
    await cacheRecord(db, `vehicle:${vehicle.vehicleKey}`, vehicle, 'vehicle');
    await afterSave(`${vehicle.displayName}`, vehicle.vehicleKey);
  });
}

// ---------- registration-data lookup ----------
// Check what is on file first. Only a plate that is not listed (search), a vehicle whose make or model is
// unknown, or a new plate typed into the form is looked up, and only for the states in LOOKUP_STATES.
// The answer helps fill the form. It is stored on the vehicle (no VIN) only when make AND model agree.

const isUnknownText = (s) => ['', 'unknown'].includes(String(s || '').trim().toLowerCase());

async function runLookup(state, plate) {
  const key = plateKey(state, plate);
  const known = appState.lookups[key];
  if (known) return known;
  const result = await lookupVehicle(state, plate, token);
  if (result.status === 'found' || result.status === 'not_found') appState.lookups[key] = result;
  return result;
}

function lookupProblem(result) {
  if (result.status === 'not_found') return 'No registration data found for this plate.';
  if (result.status === 'offline') return 'Registration lookup unavailable offline.';
  if (result.status === 'unauthorized') return 'Registration lookup refused this token.';
  if (result.status === 'limit') return 'Registration lookup limit reached for today.';
  if (result.status === 'not_configured') return '';
  return 'Registration lookup failed.';
}

/** Put registration make/model into any form field that is empty or "unknown". Returns what was filled. */
function fillFromLookup(vehicle) {
  const filled = [];
  for (const [id, value] of [['make', vehicle.make], ['model', vehicle.model]]) {
    const el = byId(id);
    if (el && value && isUnknownText(el.value)) { el.value = value; filled.push(id); }
  }
  return filled;
}

function showLookupResult(box, result, { filled = [] } = {}) {
  if (!box) return;
  if (result.status !== 'found') { box.textContent = lookupProblem(result); return; }
  const v = result.vehicle;
  const entered = { make: byId('make') ? byId('make').value : '', model: byId('model') ? byId('model').value : '' };
  const c = compareToLookup(entered, v);
  const note = filled.length ? ' Filled in what was blank.'
    : (!isUnknownText(entered.make) && !c.make) || c.model === false ? ' This differs from what you entered, so it will not be saved.'
    : c.make && c.model ? ' Matches what you entered; it will be saved with the vehicle.' : '';
  box.textContent = `Registration data: ${lookupText(v)}.${note}`;
}

/** The answer to store with this save: needs make and model entered, and both agreeing. */
function lookupRecordFor(form, vehicle, extraKeys = []) {
  const entered = { make: form.make || vehicle?.make, model: form.model || vehicle?.model };
  const keys = [plateKey(form.plateState, form.plate), ...extraKeys].filter(Boolean);
  for (const key of keys) {
    const found = appState.lookups[key];
    const record = found && found.status === 'found' ? buildPlateLookup(entered, key, found) : null;
    if (record) return record;
  }
  return null;
}

/** New-vehicle form: when a lookup-able plate is typed, check whether it is on file, then look it up. */
async function checkFormPlate() {
  const box = byId('form-lookup');
  const input = byId('plate');
  if (!box || !input || appState.currentView !== 'vehicle-form') return;
  const plate = normalizePlate(input.value);
  const state = normalizeState(stateOf('plateState'));
  box.textContent = '';
  if (plate.length < 2 || !lookupEnabled(state)) return;
  const key = plateKey(state, plate);
  box.textContent = 'Checking…';
  try {
    if (await GitHub.getPlate(key, token)) { box.textContent = 'This plate is already on file. Saving adds a sighting to it.'; return; }
  } catch (err) {
    if (err instanceof GitHub.NetworkError) { box.textContent = ''; return; }
    throw err;
  }
  const result = await runLookup(state, plate);
  if (!byId('plate') || plateKey(normalizeState(stateOf('plateState')), byId('plate').value) !== key) return; // edited meanwhile
  showLookupResult(box, result, { filled: result.status === 'found' ? fillFromLookup(result.vehicle) : [] });
}

/** Update form: unknown make or model is looked up automatically; a known vehicle gets a manual check button. */
async function lookupForOpenVehicle(vehicle) {
  const box = byId('form-lookup');
  const key = lookupKeyFor(vehicle);
  if (!box || !key) return;
  if (vehicle.plateLookup && !detailsUnknown(vehicle)) {
    box.textContent = `Registration data on file: ${lookupText(vehicle.plateLookup)}.`;
    return;
  }
  if (!detailsUnknown(vehicle)) {
    box.innerHTML = '<button type="button" class="secondary compact" data-action="check-lookup">Check against registration data</button>';
    return;
  }
  box.textContent = 'Make or model unknown: checking registration data…';
  const { state, plate } = splitPlateKey(key);
  const result = await runLookup(state, plate);
  if (appState.currentVehicle !== vehicle || !byId('form-lookup')) return;
  showLookupResult(byId('form-lookup'), result, { filled: result.status === 'found' ? fillFromLookup(result.vehicle) : [] });
}

async function checkLookupNow(btn) {
  const vehicle = appState.currentVehicle;
  const key = vehicle && lookupKeyFor(vehicle);
  if (!key) return;
  const { state, plate } = splitPlateKey(key);
  await withBusy(btn, async () => {
    const box = byId('form-lookup');
    box.textContent = 'Checking registration data…';
    showLookupResult(box, await runLookup(state, plate));
  });
}

/** Plate search found nothing for a lookup-able state: look it up and offer the answer on the create button. */
async function lookupNotListed(plate, state) {
  const result = await runLookup(state, plate);
  const box = byId('lookup-box');
  if (!box) return;
  if (result.status !== 'found') { box.textContent = lookupProblem(result); return; }
  box.textContent = `Registration data: ${lookupText(result.vehicle)}. Creating a vehicle will fill in the make and model.`;
  const create = document.querySelector('[data-action="create-with-plate"]');
  if (create) { create.dataset.make = result.vehicle.make || ''; create.dataset.model = result.vehicle.model || ''; }
}

// ---------- plate lookup ----------

/**
 * One list row per plate, so a plate is never listed twice: the flag's colored circle (as in the Nearby list),
 * the state and plate large with the matching characters highlighted, and the vehicle's description below in
 * smaller letters. Used by every plate search result.
 */
function plateResultRow(entry, key, kind, query = '') {
  const parts = splitPlateKey(key);
  const plate = parts ? parts.plate : key;
  const at = query ? plate.indexOf(query) : -1;
  const shown = at < 0 ? esc(plate)
    : `${esc(plate.slice(0, at))}<b class="hit">${esc(plate.slice(at, at + query.length))}</b>${esc(plate.slice(at + query.length))}`;
  const state = parts && parts.state !== UNKNOWN_STATE ? parts.state : ''; // like the rest of the app, an unknown state is not shown
  const flag = entry.flag || 'unknown';
  return `
    <div class="vrow plate-hit" role="button" tabindex="0" data-match="${esc(kind)}" data-action="view-vehicle" data-key="${esc(entry.vehicleKey)}">
      <span class="dot dot-${esc(flag)}" role="img" aria-label="${esc(flag)}" title="${esc(flag)}"></span>
      <span class="vrow-main"><strong class="plate-text">${state ? `<span class="plate-state">${esc(state)}</span> ` : ''}${shown}</strong>
        <span class="vrow-sub">${esc(entry.displayName || 'Vehicle')}</span></span>
    </div>`;
}

function showPlateSearch() {
  render(`
    <h2>Look up plate</h2>
    ${plateRow('plate-input', 'Plate or part of one (3+ characters)', '', ANY_STATE, 'state-input', true)}
    <button data-action="search-plate">Search</button>
    <div id="plate-results"></div>
    <button data-action="go-home" class="secondary">Cancel</button>
  `, 'plate-search');
}

async function searchPlate(btn) {
  liveTypeToken++; // a pending as-you-type list must not overwrite this search
  const raw = byId('plate-input').value;
  const plate = normalizePlate(raw);
  if (!plate) return;
  const picked = byId('state-input').value;
  const anyState = picked === ANY_STATE;
  const state = anyState ? ANY_STATE : normalizeState(picked);
  if (!anyState) rememberState(state);
  const results = byId('plate-results');
  results.hidden = false;
  results.innerHTML = '<p>Searching…</p>';
  const nearby = byId('home-list');
  if (nearby) nearby.hidden = true;
  const clear = byId('clear-plate');
  if (clear) clear.hidden = false;
  live.showing = 'plate';

  await withBusy(btn, async () => {
    const { vehicle, matches, similar, offline } = await lookupPlate(plate, state, db, token);
    if (vehicle) {
      appState.currentVehicle = vehicle;
      appState.draft = {};
      if (offline) flashTo('Offline: showing the copy saved on this device.', 'warn');
      showVehicleUpdateForm();
      return;
    }

    if (matches.length) {
      appState.plateSearch = { plate, anyState, state, matches, filter: '', expanded: false };
      renderPlateMatches();
      return;
    }
    const label = anyState ? esc(plate) : esc(formatPlateKey(plateKey(state, plate)));
    let html = offline
      ? '<p class="warn">Offline, and this plate is not saved on this device.</p>'
      : `<p>No vehicle found for <strong>${label}</strong>${anyState ? ' in any state' : ''}.</p>`;
    const same = similar.filter((s) => entriesWithPlate([s], plate).length);
    const near = similar.filter((s) => !same.includes(s));
    const rowsFor = (list, kind) => list.flatMap((e) => {
      const keys = e.plateAliases || [];
      const picked = kind === 'other' ? keys.filter((k) => (splitPlateKey(k) || {}).plate === plate) : keys.slice(0, 1);
      return picked.map((k) => plateResultRow(e, k, kind));
    });
    if (same.length) html += `<p>Same plate under another state:</p><div class="results-list">${rowsFor(same, 'other').join('')}</div>`;
    if (near.length) html += `<p>Similar plates:</p><div class="results-list">${rowsFor(near, 'similar').join('')}</div>`;
    if (plate.length < PARTIAL_MIN) html += `<p class="small">Type ${PARTIAL_MIN} or more characters to find plates that contain them.</p>`;
    const lookupNow = !anyState && !offline && lookupEnabled(state);
    if (lookupNow) html += '<p id="lookup-box" class="small" aria-live="polite">Not on file: checking registration data…</p>';
    html += `<button data-action="create-with-plate" data-plate="${esc(plate)}" data-state="${esc(anyState ? lastState() : state)}">Create new vehicle with this plate</button>`;
    if (!offline) {
      html += '<p class="small">No result? Look the plate up yourself, then enter the year, make and model on the new vehicle.</p>'
        + PLATE_SITES.map((s) => `<button class="secondary" data-action="open-plate-site" data-site="${esc(s.id)}" data-plate="${esc(plate)}" data-state="${esc(anyState ? lastState() : state)}">Look up on ${esc(s.name)}</button>`).join('')
        + '<p id="site-note" class="small" aria-live="polite"></p>';
    }
    results.innerHTML = html;
    if (lookupNow) lookupNotListed(plate, state);
  });
}

/**
 * The list of vehicles whose plate contains the search text. When the search covered any state and the
 * matches span several, one tap on a state narrows the list.
 */
function renderPlateMatches() {
  const s = appState.plateSearch;
  if (!s) return;
  const all = plateMatchRows(s.matches, s.plate, s.anyState ? null : s.state); // one row per plate
  const states = new Map(); // state -> plates in it
  for (const r of all) states.set(r.state, (states.get(r.state) || 0) + 1);
  if (s.filter && !states.has(s.filter)) s.filter = ''; // typing more can remove the chosen state
  const shown = s.filter ? all.filter((r) => r.state === s.filter) : all;
  const chip = (value, label, count) => `<button type="button" class="chip${s.filter === value ? ' on' : ''}" data-action="filter-plate-state" data-state="${esc(value)}">${esc(label)} <span>${count}</span></button>`;
  const chips = s.anyState && states.size > 1
    ? `<div class="chips" role="group" aria-label="Narrow by state">${chip('', 'All', all.length)}${
      [...states].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([st, n]) => chip(st, st === UNKNOWN_STATE ? 'State unknown' : st, n)).join('')}</div>`
    : '';
  const where = s.anyState ? (s.filter ? ` in ${s.filter === UNKNOWN_STATE ? 'an unknown state' : esc(s.filter)}` : '') : ` in ${esc(s.state)}`;
  byId('plate-results').innerHTML = `<p>${shown.length.toLocaleString()} plate${shown.length === 1 ? '' : 's'} matching <strong>${esc(s.plate)}</strong>${where}.</p>${chips}`
    + `<div class="results-list">${shown.slice(0, capFor(s.expanded)).map((r) => plateResultRow(r.entry, r.key, r.kind, s.plate)).join('')}</div>`
    + moreButton(shown.length, s.expanded, 'view-more-plate')
    + capNote(shown.length, s.expanded, `Add characters${s.anyState ? ' or pick a state' : ''} to narrow it down.`);
}


// ---------- plates appear as they are typed ----------
// From LIVE_MIN characters, every plate containing the text is listed in place of the Nearby list, from the vehicle
// list already in memory (no network request per key). Search still does the exact lookup and opens a single exact plate.

function showNearbyAgain() {
  const results = byId('plate-results');
  if (results) { results.hidden = true; results.innerHTML = ''; }
  const list = byId('home-list');
  if (list) list.hidden = false;
  const input = byId('plate-input');
  const clear = byId('clear-plate');
  if (clear) clear.hidden = !(input && input.value);
  appState.plateSearch = null;
  if (live.showing === 'plate') { live.showing = 'nearby'; drawHomeList(); }
}

let liveTypeToken = 0;
async function liveTypeSearch() {
  const input = byId('plate-input');
  const results = byId('plate-results');
  if (!input || !results || !token) return;
  const plate = normalizePlate(input.value);
  if (plate.length < LIVE_MIN) { showNearbyAgain(); return; }
  const mine = ++liveTypeToken;
  if (!live.entries.length) await loadHomeEntries(false); // only if the list is not in memory yet
  if (mine !== liveTypeToken || byId('plate-input') !== input) return; // typed further, or left the screen
  const picked = byId('state-input').value;
  const anyState = picked === ANY_STATE;
  const state = anyState ? ANY_STATE : normalizeState(picked);
  const matches = rankPlateMatches(live.entries, plate, anyState ? null : state);
  const previous = appState.plateSearch;
  results.hidden = false;
  const list = byId('home-list');
  if (list) list.hidden = true;
  const clear = byId('clear-plate');
  if (clear) clear.hidden = false;
  live.showing = 'plate';
  if (!matches.length) {
    appState.plateSearch = null;
    results.innerHTML = `<p>No plate on file contains <strong>${esc(plate)}</strong>${anyState ? '' : ` in ${esc(state)}`}.</p><p class="small">Press Search to check for similar plates or to add it.</p>`;
    return;
  }
  appState.plateSearch = { plate, anyState, state, matches, filter: previous && previous.anyState === anyState ? previous.filter : '', expanded: false };
  renderPlateMatches();
}

function filterPlateState(el) {
  if (!appState.plateSearch) return;
  appState.plateSearch.filter = el.dataset.state || '';
  appState.plateSearch.expanded = false;
  renderPlateMatches();
}

/** Open a public plate-lookup site in a new tab. The plate is copied first so it can be pasted there. */
function openPlateSite(el) {
  const site = PLATE_SITES.find((s) => s.id === el.dataset.site);
  if (!site) return;
  const state = el.dataset.state || '';
  const usable = !site.url.includes('{') || (/^[A-Z]{2}$/.test(state) && state !== UNKNOWN_STATE && el.dataset.plate);
  const url = usable
    ? site.url.replace('{state}', encodeURIComponent(state)).replace('{plate}', encodeURIComponent(el.dataset.plate || ''))
    : (site.fallback || site.url);
  try { navigator.clipboard?.writeText(el.dataset.plate || '').catch(() => {}); } catch { /* clipboard unavailable */ }
  window.open(url, '_blank', 'noopener,noreferrer');
  const note = byId('site-note');
  if (note) note.textContent = `Plate ${el.dataset.plate} copied. Paste it on the site, then enter the year, make and model here.`;
}

function createWithPlate(el) {
  appState.draft = { plate: el.dataset.plate, plateState: el.dataset.state, make: el.dataset.make || '', model: el.dataset.model || '' };
  showVehicleForm();
  checkFormPlate(); // adds the "matches what you entered" note and keeps the answer for saving
}

// ---------- vehicle update ----------

/** A link that opens directions to a recorded location in the phone's maps app. */
function mapLink(location, label, cls = '') {
  if (!location || !isValidCoordinate(location.lat, location.lng)) return '';
  return `<a class="maplink ${cls}" href="${esc(mapsDirectionsUrl(location.lat, location.lng))}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}

/** Most recent sightings, newest first: flag, time and notes. */
function historyList(vehicle) {
  const recent = [...(vehicle.sightings || [])]
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, 5);
  if (!recent.length) return '';
  const items = recent.map((s) => `
    <li class="flag-${esc(s.flag)}"><strong>${esc(s.flag)}</strong> · ${esc(new Date(s.timestamp).toLocaleString())}${
      s.observer ? ` · ${esc(s.observer)}` : ''}${s.location ? ` · ${mapLink(s.location, 'Map')}` : ' · no location'}${s.notes ? `<br>${esc(s.notes)}` : ''}${
      canEditSighting(s, observer) ? ` <button type="button" class="secondary compact" data-action="edit-sighting" data-id="${esc(s.id)}">Edit</button>` : ''}</li>`).join('');
  return `<h3>Recent sightings</h3><ul class="history">${items}</ul>`;
}

/** "Navigate" to where the record was last seen with a location, so a teammate can go there. */
function navigateBlock(vehicle) {
  const at = latestLocatedSighting(vehicle);
  if (!at) return '<p class="small">No location recorded for this vehicle yet.</p>';
  return `<a class="btn-link" href="${esc(mapsDirectionsUrl(at.location.lat, at.location.lng))}" target="_blank" rel="noopener noreferrer" data-navigate>📍 Navigate to last seen location (${esc(formatTimeSince(new Date(at.timestamp)))})</a>`;
}

function showVehicleUpdateForm() {
  const v = appState.currentVehicle;
  const last = v.lastSeen ? new Date(v.lastSeen).toLocaleString() : 'unknown';
  render(`
    <h2>Update: ${esc(v.displayName)}</h2>
    <p class="small">Last seen: ${esc(last)}<br>Plates: ${esc(keysText(v.plateAliases, 'none on file'))}<br>Features: ${esc((v.distinguishing || []).join(', ') || 'none recorded')}</p>
    ${navigateBlock(v)}
    <button type="button" class="secondary compact" data-action="share-vehicle" data-key="${esc(v.vehicleKey)}">Share this record</button>
    <div id="vehicle-photos" class="thumbs"></div>
    ${historyList(v)}
    <input type="text" id="color" placeholder="Color" value="${esc(draftValue('color', v.color))}">
    <input type="text" id="make" placeholder="Make" value="${esc(draftValue('make', v.make))}">
    <input type="text" id="model" placeholder="Model" value="${esc(draftValue('model', v.model || ''))}">
    ${siteChecksBlock(appState.draft || {}, v)}
    <select id="bodyStyle">${options(BODY_STYLES, draftValue('bodyStyle', v.bodyStyle))}</select>
    <input type="text" id="distinguishing" placeholder="Additional features (comma-separated)" value="${esc(draftValue('distinguishing'))}">
    ${plateRow('plate', 'Add another plate (optional)', draftValue('plate'), draftValue('plateState', lastState()))}
    <div id="form-lookup" class="small" aria-live="polite"></div>
    <select id="plateType">${options(PLATE_TYPES, draftValue('plateType', 'standard'))}</select>
    <select id="flag">${options(FLAGS, draftValue('flag', v.flag))}</select>
    <textarea id="notes" placeholder="Sighting notes">${esc(draftValue('notes'))}</textarea>
    ${locationCheckbox()}
    ${previousSightingBlock()}
    <div class="small">${esc(photoSummary())}</div>
    <button data-action="add-photos" class="secondary">📷 Add photos</button>
    <button data-action="update-vehicle">Save update</button>
    <button data-action="go-home" class="secondary">Cancel</button>
  `, 'vehicle-update');
  loadVehiclePhotos(v);
  lookupForOpenVehicle(v);
}

async function loadVehiclePhotos(vehicle) {
  const paths = (vehicle.sightings || []).flatMap((s) => s.photos || []).slice(-6).reverse();
  const holder = byId('vehicle-photos');
  for (const path of paths) {
    try {
      const url = await GitHub.fetchPhotoBlobUrl(path, token);
      appState.blobUrls.push(url);
      if (!byId('vehicle-photos') || byId('vehicle-photos') !== holder) return; // navigated away
      const img = document.createElement('img');
      img.src = url;
      img.alt = 'Earlier sighting';
      img.className = 'thumb-img';
      holder.appendChild(img);
    } catch {
      break; // offline or missing; photos are optional here
    }
  }
}

async function updateExistingVehicle(btn) {
  const vehicle = appState.currentVehicle;
  const form = readForm();
  const check = validateVehicleUpdate(form, appState.currentVehicle);
  if (!check.isValid) {
    setNotice(check.errors.join('. '), 'error');
    return;
  }

  await withBusy(btn, async () => {
    const newPlate = normalizePlate(form.plate);
    const newKey = plateKey(form.plateState, newPlate);
    if (newPlate) rememberState(normalizeState(form.plateState));
    if (newKey && !(vehicle.plateAliases || []).includes(newKey)) {
      try {
        const owner = await GitHub.getPlate(newKey, token);
        if (owner && owner.currentVehicleKey !== vehicle.vehicleKey) {
          setNotice(`Plate ${formatPlateKey(newKey)} already belongs to another vehicle (${owner.currentVehicleKey}).`, 'error');
          return;
        }
      } catch (err) {
        if (!(err instanceof GitHub.NetworkError)) throw err; // offline: skip the check
      }
    }

    const captured = await resolveWhenAndWhere(form);
    if (captured.cancelled) return;
    const location = captured.location;
    form.when = captured.when;
    const own = lookupKeyFor(vehicle);
    await queueVehicleUpdate(vehicle, { ...form, plateLookup: lookupRecordFor(form, vehicle, own ? [own] : []) }, Photos.getCapturedPhotos(), location, db, observer);
    await afterSave(`${vehicle.displayName} updated;`, vehicle.vehicleKey);
  });
}

// ---------- sharing a record ----------
// A link such as https://.../ParkingTracker/#v=VEH_1a2b3c4d opens that vehicle for anyone signed in on that
// browser. The link holds only the vehicle's key, no data and no token.

const LINK_KEY_RE = /(?:^#|&)v=(VEH_[0-9a-f]{8})(?:&|$)/;
const PENDING_LINK = 'pt-pending-link';

function shareUrl(key) {
  return `${location.origin}${location.pathname}#v=${key}`;
}

async function shareVehicle(el) {
  const key = (el && el.dataset && el.dataset.key) || (appState.currentVehicle && appState.currentVehicle.vehicleKey);
  if (!key) return;
  const url = shareUrl(key);
  const name = appState.currentVehicle && appState.currentVehicle.vehicleKey === key ? appState.currentVehicle.displayName : 'a vehicle';
  if (navigator.share) {
    try {
      await navigator.share({ title: 'Tracker record', text: `Tracker record: ${name}`, url });
      return;
    } catch (err) {
      if (err && err.name === 'AbortError') return; // the person closed the share sheet
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    setNotice('Link copied. Paste it in a message. It works once the record has uploaded (Sync now, if you were offline).', 'ok');
  } catch {
    setNotice(`Copy this link: ${url}`, 'info');
  }
}

/** Open the record a shared link points at. Signed out: remember it and open it after sign-in. */
async function openLinkedVehicle(key) {
  history.replaceState(null, '', location.pathname + location.search);
  if (!token || !observer) {
    try { sessionStorage.setItem(PENDING_LINK, key); } catch { /* storage blocked */ }
    return;
  }
  await viewVehicle({ dataset: { key } }, 'That shared record is not on the server yet. Ask the sender to open the menu and tap Sync now, then try the link again.');
}

function openPendingLink() {
  let key = null;
  try { key = sessionStorage.getItem(PENDING_LINK); sessionStorage.removeItem(PENDING_LINK); } catch { /* storage blocked */ }
  const fromHash = LINK_KEY_RE.exec(location.hash);
  if (fromHash) key = fromHash[1];
  if (key) openLinkedVehicle(key);
}

async function viewVehicle(el, missingText = 'Could not load that vehicle.') {
  const key = el.dataset.key;
  let vehicle;
  try {
    vehicle = await GitHub.getVehicle(key, token);
  } catch (err) {
    if (!(err instanceof GitHub.NetworkError)) throw err;
    const cached = await getCachedRecord(db, `vehicle:${key}`);
    vehicle = cached ? cached.data : null;
    if (vehicle) flashTo('Offline: showing the copy saved on this device.', 'warn');
  }
  if (!vehicle) {
    setNotice(missingText, 'error');
    return;
  }
  await cacheRecord(db, `vehicle:${key}`, vehicle, 'vehicle');
  appState.currentVehicle = vehicle;
  appState.draft = {};
  showVehicleUpdateForm();
}

// ---------- local search ----------

function showLocalSearch() {
  render(`
    <h2>Find nearby vehicles</h2>
    <p class="small">Within ${esc(DEFAULT_RADIUS_METERS / 1000)} km. Your position is used for this search only and is never saved.</p>
    <button data-action="use-location">📍 Use my location</button>
    <div id="manual-input">
      <label for="lat">Or enter coordinates:</label>
      <input type="number" id="lat" placeholder="Latitude" step="any" inputmode="decimal">
      <input type="number" id="lng" placeholder="Longitude" step="any" inputmode="decimal">
      <button data-action="search-local">Search</button>
    </div>
    <button data-action="refresh-local" class="secondary">↻ Refresh index</button>
    <div id="local-status" class="small"></div>
    <div id="local-results"></div>
    <button data-action="go-home" class="secondary">Cancel</button>
  `, 'local-search');
}

async function useDeviceLocation(btn) {
  await withBusy(btn, async () => {
    setNotice('Getting your location…');
    const pos = await getDeviceLocation();
    if (!pos) {
      setNotice('Could not get your location. Enter coordinates instead.', 'warn');
      return;
    }
    setNotice('');
    appState.localUserLocation = pos;
    await performLocalSearch();
  });
}

async function searchLocal(btn) {
  const lat = parseFloat(byId('lat').value);
  const lng = parseFloat(byId('lng').value);
  if (!isValidCoordinate(lat, lng)) {
    setNotice('Enter a valid latitude (-90 to 90) and longitude (-180 to 180).', 'error');
    return;
  }
  appState.localUserLocation = { lat, lng };
  await withBusy(btn, () => performLocalSearch());
}

async function refreshLocal(btn) {
  if (!appState.localUserLocation) {
    setNotice('Choose a location first.', 'warn');
    return;
  }
  await withBusy(btn, () => performLocalSearch({ force: true }));
}

async function performLocalSearch({ force = false } = {}) {
  const results = byId('local-results');
  results.innerHTML = '<p>Loading…</p>';

  const { entries, source, fetchedAt } = await loadIndex(db, token, { force });
  const ranked = rankLocalResults(entries, appState.localUserLocation, DEFAULT_RADIUS_METERS);

  const age = fetchedAt ? `${Math.max(0, Math.round((Date.now() - fetchedAt) / 60000))} min ago` : 'never';
  const labels = {
    network: `Index refreshed just now`,
    cache: `Using saved index (fetched ${age})`,
    'stale-cache': `Offline: using saved index (fetched ${age})`,
    'offline-empty': 'Offline and no saved index yet'
  };
  byId('local-status').textContent = labels[source] || '';

  appState.localRanked = ranked;
  appState.localExpanded = false;
  renderLocalResults();
}

function renderLocalResults() {
  const results = byId('local-results');
  const ranked = appState.localRanked || [];
  if (!results) return;
  if (ranked.length === 0) {
    results.innerHTML = '<p>No vehicles found nearby.</p>';
    return;
  }
  const expanded = appState.localExpanded;
  results.innerHTML = '<div class="results-list">' + ranked.slice(0, capFor(expanded)).map((item) => {
    const f = formatLocalResult(item, item.distance);
    const plates = f.plateAliases.length ? `<div>Plate: ${esc(keysText(f.plateAliases, ''))}</div>` : '';
    return `
      <div class="result-card flag-${esc(f.flag)}" data-action="view-vehicle" data-key="${esc(f.vehicleKey)}">
        <strong>${esc(f.displayName)}</strong>
        <div>Flag: ${esc(f.flag)}</div>
        ${plates}
        <div>Distance: ${esc(f.distance)}</div>
        <div>Last seen: ${esc(f.timeSince)}</div>
      </div>`;
  }).join('') + '</div>' + moreButton(ranked.length, expanded, 'view-more-local') + capNote(ranked.length, expanded, 'These are the nearest.');
}

// ---------- find by description ----------

const anyOption = (label) => `<option value="">${esc(label)}</option>`;

async function showDescribeSearch() {
  render(`
    <h2>Find by description</h2>
    <p class="small">Words are ANDed and can be part of a word: <em>grey nissan</em>, <em>pickup dent</em>, <em>2019</em>, a plate fragment.</p>
    <input type="search" id="desc-q" placeholder="Color, make, model, year, features, plate" autocomplete="off" autocapitalize="none">
    <select id="desc-flag" aria-label="Flag">${anyOption('Any flag')}${options(FLAGS, '')}</select>
    <select id="desc-body" aria-label="Body style">${anyOption('Any body style')}${options(BODY_STYLES.filter((b) => b !== 'unknown'), '')}</select>
    <div id="desc-status" class="small" aria-live="polite">Loading…</div>
    <div id="desc-results"></div>
    <button data-action="go-home" class="secondary">Cancel</button>
  `, 'describe-search');
  const { entries, source } = await loadIndex(db, token);
  if (appState.currentView !== 'describe-search') return;
  appState.describe = { entries, shown: [], expanded: false };
  byId('desc-status').textContent = source === 'offline-empty' ? 'Offline and no saved index yet.' : source === 'stale-cache' ? 'Offline: searching the copy saved on this device.' : `${entries.length} vehicles`;
  byId('desc-q').focus();
  runDescribeSearch();
}

function runDescribeSearch() {
  const state = appState.describe;
  const results = byId('desc-results');
  if (!state || !results) return;
  const criteria = { query: byId('desc-q').value, flag: byId('desc-flag').value, bodyStyle: byId('desc-body').value };
  state.shown = searchByDescription(state.entries, criteria);
  state.expanded = false;
  renderDescribeResults(Boolean(criteria.query.trim() || criteria.flag || criteria.bodyStyle));
}

function renderDescribeResults(searched = true) {
  const state = appState.describe;
  const results = byId('desc-results');
  if (!results || !state) return;
  if (!searched) { results.innerHTML = ''; return; }
  if (!state.shown.length) { results.innerHTML = '<p>No vehicles match.</p>'; return; }
  const all = state.shown;
  results.innerHTML = `<p class="small">${all.length} match${all.length === 1 ? '' : 'es'}</p><div class="results-list">`
    + all.slice(0, capFor(state.expanded)).map((e) => `
      <div class="result-card flag-${esc(e.flag)}" data-action="view-vehicle" data-key="${esc(e.vehicleKey)}">
        <strong>${esc(e.displayName)}</strong>
        ${e.year ? `<div>Year: ${esc(e.year)}</div>` : ''}
        ${(e.features || []).length ? `<div>Features: ${esc(e.features.join(', '))}</div>` : ''}
        ${(e.plateAliases || []).length ? `<div>Plate: ${esc(keysText(e.plateAliases, ''))}</div>` : ''}
        <div>Flag: ${esc(e.flag)} · Last seen: ${esc(formatTimeSince(new Date(e.lastSeen)))}</div>
      </div>`).join('') + '</div>'
    + moreButton(all.length, state.expanded, 'view-more-describe') + capNote(all.length, state.expanded, 'Narrow the search to see the rest.');
}

// ---------- navigation ----------

function goHome() {
  Photos.stopCamera();
  Photos.clearCapturedPhotos();
  appState.draft = {};
  appState.currentVehicle = null;
  showHomeScreen();
}

function hasUnsavedEntry() {
  if (!['vehicle-form', 'vehicle-update', 'photo-capture'].includes(appState.currentView)) return false;
  if (Photos.getCapturedPhotos().length > 0) return true;
  const form = readForm();
  return ['color', 'make', 'model', 'year', 'distinguishing', 'plate', 'notes'].some((id) => (form[id] || '').trim() !== '');
}

function logoHome() {
  if (appState.currentView === 'home-screen') return;
  if (hasUnsavedEntry() && !confirm('Leave this screen? What you entered has not been saved.')) return;
  goHome();
}

function startVehicleFlow() {
  appState.draft = {};
  appState.returnTo = 'vehicle-form';
  showVehicleForm();
}

const actions = {
  'start-describe': showDescribeSearch,
  'view-more-describe': () => { if (appState.describe) { appState.describe.expanded = true; renderDescribeResults(); } },
  'edit-sighting': editSighting,
  'save-sighting-edit': saveSightingEdit,
  'find-place': findPlace,
  'logo-home': logoHome,
  'go-back': goBack,
  'request-permissions': requestPermissions,
  'dismiss-permissions': dismissPermissions,
  'toggle-location': toggleLocation,
  'share-vehicle': shareVehicle,
  'home-tab': (el) => { live.tab = el.dataset.tab; live.tabChosen = true; live.expanded = false; drawHomeList(); },
  'refresh-home': () => loadHomeEntries(true),
  'toggle-menu': () => setMenu(byId('menu') ? byId('menu').hidden : false),
  'save-token': handleTokenSubmit,
  'start-photo': () => { appState.draft = {}; return startPhotoCapture('vehicle-form'); },
  'start-plate': showPlateSearch,
  'start-vehicle': startVehicleFlow,
  'start-local': showLocalSearch,
  'sync-now': syncNow,
  'retry-failed': retryFailedItems,
  logout,
  'capture-photo': capturePhoto,
  'accept-photo': acceptPhoto,
  'retake-photo': retakePhoto,
  'remove-photo': (el) => { Photos.removeCapturedPhoto(Number(el.dataset.index)); refreshPhotoUI(); },
  'finish-photos': finishPhotoCapture,
  'add-photos': addPhotosFromForm,
  'save-vehicle': saveVehicle,
  'update-vehicle': updateExistingVehicle,
  'search-plate': searchPlate,
  'create-with-plate': createWithPlate,
  'open-plate-site': openPlateSite,
  'filter-plate-state': filterPlateState,
  'view-vehicle': (el) => viewVehicle(el),
  'use-location': useDeviceLocation,
  'search-local': searchLocal,
  'refresh-local': refreshLocal,
  'go-home': goHome,
  'open-tutorial': () => openPage('tutorial.html'),
  'open-glossary': () => openPage('glossary.html'),
  'check-lookup': checkLookupNow,
  'clear-plate-search': clearPlateSearch,
  'view-more-home': () => { live.expanded = true; drawHomeList(); },
  'view-more-local': () => { appState.localExpanded = true; renderLocalResults(); },
  'view-more-plate': () => { if (appState.plateSearch) { appState.plateSearch.expanded = true; renderPlateMatches(); } }
};

document.addEventListener('click', (event) => {
  const el = event.target.closest('[data-action]');
  const menuEl = byId('menu');
  // Any tap outside the menu, or on one of its items, closes it.
  if (menuEl && !menuEl.hidden && (!el || el.dataset.action !== 'toggle-menu')) setMenu(false);
  if (!el) return;
  const handler = actions[el.dataset.action];
  if (!handler) return;
  event.preventDefault();
  Promise.resolve(handler(el)).catch((err) => {
    console.error(err);
    setNotice(err.message || 'Something went wrong', 'error');
  });
});

document.addEventListener('input', (event) => {
  if (event.target && event.target.id === 'desc-q') { runDescribeSearch(); return; }
  if (event.target && event.target.id === 'plate-input') liveTypeSearch();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setMenu(false);
  if (event.key === 'Enter' && event.target && event.target.id === 'plate-input') {
    const searchBtn = document.querySelector('[data-action="search-plate"]');
    if (searchBtn) searchBtn.click();
  }
});

// Coming back to the app: refresh the nearby list right away rather than waiting for the timer.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && byId('home-list') && token) loadHomeEntries(true);
});

document.addEventListener('change', (event) => {
  if (event.target && event.target.id === 'file-input') handleFileChosen(event.target);
  if (event.target && event.target.id === 'camera-input') handleCameraPhoto(event.target);
  if (event.target && event.target.tagName === 'SELECT' && byId(`${event.target.id}Code`)) syncStateCode(event.target);
  if (event.target && (event.target.id === 'plate' || event.target.id === 'plateState' || event.target.id === 'plateStateCode')) checkFormPlate();
  if (event.target && event.target.id === 'state-input') liveTypeSearch();
  if (event.target && (event.target.id === 'desc-flag' || event.target.id === 'desc-body')) runDescribeSearch();
  if (event.target && /^check-/.test(event.target.id || '')) toggleYearField();
  if (event.target && (event.target.id === 'prevOn' || event.target.id === 'prevLoc')) syncPreviousUi();
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp);
} else {
  initializeApp();
}
