/**
 * plate-manager.js
 * Plate lookup (exact, then fuzzy via the index) and the update-with-sighting flow.
 */

import { normalizePlate, normalizeState, plateKey, splitPlateKey, stateMatches, computePlateSimilarity } from './matching.js';
import * as GitHub from './github.js';
import { cacheRecord, listCachedByKind, enqueueWrite } from './storage.js';
import { loadIndex } from './index-manager.js';
import { addSightingToVehicle, editSightingInVehicle, createPlateRecord } from './vehicle-manager.js';

const SIMILARITY_THRESHOLD = 0.75;

/** Fewer characters than this only find an exact plate; this many or more find any plate containing them. */
export const PARTIAL_MIN = 3;
export const LIVE_MIN = 2; // plates are listed while typing from this many characters
export const MAX_LISTED = 10; // how many vehicles a list shows at first
export const MAX_LISTED_MORE = 20; // 'View more' adds up to this many (so 30 in all)

/**
 * Index entries with a plate containing `query` (in `state`, or any state when state is null),
 * best first: exact plate, then plates starting with it, then plates containing it; newest first within each.
 */
export function rankPlateMatches(entries, query, state = null) {
  const ranked = [];
  for (const entry of entries) {
    let best = null;
    for (const key of entry.plateAliases || []) {
      const parts = splitPlateKey(key);
      if (!parts || (state && !stateMatches(parts.state, state))) continue;
      const at = parts.plate.indexOf(query);
      if (at === -1) continue;
      const rank = parts.plate === query ? 0 : at === 0 ? 1 : 2;
      if (best === null || rank < best) best = rank;
    }
    if (best !== null) ranked.push({ entry, rank: best });
  }
  return ranked
    .sort((a, b) => a.rank - b.rank || String(b.entry.lastSeen).localeCompare(String(a.entry.lastSeen)))
    .map((r) => r.entry);
}

/**
 * One row per matching plate (not per vehicle), so every plate is listed once.
 * kind 'exact': the plate is the search text. kind 'partial': it contains it.
 * Exact rows come first (newest sighting first); partial rows follow in alphanumeric order.
 * @returns {{entry: object, key: string, state: string, plate: string, kind: 'exact'|'partial'}[]}
 */
export function plateMatchRows(entries, query, state = null) {
  const rows = [];
  for (const entry of entries) {
    const seen = new Set();
    for (const key of entry.plateAliases || []) {
      const parts = splitPlateKey(key);
      if (!parts || seen.has(key) || (state && !stateMatches(parts.state, state)) || !parts.plate.includes(query)) continue;
      seen.add(key);
      rows.push({ entry, key, state: parts.state, plate: parts.plate, kind: parts.plate === query ? 'exact' : 'partial' });
    }
  }
  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  return rows.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'exact' ? -1 : 1;
    if (a.kind === 'exact') return cmp(String(b.entry.lastSeen), String(a.entry.lastSeen)) || cmp(a.key, b.key);
    return cmp(a.plate, b.plate) || cmp(a.state, b.state) || cmp(a.entry.vehicleKey, b.entry.vehicleKey);
  });
}

/** States under which this entry has a plate containing `query` (e.g. ['CA', 'XX']). */
export function matchingStates(entry, query) {
  const out = [];
  for (const key of entry.plateAliases || []) {
    const parts = splitPlateKey(key);
    if (parts && parts.plate.includes(query) && !out.includes(parts.state)) out.push(parts.state);
  }
  return out;
}

/** Search value meaning "whatever state it was recorded under". */
export const ANY_STATE = 'ANY';

/** Index entries that carry exactly this plate, in any state. */
export function entriesWithPlate(entries, normalized) {
  return entries.filter((e) => (e.plateAliases || []).some((k) => {
    const parts = splitPlateKey(k);
    return parts && parts.plate === normalized;
  }));
}

/**
 * Network first, cache only when offline, so edits made on another device are
 * never hidden by a stale local copy.
 * `state` is a state code, or ANY_STATE to find the plate under whichever state it was saved with
 * (most imported plates have an unknown state, XX).
 * With PARTIAL_MIN or more characters this is a "contains" search: one match opens the vehicle, several are listed.
 * @returns {{vehicle: object|null, matches: object[], more: number, similar: object[], offline: boolean}}
 *   matches: every vehicle to pick from (the screen lists MAX_LISTED and offers state filters)
 */
export async function lookupPlate(plate, state, db, token) {
  const normalized = normalizePlate(plate);
  if (!normalized) return { vehicle: null, matches: [], similar: [], offline: false };
  if (normalized.length >= PARTIAL_MIN) return searchPlates(normalized, state === ANY_STATE ? null : normalizeState(state), db, token);
  if (state === ANY_STATE) return lookupAnyState(normalized, db, token);
  const key = plateKey(state, normalized);

  try {
    const plateRecord = await GitHub.getPlate(key, token);
    if (plateRecord) {
      const vehicle = await GitHub.getVehicle(plateRecord.currentVehicleKey, token);
      if (vehicle) {
        await cacheRecord(db, `vehicle:${vehicle.vehicleKey}`, vehicle, 'vehicle');
        return { vehicle, matches: [], similar: [], offline: false };
      }
    }
    return { vehicle: null, matches: [], similar: await findSimilarPlates(normalized, db, token), offline: false };
  } catch (err) {
    if (!(err instanceof GitHub.NetworkError)) throw err;
    const cached = (await listCachedByKind(db, 'vehicle'))
      .map((c) => c.data)
      .find((v) => (v.plateAliases || []).includes(key));
    return { vehicle: cached || null, matches: [], similar: [], offline: true };
  }
}

async function searchPlates(query, state, db, token) {
  const none = { vehicle: null, matches: [], more: 0, offline: false };
  try {
    let { entries, source } = await loadIndex(db, token);
    let found = rankPlateMatches(entries, query, state);
    if (!found.length && source !== 'network') { // the cached index may predate the plate
      ({ entries } = await loadIndex(db, token, { force: true }));
      found = rankPlateMatches(entries, query, state);
    }
    if (!found.length) { // maybe a plate the index does not have yet: try the exact record
      const record = await GitHub.getPlate(plateKey(state || 'XX', query), token);
      const vehicle = record ? await GitHub.getVehicle(record.currentVehicleKey, token) : null;
      if (vehicle) {
        await cacheRecord(db, `vehicle:${vehicle.vehicleKey}`, vehicle, 'vehicle');
        return { ...none, vehicle, similar: [] };
      }
      return { ...none, similar: await findSimilarPlates(query, db, token) };
    }
    const rows = plateMatchRows(found, query, state);
    if (rows.length === 1 && rows[0].kind === 'exact') { // one plate, and it is the one typed: open it
      const vehicle = await GitHub.getVehicle(found[0].vehicleKey, token);
      if (vehicle) {
        await cacheRecord(db, `vehicle:${vehicle.vehicleKey}`, vehicle, 'vehicle');
        return { ...none, vehicle, similar: [] };
      }
    }
    return { ...none, matches: found, similar: [] };
  } catch (err) {
    if (!(err instanceof GitHub.NetworkError)) throw err;
    const local = rankPlateMatches((await listCachedByKind(db, 'vehicle')).map((c) => c.data), query, state);
    const localRows = plateMatchRows(local, query, state);
    const openIt = localRows.length === 1 && localRows[0].kind === 'exact';
    return { ...none, vehicle: openIt ? local[0] : null, matches: openIt ? [] : local, offline: true, similar: [] };
  }
}

async function lookupAnyState(normalized, db, token) {
  const open = async (key) => {
    const vehicle = await GitHub.getVehicle(key, token);
    if (vehicle) await cacheRecord(db, `vehicle:${vehicle.vehicleKey}`, vehicle, 'vehicle');
    return vehicle;
  };
  try {
    let { entries, source } = await loadIndex(db, token);
    let matches = entriesWithPlate(entries, normalized);
    if (!matches.length && source !== 'network') { // the cached index may predate the plate
      ({ entries } = await loadIndex(db, token, { force: true }));
      matches = entriesWithPlate(entries, normalized);
    }
    if (!matches.length) { // not in the index at all: try the unknown-state record directly
      const record = await GitHub.getPlate(plateKey('XX', normalized), token);
      const vehicle = record ? await open(record.currentVehicleKey) : null;
      if (vehicle) return { vehicle, matches: [], similar: [], offline: false };
      return { vehicle: null, matches: [], similar: await findSimilarPlates(normalized, db, token), offline: false };
    }
    if (matches.length === 1) {
      const vehicle = await open(matches[0].vehicleKey);
      if (vehicle) return { vehicle, matches: [], similar: [], offline: false };
    }
    return { vehicle: null, matches, similar: [], offline: false };
  } catch (err) {
    if (!(err instanceof GitHub.NetworkError)) throw err;
    const cached = (await listCachedByKind(db, 'vehicle')).map((c) => c.data)
      .filter((v) => (v.plateAliases || []).some((k) => (splitPlateKey(k) || {}).plate === normalized));
    return { vehicle: cached.length === 1 ? cached[0] : null, matches: [], similar: [], offline: true };
  }
}

/**
 * Index entries whose plates are close to the query. Plate characters are
 * compared without the state, so the same plate under a different (or unknown)
 * state turns up too, shown with its state. It is a hint, not a match.
 */
export async function findSimilarPlates(normalized, db, token) {
  try {
    const { entries } = await loadIndex(db, token);
    return entries
      .map((entry) => {
        const best = Math.max(0, ...(entry.plateAliases || []).map((k) => {
          const parts = splitPlateKey(k);
          return parts ? computePlateSimilarity(normalized, parts.plate) : 0;
        }));
        return { entry, score: best };
      })
      .filter(({ score }) => score >= SIMILARITY_THRESHOLD) // score 1 here = same plate, different state
      .sort((a, b) => b.score - a.score)
      .slice(0, 5)
      .map(({ entry }) => entry);
  } catch {
    return [];
  }
}

/**
 * Append a sighting to an existing vehicle and queue the write.
 * Returns the updated record; the caller flushes the outbox.
 */
export async function queueVehicleUpdate(vehicle, formData, photoDataUrls, location, db, observer = null) {
  const { vehicle: updated, photoFiles } = addSightingToVehicle(
    vehicle, formData, photoDataUrls, location, new Date(), observer, formData.when
  );

  const newPlate = normalizePlate(formData.plate);
  const newKey = plateKey(formData.plateState, newPlate);
  const addsPlate = newKey && !(vehicle.plateAliases || []).includes(newKey);
  const plate = addsPlate ? createPlateRecord(newPlate, normalizeState(formData.plateState), updated.vehicleKey, formData.plateType) : null;

  await enqueueWrite(db, {
    key: updated.vehicleKey,
    payload: { vehicle: updated, plate, photos: photoFiles }
  });
  await cacheRecord(db, `vehicle:${updated.vehicleKey}`, updated, 'vehicle');
  return updated;
}

/** Queue an edit of one of the caller's own sightings (see editSightingInVehicle for `changes`). */
export async function queueSightingEdit(vehicle, sightingId, changes, photoDataUrls, db, observer = null) {
  const { vehicle: updated, photoFiles, removedPhotos } = editSightingInVehicle(
    vehicle, sightingId, changes, photoDataUrls, new Date(), observer
  );
  await enqueueWrite(db, {
    key: updated.vehicleKey,
    payload: { vehicle: updated, plate: null, photos: photoFiles, removePhotos: removedPhotos, edited: true }
  });
  await cacheRecord(db, `vehicle:${updated.vehicleKey}`, updated, 'vehicle');
  return updated;
}
