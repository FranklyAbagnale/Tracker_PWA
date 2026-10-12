import { COARSEN_DECIMALS } from './config.js';

const EARTH_RADIUS_KM = 6371.0088;

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

export function haversineDistanceKm(lat1, lng1, lat2, lng2) {
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

export function isValidCoordinate(lat, lng) {
  return (
    Number.isFinite(lat) && Number.isFinite(lng) &&
    lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180
  );
}

export function coarsenValue(value, decimals = COARSEN_DECIMALS) {
  if (decimals === null || decimals === undefined) return value;
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/** Round a {lat, lng} pair for storage. Returns null for invalid input. */
export function coarsenLocation(location, decimals = COARSEN_DECIMALS) {
  if (!location || !isValidCoordinate(location.lat, location.lng)) return null;
  const out = {
    lat: coarsenValue(location.lat, decimals),
    lng: coarsenValue(location.lng, decimals)
  };
  if (location.manual) out.manual = true;
  return out;
}

/**
 * Ask the device for its position. Resolves to null if unsupported, denied or
 * timed out: a declined permission is a valid state (ADR-007).
 */
export function getDeviceLocation({ timeoutMs = 8000 } = {}) {
  return new Promise((resolve) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      resolve(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60000 }
    );
  });
}

/**
 * Follow the device position (low power: no GPS-grade accuracy needed for a 1 km list).
 * Calls onPosition({lat, lng}) on every fix and onError(err) on failures (err.code 1 = permission denied).
 * @returns {number|null} watch id for stopWatchingLocation, or null if unsupported
 */
export function watchDeviceLocation(onPosition, onError) {
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    onError({ code: 2 });
    return null;
  }
  return navigator.geolocation.watchPosition(
    (pos) => onPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
    (err) => onError(err),
    { enableHighAccuracy: false, timeout: 30000, maximumAge: 15000 }
  );
}

export function stopWatchingLocation(id) {
  if (id !== null && id !== undefined && typeof navigator !== 'undefined' && navigator.geolocation) {
    navigator.geolocation.clearWatch(id);
  }
}

/**
 * Where to open a map for turn-by-turn directions to a recorded location.
 * Apple Maps on iPhone and iPad, Google Maps everywhere else (both open their app when it is installed).
 */
export function mapsDirectionsUrl(lat, lng, userAgent = (typeof navigator !== 'undefined' ? navigator.userAgent : ''), touchPoints = (typeof navigator !== 'undefined' ? navigator.maxTouchPoints : 0)) {
  const point = `${Number(lat)},${Number(lng)}`;
  const apple = /iPhone|iPad|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && touchPoints > 1);
  return apple
    ? `https://maps.apple.com/?daddr=${encodeURIComponent(point)}&dirflg=d`
    : `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(point)}&travelmode=driving`;
}

/** The newest sighting that has a usable location, or null. */
export function latestLocatedSighting(vehicle) {
  let best = null;
  for (const s of (vehicle && vehicle.sightings) || []) {
    if (!s.location || !isValidCoordinate(s.location.lat, s.location.lng)) continue;
    if (!best || new Date(s.timestamp) > new Date(best.timestamp)) best = s;
  }
  return best;
}
