/**
 * storage.js
 * IndexedDB (outbox + record cache) and localStorage (token) helpers.
 *
 * Outbox item: { id, type:'save', key, payload, status, retries, lastError, created }
 *   status: 'pending' | 'failed' | 'conflict'
 * Cache item:  { key, data, kind, cachedAt }
 */

import { MAX_RETRIES } from './config.js';

const DB_NAME = 'parkingtracker-clean';
const DB_VERSION = 1;
const TOKEN_KEY = 'parkingtracker-clean.token';
const OBSERVER_KEY = 'parkingtracker-clean.observer';

export function initDB() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB is not available'));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('outbox')) {
        db.createObjectStore('outbox', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('cache')) {
        db.createObjectStore('cache', { keyPath: 'key' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function run(db, store, mode, work) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const objectStore = tx.objectStore(store);
    let result;
    const request = work(objectStore);
    if (request) request.onsuccess = () => { result = request.result; };
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

// ---- Token (localStorage; v1 only, see ADR-006) ----

export function loadToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function saveToken(token) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* storage blocked */ }
}

export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

// ---- Observer name (who is using this device; stamped on every record) ----

export function loadObserver() {
  try { return localStorage.getItem(OBSERVER_KEY); } catch { return null; }
}

export function saveObserver(name) {
  try { localStorage.setItem(OBSERVER_KEY, name); } catch { /* storage blocked */ }
}

export function clearObserver() {
  try { localStorage.removeItem(OBSERVER_KEY); } catch { /* storage blocked */ }
}

// ---- Outbox ----

export function enqueueWrite(db, { key, payload }) {
  return run(db, 'outbox', 'readwrite', (s) => s.add({
    type: 'save',
    key,
    payload,
    status: 'pending',
    retries: 0,
    lastError: null,
    created: new Date().toISOString()
  }));
}

export async function getPendingWrites(db) {
  if (!db) return [];
  const all = await run(db, 'outbox', 'readonly', (s) => s.getAll());
  return (all || []).sort((a, b) => a.id - b.id);
}

export function completeWrite(db, id) {
  return run(db, 'outbox', 'readwrite', (s) => s.delete(id));
}

async function patchWrite(db, id, patch) {
  const item = await run(db, 'outbox', 'readonly', (s) => s.get(id));
  if (!item) return;
  await run(db, 'outbox', 'readwrite', (s) => s.put({ ...item, ...patch }));
}

export async function incrementRetry(db, id, errorMessage = null) {
  const item = await run(db, 'outbox', 'readonly', (s) => s.get(id));
  if (!item) return;
  const retries = (item.retries || 0) + 1;
  await run(db, 'outbox', 'readwrite', (s) => s.put({
    ...item,
    retries,
    status: retries >= MAX_RETRIES ? 'failed' : 'pending',
    lastError: errorMessage
  }));
}

export function markStatus(db, id, status, errorMessage = null) {
  return patchWrite(db, id, { status, lastError: errorMessage });
}

/** Put failed and conflicted items back in the queue for another attempt. */
export async function resetFailed(db) {
  const all = await getPendingWrites(db);
  for (const item of all) {
    if (item.status !== 'pending') {
      await patchWrite(db, item.id, { status: 'pending', retries: 0 });
    }
  }
}

// ---- Record cache ----

export function cacheRecord(db, key, data, kind = 'record') {
  if (!db) return Promise.resolve();
  return run(db, 'cache', 'readwrite', (s) => s.put({ key, data, kind, cachedAt: Date.now() }));
}

export async function getCachedRecord(db, key) {
  if (!db) return null;
  return (await run(db, 'cache', 'readonly', (s) => s.get(key))) || null;
}

export async function listCachedByKind(db, kind) {
  if (!db) return [];
  const all = await run(db, 'cache', 'readonly', (s) => s.getAll());
  return (all || []).filter((item) => item.kind === kind);
}
