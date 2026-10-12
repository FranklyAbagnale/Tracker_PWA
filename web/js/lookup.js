/**
 * lookup.js
 * Plate lookup client. Asks the proxy in api/ for year, make and model of a California plate (see config.js).
 * The VIN is never requested or kept. Pure helpers (compare, build) have no DOM or network access.
 */

import { LOOKUP_URL, LOOKUP_STATES, LOOKUP_TIMEOUT_MS } from './config.js';
import { normalizePlate, splitPlateKey } from './matching.js';

export const lookupEnabled = (state) => Boolean(LOOKUP_URL) && LOOKUP_STATES.includes(state);

const norm = (s) => String(s ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');

/** "Unknown" is what the XML import writes for a make it could not read. */
const isBlank = (s) => norm(s) === '' || norm(s) === 'unknown';

/** True when the vehicle's make or model is missing, so registration data would add something. */
export function detailsUnknown(vehicle) {
  return isBlank(vehicle?.make) || isBlank(vehicle?.model);
}

/** The first plate alias in a state we can look up, or null. */
export function lookupKeyFor(vehicle) {
  return (vehicle?.plateAliases || []).find((k) => {
    const parts = splitPlateKey(k);
    return parts && lookupEnabled(parts.state);
  }) || null;
}

/**
 * Compare what a person entered with the registration answer.
 * make: both agree. model: both agree ("Civic" matches "Civic LX"), or null when no model was entered.
 */
export function compareToLookup(entered, found) {
  const make = !isBlank(entered?.make) && norm(entered.make) === norm(found?.make);
  if (isBlank(entered?.model)) return { make, model: null };
  const a = norm(entered.model);
  const b = norm(found?.model);
  return { make, model: Boolean(a && b && (a === b || b.startsWith(a) || a.startsWith(b))) };
}

/**
 * The record to store on a vehicle: the registration answer, but only when make AND model were checked
 * and agree. Anything else (no model entered, a mismatch, no answer) stores nothing.
 */
export function buildPlateLookup(entered, key, found, now = new Date()) {
  if (!key || !found || found.status === 'not_found') return null;
  const vehicle = found.vehicle || found;
  const c = compareToLookup(entered, vehicle);
  if (!c.make || c.model !== true) return null;
  return { plate: key, year: vehicle.year ?? null, make: vehicle.make, model: vehicle.model, checkedAt: now.toISOString() };
}

export const lookupText = (v) => [v?.year, v?.make, v?.model].filter(Boolean).join(' ');

/**
 * @returns {Promise<{status: 'found', vehicle: {year, make, model}} | {status: string, message?: string}>}
 *   status: found | not_found | not_configured | unauthorized | limit | offline | error
 */
export async function lookupVehicle(state, plate, token, { fetchImpl = fetch, url = LOOKUP_URL, timeoutMs = LOOKUP_TIMEOUT_MS } = {}) {
  if (!url) return { status: 'not_configured' };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ state, plate: normalizePlate(plate) }),
      signal: controller.signal
    });
    const body = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) return { status: 'unauthorized', message: body.message };
    if (res.status === 501) return { status: 'not_configured', message: body.message };
    if (res.status === 429) return { status: 'limit', message: body.message };
    if (!res.ok) return { status: 'error', message: body.message || `HTTP ${res.status}` };
    if (body.status === 'found' && body.vehicle && body.vehicle.make) {
      const { year, make, model } = body.vehicle; // keep only these three, whatever else a proxy sends
      return { status: 'found', vehicle: { year: Number.isInteger(year) ? year : null, make, model: model || null } };
    }
    return { status: body.status === 'not_found' ? 'not_found' : 'error', message: body.message };
  } catch {
    return { status: 'offline' };
  } finally {
    clearTimeout(timer);
  }
}
