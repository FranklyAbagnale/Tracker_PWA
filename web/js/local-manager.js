/**
 * local-manager.js
 * Local area filtering and ranking. Pure functions (no DOM, no network).
 *
 * Ranking is by flag first, then nearest-first within a flag:
 *   0. confirmed (red)     hidden once last seen more than 14 days ago
 *   1. suspected (orange)  always visible
 *   2. cleared (green) and pigs (blue), mixed together by distance; always visible
 *   3. unknown (yellow)    always visible, listed last
 */

import { haversineDistanceKm } from './geo.js';
import { DEFAULT_RADIUS_METERS, HIDDEN_AFTER_DAYS } from './config.js';

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

/** Accepts an index entry ({location}) or a full vehicle record ({sightings}). */
function locationOf(item) {
  if (item.location && Number.isFinite(item.location.lat) && Number.isFinite(item.location.lng)) {
    return item.location;
  }
  const located = [...(item.sightings || [])]
    .reverse()
    .find((s) => s.location && Number.isFinite(s.location.lat) && Number.isFinite(s.location.lng));
  return located ? located.location : null;
}

/** Display order of the flags. cleared and pigs share a tier so they interleave by distance. */
export function tierOf(flag) {
  if (flag === 'confirmed') return 0;
  if (flag === 'suspected') return 1;
  if (flag === 'cleared' || flag === 'pigs') return 2;
  return 3;
}

export function rankLocalResults(
  items,
  userLocation,
  radiusMeters = DEFAULT_RADIUS_METERS,
  now = new Date()
) {
  const radiusKm = radiusMeters / 1000;
  const ranked = [];

  for (const item of items) {
    if (!item.lastSeen) continue;
    const age = now.getTime() - new Date(item.lastSeen).getTime();
    const tier = tierOf(item.flag);

    if (item.flag === 'confirmed' && age > HIDDEN_AFTER_DAYS * DAY_MS) continue;

    const loc = locationOf(item);
    if (!loc) continue;

    const distance = haversineDistanceKm(userLocation.lat, userLocation.lng, loc.lat, loc.lng);
    if (distance > radiusKm) continue;

    ranked.push({ ...item, distance, ageSinceLastSeen: age, tier });
  }

  return ranked.sort((a, b) => a.tier - b.tier || a.distance - b.distance);
}

export function formatDistance(km) {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
}

export function formatTimeSince(date, now = new Date()) {
  const diff = now.getTime() - new Date(date).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / HOUR_MS);
  const days = Math.floor(diff / DAY_MS);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

export function formatLocalResult(item, distanceKm = item.distance, now = new Date()) {
  return {
    vehicleKey: item.vehicleKey,
    displayName: item.displayName,
    flag: item.flag,
    plateAliases: item.plateAliases || [],
    distance: formatDistance(distanceKm),
    timeSince: formatTimeSince(item.lastSeen, now)
  };
}
