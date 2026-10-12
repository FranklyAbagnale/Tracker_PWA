/**
 * lookup.js: the plate lookup proxy, as one portable request handler.
 *
 *   handleLookup(request, env, { fetch }) -> Response
 *
 * It uses only standard Request/Response/fetch, so the same code runs as a Cloudflare Worker (worker.js)
 * or as a plain Node service on an internal host (serve-node.mjs).
 *
 * What it does, in order:
 *   1. Requires a GitHub token (Authorization: Bearer ...) that can write to the app's repository, so only
 *      people who can already use the app can spend lookups. The token is never stored, only hashed for a
 *      5-minute "already verified" memo.
 *   2. Accepts {state, plate} for the states in ALLOWED_STATES (California only by default).
 *   3. Answers from a cache when it can (found: 30 days, not found: 1 day), so repeats cost nothing.
 *   4. Otherwise asks the provider adapter (providers/), within an optional DAILY_LIMIT.
 *   5. Returns ONLY year, make and model. VIN, owner and anything else a provider sends is dropped here.
 *
 * Environment (Worker vars or process env):
 *   PROVIDER        adapter name, default "stub"
 *   PROVIDER_KEY    the provider's API key (a secret; read by the adapter)
 *   ALLOWED_STATES  comma list, default "CA"
 *   ALLOWED_ORIGIN  CORS origin, default "*" (set it to the app's origin once deployed)
 *   REPO_OWNER / REPO_NAME   repository the caller's token must be able to write to
 *   DAILY_LIMIT     max provider calls per UTC day per instance; empty means no limit
 */

import { getProvider } from './providers/index.js';
import { NotConfiguredError, ProviderError } from './errors.js';

const DAY_MS = 24 * 60 * 60 * 1000;
const FOUND_TTL_MS = 30 * DAY_MS;
const MISS_TTL_MS = DAY_MS;
const AUTH_TTL_MS = 5 * 60 * 1000;
const PLATE_RE = /^[A-Z0-9]{1,10}$/;
const MAX_CACHE_ENTRIES = 5000;

const authMemo = new Map();   // sha256(token) -> expiry
const resultCache = new Map(); // "CA-ABC123" -> { expires, body }
const usage = { day: '', count: 0 };

/** Test hook: forget everything held in memory. */
export function resetLookupState() {
  authMemo.clear();
  resultCache.clear();
  usage.day = '';
  usage.count = 0;
}

function corsHeaders(env) {
  return {
    'access-control-allow-origin': env.ALLOWED_ORIGIN || '*',
    'access-control-allow-headers': 'authorization, content-type',
    'access-control-allow-methods': 'POST, OPTIONS',
    'access-control-max-age': '86400',
    vary: 'origin'
  };
}

function reply(env, status, body) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...corsHeaders(env) }
  });
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

function bearerToken(request) {
  const m = /^Bearer\s+(\S+)$/i.exec(request.headers.get('authorization') || '');
  return m ? m[1] : '';
}

/** The caller's token must see the repository and be able to write to it (the same test the app applies at sign-in). */
async function tokenAllowed(token, env, fetchImpl) {
  const id = await sha256Hex(token);
  const now = Date.now();
  if ((authMemo.get(id) || 0) > now) return true;
  const owner = env.REPO_OWNER || 'FranklyAbagnale';
  const repo = env.REPO_NAME || 'ParkingTracker';
  const res = await fetchImpl(`https://api.github.com/repos/${owner}/${repo}`, {
    headers: { authorization: `Bearer ${token}`, accept: 'application/vnd.github+json', 'user-agent': 'parkingtracker-lookup' }
  });
  if (!res.ok) return false;
  const info = await res.json().catch(() => ({}));
  if (info.permissions && info.permissions.push === false) return false;
  if (authMemo.size > 500) authMemo.clear();
  authMemo.set(id, now + AUTH_TTL_MS);
  return true;
}

function tidy(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, 40);
}

/** Keep only year, make and model, in a fixed shape. Returns null when there is no usable make. */
export function sanitizeVehicle(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const make = tidy(raw.make);
  if (!make) return null;
  const year = Number.parseInt(raw.year, 10);
  return {
    year: Number.isInteger(year) && year >= 1900 && year <= 2100 ? year : null,
    make,
    model: tidy(raw.model) || null
  };
}

function cacheGet(key) {
  const hit = resultCache.get(key);
  if (!hit) return null;
  if (hit.expires <= Date.now()) { resultCache.delete(key); return null; }
  return hit.body;
}

function cachePut(key, body, ttl) {
  if (resultCache.size >= MAX_CACHE_ENTRIES) resultCache.clear();
  resultCache.set(key, { expires: Date.now() + ttl, body });
}

function underDailyLimit(env) {
  const limit = Number.parseInt(env.DAILY_LIMIT, 10);
  if (!Number.isInteger(limit) || limit <= 0) return true;
  const day = new Date().toISOString().slice(0, 10);
  if (usage.day !== day) { usage.day = day; usage.count = 0; }
  return usage.count < limit;
}

export async function handleLookup(request, env = {}, { fetch: fetchImpl = fetch } = {}) {
  if (request.method === 'OPTIONS') return reply(env, 204);
  if (request.method !== 'POST') return reply(env, 405, { status: 'error', message: 'Use POST' });

  const token = bearerToken(request);
  if (!token) return reply(env, 401, { status: 'unauthorized', message: 'A GitHub token is required' });

  let input;
  try {
    input = await request.json();
  } catch {
    return reply(env, 400, { status: 'error', message: 'Body must be JSON: {"state":"CA","plate":"ABC1234"}' });
  }
  const state = String(input?.state ?? '').trim().toUpperCase();
  const plate = String(input?.plate ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const allowed = String(env.ALLOWED_STATES || 'CA').toUpperCase().split(',').map((s) => s.trim()).filter(Boolean);
  if (!allowed.includes(state)) return reply(env, 400, { status: 'unsupported_state', message: `Lookups cover ${allowed.join(', ')} only` });
  if (!PLATE_RE.test(plate)) return reply(env, 400, { status: 'error', message: 'Plate must be 1-10 letters or digits' });

  try {
    if (!(await tokenAllowed(token, env, fetchImpl))) {
      return reply(env, 401, { status: 'unauthorized', message: 'Token cannot write to the repository' });
    }
  } catch {
    return reply(env, 502, { status: 'error', message: 'Could not verify the token with GitHub' });
  }

  const key = `${state}-${plate}`;
  const cached = cacheGet(key);
  if (cached) return reply(env, 200, { ...cached, cached: true });

  const provider = getProvider(env.PROVIDER);
  if (!provider) return reply(env, 501, { status: 'not_configured', message: `Unknown provider "${env.PROVIDER}"` });
  if (!underDailyLimit(env)) return reply(env, 429, { status: 'limit', message: 'Daily lookup limit reached' });

  try {
    usage.count += 1;
    const vehicle = sanitizeVehicle(await provider.lookup({ state, plate, env }));
    const body = vehicle ? { status: 'found', vehicle } : { status: 'not_found' };
    cachePut(key, body, vehicle ? FOUND_TTL_MS : MISS_TTL_MS);
    return reply(env, 200, body);
  } catch (err) {
    if (err instanceof NotConfiguredError) {
      usage.count -= 1; // nothing was spent
      return reply(env, 501, { status: 'not_configured', message: err.message });
    }
    const message = err instanceof ProviderError ? err.message : 'The lookup provider failed';
    return reply(env, 502, { status: 'error', message });
  }
}
