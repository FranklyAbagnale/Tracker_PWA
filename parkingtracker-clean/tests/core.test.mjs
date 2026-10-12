import test from 'node:test';
import assert from 'node:assert/strict';

import { haversineDistanceKm, coarsenLocation, isValidCoordinate, mapsDirectionsUrl, latestLocatedSighting } from '../web/js/geo.js';
import { rankPlateMatches, plateMatchRows } from '../web/js/plate-manager.js';
import { normalizePlate, normalizeState, plateKey, splitPlateKey, formatPlateKey, computePlateSimilarity } from '../web/js/matching.js';
import { rankLocalResults, formatDistance } from '../web/js/local-manager.js';
import {
  validateVehicleCapture, hasAnyContent, buildDisplayName, createVehicleRecord, addSightingToVehicle, createPlateRecord,
  mergeVehicle, indexEntryFromVehicle, makePhotoPath, cleanObserver, mergeIndexEntry
} from '../web/js/vehicle-manager.js';

const form = {
  color: 'Grey', make: 'nissan', model: 'pathfinder', bodyStyle: 'suv',
  distinguishing: 'roof rack, dented rear bumper, Roof Rack', plate: 'abc-123', plateState: 'CA', flag: 'suspected', notes: 'Parked twice'
};

// ---------- geo ----------

test('haversine: one degree of latitude is about 111 km', () => {
  const d = haversineDistanceKm(34, -118, 35, -118);
  assert.ok(Math.abs(d - 111.2) < 0.3, `got ${d}`);
  assert.equal(haversineDistanceKm(34, -118, 34, -118), 0);
});

test('coarsenLocation rounds to 4 places by default and rejects bad input', () => {
  assert.deepEqual(coarsenLocation({ lat: 34.14812, lng: -118.14449 }), { lat: 34.1481, lng: -118.1445 });
  assert.deepEqual(coarsenLocation({ lat: 34.14812, lng: -118.14449 }, 3), { lat: 34.148, lng: -118.144 });
  assert.deepEqual(coarsenLocation({ lat: 34.14812, lng: -118.14449 }, null), { lat: 34.14812, lng: -118.14449 });
  assert.equal(coarsenLocation(null), null);
  assert.equal(coarsenLocation({ lat: 999, lng: 0 }), null);
  assert.equal(isValidCoordinate(NaN, 0), false);
});

// ---------- matching ----------

test('plate normalisation and similarity', () => {
  assert.equal(normalizePlate(' ab-123 cd '), 'AB123CD');
  assert.equal(computePlateSimilarity('AB123CD', 'ab 123 cd'), 1);
  assert.ok(computePlateSimilarity('ABC1234', 'ABC1Z34') > 0.8);
  assert.ok(computePlateSimilarity('ABC1234', 'XYZ9999') < 0.3);
});

// ---------- ranking ----------

const NOW = new Date('2026-10-10T12:00:00Z');
const hoursAgo = (h) => new Date(NOW.getTime() - h * 3600 * 1000).toISOString();
const here = { lat: 34.148, lng: -118.144 };
const entry = (key, flag, ageHours, loc = { lat: 34.1485, lng: -118.144 }) => ({
  vehicleKey: key, displayName: key, flag, lastSeen: hoursAgo(ageHours), location: loc, plateAliases: []
});

test('ranking order: confirmed, suspected, cleared and pigs mixed, unknown last', () => {
  const ranked = rankLocalResults([
    entry('unknown', 'unknown', 5, { lat: 34.1481, lng: -118.144 }),
    entry('cleared', 'cleared', 5, { lat: 34.1495, lng: -118.144 }),
    entry('pigs', 'pigs', 5, { lat: 34.1488, lng: -118.144 }),
    entry('suspected', 'suspected', 5, { lat: 34.1492, lng: -118.144 }),
    entry('confirmed', 'confirmed', 5, { lat: 34.1499, lng: -118.144 })
  ], here, 1000, NOW);
  // pigs is nearer than cleared, so within their shared tier it comes first
  assert.deepEqual(ranked.map((r) => r.vehicleKey), ['confirmed', 'suspected', 'pigs', 'cleared', 'unknown']);
});

test('flag comes before distance; distance breaks ties inside a tier', () => {
  const ranked = rankLocalResults([
    entry('near-unknown', 'unknown', 1, { lat: 34.1481, lng: -118.144 }),
    entry('far-confirmed', 'confirmed', 1, { lat: 34.155, lng: -118.144 }),
    entry('near-confirmed', 'confirmed', 1, { lat: 34.1485, lng: -118.144 })
  ], here, 1000, NOW);
  assert.deepEqual(ranked.map((r) => r.vehicleKey), ['near-confirmed', 'far-confirmed', 'near-unknown']);
});

test('only confirmed vehicles age out after 14 days', () => {
  const ranked = rankLocalResults([
    entry('old-confirmed', 'confirmed', 15 * 24),
    entry('old-suspected', 'suspected', 40 * 24),
    entry('old-unknown', 'unknown', 40 * 24),
    entry('old-cleared', 'cleared', 40 * 24),
    entry('old-pigs', 'pigs', 40 * 24)
  ], here, 1000, NOW);
  assert.deepEqual(ranked.map((r) => r.vehicleKey).sort(), ['old-cleared', 'old-pigs', 'old-suspected', 'old-unknown']);
});

test('ranking filters by radius, skips unlocated entries, sorts nearest first', () => {
  const ranked = rankLocalResults([
    entry('far', 'suspected', 1, { lat: 34.2, lng: -118.144 }),
    entry('nowhere', 'suspected', 1, null),
    entry('mid', 'suspected', 1, { lat: 34.152, lng: -118.144 }),
    entry('near', 'suspected', 1, { lat: 34.1481, lng: -118.144 })
  ], here, 1000, NOW);
  assert.deepEqual(ranked.map((r) => r.vehicleKey), ['near', 'mid']);
});

test('ranking accepts full vehicle records (uses newest located sighting)', () => {
  const { vehicle } = createVehicleRecord(form, [], { lat: 34.1481, lng: -118.144 }, new Date(NOW.getTime() - 3600e3));
  assert.equal(rankLocalResults([vehicle], here, 1000, NOW).length, 1);
});

test('formatDistance switches between metres and km', () => {
  assert.equal(formatDistance(0.25), '250 m');
  assert.equal(formatDistance(1.26), '1.3 km');
});

// ---------- records ----------

test('validateVehicleCapture: nothing is required, anything given must be valid', () => {
  assert.equal(validateVehicleCapture(form).isValid, true);
  for (const blank of [{ color: '' }, { make: '' }, { bodyStyle: '' }, { color: '', make: '', model: '', bodyStyle: '' }]) {
    assert.equal(validateVehicleCapture({ ...form, ...blank }).isValid, true, JSON.stringify(blank));
  }
  assert.equal(validateVehicleCapture({}).isValid, true);
  assert.equal(validateVehicleCapture({ ...form, bodyStyle: 'spaceship' }).isValid, false);
});

test('hasAnyContent: a plate, photo, note, description or location is enough', () => {
  assert.equal(hasAnyContent({}), false);
  assert.equal(hasAnyContent({ flag: 'suspected', plateType: 'vanity', plateState: 'CA', bodyStyle: 'unknown', notes: '  ' }), false);
  for (const f of [{ plate: 'ABC' }, { color: 'red' }, { make: 'x' }, { model: 'x' }, { notes: 'blocked the gate' }, { distinguishing: 'dent' }, { bodyStyle: 'suv' }]) {
    assert.equal(hasAnyContent(f), true, JSON.stringify(f));
  }
  assert.equal(hasAnyContent({}, 1), true);
  assert.equal(hasAnyContent({}, 0, true), true);
});

test('a record with almost nothing is saved as unknown and can be completed later', () => {
  const { vehicle } = createVehicleRecord({ notes: 'white van by gate B', flag: 'suspected' });
  assert.deepEqual([vehicle.color, vehicle.make, vehicle.model, vehicle.bodyStyle, vehicle.displayName], ['unknown', 'unknown', null, 'unknown', 'Unknown vehicle']);
  assert.deepEqual(vehicle.distinguishing, []);
  const { vehicle: filled } = addSightingToVehicle(vehicle, { make: 'ford', color: 'white', bodyStyle: 'van' });
  assert.deepEqual([filled.color, filled.make, filled.bodyStyle, filled.displayName], ['white', 'Ford', 'van', 'White Ford']);
  assert.equal(buildDisplayName({ color: 'unknown', make: 'Ford', model: '' }), 'Ford');
});

test('mapsDirectionsUrl: Apple Maps on iPhone/iPad, Google Maps elsewhere', () => {
  assert.equal(mapsDirectionsUrl(34.1481, -118.1445, 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', 5), 'https://maps.apple.com/?daddr=34.1481%2C-118.1445&dirflg=d');
  assert.match(mapsDirectionsUrl(34.1481, -118.1445, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 5), /^https:\/\/maps\.apple\.com\//); // iPad that reports as a Mac
  assert.equal(mapsDirectionsUrl(34.1481, -118.1445, 'Mozilla/5.0 (Linux; Android 14)', 5), 'https://www.google.com/maps/dir/?api=1&destination=34.1481%2C-118.1445&travelmode=driving');
  assert.match(mapsDirectionsUrl(34.1481, -118.1445, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 0), /google\.com/); // a real Mac
});

test('latestLocatedSighting picks the newest sighting that has a location', () => {
  const v = { sightings: [
    { id: 'a', timestamp: '2026-01-03T00:00:00Z', location: { lat: 1, lng: 2 } },
    { id: 'b', timestamp: '2026-01-05T00:00:00Z', location: null },
    { id: 'c', timestamp: '2026-01-04T00:00:00Z', location: { lat: 3, lng: 4 } }] };
  assert.equal(latestLocatedSighting(v).id, 'c');
  assert.equal(latestLocatedSighting({ sightings: [{ id: 'x', timestamp: '2026-01-01T00:00:00Z', location: null }] }), null);
  assert.equal(latestLocatedSighting({}), null);
});

test('distinguishing features are optional', () => {
  for (const distinguishing of ['', ' , ', undefined]) {
    assert.equal(validateVehicleCapture({ ...form, distinguishing }).isValid, true);
  }
  const { vehicle } = createVehicleRecord({ ...form, distinguishing: '' });
  assert.deepEqual(vehicle.distinguishing, []);
});

test('createVehicleRecord builds a schema-shaped record with staged photos', () => {
  const when = new Date('2026-10-10T14:32:05Z');
  const { vehicle, photoFiles } = createVehicleRecord(form, ['data:image/jpeg;base64,AAAA', 'data:image/jpeg;base64,BBBB'], { lat: 1, lng: 2 }, when);
  assert.match(vehicle.vehicleKey, /^VEH_[0-9a-f]{8}$/);
  assert.equal(vehicle.displayName, 'Grey Nissan Pathfinder');
  assert.deepEqual(vehicle.plateAliases, ['CA-ABC123']);
  assert.deepEqual(vehicle.distinguishing, ['roof rack', 'dented rear bumper']); // de-duplicated
  assert.equal(vehicle.sightings.length, 1);
  assert.match(vehicle.sightings[0].id, /^S_[0-9a-f]{8}$/);
  assert.equal(photoFiles[0].path, `photos/${vehicle.vehicleKey}_20261010T143205_001.jpg`);
  assert.deepEqual(vehicle.sightings[0].photos, photoFiles.map((p) => p.path));
  assert.equal(vehicle.firstSeen, vehicle.lastSeen);
});

test('addSightingToVehicle appends, preserves blanks, adds plate alias, does not mutate', () => {
  const { vehicle } = createVehicleRecord(form, [], null, new Date('2026-10-09T09:00:00Z'));
  const snapshot = JSON.stringify(vehicle);
  const { vehicle: next } = addSightingToVehicle(
    vehicle,
    { color: '', make: '', model: '', bodyStyle: '', distinguishing: 'cracked windshield', plate: 'XYZ789', plateState: 'NV', flag: 'confirmed', notes: 'Seen again' },
    [], { lat: 1, lng: 2 }, new Date('2026-10-10T09:00:00Z')
  );
  assert.equal(JSON.stringify(vehicle), snapshot);
  assert.equal(next.color, 'grey');
  assert.equal(next.sightings.length, 2);
  assert.equal(next.flag, 'confirmed');
  assert.deepEqual(next.plateAliases, ['CA-ABC123', 'NV-XYZ789']);
  assert.ok(next.distinguishing.includes('cracked windshield'));
  assert.equal(next.firstSeen, vehicle.firstSeen);
  assert.equal(next.lastSeen, '2026-10-10T09:00:00.000Z');
});

test('createPlateRecord normalises and defaults the plate type', () => {
  const p = createPlateRecord('ab 12', 'nv', 'VEH_00000000', 'bogus', new Date('2026-10-10T00:00:00Z'));
  assert.equal(p.plate, 'AB12');
  assert.equal(p.plateState, 'NV');
  assert.equal(p.plateType, 'standard');
});

test('makePhotoPath is stable and zero-padded', () => {
  assert.equal(makePhotoPath('VEH_a', new Date('2026-01-02T03:04:05Z'), 11), 'photos/VEH_a_20260102T030405_012.jpg');
});

// ---------- merge (409 handling) ----------

function twoDeviceFixture() {
  const { vehicle: base } = createVehicleRecord(form, [], { lat: 1, lng: 2 }, new Date('2026-10-09T09:00:00Z'));
  const a = addSightingToVehicle(base, { distinguishing: '', flag: 'suspected', notes: 'device A' }, [], null, new Date('2026-10-10T10:00:00Z')).vehicle;
  const b = addSightingToVehicle(base, { distinguishing: 'sticker', flag: 'cleared', notes: 'device B' }, [], null, new Date('2026-10-10T11:00:00Z')).vehicle;
  return { base, a, b };
}

test('mergeVehicle keeps both devices\' sightings, newest flag wins, aliases union', () => {
  const { a, b } = twoDeviceFixture();
  const merged = mergeVehicle(a, b);
  assert.equal(merged.sightings.length, 3);
  assert.deepEqual(merged.sightings.map((s) => s.notes), ['Parked twice', 'device A', 'device B']);
  assert.equal(merged.flag, 'cleared');
  assert.ok(merged.distinguishing.includes('sticker'));
  assert.equal(merged.lastSeen, b.lastSeen);
  assert.equal(merged.firstSeen, a.firstSeen);
});

test('mergeVehicle is idempotent and order-independent for sightings', () => {
  const { a, b } = twoDeviceFixture();
  const once = mergeVehicle(a, b);
  const twice = mergeVehicle(once, b);
  assert.deepEqual(twice.sightings, once.sightings);
  assert.deepEqual(mergeVehicle(b, a).sightings, once.sightings);
});

test('a delayed older write cannot overwrite a newer flag or description', () => {
  const { a, b } = twoDeviceFixture();
  const merged = mergeVehicle(b, { ...a, color: 'pink' }); // a is older than b
  assert.equal(merged.flag, 'cleared');
  assert.equal(merged.color, 'grey');
});

test('mergeVehicle with no remote returns the incoming record', () => {
  const { a } = twoDeviceFixture();
  assert.equal(mergeVehicle(null, a), a);
});

// ---------- index projection ----------

test('indexEntryFromVehicle uses the newest located sighting', () => {
  const { base } = twoDeviceFixture();
  const moved = addSightingToVehicle(base, { flag: 'suspected' }, [], { lat: 9, lng: 8 }, new Date('2026-10-11T00:00:00Z')).vehicle;
  const noLoc = addSightingToVehicle(moved, { flag: 'suspected' }, [], null, new Date('2026-10-12T00:00:00Z')).vehicle;
  const entry = indexEntryFromVehicle(noLoc);
  assert.deepEqual(entry.location, { lat: 9, lng: 8 });
  assert.equal(entry.lastSeen, '2026-10-12T00:00:00.000Z');
  for (const k of ['displayName', 'flag', 'lastSeen', 'location', 'plateAliases', 'vehicleKey']) assert.ok(k in entry, k);
  assert.ok(Object.keys(entry).every((k) => ['displayName', 'flag', 'lastSeen', 'location', 'plateAliases', 'vehicleKey', 'color', 'make', 'model', 'bodyStyle', 'year', 'features'].includes(k)));
});

// ---------- attribution (shared token: the record is the only audit trail) ----------

test('cleanObserver trims, collapses whitespace, caps length, and nulls blanks', () => {
  assert.equal(cleanObserver('  Alex   Kim '), 'Alex Kim');
  assert.equal(cleanObserver('x'.repeat(100)).length, 40);
  assert.equal(cleanObserver('   '), null);
  assert.equal(cleanObserver(null), null);
});

test('records are stamped with the observer on create and on every added sighting', () => {
  const when = new Date('2026-10-10T10:00:00Z');
  const { vehicle } = createVehicleRecord(form, [], null, when, ' Alex  Kim ');
  assert.equal(vehicle.sightings[0].observer, 'Alex Kim');
  assert.equal(vehicle.lastUpdatedBy, 'Alex Kim');

  const { vehicle: next } = addSightingToVehicle(vehicle, { flag: 'confirmed' }, [], null, new Date('2026-10-10T11:00:00Z'), 'Sam');
  assert.deepEqual(next.sightings.map((s) => s.observer), ['Alex Kim', 'Sam']);
  assert.equal(next.lastUpdatedBy, 'Sam');
});

test('no observer means no observer field (older callers and sample data stay valid)', () => {
  const { vehicle } = createVehicleRecord(form, [], null, new Date('2026-10-10T10:00:00Z'));
  assert.equal('observer' in vehicle.sightings[0], false);
  assert.equal('lastUpdatedBy' in vehicle, false);
});

test('merging two devices keeps each sighting\'s own observer', () => {
  const { vehicle: base } = createVehicleRecord(form, [], null, new Date('2026-10-09T09:00:00Z'), 'Alex');
  const a = addSightingToVehicle(base, { flag: 'suspected' }, [], null, new Date('2026-10-10T10:00:00Z'), 'Sam').vehicle;
  const b = addSightingToVehicle(base, { flag: 'cleared' }, [], null, new Date('2026-10-10T11:00:00Z'), 'Jo').vehicle;
  const merged = mergeVehicle(a, b);
  assert.deepEqual(merged.sightings.map((s) => s.observer), ['Alex', 'Sam', 'Jo']);
  assert.equal(merged.lastUpdatedBy, 'Jo');
});

// ---------- client-maintained index (replaces the index workflow) ----------

const e = (key, lastSeen, extra = {}) => ({ vehicleKey: key, displayName: key, flag: 'unknown', lastSeen, location: null, plateAliases: [], ...extra });

test('mergeIndexEntry inserts, replaces, and keeps the list sorted by key', () => {
  let idx = mergeIndexEntry([], e('VEH_b', '2026-10-10T10:00:00.000Z'));
  idx = mergeIndexEntry(idx, e('VEH_a', '2026-10-10T10:00:00.000Z'));
  assert.deepEqual(idx.map((x) => x.vehicleKey), ['VEH_a', 'VEH_b']);
  idx = mergeIndexEntry(idx, e('VEH_a', '2026-10-10T11:00:00.000Z', { flag: 'confirmed' }));
  assert.equal(idx.length, 2);
  assert.equal(idx[0].flag, 'confirmed');
});

test('mergeIndexEntry never lets an older entry overwrite a newer one, and is idempotent', () => {
  const newer = e('VEH_a', '2026-10-10T12:00:00.000Z', { flag: 'cleared' });
  const older = e('VEH_a', '2026-10-10T09:00:00.000Z', { flag: 'suspected' });
  const once = mergeIndexEntry([newer], older);
  assert.deepEqual(once, [newer]);
  assert.deepEqual(mergeIndexEntry(once, newer), once);
});

test('mergeIndexEntry is order-independent (concurrent writers converge)', () => {
  const x = e('VEH_x', '2026-10-10T10:00:00.000Z');
  const y = e('VEH_y', '2026-10-10T10:00:00.000Z');
  const z = e('VEH_x', '2026-10-10T11:00:00.000Z', { flag: 'confirmed' });
  const fold = (order) => order.reduce((acc, item) => mergeIndexEntry(acc, item), []);
  assert.deepEqual(fold([x, y, z]), fold([z, y, x]));
  assert.deepEqual(fold([y, z, x]), fold([x, z, y]));
});

test('mergeIndexEntry tolerates a missing or malformed remote index', () => {
  assert.deepEqual(mergeIndexEntry(null, e('VEH_a', '2026-10-10T10:00:00.000Z')).length, 1);
  assert.deepEqual(mergeIndexEntry({ not: 'an array' }, e('VEH_a', '2026-10-10T10:00:00.000Z')).length, 1);
});

test('plates may be up to 20 characters and are cut at 20', () => {
  assert.equal(normalizePlate('abc-123 456'), 'ABC123456');
  assert.equal(normalizePlate('ABCDEFGHIJKLMNOPQRST'), 'ABCDEFGHIJKLMNOPQRST');
  assert.equal(normalizePlate('ABCDEFGHIJKLMNOPQRSTU'), 'ABCDEFGHIJKLMNOPQRST');
  assert.deepEqual(splitPlateKey('CA-ABCDEFGHIJKLMNOPQRST'), { state: 'CA', plate: 'ABCDEFGHIJKLMNOPQRST' });
});

test('"pigs" is an accepted flag', () => {
  const form = { color: 'black', make: 'Dodge', bodyStyle: 'sedan', distinguishing: 'push bar', flag: 'pigs' };
  assert.equal(validateVehicleCapture(form).isValid, true);
});

test('"unknown" is an accepted body style', () => {
  const form = { color: 'grey', make: 'Nissan', bodyStyle: 'unknown', distinguishing: 'dent', flag: 'unknown' };
  assert.equal(validateVehicleCapture(form).isValid, true);
});

test('plate state: codes, keys and display', () => {
  assert.equal(normalizeState(' ca '), 'CA');
  assert.equal(normalizeState('Atlantis'), 'XX');
  assert.equal(normalizeState(''), 'XX');
  assert.equal(normalizeState('BC'), 'BC');
  assert.equal(plateKey('ca', 'ab 12'), 'CA-AB12');
  assert.equal(plateKey('', 'ab12'), 'XX-AB12');
  assert.equal(plateKey('CA', ''), '');
  assert.deepEqual(splitPlateKey('NV-ABC1'), { state: 'NV', plate: 'ABC1' });
  assert.equal(splitPlateKey('ABC1'), null);
  assert.equal(formatPlateKey('NV-ABC1'), 'NV ABC1');
  assert.equal(formatPlateKey('XX-ABC1'), 'ABC1 (state unknown)');
});

test('the same plate in two states is two plates', () => {
  assert.notEqual(plateKey('CA', 'ABC123'), plateKey('NV', 'ABC123'));
  const a = createVehicleRecord({ ...form, plate: 'ABC123', plateState: 'CA' }, [], null, new Date());
  const b = createVehicleRecord({ ...form, plate: 'ABC123', plateState: 'NV' }, [], null, new Date());
  assert.deepEqual(a.vehicle.plateAliases, ['CA-ABC123']);
  assert.deepEqual(b.vehicle.plateAliases, ['NV-ABC123']);
});

test('rankPlateMatches: contains search, best first, state filter', () => {
  const entry = (k, aliases, lastSeen) => ({ vehicleKey: k, plateAliases: aliases, lastSeen });
  const entries = [
    entry('VEH_00000001', ['XX-7RAJ718'], '2026-05-01T00:00:00Z'),
    entry('VEH_00000002', ['XX-8RAP124'], '2026-06-01T00:00:00Z'),
    entry('VEH_00000003', ['CA-8RAP135'], '2026-07-01T00:00:00Z'),
    entry('VEH_00000004', ['NV-XX8RAP1', 'CA-ZZZ999'], '2026-08-01T00:00:00Z'),
    entry('VEH_00000005', ['CA-8RAP'], '2026-01-01T00:00:00Z'),
  ];
  const keys = (r) => r.map((e) => e.vehicleKey);
  assert.deepEqual(keys(rankPlateMatches(entries, '8RAP')), ['VEH_00000005', 'VEH_00000003', 'VEH_00000002', 'VEH_00000004']); // exact, prefixes newest first, then contains
  assert.deepEqual(keys(rankPlateMatches(entries, '8RAP', 'CA')), ['VEH_00000005', 'VEH_00000003']);
  assert.deepEqual(keys(rankPlateMatches(entries, 'RAJ')), ['VEH_00000001']);
  assert.deepEqual(rankPlateMatches(entries, 'QQQ'), []);
});

test('year is optional, four digits, 1900-2100, and needs a Verified site check', async () => {
  const { cleanYear, createVehicleRecord, addSightingToVehicle, validateVehicleCapture, validateVehicleUpdate, applySiteChecks, mergeVehicle } =
    await import('../web/js/vehicle-manager.js');
  assert.equal(cleanYear('2019'), 2019);
  for (const bad of ['', '19', '20x9', '1899', '2101', null, undefined]) assert.equal(cleanYear(bad), null, String(bad));
  const base = { color: 'grey', make: 'Honda', bodyStyle: 'sedan', distinguishing: 'dent' };
  const verified = { ...base, year: '2019', 'check-faxvin': 'verified' };
  assert.equal(createVehicleRecord(verified).vehicle.year, 2019);
  assert.equal(createVehicleRecord(verified).vehicle.siteChecks.faxvin.status, 'verified');
  assert.equal('year' in createVehicleRecord({ ...base, year: '2019' }).vehicle, false, 'no verified site, no year');
  assert.equal('year' in createVehicleRecord({ ...base, year: '2019', 'check-faxvin': 'wrong' }).vehicle, false);
  assert.equal(validateVehicleCapture({ ...base, year: '2019' }).isValid, false);
  assert.equal(validateVehicleCapture({ ...base, year: '20x9', 'check-faxvin': 'verified' }).isValid, false);
  assert.equal(validateVehicleCapture(verified).isValid, true);
  assert.equal('siteChecks' in createVehicleRecord({ ...base, 'check-faxvin': '' }).vehicle, false);

  const rec = createVehicleRecord({ ...base, 'check-faxvin': 'not_found' }, [], null, new Date('2026-01-01T00:00:00Z')).vehicle;
  const t2 = new Date('2026-02-01T00:00:00Z');
  const up = addSightingToVehicle(rec, { year: '2021', 'check-carfax': 'verified' }, [], null, t2).vehicle;
  assert.equal(up.year, 2021);
  assert.equal(up.siteChecks.faxvin.checkedAt, '2026-01-01T00:00:00.000Z', 'unchanged check keeps its date');
  assert.equal(up.siteChecks.carfax.checkedAt, t2.toISOString());
  assert.equal(validateVehicleUpdate({ year: '2022' }, rec).isValid, false);
  assert.equal(validateVehicleUpdate({ year: '2022', 'check-carfax': 'verified' }, rec).isValid, true);
  assert.equal(validateVehicleUpdate({ year: '2021' }, up).isValid, true, 'an unchanged year stays valid');
  assert.equal(addSightingToVehicle(up, { year: '' }, [], null, t2).vehicle.year, 2021, 'blank year leaves it alone');
  assert.deepEqual(applySiteChecks(up.siteChecks, { 'check-carfax': '' }, t2).carfax, undefined, 'blank clears a check');
  assert.deepEqual(applySiteChecks({}, { 'check-evil': 'verified', 'check-faxvin': 'bogus' }, t2), { evil: { status: 'verified', checkedAt: t2.toISOString() } });

  const a = { ...rec, siteChecks: { faxvin: { status: 'wrong', checkedAt: '2026-03-01T00:00:00.000Z' } } };
  const b = { ...rec, siteChecks: { faxvin: { status: 'verified', checkedAt: '2026-02-01T00:00:00.000Z' }, carfax: { status: 'verified', checkedAt: '2026-02-01T00:00:00.000Z' } } };
  const m = mergeVehicle(a, b);
  assert.equal(m.siteChecks.faxvin.status, 'wrong', 'later check wins per site');
  assert.equal(m.siteChecks.carfax.status, 'verified', 'sites merge');
});

test('plateMatchRows: one row per plate, exact first, partial in alphanumeric order', () => {
  const e = (vehicleKey, lastSeen, ...plateAliases) => ({ vehicleKey, lastSeen, plateAliases });
  const entries = [
    e('VEH_00000001', '2026-01-01', 'CA-ZZ8RAP9'),
    e('VEH_00000002', '2026-03-01', 'XX-8RAP', 'CA-1ABC8RAPX'),
    e('VEH_00000003', '2026-02-01', 'CA-8RAP'),
    e('VEH_00000004', '2026-01-01', 'CA-A8RAP'),
    e('VEH_00000005', '2026-01-01', 'CA-NOPE')
  ];
  const rows = plateMatchRows(entries, '8RAP');
  assert.deepEqual(rows.map((r) => `${r.kind}:${r.key}`), [
    'exact:XX-8RAP', 'exact:CA-8RAP',            // exact first, newest sighting first
    'partial:CA-1ABC8RAPX', 'partial:CA-A8RAP', 'partial:CA-ZZ8RAP9' // then by plate, alphanumeric
  ]);
  assert.deepEqual(plateMatchRows(entries, '8RAP', 'CA').map((r) => r.key), ['CA-8RAP', 'CA-1ABC8RAPX', 'CA-A8RAP', 'CA-ZZ8RAP9']);
  assert.equal(new Set(plateMatchRows(entries, '8RAP').map((r) => r.key)).size, rows.length);
});

// ---------- previous sighting ----------
import { createVehicleRecord as _create, addSightingToVehicle as _add, validPastDate } from '../web/js/vehicle-manager.js';
import { parseLatLng, searchAddress } from '../web/js/place-finder.js';

test('previous sighting: backdated record keeps the entry time in recordedAt', () => {
  const now = new Date('2026-10-11T22:00:00Z');
  const when = new Date('2026-10-11T08:30:00Z');
  const { vehicle } = _create({ plate: 'ABC123', plateState: 'CA' }, [], { lat: 1, lng: 2, manual: true }, now, 'sam', when);
  const s = vehicle.sightings[0];
  assert.equal(s.timestamp, when.toISOString());
  assert.equal(s.recordedAt, now.toISOString());
  assert.equal(vehicle.firstSeen, when.toISOString());
  assert.equal(vehicle.lastSeen, when.toISOString());
});

test('previous sighting: normal record has no recordedAt', () => {
  const { vehicle } = _create({ plate: 'ABC123', plateState: 'CA' }, [], null, new Date('2026-10-11T22:00:00Z'), 'sam');
  assert.equal('recordedAt' in vehicle.sightings[0], false);
});

test('previous sighting: an older sighting does not move lastSeen back, and can move firstSeen earlier', () => {
  const now = new Date('2026-10-11T22:00:00Z');
  const { vehicle } = _create({ plate: 'ABC123', plateState: 'CA' }, [], null, now, 'sam');
  const early = new Date('2026-10-10T09:00:00Z');
  const { vehicle: next } = _add(vehicle, {}, [], null, new Date('2026-10-11T23:00:00Z'), 'sam', early);
  assert.equal(next.firstSeen, early.toISOString());
  assert.equal(next.lastSeen, now.toISOString());
  assert.equal(next.sightings.length, 2);
});

test('validPastDate rejects future, too old and garbage', () => {
  const now = new Date('2026-10-11T12:00:00Z');
  assert.ok(validPastDate('2026-10-11T08:00:00Z', now));
  assert.equal(validPastDate('2026-10-12T08:00:00Z', now), null);
  assert.equal(validPastDate('2020-01-01T00:00:00Z', now), null);
  assert.equal(validPastDate('nope', now), null);
  assert.equal(validPastDate('', now), null);
});

test('parseLatLng reads coordinates and common map links', () => {
  assert.deepEqual(parseLatLng('37.7749, -122.4194'), { lat: 37.7749, lng: -122.4194 });
  assert.deepEqual(parseLatLng('https://www.google.com/maps/@37.77,-122.41,15z'), { lat: 37.77, lng: -122.41 });
  assert.deepEqual(parseLatLng('https://maps.google.com/?q=37.77,-122.41'), { lat: 37.77, lng: -122.41 });
  assert.deepEqual(parseLatLng('https://www.openstreetmap.org/#map=17/37.77/-122.41'), { lat: 37.77, lng: -122.41 });
  assert.equal(parseLatLng('200, 400'), null);
  assert.equal(parseLatLng('Main Street'), null);
});

test('searchAddress returns the first hit, and null when offline or empty', async () => {
  const ok = async () => ({ ok: true, json: async () => [{ lat: '37.1', lon: '-122.2', display_name: 'Somewhere' }] });
  assert.deepEqual(await searchAddress('x', ok), { lat: 37.1, lng: -122.2, label: 'Somewhere' });
  assert.equal(await searchAddress('x', async () => { throw new Error('offline'); }), null);
  assert.equal(await searchAddress('x', async () => ({ ok: true, json: async () => [] })), null);
});

// ---------- editing your own sighting ----------
import { editSightingInVehicle, canEditSighting, mergeVehicle as _merge, mergeIndexEntry as _mergeIdx, indexEntryFromVehicle as _idx } from '../web/js/vehicle-manager.js';

function _fixture() {
  const now = new Date('2026-10-11T12:00:00Z');
  const { vehicle } = _create({ plate: 'ABC123', plateState: 'CA', color: 'blue', make: 'ford', notes: 'first' }, ['data:image/jpeg;base64,AAAA'], { lat: 1, lng: 2 }, now, 'Sam');
  return { vehicle, now };
}

test('canEditSighting: own name, inside 24 h only', () => {
  const { vehicle, now } = _fixture();
  const s = vehicle.sightings[0];
  assert.equal(canEditSighting(s, 'sam', new Date(now.getTime() + 23 * 3600000)), true);
  assert.equal(canEditSighting(s, 'Sam', new Date(now.getTime() + 25 * 3600000)), false);
  assert.equal(canEditSighting(s, 'Pat', now), false);
  assert.equal(canEditSighting(s, null, now), false);
});

test('window counts from when it was saved, not from the event time', () => {
  const now = new Date('2026-10-11T22:00:00Z');
  const { vehicle } = _create({ plate: 'ABC123', plateState: 'CA' }, [], null, now, 'Sam', new Date('2026-10-10T08:00:00Z'));
  assert.equal(canEditSighting(vehicle.sightings[0], 'Sam', new Date('2026-10-12T08:00:00Z')), true);
});

test('edit: changes fields, removes a photo, moves times, stamps editedAt', () => {
  const { vehicle, now } = _fixture();
  const s = vehicle.sightings[0];
  const later = new Date(now.getTime() + 3600000);
  const when = new Date(now.getTime() - 3 * 3600000);
  const r = editSightingInVehicle(vehicle, s.id, { notes: 'fixed', location: null, when, removePhotos: [s.photos[0]], vehicle: { color: 'Red', make: 'mazda', model: '', bodyStyle: 'sedan', distinguishing: 'dent, sticker' } }, [], later, 'Sam');
  const e = r.vehicle.sightings[0];
  assert.equal(e.notes, 'fixed');
  assert.equal(e.location, null);
  assert.deepEqual(e.photos, []);
  assert.deepEqual(r.removedPhotos, [s.photos[0]]);
  assert.equal(e.timestamp, when.toISOString());
  assert.equal(e.recordedAt, s.timestamp);
  assert.equal(e.editedAt, later.toISOString());
  assert.equal(r.vehicle.color, 'red');
  assert.deepEqual(r.vehicle.distinguishing, ['dent', 'sticker']);
  assert.equal(r.vehicle.lastSeen, when.toISOString());
  assert.equal(r.vehicle.firstSeen, when.toISOString());
});

test('edit: refuses other people, expired windows and unknown ids', () => {
  const { vehicle, now } = _fixture();
  const id = vehicle.sightings[0].id;
  assert.throws(() => editSightingInVehicle(vehicle, id, {}, [], now, 'Pat'));
  assert.throws(() => editSightingInVehicle(vehicle, id, {}, [], new Date(now.getTime() + 30 * 3600000), 'Sam'));
  assert.throws(() => editSightingInVehicle(vehicle, 'S_nope', {}, [], now, 'Sam'));
});

test('merge: an edited sighting beats a stale copy, either way round', () => {
  const { vehicle, now } = _fixture();
  const r = editSightingInVehicle(vehicle, vehicle.sightings[0].id, { notes: 'fixed', location: null }, [], new Date(now.getTime() + 60000), 'Sam');
  for (const [remote, incoming] of [[vehicle, r.vehicle], [r.vehicle, vehicle]]) {
    const m = _merge(remote, incoming);
    assert.equal(m.sightings.length, 1);
    assert.equal(m.sightings[0].notes, 'fixed');
    assert.equal(m.sightings[0].location, null);
  }
});

test('merge: an edit keeps another device\'s new sighting, and lastSeen can move earlier', () => {
  const { vehicle, now } = _fixture();
  const other = _add(vehicle, { notes: 'other' }, [], null, new Date(now.getTime() + 120000), 'Pat').vehicle;
  const r = editSightingInVehicle(vehicle, vehicle.sightings[0].id, { when: new Date(now.getTime() - 3600000) }, [], new Date(now.getTime() + 60000), 'Sam');
  const m = _merge(other, r.vehicle);
  assert.equal(m.sightings.length, 2);
  assert.equal(m.firstSeen, new Date(now.getTime() - 3600000).toISOString());
  assert.equal(m.lastSeen, other.lastSeen);
});

test('index merge: forced entries replace a newer lastSeen', () => {
  const { vehicle } = _fixture();
  const entry = _idx(vehicle);
  const stale = [{ ...entry, lastSeen: '2030-01-01T00:00:00.000Z' }];
  assert.equal(_mergeIdx(stale, entry)[0].lastSeen, '2030-01-01T00:00:00.000Z');
  assert.equal(_mergeIdx(stale, entry, true)[0].lastSeen, entry.lastSeen);
});

// ---------- find by description ----------
import { searchByDescription, tokenize } from '../web/js/describe-search.js';
import { searchFieldsOf } from '../web/js/vehicle-manager.js';

const _entries = [
  { vehicleKey: 'VEH_1', displayName: 'Grey Nissan Pathfinder', flag: 'confirmed', lastSeen: '2026-10-01T00:00:00Z', color: 'grey', make: 'Nissan', model: 'Pathfinder', bodyStyle: 'suv', year: 2019, features: ['roof rack', 'dent'], plateAliases: ['CA-ABC123'] },
  { vehicleKey: 'VEH_2', displayName: 'Blue Ford F-150', flag: 'unknown', lastSeen: '2026-10-05T00:00:00Z', color: 'blue', make: 'Ford', model: 'F-150', bodyStyle: 'pickup', plateAliases: ['NV-XYZ789'] },
  { vehicleKey: 'VEH_3', displayName: 'Unknown Chevy Tahoe', flag: 'unknown', lastSeen: '2025-01-01T00:00:00Z', plateAliases: [] }
];

test('describe search: words are ANDed and match parts of words', () => {
  assert.deepEqual(searchByDescription(_entries, { query: 'grey nis' }).map((e) => e.vehicleKey), ['VEH_1']);
  assert.deepEqual(searchByDescription(_entries, { query: 'dent rack' }).map((e) => e.vehicleKey), ['VEH_1']);
  assert.deepEqual(searchByDescription(_entries, { query: '2019' }).map((e) => e.vehicleKey), ['VEH_1']);
  assert.deepEqual(searchByDescription(_entries, { query: 'xyz7' }).map((e) => e.vehicleKey), ['VEH_2']);
  assert.deepEqual(searchByDescription(_entries, { query: 'grey ford' }), []);
});

test('describe search: filters, ordering, legacy entries and empty criteria', () => {
  assert.deepEqual(searchByDescription(_entries, { flag: 'unknown' }).map((e) => e.vehicleKey), ['VEH_2', 'VEH_3']);
  assert.deepEqual(searchByDescription(_entries, { query: 'blue', bodyStyle: 'sedan' }), []);
  assert.deepEqual(searchByDescription(_entries, { query: 'tahoe' }).map((e) => e.vehicleKey), ['VEH_3']);
  assert.deepEqual(searchByDescription(_entries, {}), []);
  assert.deepEqual(tokenize('"roof rack"  Dent'), ['roof rack', 'dent']);
});

test('searchFieldsOf leaves out unknown and empty values', () => {
  assert.deepEqual(searchFieldsOf({ color: 'unknown', make: 'Ford', model: null, bodyStyle: 'unknown', distinguishing: [] }), { make: 'Ford' });
  assert.deepEqual(searchFieldsOf({ color: 'red', make: 'Kia', model: 'Soul', bodyStyle: 'hatchback', year: 2020, distinguishing: ['dent'] }),
    { color: 'red', make: 'Kia', model: 'Soul', bodyStyle: 'hatchback', year: 2020, features: ['dent'] });
});

// ---------- index overlay after an edit ----------
import { preferLocalEntry } from '../web/js/index-manager.js';

test('overlay: a recent local edit that moved lastSeen earlier still replaces the shared entry', () => {
  const now = Date.parse('2026-10-11T12:00:00Z');
  const remote = { lastSeen: '2026-10-11T10:00:00.000Z' };
  const local = { lastSeen: '2026-10-11T08:00:00.000Z' };
  assert.equal(preferLocalEntry(local, remote, {}, now), false);
  assert.equal(preferLocalEntry(local, remote, { editedAt: '2026-10-11T11:00:00.000Z' }, now), true);
  assert.equal(preferLocalEntry(local, remote, { editedAt: '2026-10-09T11:00:00.000Z' }, now), false);
  assert.equal(preferLocalEntry(remote, local, {}, now), true);
  assert.equal(preferLocalEntry(local, null, {}, now), true);
});
