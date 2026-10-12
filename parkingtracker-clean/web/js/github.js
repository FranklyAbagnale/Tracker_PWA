/**
 * github.js
 * GitHub contents-API wrappers with stale-SHA (409) merge-and-retry.
 * One retry only (see "Concurrency and Conflicts"): a second conflict raises
 * ConflictError and the item stays queued for manual retry.
 */

import { REPO_OWNER, REPO_NAME, REPO_BRANCH } from './config.js';
import { mergeVehicle, mergePlate, mergeIndexEntry } from './vehicle-manager.js';

const API = 'https://api.github.com';

export class GitHubError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = 'GitHubError';
    this.status = status;
  }
}
export class NetworkError extends GitHubError {
  constructor(message = 'Network unavailable') { super(message, 0); this.name = 'NetworkError'; }
}
export class AuthError extends GitHubError {
  constructor(message, status) { super(message, status); this.name = 'AuthError'; }
}
export class ConflictError extends GitHubError {
  constructor(message) { super(message, 409); this.name = 'ConflictError'; }
}

// ---------- low level ----------

function repoUrl(path = '') {
  return `${API}/repos/${REPO_OWNER}/${REPO_NAME}${path}`;
}

function contentsUrl(path) {
  return repoUrl(`/contents/${path.split('/').map(encodeURIComponent).join('/')}`);
}

async function request(url, token, { method = 'GET', body, accept } = {}) {
  const headers = {
    Accept: accept || 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    Authorization: `Bearer ${token}`
  };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  try {
    return await fetch(url, {
      method,
      headers,
      cache: 'no-store',
      body: body !== undefined ? JSON.stringify(body) : undefined
    });
  } catch {
    throw new NetworkError();
  }
}

async function errorFor(res) {
  let message = res.statusText || `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && body.message) message = body.message;
  } catch { /* no JSON body */ }

  if (res.status === 401) return new AuthError(`Token rejected: ${message}`, 401);
  if (res.status === 403) {
    if (res.headers.get('x-ratelimit-remaining') === '0') {
      return new GitHubError(`GitHub rate limit reached: ${message}`, 403);
    }
    return new AuthError(`Token lacks permission: ${message}`, 403);
  }
  return new GitHubError(message, res.status);
}

function encodeBase64Utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

function decodeBase64Utf8(b64) {
  const binary = atob(b64.replace(/\s/g, ''));
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

// ---------- file access ----------

/** @returns {Promise<{data:any, sha:string}|null>} null when the file does not exist */
async function getFile(path, token) {
  const res = await request(`${contentsUrl(path)}?ref=${encodeURIComponent(REPO_BRANCH)}`, token);
  if (res.status === 404) return null;
  if (!res.ok) throw await errorFor(res);

  const body = await res.json();
  if (Array.isArray(body)) throw new GitHubError(`${path} is a directory`, 400);

  let text;
  if (body.content) {
    text = decodeBase64Utf8(body.content);
  } else {
    // Files over 1 MB come back without inline content.
    const raw = await request(`${contentsUrl(path)}?ref=${encodeURIComponent(REPO_BRANCH)}`, token, {
      accept: 'application/vnd.github.raw+json'
    });
    if (!raw.ok) throw await errorFor(raw);
    text = await raw.text();
  }
  return { data: JSON.parse(text), sha: body.sha };
}

async function putFile(path, base64Content, message, token, sha) {
  const body = { message, content: base64Content, branch: REPO_BRANCH };
  if (sha) body.sha = sha;
  const res = await request(contentsUrl(path), token, { method: 'PUT', body });
  if (!res.ok) throw await errorFor(res);
  return res.json();
}

/**
 * Read-modify-write a JSON file. `produce(remoteData|null)` returns the new
 * content. A stale SHA (409, or 422 "sha wasn't supplied") triggers a re-read
 * and re-merge, `attempts` times in all (default 2 = one retry) before giving up.
 * Resolves to the merged content that was written.
 */
async function writeJson(path, token, message, produce, attempts = 2) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    const remote = await getFile(path, token);
    const next = produce(remote ? remote.data : null);
    try {
      await putFile(
        path,
        encodeBase64Utf8(`${JSON.stringify(next, null, 2)}\n`),
        message,
        token,
        remote ? remote.sha : undefined
      );
      return next;
    } catch (err) {
      const stale = err instanceof GitHubError && (err.status === 409 || err.status === 422);
      if (!stale) throw err;
    }
  }
  throw new ConflictError(`Conflict writing ${path}; try again`);
}

// ---------- records ----------

export async function getVehicle(vehicleKey, token) {
  const file = await getFile(`data/vehicles/${vehicleKey}.json`, token);
  return file ? file.data : null;
}

/** @param {string} key plate key: <state>-<plate>, e.g. CA-7ABC123 */
export async function getPlate(key, token) {
  const file = await getFile(`data/plates/${key}.json`, token);
  return file ? file.data : null;
}

/** data/index.json is a derived projection; a missing file means "empty". */
export async function getIndex(token) {
  const file = await getFile('data/index.json', token);
  return file && Array.isArray(file.data) ? file.data : [];
}

/** @returns {Promise<object>} the merged vehicle as written */
export function saveVehicle(vehicle, token) {
  return writeJson(
    `data/vehicles/${vehicle.vehicleKey}.json`,
    token,
    `Add/update vehicle ${vehicle.vehicleKey}`,
    (remote) => mergeVehicle(remote, vehicle)
  );
}

/**
 * Update this vehicle's entry in data/index.json. The app does this itself
 * (rather than a workflow) so that field activity never consumes Actions
 * minutes. The merge is commutative, so extra attempts under contention are safe.
 */
export function saveIndexEntry(entry, token, force = false) {
  return writeJson(
    'data/index.json',
    token,
    `Update index for ${entry.vehicleKey}`,
    (remote) => mergeIndexEntry(remote, entry, force),
    4
  );
}

export function savePlate(plate, token) {
  const key = `${plate.plateState}-${plate.plate}`;
  return writeJson(
    `data/plates/${key}.json`,
    token,
    `Add/update plate ${key}`,
    (remote) => mergePlate(remote, plate)
  );
}

// ---------- photos ----------

/** Upload a photo file. Photos are uploaded before the record that references them. */
export async function putPhoto(path, dataUrl, token) {
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
  try {
    await putFile(path, base64, `Add photo ${path}`, token);
  } catch (err) {
    // Replaying a queued write: the photo already landed on an earlier attempt.
    const exists = err instanceof GitHubError && err.status === 422 && /sha|exist/i.test(err.message);
    if (!exists) throw err;
  }
}

/** Delete a photo file. A photo that is already gone counts as deleted (safe to replay). */
export async function deletePhoto(path, token) {
  const res = await request(`${contentsUrl(path)}?ref=${encodeURIComponent(REPO_BRANCH)}`, token);
  if (res.status === 404) return;
  if (!res.ok) throw await errorFor(res);
  const { sha } = await res.json();
  const del = await request(contentsUrl(path), token, { method: 'DELETE', body: { message: `Remove photo ${path}`, sha, branch: REPO_BRANCH } });
  if (!del.ok && del.status !== 404) throw await errorFor(del);
}

/** Fetch a photo through the API (works for private repos too) as a blob: URL. */
export async function fetchPhotoBlobUrl(path, token) {
  const res = await request(`${contentsUrl(path)}?ref=${encodeURIComponent(REPO_BRANCH)}`, token, {
    accept: 'application/vnd.github.raw+json'
  });
  if (!res.ok) throw await errorFor(res);
  return URL.createObjectURL(await res.blob());
}

// ---------- token check ----------

/** Confirms the token can reach the repo and has write access. */
export async function checkAccess(token) {
  const res = await request(repoUrl(), token);
  if (res.status === 404) {
    throw new AuthError(`Token cannot see ${REPO_OWNER}/${REPO_NAME} (check repository access)`, 404);
  }
  if (!res.ok) throw await errorFor(res);
  const repo = await res.json();
  if (repo.permissions && repo.permissions.push === false) {
    throw new AuthError('Token has read-only access; Contents: Read and write is required', 403);
  }
  return repo;
}
