// ops.js — path normalisation shared by docdiff.js and compare.js.
//
// An operation key is "METHOD /path" after these steps, in order:
//  1. the document's server URL (or a path-level `servers` override) is prefixed, so both sides
//     use full paths (/api/v1/..., /api/v3/..., /api/versions);
//  2. a trailing slash is dropped;
//  3. literal segments are lower-cased: both servers route case-insensitively (express's default
//     `caseSensitive: false`; ASP.NET Core routing), and Nocturne's document spells controller
//     names (`/api/v1/Entries`);
//  4. every template parameter becomes `{}`, whatever its name (`{id}`, `{_id}`, `{spec}`,
//     `{identifier}`), so positions are compared, not names;
//  5. cgm-remote-monitor's v3 `{collection}` is expanded to its six collections (the enum in the
//     document): Nocturne's document lists each collection as a literal path;
//  6. cgm-remote-monitor documents an express optional tail as one template whose description says
//     trailing parameters may be left off (`/slice/{storage}/{field}/{type}/{prefix}/{regex}`,
//     express `/slice/:storage/:field{/:type}{/:prefix}{/:regex}`); it is expanded to one key per
//     depth (OPTIONAL_TAILS below, taken from the descriptions). Nocturne's document lists each
//     depth as its own path;
//  7. keys are joined exactly first. A Nocturne key left over joins a cgm-remote-monitor template
//     that covers it (crm has `{}` wherever the two differ) when exactly one such template exists:
//     `GET /api/v1/count/entries/where` in Nocturne's document joins `GET /api/v1/count/{}/where`.
//     The reverse (a Nocturne template covering a crm literal, such as `/api/v1/profile/{}` and
//     `/api/v1/profile/current`) is never joined: those are different operations.
// Format suffixes (`/entries.json`) and query strings are not part of a key.
const V3_COLLECTIONS = ['devicestatus', 'entries', 'food', 'profile', 'settings', 'treatments'];
// crm template (after steps 1-4) -> how many trailing parameters may be left off, and how many
// more may follow, as the document's description of the operation says
const OPTIONAL_TAILS = {
  '/api/v1/slice/{}/{}/{}/{}/{}': {drop: 3, add: 0},  // type, prefix, regex may be left off
  '/api/v1/times/{}/{}': {drop: 2, add: 0},           // regex, or both, may be left off
  '/api/v1/times/echo/{}/{}': {drop: 2, add: 0},      // as for /times
  '/api/v1/echo/{}/{}': {drop: 1, add: 1},            // model may be left off; a third segment may follow
};

function joinServer (server, p) {
  return (server.replace(/\/$/, '') + p).replace(/\/+/g, '/');
}
function normPath (p) {
  return p.replace(/\/+$/, '').split('/').map(s => /^\{.*\}$/.test(s) ? '{}' : s.toLowerCase()).join('/') || '/';
}
// expand one crm (path, method) into keys
function crmKeys (fullPath) {
  let p = normPath(fullPath);
  const paths = fullPath.includes('/api/v3/{collection}')
    ? V3_COLLECTIONS.map(c => p.replace('/api/v3/{}', '/api/v3/' + c)) : [p];
  const out = [];
  for (const q of paths) {
    const t = OPTIONAL_TAILS[q];
    if (t) {
      const segs = q.split('/');
      for (let n = segs.length - t.drop; n <= segs.length + t.add; n++) {
        const s = segs.slice(0, n); while (s.length < n) s.push('{}');
        out.push(s.join('/'));
      }
    } else out.push(q);
  }
  return out;
}
function matches (a, b) { // segment-wise, `{}` matches anything
  const x = a.split('/'), y = b.split('/');
  return x.length === y.length && x.every((s, i) => s === y[i] || s === '{}' || y[i] === '{}');
}
module.exports = {V3_COLLECTIONS, OPTIONAL_TAILS, joinServer, normPath, crmKeys, matches};
