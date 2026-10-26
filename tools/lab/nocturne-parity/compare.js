// compare.js — the parity table (results/compare.md) from the document diff and the probe results.
//
// Usage:
//   node compare.js <results dir>             prints compare.md (reads docdiff.json, meta.json and
//                                             the four probe-*.jsonl files in <results dir>)
//   node compare.js --selftest <results dir>  checks the probe comparator: identical inputs agree
//                                             everywhere; one changed status gives exactly one
//                                             disagreement, on that probe
//
// How two probe results are compared (README "How results are compared"): joined on probe id and
// credential class; equal when status, body kind (array / object / text / empty / null), the
// top-level keys of an object body, the kind of an envelope's `result`, and the probe's named
// semantic values (`sem`) are all equal. Array lengths and record field lists (the keys inside
// array items or inside `result`) are reported, not judged: both servers return stored client
// fields and add their own.
const fs = require('fs');
const path = require('path');

const MODES = [ // [crm file, Nocturne file, what the anonymous set-up is]
  ['probe-crm-denied.jsonl', 'probe-noc-public-none.jsonl', 'crm AUTH_DEFAULT_ROLES=denied | Nocturne Public member with no permissions (its default)'],
  ['probe-crm-readable.jsonl', 'probe-noc-public-read.jsonl', 'crm AUTH_DEFAULT_ROLES=readable | Nocturne Public member given its read scopes, 24-hour clamp off (applies to share-link hosts only, so apex requests are unchanged: see README)'],
];
function load (file) {
  const m = new Map();
  for (const l of fs.readFileSync(file, 'utf8').split('\n')) {
    if (!l.trim()) continue;
    const r = JSON.parse(l);
    m.set(r.id + '|' + (r.cred || ''), r);
  }
  return m;
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function judge (c, n) {
  if (!c || !n) return {verdict: !c ? 'only-noc-run' : 'only-crm-run', why: [(!c ? 'not run on crm' : 'not run on Nocturne') + ' (the credential it needs was not issued)']};
  const why = [];
  if (c.error || n.error) { if (!eq(c.error, n.error)) why.push('request error'); }
  if (c.status !== n.status) why.push('status');
  const cs = c.shape || {}, ns = n.shape || {};
  if (cs.kind !== ns.kind) why.push('body kind');
  else if (cs.kind === 'object' && !eq(cs.keys, ns.keys)) why.push('body keys');
  if (cs.result || ns.result) if ((cs.result || {}).kind !== (ns.result || {}).kind) why.push('result kind');
  if ((c.sem || n.sem) && !eq(c.sem, n.sem)) why.push('semantics');
  return {verdict: why.length ? 'differs' : 'same', why};
}
function cell (r) {
  if (!r) return 'not run';
  if (r.status === undefined) return r.error ? 'error' : '—';
  const s = r.shape || {};
  let t = r.status + ' ' + s.kind;
  if (s.kind === 'object') t += ' {' + s.keys.join(',') + '}';
  if (s.result) t += ' result:' + s.result.kind;
  return t;
}
function semCell (r) { return r && r.sem ? '`' + JSON.stringify(r.sem).replace(/\|/g, '\\|') + '`' : ''; }
function fieldNote (c, n) {
  const ik = r => (r && r.shape && (r.shape.itemKeys || (r.shape.result && (r.shape.result.itemKeys || r.shape.result.keys)))) || null;
  const a = ik(c), b = ik(n);
  if (!a || !b) return '';
  const onlyC = a.filter(x => !b.includes(x)), onlyN = b.filter(x => !a.includes(x));
  if (!onlyC.length && !onlyN.length) return '';
  return 'record fields: ' + (onlyC.length ? onlyC.length + ' only crm (' + onlyC.slice(0, 4).join(', ') + (onlyC.length > 4 ? ', …' : '') + ')' : '') +
    (onlyC.length && onlyN.length ? '; ' : '') + (onlyN.length ? onlyN.length + ' only Nocturne (' + onlyN.slice(0, 4).join(', ') + (onlyN.length > 4 ? ', …' : '') + ')' : '');
}
function msgNote (c, n) {
  const m = r => r && r.msg ? '"' + r.msg.replace(/\|/g, '\\|') + '"' : null;
  const a = m(c), b = m(n);
  if (!a && !b) return '';
  return 'message: crm ' + (a || '—') + ' / Nocturne ' + (b || '—');
}
function compareProbes (crm, noc) {
  const keys = [...new Set([...crm.keys(), ...noc.keys()])];
  return keys.map(k => { const c = crm.get(k), n = noc.get(k); return {key: k, id: k.split('|')[0], cred: k.split('|')[1], op: (c || n).op, c, n, ...judge(c, n)}; });
}
function docAspects (row) {
  if (!row.diffs) return '';
  return row.diffs.map(d => {
    if (d.crm !== undefined) return d.aspect + ' crm ' + d.crm + ' / Nocturne ' + d.noc;
    const f = (l, w) => l.length ? w + ' ' + (l.length > 5 ? l.slice(0, 5).join(', ') + ` (+${l.length - 5})` : l.join(', ')) : '';
    return d.aspect + ': ' + [f(d.onlyCrm, 'only crm'), f(d.onlyNoc, 'only Nocturne')].filter(Boolean).join('; ');
  }).join(' · ');
}
function render (dir) {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json'), 'utf8'));
  const doc = JSON.parse(fs.readFileSync(path.join(dir, 'docdiff.json'), 'utf8')).rows;
  const runs = MODES.map(([cf, nf, what]) => ({what, rows: compareProbes(load(path.join(dir, cf)), load(path.join(dir, nf)))}));
  const primary = runs[0].rows;
  const L = [];
  L.push('# cgm-remote-monitor 16.0.0 API and Nocturne: parity table', '');
  L.push('*Generated by `compare.js` from the files beside it; do not edit by hand.* Contributor-facing. ' +
    'How it was measured and what it leaves out: [../README.md](../README.md).', '');
  L.push('| | commit |', '|---|---|');
  L.push(`| cgm-remote-monitor | \`${meta.crm.commit.slice(0, 8)}\` (${meta.crm.what}) |`);
  L.push(`| Nocturne | \`${meta.noc.commit.slice(0, 9)}\` (${meta.noc.what}) |`);
  L.push(`| probe set | \`probe.js\` sha256 \`${meta.probeSha256.slice(0, 12)}\` |`, '');

  // ---- counts
  const dc = {}; for (const r of doc) dc[r.class] = (dc[r.class] || 0) + 1;
  const asp = {}; for (const r of doc) for (const d of r.diffs || []) asp[d.aspect] = (asp[d.aspect] || 0) + 1;
  L.push('## Counts', '');
  L.push('Documents (one row per operation key after the normalisation in `ops.js`; a cgm-remote-monitor template that several Nocturne paths join counts once per join):', '');
  L.push('| class | operations |', '|---|---|');
  for (const k of ['same', 'differs', 'only-crm', 'only-noc', 'only-noc-outside-crm-docs']) L.push(`| ${k} | ${dc[k] || 0} |`);
  L.push('', 'Aspects behind `differs` (an operation can differ in several):', '', '| aspect | operations |', '|---|---|');
  for (const [k, v] of Object.entries(asp).sort()) L.push(`| ${k} | ${v} |`);
  L.push('');
  for (const run of runs) {
    const pc = {}; for (const r of run.rows) pc[r.verdict] = (pc[r.verdict] || 0) + 1;
    const why = {}; for (const r of run.rows) for (const w of r.why) if (r.verdict === 'differs') why[w] = (why[w] || 0) + 1;
    L.push(`Probes, ${run.what}: ${run.rows.length} joined results — ` + Object.entries(pc).sort().map(([k, v]) => `${k} ${v}`).join(', ') +
      '; differing in ' + Object.entries(why).sort().map(([k, v]) => `${k} ${v}`).join(', ') + '.', '');
  }

  // ---- operations
  L.push('## Operations', '');
  L.push('Measured cells are the first probe of that operation with the full-access credential, in the first set-up (`status kind {keys}`); the verdict\'s measured part counts every probe of the operation in both set-ups. `—` in a doc column: not in that document.', '');
  L.push('| operation | crm 16.0.0 doc | crm measured | Nocturne doc | Nocturne measured | verdict | note |', '|---|---|---|---|---|---|---|');
  const allProbes = runs.flatMap(r => r.rows);
  const statted = new Set();
  // probe statistics go on the first table row of an operation key (a crm template that several
  // Nocturne paths join has several rows)
  const opRow = (display, key, crmDoc, nocDoc, docClass, note) => {
    let first = null, measured = '';
    if (!statted.has(key)) {
      statted.add(key);
      const ps = allProbes.filter(p => p.op === key);
      first = primary.find(p => p.op === key && p.cred === 'full');
      measured = ps.length ? `; measured ${ps.filter(p => p.verdict === 'same').length}/${ps.length} same` : '; not probed';
    } else measured = '; probes on the row above';
    L.push(`| \`${display}\` | ${crmDoc} | ${first ? cell(first.c) : '—'} | ${nocDoc} | ${first ? cell(first.n) : '—'} | doc ${docClass}${measured} | ${note.replace(/\|/g, '\\|')} |`);
  };
  for (const r of doc) {
    if (r.class === 'only-noc-outside-crm-docs') continue;
    opRow(r.key, r.key, r.crm ? 'yes' : '—', r.noc ? '`' + r.noc.paths.join('`, `') + '`' : '—', r.class, docAspects(r));
  }
  const extra = [...new Set(allProbes.map(p => p.op))].filter(o => !statted.has(o)).sort();
  for (const o of extra) opRow(o, o, '—', '—', 'in neither document', '');
  L.push('');
  L.push('Operations in Nocturne\'s document outside the paths cgm-remote-monitor\'s v1 and v3 documents cover (v2, `/pebble`); cgm-remote-monitor serves v2 routes too, undocumented in #8858, so these are not compared:', '');
  L.push(doc.filter(r => r.class === 'only-noc-outside-crm-docs').map(r => '`' + r.key + '`').join(', '), '');

  // ---- semantics
  L.push('## Semantics probed', '');
  L.push('Full-access credential, first set-up. `sem` values are computed by `probe.js` from the response body; see its source for each.', '');
  L.push('| probe | crm | Nocturne | verdict | note |', '|---|---|---|---|---|');
  for (const r of primary.filter(p => p.id.startsWith('sem.') || /\.create(\.again)?$|\.read$|\.client-identifier$|^v3\.credential$|^v2\.subject\.accessToken$|^v3\.lastModified$/.test(p.id))) {
    L.push(`| \`${r.id}\` | ${cell(r.c)} ${semCell(r.c)} | ${cell(r.n)} ${semCell(r.n)} | ${r.verdict}${r.why.length ? ' (' + r.why.join(', ') + ')' : ''} | ${msgNote(r.c, r.n)} |`);
  }
  L.push('');

  // ---- every probe
  for (const run of runs) {
    L.push(`## Every probe: ${run.what}`, '');
    L.push('| probe | credential | operation | crm | Nocturne | verdict | note |', '|---|---|---|---|---|---|---|');
    for (const r of run.rows) L.push(`| \`${r.id}\` | ${r.cred} | \`${r.op}\` | ${cell(r.c)} | ${cell(r.n)} | ${r.verdict}${r.why.length ? ' (' + r.why.join(', ') + ')' : ''} | ${[fieldNote(r.c, r.n), msgNote(r.c, r.n)].filter(Boolean).join(' · ')} |`);
    L.push('');
  }
  return L.join('\n') + '\n';
}

if (process.argv[2] === '--selftest') {
  const dir = process.argv[3];
  const crm = load(path.join(dir, MODES[0][0]));
  const same = compareProbes(crm, crm);
  if (same.some(r => r.verdict !== 'same')) { console.error('selftest: identical inputs disagree'); process.exit(1); }
  const altered = new Map([...crm].map(([k, v]) => [k, JSON.parse(JSON.stringify(v))]));
  const victim = [...altered.keys()].find(k => altered.get(k).status === 200);
  altered.get(victim).status = 299;
  const diff = compareProbes(crm, altered).filter(r => r.verdict !== 'same');
  if (diff.length !== 1 || diff[0].key !== victim || !eq(diff[0].why, ['status'])) { console.error('selftest: expected one status disagreement on ' + victim, diff.map(r => r.key)); process.exit(1); }
  console.error('selftest ok: ' + same.length + ' identical pairs agree; one changed status (' + victim + ') gives exactly one disagreement');
} else {
  process.stdout.write(render(process.argv[2]));
}
