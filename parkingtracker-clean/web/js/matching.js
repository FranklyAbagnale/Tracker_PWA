import { PLATE_MAX_LENGTH, STATES, UNKNOWN_STATE, FEDERAL_STATES, FEDERAL_CODE_MAX, STATE_LABELS } from './config.js';

export function normalizePlate(value) {
  return String(value || '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
    .slice(0, PLATE_MAX_LENGTH);
}

const FEDERAL_RE = new RegExp(`^(${FEDERAL_STATES.join('|')})(?:[\\s\\-_:/]+([A-Z0-9]{1,${FEDERAL_CODE_MAX}}))?$`);
const foldText = (v) => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim().toUpperCase();

/** USG / GOV with an optional code ("usg g42" gives USG-G42), or null when the text is not one. */
export function federalState(value) {
  const m = FEDERAL_RE.exec(foldText(value));
  return m ? (m[2] ? `${m[1]}-${m[2]}` : m[1]) : null;
}

/** True for a known code (CA, BC, SON, XX, USG, GOV) or USG / GOV with a code (GOV-DHS). */
export function isValidState(value) {
  const s = String(value || '');
  return STATES.includes(s) || new RegExp(`^(?:${FEDERAL_STATES.join('|')})-[A-Z0-9]{1,${FEDERAL_CODE_MAX}}$`).test(s);
}

/** The part of a state before its code: GOV-DHS gives GOV, CA gives CA. */
export const baseState = (state) => String(state || '').split('-')[0];
export const stateCode = (state) => String(state || '').split('-').slice(1).join('-');

/** Does a plate's state satisfy a search state? GOV matches GOV and GOV-DHS; GOV-DHS matches only GOV-DHS. */
export function stateMatches(have, want) {
  return have === want || (FEDERAL_STATES.includes(want) && baseState(have) === want);
}

/** A state as stored: CA, BC, SON, USG, GOV, USG-G42, GOV-DHS, or XX when missing or not a known code. */
export function normalizeState(value) {
  const federal = federalState(value);
  if (federal) return federal;
  const s = foldText(value).replace(/[^A-Z]/g, '');
  return STATES.includes(s) ? s : UNKNOWN_STATE;
}

/** For pickers: "Sonora (SON)", "CA". */
export function stateLabel(state) {
  const base = baseState(state);
  if (state === UNKNOWN_STATE) return 'State unknown';
  const name = STATE_LABELS[base];
  return name ? `${name}${stateCode(state) ? ' ' + stateCode(state) : ` (${state})`}` : state;
}

/** The identity of a plate: state + plate, e.g. CA-7ABC123. Empty when there is no plate. */
export function plateKey(state, plate) {
  const p = normalizePlate(plate);
  return p ? `${normalizeState(state)}-${p}` : '';
}

export function splitPlateKey(key) {
  const i = String(key || '').lastIndexOf('-'); // the plate has no dash, so the state is everything before the last one
  if (i < 1) return null;
  const state = key.slice(0, i); const plate = key.slice(i + 1);
  return isValidState(state) && /^[A-Z0-9]{1,20}$/.test(plate) ? { state, plate } : null;
}

/** For people: "CA 7ABC123", or "7ABC123 (state unknown)". */
export function formatPlateKey(key) {
  const parts = splitPlateKey(key);
  if (!parts) return String(key || '');
  return parts.state === UNKNOWN_STATE ? `${parts.plate} (state unknown)` : `${parts.state} ${parts.plate}`;
}

export function computePlateSimilarity(a, b) {
  const pa = normalizePlate(a);
  const pb = normalizePlate(b);
  if (!pa || !pb) return 0;
  if (pa === pb) return 1;
  const dist = levenshtein(pa, pb);
  const maxLen = Math.max(pa.length, pb.length, 1);
  return 1 - dist / maxLen;
}

function levenshtein(a, b) {
  const dp = Array.from({ length: a.length + 1 }, () => Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) dp[i][0] = i;
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;

  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + cost
      );
    }
  }

  return dp[a.length][b.length];
}
