// Turns what a person types into coordinates for a "previous sighting": "lat, lng", a map link, or an address.
// Address lookup uses OpenStreetMap Nominatim and only runs when the person taps Find (one request per tap).
import { isValidCoordinate } from './geo.js';

const NUM = '(-?\\d{1,3}(?:\\.\\d+)?)';
const PATTERNS = [
  new RegExp(`^\\s*${NUM}\\s*[,; ]\\s*${NUM}\\s*$`),               // 37.77, -122.41
  new RegExp(`@${NUM},${NUM}`),                                      // google.com/maps/@lat,lng,15z
  new RegExp(`!3d${NUM}!4d${NUM}`),                                  // google place links
  new RegExp(`[?&](?:q|query|ll|center|destination)=${NUM}(?:,|%2C)${NUM}`), // ?q=lat,lng
  new RegExp(`[?&]mlat=${NUM}&mlon=${NUM}`),                         // openstreetmap marker
  new RegExp(`#map=\\d+/${NUM}/${NUM}`)                              // openstreetmap view
];

/** @returns {{lat:number,lng:number}|null} */
export function parseLatLng(text) {
  const s = String(text || '').trim();
  if (!s) return null;
  for (const re of PATTERNS) {
    const m = re.exec(s);
    if (m) {
      const lat = Number(m[1]);
      const lng = Number(m[2]);
      if (isValidCoordinate(lat, lng)) return { lat, lng };
    }
  }
  return null;
}

/** Look an address up. Resolves to {lat,lng,label} or null (not found or offline). */
export async function searchAddress(query, fetchImpl = fetch) {
  const q = String(query || '').trim();
  if (!q) return null;
  try {
    const res = await fetchImpl(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=${encodeURIComponent(q)}`,
      { headers: { Accept: 'application/json' } });
    if (!res.ok) return null;
    const rows = await res.json();
    const hit = Array.isArray(rows) ? rows[0] : null;
    if (!hit) return null;
    const lat = Number(hit.lat);
    const lng = Number(hit.lon);
    return isValidCoordinate(lat, lng) ? { lat, lng, label: String(hit.display_name || '') } : null;
  } catch {
    return null;
  }
}

/** Link to view a point on the map (shown so the person can confirm the pin before saving). */
export const osmViewUrl = (lat, lng) => `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`;
