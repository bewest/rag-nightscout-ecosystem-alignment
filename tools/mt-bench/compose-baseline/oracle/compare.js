'use strict';
// Compares oracle-stored.tsv with the clients' accepted totals. Exit 1 (RED) on any mismatch.
// k6 counts writes per kind and in total, never per tenant: the per-tenant figure is the stored
// row count. A write the client could not classify (timeout/5xx) may have committed: stored must
// lie in [accepted, accepted + uncertain]; with zero uncertain writes the match must be exact.
const fs = require('node:fs'), path = require('node:path');
const dir = process.argv[2];
const stored = {};
for (const line of fs.readFileSync(path.join(dir, 'oracle-stored.tsv'), 'utf8').split('\n').filter(Boolean)) {
  const [tenant, kind, n] = line.split('\t'); (stored[tenant] ||= {})[kind] = Number(n);
}
const k6 = JSON.parse(fs.readFileSync(path.join(dir, 'k6-summary.json'), 'utf8')).metrics;
const count = key => k6[key]?.count ?? k6[key]?.values?.count ?? 0;
let probe = {}; try { probe = JSON.parse(fs.readFileSync(path.join(dir, 'fanout.json'), 'utf8')).probeWrites.byTenant || {}; } catch {}
const KINDS = ['entries', 'devicestatus', 'treatments'];
const rows = []; let red = 0, totalStored = 0;
for (const t of Object.keys(stored).sort()) {
  const s = KINDS.reduce((a, k) => a + (stored[t]?.[k] || 0), 0);
  const ps = stored[t]?.probe || 0, pk = probe[t] || 0;
  if (ps !== pk) red++;
  totalStored += s;
  rows.push([t, s, ps, pk, ps === pk ? 'ok' : 'MISMATCH'].join('\t'));
}
const ok = count('writes_ok'), un = count('writes_uncertain');
if (!(totalStored >= ok && totalStored <= ok + un)) red++;
const kinds = KINDS.map(k => {
  const s = Object.values(stored).reduce((a, v) => a + (v[k] || 0), 0), accepted = count(`writes_ok{kind:${k}}`);
  if (!(s >= accepted && s <= accepted + un)) red++;
  return `${k}: stored ${s} accepted ${accepted}`;
});
console.log('tenant\tstored\tprobe_stored\tprobe_accepted\tverdict');
rows.forEach(r => console.log(r));
console.log(kinds.join('; '));
console.log(`ORACLE ${red ? 'RED' : 'GREEN'}: tenants ${rows.length}, mismatches ${red}, stored ${totalStored}, accepted ${ok}, uncertain ${un}`);
process.exit(red ? 1 : 0);
