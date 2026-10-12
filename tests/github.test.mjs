import test from 'node:test';
import assert from 'node:assert/strict';

import * as GitHub from '../web/js/github.js';
import { createVehicleRecord, addSightingToVehicle, indexEntryFromVehicle } from '../web/js/vehicle-manager.js';

// A tiny fake of the GitHub contents API: scripted responses, recorded requests.
function fakeFetch(script) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const call = { url, method: init.method || 'GET', body: init.body ? JSON.parse(init.body) : null };
    calls.push(call);
    const step = script.shift();
    if (!step) throw new Error(`unexpected request: ${call.method} ${url}`);
    if (step === 'network-error') throw new TypeError('Failed to fetch');
    const { status = 200, json = {} } = step;
    return {
      status,
      ok: status >= 200 && status < 300,
      statusText: String(status),
      headers: { get: () => null },
      json: async () => json,
      text: async () => JSON.stringify(json)
    };
  };
  return calls;
}

const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64');
const decode = (b) => JSON.parse(Buffer.from(b, 'base64').toString('utf8'));

const form = { color: 'grey', make: 'Nissan', bodyStyle: 'suv', distinguishing: 'roof rack', flag: 'suspected', notes: 'first' };
const created = () => createVehicleRecord(form, [], null, new Date('2026-10-09T09:00:00Z')).vehicle;

test('saveVehicle creates a new file with no sha when none exists', async () => {
  const calls = fakeFetch([{ status: 404 }, { status: 201 }]);
  const vehicle = created();
  await GitHub.saveVehicle(vehicle, 'tok');
  assert.equal(calls[1].method, 'PUT');
  assert.equal(calls[1].body.sha, undefined);
  assert.equal(calls[1].body.message, `Add/update vehicle ${vehicle.vehicleKey}`);
  assert.deepEqual(decode(calls[1].body.content), vehicle);
});

test('saveVehicle on a 409 re-reads, merges, and retries once with the fresh sha', async () => {
  const mine = created();
  const theirs = addSightingToVehicle(mine, { flag: 'confirmed', notes: 'other device' }, [], null, new Date('2026-10-10T08:00:00Z')).vehicle;
  const mineNewer = addSightingToVehicle(mine, { flag: 'cleared', notes: 'this device' }, [], null, new Date('2026-10-10T09:00:00Z')).vehicle;

  const calls = fakeFetch([
    { json: { content: b64(mine), sha: 'sha-A' } },   // first read
    { status: 409, json: { message: 'sha does not match' } },
    { json: { content: b64(theirs), sha: 'sha-B' } }, // re-read after conflict
    { status: 200 }
  ]);
  await GitHub.saveVehicle(mineNewer, 'tok');

  const puts = calls.filter((c) => c.method === 'PUT');
  assert.equal(puts.length, 2);
  assert.equal(puts[0].body.sha, 'sha-A');
  assert.equal(puts[1].body.sha, 'sha-B');
  const written = decode(puts[1].body.content);
  assert.deepEqual(written.sightings.map((s) => s.notes), ['first', 'other device', 'this device']);
  assert.equal(written.flag, 'cleared');
});

test('a second conflict raises ConflictError instead of retrying forever', async () => {
  const v = created();
  const conflict = { status: 409, json: { message: 'conflict' } };
  const read = { json: { content: b64(v), sha: 'x' } };
  const calls = fakeFetch([read, conflict, read, conflict]);
  await assert.rejects(() => GitHub.saveVehicle(v, 'tok'), GitHub.ConflictError);
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 2);
});

test('fetch failure becomes NetworkError; 401 becomes AuthError', async () => {
  fakeFetch(['network-error']);
  await assert.rejects(() => GitHub.getVehicle('VEH_00000000', 'tok'), GitHub.NetworkError);

  fakeFetch([{ status: 401, json: { message: 'Bad credentials' } }]);
  await assert.rejects(() => GitHub.getVehicle('VEH_00000000', 'tok'), GitHub.AuthError);
});

test('getVehicle returns null on 404 and getIndex treats a missing file as empty', async () => {
  fakeFetch([{ status: 404 }]);
  assert.equal(await GitHub.getVehicle('VEH_00000000', 'tok'), null);
  fakeFetch([{ status: 404 }]);
  assert.deepEqual(await GitHub.getIndex('tok'), []);
});

test('putPhoto treats "already exists" as success but surfaces other errors', async () => {
  fakeFetch([{ status: 422, json: { message: "Invalid request. \"sha\" wasn't supplied." } }]);
  await GitHub.putPhoto('photos/a.jpg', 'data:image/jpeg;base64,AAAA', 'tok');

  fakeFetch([{ status: 500, json: { message: 'boom' } }]);
  await assert.rejects(() => GitHub.putPhoto('photos/a.jpg', 'data:image/jpeg;base64,AAAA', 'tok'), /boom/);
});

test('checkAccess rejects a read-only token', async () => {
  fakeFetch([{ json: { permissions: { push: false } } }]);
  await assert.rejects(() => GitHub.checkAccess('tok'), GitHub.AuthError);
  fakeFetch([{ json: { permissions: { push: true } } }]);
  await GitHub.checkAccess('tok');
});

test('saveVehicle resolves to the merged record that was written (used to build the index entry)', async () => {
  const mine = created();
  const theirs = addSightingToVehicle(mine, { flag: 'confirmed', notes: 'other' }, [], null, new Date('2026-10-10T08:00:00Z')).vehicle;
  const mineNewer = addSightingToVehicle(mine, { flag: 'cleared', notes: 'me' }, [], null, new Date('2026-10-10T09:00:00Z')).vehicle;
  fakeFetch([{ json: { content: b64(theirs), sha: 'B' } }, { status: 200 }]);
  const merged = await GitHub.saveVehicle(mineNewer, 'tok');
  assert.equal(merged.sightings.length, 3);
  assert.equal(merged.flag, 'cleared');
});

test('saveIndexEntry creates the index when missing and merges into an existing one', async () => {
  const v = created();
  const entry = indexEntryFromVehicle(v);

  let calls = fakeFetch([{ status: 404 }, { status: 201 }]);
  await GitHub.saveIndexEntry(entry, 'tok');
  assert.equal(calls[1].body.message, `Update index for ${v.vehicleKey}`);
  assert.deepEqual(decode(calls[1].body.content), [entry]);

  const other = { ...entry, vehicleKey: 'VEH_00000001' };
  calls = fakeFetch([{ json: { content: b64([other]), sha: 'S1' } }, { status: 200 }]);
  await GitHub.saveIndexEntry(entry, 'tok');
  assert.equal(calls[1].body.sha, 'S1');
  assert.deepEqual(decode(calls[1].body.content).map((x) => x.vehicleKey).sort(), [v.vehicleKey, 'VEH_00000001'].sort());
});

test('saveIndexEntry survives contention: up to 4 attempts, then ConflictError', async () => {
  const entry = indexEntryFromVehicle(created());
  const read = (sha) => ({ json: { content: b64([]), sha } });
  const conflict = { status: 409, json: { message: 'conflict' } };

  // three losses then a win
  let calls = fakeFetch([read('1'), conflict, read('2'), conflict, read('3'), conflict, read('4'), { status: 200 }]);
  await GitHub.saveIndexEntry(entry, 'tok');
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 4);

  // always losing: stops at 4, never loops
  calls = fakeFetch([read('1'), conflict, read('2'), conflict, read('3'), conflict, read('4'), conflict]);
  await assert.rejects(() => GitHub.saveIndexEntry(entry, 'tok'), GitHub.ConflictError);
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 4);
});
