import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { handleLookup, resetLookupState, sanitizeVehicle } from '../api/lookup.js';
import { createNodeServer } from '../api/serve-node.mjs';
import {
  compareToLookup, buildPlateLookup, detailsUnknown, lookupVehicle, lookupText
} from '../web/js/lookup.js';
import {
  createVehicleRecord, addSightingToVehicle, mergeVehicle, cleanPlateLookup
} from '../web/js/vehicle-manager.js';
import { LOOKUP_URL } from '../web/js/config.js';

// ---------- proxy ----------

const gh = ({ push = true, status = 200 } = {}) => {
  const fn = async (url, init) => {
    fn.calls.push({ url, auth: init.headers.authorization });
    return new Response(JSON.stringify({ permissions: { push } }), { status });
  };
  fn.calls = [];
  return fn;
};
const call = (body, { headers = {}, method = 'POST' } = {}) => new Request('https://lookup.test/lookup', {
  method,
  headers: { 'content-type': 'application/json', authorization: 'Bearer tok_abc', ...headers },
  body: method === 'POST' ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined
});
const MOCK = { PROVIDER: 'mock' };
const ask = (body, env = MOCK, deps = { fetch: gh() }, opts) => handleLookup(call(body, opts), env, deps);

test.beforeEach(() => resetLookupState());

test('proxy: preflight and wrong method', async () => {
  const pre = await handleLookup(call(null, { method: 'OPTIONS' }), { ALLOWED_ORIGIN: 'https://app.test' });
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get('access-control-allow-origin'), 'https://app.test');
  const get = await handleLookup(call(null, { method: 'GET' }), MOCK);
  assert.equal(get.status, 405);
});

test('proxy: a GitHub token is required, and it must be able to write to the repository', async () => {
  const none = await handleLookup(new Request('https://lookup.test/', { method: 'POST', body: '{}' }), MOCK, { fetch: gh() });
  assert.equal(none.status, 401);

  const readOnly = await ask({ state: 'CA', plate: 'TST1001' }, MOCK, { fetch: gh({ push: false }) });
  assert.equal(readOnly.status, 401);

  const rejected = await ask({ state: 'CA', plate: 'TST1001' }, MOCK, { fetch: gh({ status: 401 }) });
  assert.equal(rejected.status, 401);
  assert.equal((await rejected.json()).status, 'unauthorized');
});

test('proxy: the repository comes from REPO_OWNER and REPO_NAME', async () => {
  const fetch = gh();
  await ask({ state: 'CA', plate: 'TST1001' }, { ...MOCK, REPO_OWNER: 'Acme', REPO_NAME: 'Cars' }, { fetch });
  assert.equal(fetch.calls[0].url, 'https://api.github.com/repos/Acme/Cars');
  assert.equal(fetch.calls[0].auth, 'Bearer tok_abc');
});

test('proxy: input checks (JSON, state, plate)', async () => {
  assert.equal((await ask('not json')).status, 400);
  const nv = await ask({ state: 'NV', plate: 'ABC123' });
  assert.equal(nv.status, 400);
  assert.equal((await nv.json()).status, 'unsupported_state');
  assert.equal((await ask({ state: 'CA', plate: '' })).status, 400);
  assert.equal((await ask({ state: 'CA', plate: 'WAYTOOLONGPLATE' })).status, 400);
  // ALLOWED_STATES widens the list
  assert.equal((await ask({ state: 'NV', plate: 'NEW1234' }, { ...MOCK, ALLOWED_STATES: 'CA, NV' })).status, 200);
});

test('proxy: the shipped stub answers "not configured" (501) and costs nothing', async () => {
  const res = await ask({ state: 'CA', plate: 'TST1001' }, {}, { fetch: gh() });
  assert.equal(res.status, 501);
  assert.equal((await res.json()).status, 'not_configured');
  const unknown = await ask({ state: 'CA', plate: 'TST1001' }, { PROVIDER: 'nope' });
  assert.equal(unknown.status, 501);
});

test('proxy: returns only year, make and model; VIN and owner are dropped', async () => {
  const res = await ask({ state: 'ca', plate: 'tst-1001' });
  assert.equal(res.status, 200);
  const text = await res.text();
  assert.deepEqual(JSON.parse(text), { status: 'found', vehicle: { year: 2019, make: 'HONDA', model: 'CIVIC LX' } });
  assert.ok(!/vin|owner|1HGB|Real Person/i.test(text), text);
});

test('proxy: year strings are parsed, impossible years become null, misses are reported', async () => {
  const kia = await (await ask({ state: 'CA', plate: 'NEW1234' })).json();
  assert.deepEqual(kia.vehicle, { year: 2021, make: 'Kia', model: 'Soul' });
  const odd = await (await ask({ state: 'CA', plate: 'BADYEAR' })).json();
  assert.equal(odd.vehicle.year, null);
  const miss = await (await ask({ state: 'CA', plate: 'NOSUCH1' })).json();
  assert.deepEqual(miss, { status: 'not_found' });
});

test('proxy: repeats are served from the cache and do not use the daily limit', async () => {
  const env = { ...MOCK, DAILY_LIMIT: '1' };
  const first = await ask({ state: 'CA', plate: 'NEW1234' }, env);
  assert.equal(first.status, 200);
  const again = await (await ask({ state: 'CA', plate: 'NEW1234' }, env)).json();
  assert.equal(again.cached, true);
  const other = await ask({ state: 'CA', plate: 'UNK0001' }, env);
  assert.equal(other.status, 429);
});

test('proxy: a verified token is remembered, so GitHub is asked once', async () => {
  const fetch = gh();
  await ask({ state: 'CA', plate: 'NEW1234' }, MOCK, { fetch });
  await ask({ state: 'CA', plate: 'UNK0001' }, MOCK, { fetch });
  assert.equal(fetch.calls.length, 1);
});

test('proxy: a GitHub outage is a 502, not a pass', async () => {
  const res = await ask({ state: 'CA', plate: 'NEW1234' }, MOCK, { fetch: async () => { throw new Error('down'); } });
  assert.equal(res.status, 502);
});

test('sanitizeVehicle keeps only the three fields and needs a make', () => {
  assert.deepEqual(sanitizeVehicle({ year: '2020', make: ' Toyota ', model: 'Camry', vin: 'X', owner: 'Y' }), { year: 2020, make: 'Toyota', model: 'Camry' });
  assert.equal(sanitizeVehicle({ year: 2020, model: 'Camry' }), null);
  assert.equal(sanitizeVehicle(null), null);
  assert.equal(sanitizeVehicle({ make: 'Ford' }).model, null);
});

test('node wrapper serves the same handler over HTTP', async () => {
  const server = createNodeServer(MOCK, { fetch: gh() });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const found = await fetch(base, {
      method: 'POST', headers: { authorization: 'Bearer tok_abc', 'content-type': 'application/json' },
      body: JSON.stringify({ state: 'CA', plate: 'NEW1234' })
    });
    assert.equal(found.status, 200);
    assert.equal((await found.json()).vehicle.make, 'Kia');
    const pre = await fetch(base, { method: 'OPTIONS' });
    assert.equal(pre.status, 204);
    const huge = await fetch(base, { method: 'POST', body: 'x'.repeat(9000) });
    assert.equal(huge.status, 413);
  } finally {
    server.close();
  }
});

// ---------- client helpers ----------

test('compareToLookup: make must agree; model may be a prefix either way', () => {
  const found = { year: 2019, make: 'HONDA', model: 'CIVIC LX' };
  assert.deepEqual(compareToLookup({ make: 'Honda', model: 'Civic' }, found), { make: true, model: true });
  assert.deepEqual(compareToLookup({ make: 'honda', model: 'civic lx sport' }, found), { make: true, model: true });
  assert.deepEqual(compareToLookup({ make: 'Honda', model: 'Accord' }, found), { make: true, model: false });
  assert.deepEqual(compareToLookup({ make: 'Toyota', model: 'Civic' }, found), { make: false, model: true });
  assert.deepEqual(compareToLookup({ make: 'Honda', model: '' }, found), { make: true, model: null });
  assert.deepEqual(compareToLookup({ make: 'Unknown', model: 'Civic' }, found).make, false);
  assert.equal(compareToLookup({ make: 'Ford', model: 'F-150' }, { make: 'Ford', model: 'F150' }).model, true);
});

test('buildPlateLookup stores the answer only when make and model were checked and agree', () => {
  const found = { status: 'found', vehicle: { year: 2019, make: 'Honda', model: 'Civic LX' } };
  const now = new Date('2026-10-10T12:00:00Z');
  assert.deepEqual(buildPlateLookup({ make: 'Honda', model: 'Civic' }, 'CA-TST1001', found, now),
    { plate: 'CA-TST1001', year: 2019, make: 'Honda', model: 'Civic LX', checkedAt: '2026-10-10T12:00:00.000Z' });
  assert.equal(buildPlateLookup({ make: 'Honda', model: '' }, 'CA-TST1001', found, now), null, 'no model entered');
  assert.equal(buildPlateLookup({ make: 'Honda', model: 'Accord' }, 'CA-TST1001', found, now), null, 'model differs');
  assert.equal(buildPlateLookup({ make: 'Honda', model: 'Civic' }, 'CA-TST1001', { status: 'not_found' }, now), null);
  assert.equal(buildPlateLookup({ make: 'Honda', model: 'Civic' }, '', found, now), null);
});

test('detailsUnknown flags a missing or "Unknown" make or model', () => {
  assert.equal(detailsUnknown({ make: 'Unknown', model: null }), true);
  assert.equal(detailsUnknown({ make: 'Honda', model: null }), true);
  assert.equal(detailsUnknown({ make: 'Honda', model: 'unknown' }), true);
  assert.equal(detailsUnknown({ make: 'Honda', model: 'Civic' }), false);
});

test('lookupText joins what is known', () => {
  assert.equal(lookupText({ year: 2019, make: 'Honda', model: 'Civic' }), '2019 Honda Civic');
  assert.equal(lookupText({ year: null, make: 'Honda', model: null }), 'Honda');
});

test('lookupVehicle maps proxy answers to statuses and sends only state and plate', async () => {
  let sent;
  const reply = (status, body) => async (url, init) => { sent = { url, init }; return new Response(JSON.stringify(body), { status }); };
  const run = (fetchImpl) => lookupVehicle('CA', 'tst-1001', 'tok', { fetchImpl, url: 'https://p.test/lookup', timeoutMs: 50 });

  const found = await run(reply(200, { status: 'found', vehicle: { year: 2019, make: 'Honda', model: 'Civic' } }));
  assert.deepEqual(found, { status: 'found', vehicle: { year: 2019, make: 'Honda', model: 'Civic' } });
  assert.equal(sent.url, 'https://p.test/lookup');
  assert.deepEqual(JSON.parse(sent.init.body), { state: 'CA', plate: 'TST1001' });
  assert.equal(sent.init.headers.authorization, 'Bearer tok');

  assert.equal((await run(reply(200, { status: 'not_found' }))).status, 'not_found');
  assert.equal((await run(reply(501, { status: 'not_configured' }))).status, 'not_configured');
  assert.equal((await run(reply(401, {}))).status, 'unauthorized');
  assert.equal((await run(reply(429, {}))).status, 'limit');
  assert.equal((await run(reply(502, { message: 'bad' }))).status, 'error');
  assert.equal((await run(reply(200, { status: 'found', vehicle: {} }))).status, 'error');
  assert.equal((await run(async () => { throw new TypeError('offline'); })).status, 'offline');
  const slow = await run((url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted')))));
  assert.equal(slow.status, 'offline', 'a timeout counts as offline');
  assert.equal((await lookupVehicle('CA', 'X', 't', { url: '' })).status, 'not_configured');
});

test('the lookup URL, when set, is allowed by the page security policy', () => {
  if (!LOOKUP_URL) return; // feature off: nothing to check
  const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
  const connect = /connect-src([^;"]*)/.exec(html)[1];
  const origin = new URL(LOOKUP_URL, 'https://app.invalid').origin;
  assert.ok(connect.includes(origin) || new URL(LOOKUP_URL, 'https://app.invalid').origin === 'https://app.invalid',
    `add ${origin} to connect-src in web/index.html`);
});

// ---------- records ----------

const form = { color: 'red', make: 'Honda', model: 'Civic', bodyStyle: 'sedan', distinguishing: 'dent', flag: 'unknown', plate: 'TST1001', plateState: 'CA' };
const good = { plate: 'CA-TST1001', year: 2019, make: 'Honda', model: 'Civic LX', checkedAt: '2026-10-10T12:00:00.000Z' };

test('cleanPlateLookup accepts a well-formed answer and rejects the rest', () => {
  assert.deepEqual(cleanPlateLookup(good), good);
  assert.equal(cleanPlateLookup({ ...good, plate: 'ABC' }), null);
  assert.equal(cleanPlateLookup({ ...good, model: '' }), null);
  assert.equal(cleanPlateLookup(null), null);
  assert.equal(cleanPlateLookup({ ...good, year: 1066 }).year, null);
  assert.equal(cleanPlateLookup({ ...good, vin: '1HGBH41JXMN109186' }).vin, undefined, 'a VIN can never ride along');
});

test('plateLookup is stored on new vehicles and kept through updates and merges', () => {
  const { vehicle } = createVehicleRecord({ ...form, plateLookup: good });
  assert.deepEqual(vehicle.plateLookup, good);
  assert.equal(createVehicleRecord(form).vehicle.plateLookup, undefined);

  const { vehicle: updated } = addSightingToVehicle(vehicle, { notes: 'again' });
  assert.deepEqual(updated.plateLookup, good, 'an update without a lookup keeps the stored one');

  const { vehicle: plain } = addSightingToVehicle(createVehicleRecord(form).vehicle, { plateLookup: good });
  assert.deepEqual(plain.plateLookup, good, 'an update can add one');

  const later = new Date(Date.now() + 60_000);
  const { vehicle: newer } = addSightingToVehicle({ ...vehicle, plateLookup: undefined }, { notes: 'x' }, [], null, later);
  assert.deepEqual(mergeVehicle(vehicle, newer).plateLookup, good, 'a newer write without one does not erase it');
});
