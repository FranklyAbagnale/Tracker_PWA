/**
 * index-manager.js
 * Loads data/index.json with a 24 h cache, then overlays records this device
 * has saved or viewed so its own fresh writes show up before the server-side
 * index rebuild catches up.
 */

import * as GitHub from './github.js';
import { cacheRecord, getCachedRecord, listCachedByKind } from './storage.js';
import { indexEntryFromVehicle } from './vehicle-manager.js';
import { INDEX_MAX_AGE_HOURS, SIGHTING_EDIT_WINDOW_HOURS } from './config.js';

const INDEX_KEY = 'index';

const EDIT_WINDOW_MS = SIGHTING_EDIT_WINDOW_HOURS * 3600000;

/**
 * Should this device's copy of a vehicle replace the shared index entry? Yes when it is at least as recent, or when
 * it was edited here within the edit window (an edit can move lastSeen earlier, which `>=` alone would ignore).
 */
export function preferLocalEntry(local, remote, vehicle, now = Date.now()) {
  if (!remote) return true;
  if (new Date(local.lastSeen) >= new Date(remote.lastSeen)) return true;
  const edited = Date.parse(vehicle && vehicle.editedAt);
  return Number.isFinite(edited) && now - edited <= EDIT_WINDOW_MS;
}

async function overlayLocal(db, entries) {
  const byKey = new Map(entries.map((e) => [e.vehicleKey, e]));
  for (const cached of await listCachedByKind(db, 'vehicle')) {
    const local = indexEntryFromVehicle(cached.data);
    const remote = byKey.get(local.vehicleKey);
    if (preferLocalEntry(local, remote, cached.data)) byKey.set(local.vehicleKey, local);
  }
  return [...byKey.values()];
}

/**
 * @returns {Promise<{entries:object[], source:string, fetchedAt:number|null}>}
 *   source: 'network' | 'cache' | 'stale-cache' | 'offline-empty'
 */
export async function loadIndex(db, token, { force = false } = {}) {
  const cached = await getCachedRecord(db, INDEX_KEY);
  const fresh = cached && Date.now() - cached.cachedAt < INDEX_MAX_AGE_HOURS * 3600 * 1000;

  let entries;
  let source;
  let fetchedAt = cached ? cached.cachedAt : null;

  if (!force && fresh) {
    entries = cached.data;
    source = 'cache';
  } else {
    try {
      entries = await GitHub.getIndex(token);
      await cacheRecord(db, INDEX_KEY, entries, 'index');
      source = 'network';
      fetchedAt = Date.now();
    } catch (err) {
      if (!(err instanceof GitHub.NetworkError)) throw err;
      entries = cached ? cached.data : [];
      source = cached ? 'stale-cache' : 'offline-empty';
    }
  }

  return { entries: await overlayLocal(db, entries), source, fetchedAt };
}

/** Startup freshness check: refresh the cached index if older than 24 h. Never throws. */
export async function refreshIndexIfStale(db, token) {
  try {
    await loadIndex(db, token);
  } catch (err) {
    console.warn('Index refresh skipped:', err.message);
  }
}
