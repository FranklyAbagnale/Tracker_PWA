// Plate states: the web app against tests/fixtures/state_cases.json (the same cases are run against
// scripts/plate_states.py and tools/import.html, so the three cannot drift apart).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { normalizeState, splitPlateKey, plateKey, formatPlateKey, isValidState, stateMatches, baseState, stateCode, stateLabel } from '../web/js/matching.js';
import { rankPlateMatches, plateMatchRows } from '../web/js/plate-manager.js';
import { STATES, MX_STATES, STATE_LABELS, STATE_NAMES, STATE_GROUPS } from '../web/js/config.js';

const CASES = JSON.parse(readFileSync(new URL('./fixtures/state_cases.json', import.meta.url), 'utf8'));

test('normalizeState cases', () => {
  for (const [text, code] of CASES.normalize) assert.equal(normalizeState(text), code, text);
});

test('splitPlateKey cases', () => {
  for (const [key, parts] of CASES.keys) assert.deepEqual(splitPlateKey(key), parts ? { state: parts[0], plate: parts[1] } : null, key);
});

test('plate keys carry Mexican and federal states', () => {
  assert.equal(plateKey('son', 'abc 123'), 'SON-ABC123');
  assert.equal(plateKey('gov dhs', '12345'), 'GOV-DHS-12345');
  assert.equal(plateKey('USG', 'g42'), 'USG-G42');
  assert.equal(formatPlateKey('GOV-DHS-12345'), 'GOV-DHS 12345');
  assert.equal(formatPlateKey('SON-ABC123'), 'SON ABC123');
  assert.equal(formatPlateKey('XX-ABC123'), 'ABC123 (state unknown)');
});

test('state lists', () => {
  assert.equal(MX_STATES.length, 32);
  assert.equal(new Set(STATES).size, STATES.length);
  for (const s of MX_STATES) assert.ok(STATE_LABELS[s], s);
  assert.ok(['SON', 'USG', 'GOV', 'BC', 'QC', 'XX'].every((s) => STATES.includes(s)));
  assert.ok(isValidState('GOV-DHS') && isValidState('SON') && !isValidState('GOV-') && !isValidState('ZZZ'));
  assert.equal(baseState('GOV-DHS'), 'GOV');
  assert.equal(stateCode('GOV-DHS'), 'DHS');
  assert.equal(stateLabel('SON'), 'Sonora (SON)');
  assert.equal(stateLabel('CA'), 'CA');
  assert.equal(stateLabel('XX'), 'State unknown');
});

test('the glossary has a name for every state and lists each once', () => {
  for (const s of STATES) assert.ok(STATE_NAMES[s], `no name for ${s}`);
  const listed = STATE_GROUPS.flatMap((g) => g.codes);
  assert.equal(listed.length, STATES.length);
  assert.deepEqual([...listed].sort(), [...STATES].sort());
});

test('a federal search without a code finds every code; with a code only that one', () => {
  assert.ok(stateMatches('GOV-DHS', 'GOV') && stateMatches('GOV', 'GOV') && stateMatches('GOV-DHS', 'GOV-DHS'));
  assert.ok(!stateMatches('GOV-FBI', 'GOV-DHS') && !stateMatches('USG-G42', 'GOV') && !stateMatches('CA', 'CAL'));
  const entries = [
    { vehicleKey: 'VEH_00000001', plateAliases: ['GOV-DHS-12345'], lastSeen: '2026-01-02T00:00:00Z' },
    { vehicleKey: 'VEH_00000002', plateAliases: ['GOV-FBI-12345'], lastSeen: '2026-01-01T00:00:00Z' },
    { vehicleKey: 'VEH_00000003', plateAliases: ['CA-12345'], lastSeen: '2026-01-03T00:00:00Z' }
  ];
  assert.deepEqual(rankPlateMatches(entries, '12345', 'GOV').map((e) => e.vehicleKey), ['VEH_00000001', 'VEH_00000002']);
  assert.deepEqual(rankPlateMatches(entries, '12345', 'GOV-FBI').map((e) => e.vehicleKey), ['VEH_00000002']);
  assert.equal(plateMatchRows(entries, '12345', null).length, 3);
});
