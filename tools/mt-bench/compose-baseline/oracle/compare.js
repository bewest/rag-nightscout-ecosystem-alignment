'use strict';
// Compares oracle-stored.tsv with the clients' accepted counts. Exit 1 (RED) on any mismatch.
// A write the client could not classify (timeout/5xx) may have committed: stored must lie in
// [accepted, accepted + uncertain]; with zero uncertain writes the match must be exact.
const fs = require('node:fs'), path = require('node:path');
const dir = process.argv[2];
const stored = {};
for (const line of fs.readFileSync(path.join(dir, 'oracle-stored.tsv'), 'utf8').split('\n').filter(Boolean)) {
  const [tenant, kind, n] = line.split('\t'); (stored[tenant] ||= {})[kind] = Number(n);
}
const k6 = JSON.parse(fs.readFileSync(path.join(dir, 'k6-summary.json'), 'utf8')).metrics;
const count = key => k6[key]?.count ?? k6[key]?.values?.count ?? 0;
let probe = {}; try { probe = JSON.parse(fs.readFileSync(path.join(dir, 'fanout.json'), 'utf8')).probeWrites.byTenant || {}; } catch {}
const tenants = new Set([...Object.keys(stored), ...Object.keys(k6).map(k => /^writes_(?:ok|uncertain)\{tenant:([0-9a-f-]{36})\}$/.exec(k)?.[1]).filter(Boolean)]);
const rows = []; let red = 0, totalStored = 0, totalOk = 0, totalUncertain = 0;
for (const t of [...tenants].sort()) {
  const s = ['entries', 'devicestatus', 'treatments'].reduce((a, k) => a + (stored[t]?.[k] || 0), 0);
  const ok = count(`writes_ok{tenant:${t}}`), un = count(`writes_uncertain{tenant:${t}}`);
  const ps = stored[t]?.probe || 0, pk = probe[t] || 0;
  const match = s >= ok && s <= ok + un && ps === pk;
  if (!match) red++;
  totalStored += s; totalOk += ok; totalUncertain += un;
  rows.push([t, s, ok, un, ps, pk, match ? 'ok' : 'MISMATCH'].join('\t'));
}
const kinds = ['entries', 'devicestatus', 'treatments'].map(k => {
  const s = Object.values(stored).reduce((a, v) => a + (v[k] || 0), 0); return `${k}: stored ${s} accepted ${count(`writes_ok{kind:${k}}`)}`;
});
console.log('tenant\tstored\taccepted\tuncertain\tprobe_stored\tprobe_accepted\tverdict');
rows.forEach(r => console.log(r));
console.log(kinds.join('; '));
console.log(`ORACLE ${red ? 'RED' : 'GREEN'}: tenants ${tenants.size}, mismatched ${red}, stored ${totalStored}, accepted ${totalOk}, uncertain ${totalUncertain}`);
process.exit(red ? 1 : 0);
