/**
 * vehicle-manager.js
 * Pure record logic: validation, creation, sightings, merge, index entries.
 * No DOM or network access, so it is unit-testable in Node.
 */

import { BODY_STYLES, FLAGS, PLATE_TYPES, PREVIOUS_SIGHTING_MAX_DAYS, SIGHTING_EDIT_WINDOW_HOURS, SITE_CHECK_STATUSES } from './config.js';
import { normalizePlate, normalizeState, plateKey, splitPlateKey } from './matching.js';

// ---------- small helpers ----------

function randomHex(bytes) {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function generateVehicleKey() {
  return `VEH_${randomHex(4)}`;
}

function generateSightingId() {
  return `S_${randomHex(4)}`;
}

function clean(value) {
  return String(value ?? '').trim();
}

export const OBSERVER_MAX = 40;

/** Display name of the person using the device. Null when blank. */
export function cleanObserver(value) {
  const name = clean(value).replace(/\s+/g, ' ').slice(0, OBSERVER_MAX);
  return name || null;
}

/** Capitalise only when the user typed all-lowercase, so "BMW" stays "BMW". */
function tidyWord(value) {
  const v = clean(value);
  if (!v) return v;
  return v === v.toLowerCase() ? v.charAt(0).toUpperCase() + v.slice(1) : v;
}

export function parseDistinguishing(input) {
  const parts = Array.isArray(input) ? input : String(input ?? '').split(/[,;\n]/);
  const seen = new Set();
  const out = [];
  for (const part of parts) {
    const t = clean(part);
    if (t && !seen.has(t.toLowerCase())) {
      seen.add(t.toLowerCase());
      out.push(t);
    }
  }
  return out;
}

/** "Grey Nissan Pathfinder". Words that are blank or "unknown" are left out; with nothing left it is "Unknown vehicle". */
export function buildDisplayName({ color, make, model }) {
  const words = [color, make, model].map(clean).filter((w) => w && w.toLowerCase() !== 'unknown').map(tidyWord);
  return words.join(' ') || 'Unknown vehicle';
}

function tsOf(value) {
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : 0;
}

/**
 * Shape-check a plate lookup answer before it goes into a record. The app only passes one when the
 * registration data agreed with the make and model entered. Returns null for anything malformed.
 */
/**
 * Site checks: what a person found when running the plate on a lookup site. Form fields are named
 * check-<siteId> and hold a status, or '' for "not checked". Absent fields leave the existing check alone;
 * an unchanged status keeps its original date.
 */
export function applySiteChecks(existing, form, now = new Date()) {
  const out = {};
  for (const [id, c] of Object.entries(existing || {})) {
    if (/^[a-z]{2,20}$/.test(id) && c && SITE_CHECK_STATUSES.includes(c.status)) out[id] = { status: c.status, checkedAt: c.checkedAt };
  }
  for (const [name, value] of Object.entries(form || {})) {
    const m = /^check-([a-z]{2,20})$/.exec(name);
    if (!m) continue;
    const status = clean(value);
    if (!status) delete out[m[1]];
    else if (SITE_CHECK_STATUSES.includes(status) && out[m[1]]?.status !== status) out[m[1]] = { status, checkedAt: now.toISOString() };
  }
  return out;
}

export function hasVerifiedSite(checks) {
  return Object.values(checks || {}).some((c) => c && c.status === 'verified');
}

/** A model year typed by hand: a whole number 1900-2100, else null. */
export function cleanYear(value) {
  const text = clean(value);
  if (!/^\d{4}$/.test(text)) return null;
  const year = Number(text);
  return year >= 1900 && year <= 2100 ? year : null;
}

export function cleanPlateLookup(value, now = new Date()) {
  if (!value || typeof value !== 'object') return null;
  const make = clean(value.make);
  const model = clean(value.model);
  const plate = clean(value.plate);
  if (!make || !model || !splitPlateKey(plate)) return null;
  const year = Number.isInteger(value.year) && value.year >= 1900 && value.year <= 2100 ? value.year : null;
  const checked = new Date(value.checkedAt);
  return { plate, year, make, model, checkedAt: (Number.isFinite(checked.getTime()) ? checked : now).toISOString() };
}

function latestSighting(vehicle) {
  const list = vehicle?.sightings || [];
  return list.reduce((best, s) => (!best || tsOf(s.timestamp) >= tsOf(best.timestamp) ? s : best), null);
}

// ---------- validation ----------

/**
 * Does the form hold anything worth saving? A plate, a photo, any description or note, or the person's location.
 * Nothing else is required: a person can save the little they know and hand the record to someone else to complete.
 */
export function hasAnyContent(form, photoCount = 0, hasLocation = false) {
  return Boolean(photoCount > 0 || hasLocation
    || ['plate', 'color', 'make', 'model', 'distinguishing', 'notes'].some((f) => clean(form[f]))
    || (clean(form.bodyStyle) && clean(form.bodyStyle) !== 'unknown'));
}

/** New vehicle form: nothing is required, but anything given must be valid. */
export function validateVehicleCapture(form) {
  const errors = [];
  if (clean(form.year) && cleanYear(form.year) === null) errors.push('Year must be four digits, 1900-2100');
  else if (clean(form.year) && !hasVerifiedSite(applySiteChecks({}, form))) errors.push('Year can be added once a lookup site is marked Verified');
  if (clean(form.bodyStyle) && !BODY_STYLES.includes(clean(form.bodyStyle))) errors.push('Invalid body style');
  if (form.flag && !FLAGS.includes(form.flag)) errors.push('Invalid flag');
  if (clean(form.plate)) {
    if (!normalizePlate(form.plate)) errors.push('Plate has no valid characters');
    if (form.plateType && !PLATE_TYPES.includes(form.plateType)) errors.push('Invalid plate type');
  }
  return { isValid: errors.length === 0, errors };
}

/** Update form: everything is optional, but anything given must be valid. */
export function validateVehicleUpdate(form, existing = null) {
  const errors = [];
  if (form.bodyStyle && !BODY_STYLES.includes(clean(form.bodyStyle))) errors.push('Invalid body style');
  if (clean(form.year) && cleanYear(form.year) === null) errors.push('Year must be four digits, 1900-2100');
  else if (clean(form.year) && cleanYear(form.year) !== (existing?.year ?? null) && !hasVerifiedSite(applySiteChecks(existing?.siteChecks, form))) errors.push('Year can be added once a lookup site is marked Verified');
  if (form.flag && !FLAGS.includes(form.flag)) errors.push('Invalid flag');
  if (clean(form.plate)) {
    if (!normalizePlate(form.plate)) errors.push('Plate has no valid characters');
    if (form.plateType && !PLATE_TYPES.includes(form.plateType)) errors.push('Invalid plate type');
  }
  return { isValid: errors.length === 0, errors };
}

// ---------- photos ----------

function pad(n, width = 2) {
  return String(n).padStart(width, '0');
}

export function makePhotoPath(vehicleKey, when, index) {
  const d = new Date(when);
  const stamp =
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}`;
  return `photos/${vehicleKey}_${stamp}_${pad(index + 1, 3)}.jpg`;
}

function stagePhotos(vehicleKey, dataUrls, when) {
  return (dataUrls || []).map((dataUrl, i) => ({
    path: makePhotoPath(vehicleKey, when, i),
    dataUrl
  }));
}

// ---------- creation ----------

/** A Date for a "previous sighting" time: valid, not in the future, within PREVIOUS_SIGHTING_MAX_DAYS. Else null. */
export function validPastDate(value, now = new Date()) {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  if (d.getTime() > now.getTime() + 60000) return null;
  if (now.getTime() - d.getTime() > PREVIOUS_SIGHTING_MAX_DAYS * 86400000) return null;
  return d;
}

function buildSighting({ id, timestamp, recordedAt, location, photoPaths, flag, notes, observer }) {
  const sighting = {
    id: id || generateSightingId(),
    timestamp,
    location: location || null,
    photos: photoPaths,
    flag: FLAGS.includes(flag) ? flag : 'unknown',
    notes: clean(notes) || null,
    source: 'field-app'
  };
  if (recordedAt && recordedAt !== timestamp) sighting.recordedAt = recordedAt;
  if (observer) sighting.observer = observer;
  return sighting;
}

/**
 * Build a new vehicle record.
 * @returns {{ vehicle: object, photoFiles: {path:string, dataUrl:string}[] }}
 */
export function createVehicleRecord(form, photoDataUrls = [], location = null, now = new Date(), observerName = null, when = null) {
  const happened = validPastDate(when, now) || now;
  const ts = happened.toISOString();
  const recordedAt = now.toISOString();
  const observer = cleanObserver(observerName);
  const vehicleKey = generateVehicleKey();
  const photoFiles = stagePhotos(vehicleKey, photoDataUrls, now);
  const aliasKey = plateKey(form.plateState, form.plate);
  const flag = FLAGS.includes(form.flag) ? form.flag : 'unknown';

  // Anything left blank is recorded as "unknown", the same as imported records, and can be completed later.
  const color = clean(form.color) ? clean(form.color).toLowerCase() : 'unknown';
  const make = clean(form.make) ? tidyWord(form.make) : 'unknown';
  const model = clean(form.model) ? tidyWord(form.model) : null;
  const vehicle = {
    vehicleKey,
    displayName: buildDisplayName({ color, make, model }),
    color,
    make,
    model,
    bodyStyle: BODY_STYLES.includes(clean(form.bodyStyle)) ? clean(form.bodyStyle) : 'unknown',
    distinguishing: parseDistinguishing(form.distinguishing),
    plateAliases: aliasKey ? [aliasKey] : [],
    flag,
    sightings: [buildSighting({
      timestamp: ts,
      recordedAt,
      location,
      photoPaths: photoFiles.map((p) => p.path),
      flag,
      notes: form.notes,
      observer
    })],
    firstSeen: ts,
    lastSeen: ts,
    possibleDuplicate: Boolean(form.possibleDuplicate)
  };
  if (observer) vehicle.lastUpdatedBy = observer;
  const siteChecks = applySiteChecks({}, form, now);
  if (Object.keys(siteChecks).length) vehicle.siteChecks = siteChecks;
  const year = cleanYear(form.year);
  if (year !== null && hasVerifiedSite(siteChecks)) vehicle.year = year;
  const lookup = cleanPlateLookup(form.plateLookup, now);
  if (lookup) vehicle.plateLookup = lookup;
  return { vehicle, photoFiles };
}

/**
 * Append a sighting to an existing vehicle (returns a new object).
 * Blank fields leave the existing value alone; plate itself is never edited,
 * but a new plate may be added as an alias.
 * @returns {{ vehicle: object, photoFiles: {path:string, dataUrl:string}[] }}
 */
export function addSightingToVehicle(existing, form, photoDataUrls = [], location = null, now = new Date(), observerName = null, when = null) {
  const happened = validPastDate(when, now) || now;
  const ts = happened.toISOString();
  const recordedAt = now.toISOString();
  const observer = cleanObserver(observerName);
  const photoFiles = stagePhotos(existing.vehicleKey, photoDataUrls, now);
  const flag = FLAGS.includes(form.flag) ? form.flag : existing.flag;

  const next = {
    ...existing,
    color: clean(form.color) ? clean(form.color).toLowerCase() : existing.color,
    make: clean(form.make) ? tidyWord(form.make) : existing.make,
    model: clean(form.model) ? tidyWord(form.model) : (existing.model ?? null),
    bodyStyle: BODY_STYLES.includes(clean(form.bodyStyle)) ? clean(form.bodyStyle) : existing.bodyStyle,
    distinguishing: parseDistinguishing([
      ...(existing.distinguishing || []),
      ...parseDistinguishing(form.distinguishing)
    ]),
    plateAliases: [...(existing.plateAliases || [])],
    flag,
    sightings: [
      ...(existing.sightings || []),
      buildSighting({
        timestamp: ts,
        recordedAt,
        location,
        photoPaths: photoFiles.map((p) => p.path),
        flag,
        notes: form.notes,
        observer
      })
    ],
    firstSeen: tsOf(existing.firstSeen) <= happened.getTime() ? existing.firstSeen : ts,
    lastSeen: tsOf(existing.lastSeen) >= happened.getTime() ? existing.lastSeen : ts
  };
  if (observer) next.lastUpdatedBy = observer;
  const siteChecks = applySiteChecks(existing.siteChecks, form, now);
  if (Object.keys(siteChecks).length) next.siteChecks = siteChecks; else delete next.siteChecks;
  const year = cleanYear(form.year);
  if (year !== null && (hasVerifiedSite(siteChecks) || year === existing.year)) next.year = year;
  const lookup = cleanPlateLookup(form.plateLookup, now);
  if (lookup) next.plateLookup = lookup;

  const aliasKey = plateKey(form.plateState, form.plate);
  if (aliasKey && !next.plateAliases.includes(aliasKey)) next.plateAliases.push(aliasKey);
  next.displayName = buildDisplayName(next);
  return { vehicle: next, photoFiles };
}

export function createPlateRecord(plate, state, vehicleKey, plateType = 'standard', now = new Date()) {
  const ts = now.toISOString();
  return {
    plate: normalizePlate(plate),
    plateState: normalizeState(state),
    plateType: PLATE_TYPES.includes(plateType) ? plateType : 'standard',
    currentVehicleKey: vehicleKey,
    firstSeen: ts,
    updated: ts
  };
}

// ---------- merge (409 conflict handling) ----------

function union(a = [], b = []) {
  return [...new Set([...a, ...b])];
}

/**
 * Merge an incoming vehicle write onto the current remote copy.
 * - sightings: union by id (so replaying a write is idempotent)
 * - firstSeen: earliest; lastSeen: latest
 * - descriptive fields and flag: taken from whichever side has the newest
 *   sighting, so a delayed offline write cannot overwrite fresher data
 * - plateAliases / distinguishing: union
 */
export function mergeVehicle(remote, incoming) {
  if (!remote) return incoming;

  const byId = new Map();
  for (const s of [...(remote.sightings || []), ...(incoming.sightings || [])]) {
    const id = s.id || `${s.timestamp}`;
    const had = byId.get(id);
    // The copy edited most recently wins; with no edits the incoming copy replaces the remote one as before.
    if (!had || tsOf(s.editedAt) >= tsOf(had.editedAt)) byId.set(id, s);
  }
  const sightings = [...byId.values()].sort((a, b) => tsOf(a.timestamp) - tsOf(b.timestamp));

  const edited = tsOf(incoming.editedAt) > 0 || tsOf(remote.editedAt) > 0 || sightings.some((s) => s.editedAt);
  const incomingNewer = tsOf(incoming.editedAt) !== tsOf(remote.editedAt)
    ? tsOf(incoming.editedAt) > tsOf(remote.editedAt)
    : tsOf(latestSighting(incoming)?.timestamp) >= tsOf(latestSighting(remote)?.timestamp);
  const winner = incomingNewer ? incoming : remote;

  const merged = {
    ...remote,
    ...winner,
    sightings,
    distinguishing: tsOf(winner.editedAt) > 0 ? (winner.distinguishing || []) : union(remote.distinguishing, incoming.distinguishing),
    plateAliases: union(remote.plateAliases, incoming.plateAliases),
    flag: latestSighting({ sightings })?.flag || winner.flag,
    firstSeen: tsOf(remote.firstSeen) <= tsOf(incoming.firstSeen) ? remote.firstSeen : incoming.firstSeen,
    lastSeen: tsOf(remote.lastSeen) >= tsOf(incoming.lastSeen) ? remote.lastSeen : incoming.lastSeen,
    possibleDuplicate: Boolean(remote.possibleDuplicate && incoming.possibleDuplicate)
  };
  // Once a sighting has been edited, its times are the truth (an edit can move lastSeen earlier).
  if (edited && sightings.length) {
    merged.firstSeen = sightings[0].timestamp;
    merged.lastSeen = sightings[sightings.length - 1].timestamp;
  }
  if (tsOf(remote.editedAt) > 0 || tsOf(incoming.editedAt) > 0) {
    merged.editedAt = tsOf(incoming.editedAt) >= tsOf(remote.editedAt) ? incoming.editedAt : remote.editedAt;
  }
  // A registration-data answer is never lost to a write that lacks one; the newer side wins when both have one.
  const lookup = winner.plateLookup || remote.plateLookup || incoming.plateLookup;
  if (lookup) merged.plateLookup = lookup;
  else delete merged.plateLookup;
  // Site checks merge per site; the later check wins.
  const checks = { ...(remote.siteChecks || {}) };
  for (const [id, c] of Object.entries(incoming.siteChecks || {})) {
    if (!checks[id] || tsOf(c.checkedAt) >= tsOf(checks[id].checkedAt)) checks[id] = c;
  }
  if (Object.keys(checks).length) merged.siteChecks = checks;
  else delete merged.siteChecks;
  merged.displayName = buildDisplayName(merged);
  return merged;
}

export function mergePlate(remote, incoming) {
  if (!remote) return incoming;
  return {
    ...remote,
    ...incoming,
    plateState: incoming.plateState || remote.plateState,
    plateType: incoming.plateType || remote.plateType,
    firstSeen: tsOf(remote.firstSeen) <= tsOf(incoming.firstSeen) ? remote.firstSeen : incoming.firstSeen,
    updated: tsOf(remote.updated) >= tsOf(incoming.updated) ? remote.updated : incoming.updated
  };
}

// ---------- index projection (mirrors scripts/build_index.py) ----------

/**
 * Insert or replace one vehicle's entry in the index. Commutative and
 * idempotent: the entry with the newest lastSeen wins, so concurrent writers
 * and replayed writes converge on the same file. Sorted by key, like
 * scripts/build_index.py, so rebuilds produce no diff.
 */
export function mergeIndexEntry(index, entry, force = false) {
  const list = Array.isArray(index) ? index : [];
  const current = list.find((e) => e.vehicleKey === entry.vehicleKey);
  if (!force && current && tsOf(current.lastSeen) > tsOf(entry.lastSeen)) return list;
  return [...list.filter((e) => e.vehicleKey !== entry.vehicleKey), entry]
    .sort((a, b) => (a.vehicleKey < b.vehicleKey ? -1 : a.vehicleKey > b.vehicleKey ? 1 : 0));
}

/**
 * Compact search entry for data/index.json. Location comes from the most
 * recent sighting that has one.
 */
/** Descriptive fields kept in the index so the app can search by description. Unknown or empty values are left out. */
export function searchFieldsOf(vehicle) {
  const out = {};
  for (const k of ['color', 'make', 'model', 'bodyStyle']) {
    const v = vehicle[k];
    if (typeof v === 'string' && v && v !== 'unknown') out[k] = v;
  }
  if (Number.isInteger(vehicle.year)) out.year = vehicle.year;
  const feats = (vehicle.distinguishing || []).filter((f) => f && f !== 'unknown');
  if (feats.length) out.features = feats;
  return out;
}

export function indexEntryFromVehicle(vehicle) {
  const located = [...(vehicle.sightings || [])]
    .filter((s) => s.location && Number.isFinite(s.location.lat) && Number.isFinite(s.location.lng))
    .sort((a, b) => tsOf(b.timestamp) - tsOf(a.timestamp))[0];

  return {
    vehicleKey: vehicle.vehicleKey,
    displayName: vehicle.displayName,
    flag: vehicle.flag,
    lastSeen: vehicle.lastSeen,
    location: located ? { lat: located.location.lat, lng: located.location.lng } : null,
    plateAliases: vehicle.plateAliases || [],
    ...searchFieldsOf(vehicle)
  };
}


// ---------- editing your own sighting ----------

/** Same person (case-insensitive name) and saved less than SIGHTING_EDIT_WINDOW_HOURS ago. Honor system, not security. */
export function canEditSighting(sighting, observerName, now = new Date()) {
  const me = cleanObserver(observerName);
  if (!sighting || !me || !sighting.observer) return false;
  if (sighting.observer.toLowerCase() !== me.toLowerCase()) return false;
  const saved = tsOf(sighting.recordedAt || sighting.timestamp);
  return now.getTime() - saved <= SIGHTING_EDIT_WINDOW_HOURS * 3600000 && now.getTime() >= saved - 60000;
}

/**
 * Edit one sighting and (optionally) the vehicle's descriptive fields.
 * changes: { when?: Date|string|null (null = keep), location?: object|null|undefined (undefined = keep),
 *            notes?, flag?, removePhotos?: string[], vehicle?: {color, make, model, bodyStyle, distinguishing} }
 * @returns {{ vehicle: object, photoFiles: object[], removedPhotos: string[] }}
 */
export function editSightingInVehicle(existing, sightingId, changes, photoDataUrls = [], now = new Date(), observerName = null) {
  const target = (existing.sightings || []).find((s) => s.id === sightingId);
  if (!target) throw new Error('That sighting is no longer on this record.');
  if (!canEditSighting(target, observerName, now)) throw new Error(`You can edit your own sightings for ${SIGHTING_EDIT_WINDOW_HOURS} hours after saving them.`);
  const stamp = now.toISOString();
  const removed = (changes.removePhotos || []).filter((p) => (target.photos || []).includes(p));
  const added = stagePhotos(existing.vehicleKey, photoDataUrls, now);
  const when = changes.when ? validPastDate(changes.when, now) : null;
  if (changes.when && !when) throw new Error('That time is not valid.');

  const edited = { ...target, photos: [...(target.photos || []).filter((p) => !removed.includes(p)), ...added.map((p) => p.path)], editedAt: stamp };
  if (!target.recordedAt) edited.recordedAt = target.timestamp; // keep the true entry time once the event time moves
  if (when) edited.timestamp = when.toISOString();
  if (changes.location !== undefined) edited.location = changes.location || null;
  if (changes.notes !== undefined) edited.notes = clean(changes.notes) || null;
  if (changes.flag !== undefined && FLAGS.includes(changes.flag)) edited.flag = changes.flag;
  if (edited.recordedAt === edited.timestamp) delete edited.recordedAt;

  const sightings = existing.sightings.map((s) => (s.id === sightingId ? edited : s));
  const next = { ...existing, sightings, editedAt: stamp };
  const v = changes.vehicle;
  if (v) {
    if (clean(v.color)) next.color = clean(v.color).toLowerCase();
    if (clean(v.make)) next.make = tidyWord(v.make);
    next.model = clean(v.model) ? tidyWord(v.model) : null;
    if (BODY_STYLES.includes(clean(v.bodyStyle))) next.bodyStyle = clean(v.bodyStyle);
    if (v.distinguishing !== undefined) next.distinguishing = parseDistinguishing(v.distinguishing);
  }
  const ordered = [...sightings].sort((a, b) => tsOf(a.timestamp) - tsOf(b.timestamp));
  next.firstSeen = ordered[0].timestamp;
  next.lastSeen = ordered[ordered.length - 1].timestamp;
  next.flag = ordered[ordered.length - 1].flag || next.flag;
  const me = cleanObserver(observerName);
  if (me) next.lastUpdatedBy = me;
  next.displayName = buildDisplayName(next);
  return { vehicle: next, photoFiles: added, removedPhotos: removed };
}
