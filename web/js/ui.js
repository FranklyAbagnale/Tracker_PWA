/**
 * ui.js
 * Rendering helpers. Every dynamic value goes through esc(): record fields come
 * from a repo other people can write to, so they are untrusted.
 */

import { formatPlateKey } from './matching.js';

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

export function renderResultCard(record) {
  const wrapper = document.createElement('div');
  wrapper.className = 'result-item';
  wrapper.innerHTML = `
    <strong>${esc(record.displayName || 'Unknown vehicle')}</strong>
    <div>Flag: ${esc(record.flag || 'unknown')}</div>
    <div>Plate: ${esc((record.plateAliases || []).map(formatPlateKey).join(', ') || 'not known')}</div>
  `;
  return wrapper;
}

export function renderEmptyState(message) {
  const wrapper = document.createElement('div');
  wrapper.className = 'result-item';
  wrapper.textContent = message;
  return wrapper;
}

export function options(values, selected, labelFor = (v) => v.charAt(0).toUpperCase() + v.slice(1)) {
  return values
    .map((v) => `<option value="${esc(v)}"${v === selected ? ' selected' : ''}>${esc(labelFor(v))}</option>`)
    .join('');
}
