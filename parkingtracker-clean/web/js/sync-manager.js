/**
 * sync-manager.js
 * Offline outbox flushing. Every save goes through the outbox, so the online
 * and offline paths are the same code.
 */

import * as GitHub from './github.js';
import { indexEntryFromVehicle } from './vehicle-manager.js';
import {
  getPendingWrites, completeWrite, incrementRetry, markStatus, resetFailed
} from './storage.js';

let inFlight = null;

async function processItem(item, token) {
  const { vehicle, plate, photos = [], removePhotos = [], edited = false } = item.payload;
  for (const photo of photos) {
    await GitHub.putPhoto(photo.path, photo.dataUrl, token);
  }
  const merged = await GitHub.saveVehicle(vehicle, token);
  if (plate) await GitHub.savePlate(plate, token);
  // Last, and from the merged record, so the index reflects what is actually stored.
  // Idempotent: if this fails the whole item is retried safely.
  await GitHub.saveIndexEntry(indexEntryFromVehicle(merged), token, edited);
  // After the record no longer points at them, so a failure here leaves a harmless orphan, never a broken link.
  for (const path of removePhotos) {
    if (!(merged.sightings || []).some((s) => (s.photos || []).includes(path))) await GitHub.deletePhoto(path, token);
  }
}

async function flush(db, token, includeFailed) {
  const all = await getPendingWrites(db);
  const queue = all.filter((i) => includeFailed || i.status === 'pending');
  const result = { synced: 0, failed: 0, conflicts: 0, stopped: null };

  for (const item of queue) {
    try {
      await processItem(item, token);
      await completeWrite(db, item.id);
      result.synced++;
    } catch (err) {
      if (err instanceof GitHub.NetworkError) { result.stopped = 'offline'; break; }
      if (err instanceof GitHub.AuthError) { result.stopped = 'auth'; result.message = err.message; break; }
      if (err instanceof GitHub.ConflictError) {
        await markStatus(db, item.id, 'conflict', err.message);
        result.conflicts++;
        continue;
      }
      console.error(`Sync failed for ${item.key}:`, err);
      await incrementRetry(db, item.id, err.message);
      result.failed++;
    }
  }
  return result;
}

/**
 * Flush the outbox. Concurrent calls share one run. Stops early when the
 * device is offline or the token is rejected (retrying cannot help).
 */
export function flushOutbox(db, token, { includeFailed = false } = {}) {
  if (!db || !token) return Promise.resolve({ synced: 0, failed: 0, conflicts: 0, stopped: 'unavailable' });
  if (!inFlight) {
    inFlight = flush(db, token, includeFailed).finally(() => { inFlight = null; });
  }
  return inFlight;
}

/** Manual retry: re-queue failed and conflicted items, then flush. */
export async function retryFailed(db, token) {
  await resetFailed(db);
  return flushOutbox(db, token, { includeFailed: true });
}

export async function getSyncStatus(db) {
  const items = await getPendingWrites(db);
  const count = (status) => items.filter((i) => i.status === status).length;
  return {
    total: items.length,
    pending: count('pending'),
    failed: count('failed'),
    conflict: count('conflict'),
    items: items.map((i) => ({ key: i.key, status: i.status, retries: i.retries, lastError: i.lastError }))
  };
}
