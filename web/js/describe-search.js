/**
 * describe-search.js
 * Find vehicles by description from the index entries: color, make, model, year, body style, features, plates.
 * Words are ANDed and may match anywhere in a field; entries saved before the index carried those fields still
 * match on their display name.
 */

const norm = (s) => String(s ?? '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');

export function searchText(entry) {
  return norm([
    entry.displayName, entry.color, entry.make, entry.model, entry.year, entry.bodyStyle,
    ...(entry.features || []), ...(entry.plateAliases || [])
  ].filter((v) => v !== undefined && v !== null).join(' '));
}

/** Split into words; "quoted phrases" stay together. */
export function tokenize(query) {
  const out = [];
  for (const m of String(query || '').matchAll(/"([^"]+)"|(\S+)/g)) out.push(norm(m[1] || m[2]));
  return out.filter(Boolean);
}

/**
 * @param {object[]} entries index entries
 * @param {{query?:string, flag?:string, bodyStyle?:string}} criteria
 * @returns {object[]} matches, most recently seen first
 */
export function searchByDescription(entries, { query = '', flag = '', bodyStyle = '' } = {}) {
  const words = tokenize(query);
  if (!words.length && !flag && !bodyStyle) return [];
  const hits = (entries || []).filter((e) => {
    if (flag && e.flag !== flag) return false;
    if (bodyStyle && e.bodyStyle !== bodyStyle) return false;
    if (!words.length) return true;
    const text = searchText(e);
    return words.every((w) => text.includes(w));
  });
  return hits.sort((a, b) => (Date.parse(b.lastSeen) || 0) - (Date.parse(a.lastSeen) || 0));
}
