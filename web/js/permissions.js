/**
 * permissions.js
 * Ask for location and camera while the app is open ("while using the app").
 * Nothing runs in the background and nothing is watched: location is a one-shot
 * read and the camera is switched on and straight off again, only so the
 * browser records the person's answer now instead of in the middle of a save.
 */

const ASKED_KEY = 'parkingtracker-clean.permissionsAsked';
const DISMISSED_KEY = 'parkingtracker-clean.permissionsDismissed';

/** @returns {Promise<'granted'|'denied'|'prompt'|'unknown'>} */
async function query(name) {
  try {
    const status = await navigator.permissions.query({ name });
    return status.state;
  } catch {
    return 'unknown'; // Permissions API (or this permission name) not supported, e.g. Safari for camera
  }
}

function read(storage, key) {
  try { return storage.getItem(key); } catch { return null; }
}

function write(storage, key, value) {
  try { storage.setItem(key, value); } catch { /* storage blocked */ }
}

export async function getPermissionStatus() {
  const [location, camera] = await Promise.all([query('geolocation'), query('camera')]);
  return { location, camera };
}

/**
 * Should the "allow location and camera" card be shown?
 * Not when both are settled (granted or unavailable), not once dismissed this session, and not when the
 * browser cannot report state and the person has already been asked once.
 */
export function shouldAsk(status) {
  const open = [status.location, status.camera].filter((s) => s === 'prompt' || s === 'unknown' || s === 'denied');
  if (open.length === 0) return false; // granted, or the device has no such hardware/API
  if (read(sessionStorage, DISMISSED_KEY)) return false;
  const unknown = status.location === 'unknown' || status.camera === 'unknown';
  if (unknown && read(localStorage, ASKED_KEY)) return false;
  return true;
}

export function dismissForSession() {
  write(sessionStorage, DISMISSED_KEY, '1');
}

function requestLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) { resolve('unavailable'); return; }
    navigator.geolocation.getCurrentPosition(
      () => resolve('granted'),
      (err) => resolve(err && err.code === 1 ? 'denied' : 'granted'), // 2/3: allowed, just no fix right now
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
    );
  });
}

async function requestCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return 'unavailable';
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    stream.getTracks().forEach((track) => track.stop());
    return 'granted';
  } catch (err) {
    return err && (err.name === 'NotAllowedError' || err.name === 'SecurityError') ? 'denied' : 'unavailable';
  }
}

/** Must be called from a tap. Asks one after the other so prompts do not stack. */
export async function requestPermissions({ location: wantLocation = true } = {}) {
  write(localStorage, ASKED_KEY, '1');
  const location = wantLocation ? await requestLocation() : 'skipped';
  const camera = await requestCamera();
  return { location, camera };
}
