#!/usr/bin/env node
'use strict';
/*
 * compare.js — the case x query table from the two hubs' result files.
 *
 * Usage: node compare.js <crm.json> <nocturne.json> [nocturne-mockdedup.json]
 *        node compare.js --selftest <crm.json>
 *
 * Readings compared, per ask:
 *   tt, override_tx  cgm-remote-monitor's key against two Nocturne readings:
 *                      "GetActiveAt"  StateSpanRepository.GetActiveAtAsync(category, state: null, t);
 *                                     a Cancelled span reads as none
 *                      "list"         the spans GetStateSpansAsync returns covering t (applies the
 *                                     deduplication visibility filter), joined
 *                    for tt, GetActiveAtAsync(category, "Active", t) is shown when it differs.
 *   override_ds      active / none on both sides.
 *   profile          effective profile name and basal rate on both sides.
 * --selftest checks the comparator: a file against itself must agree everywhere, and a copy
 * with one answer changed must disagree exactly once.
 */
const path = require('path');
const load = (p) => require(path.resolve(p));

function rows (crm, noc, nocMock) {
  const out = [];
  for (const cc of crm.cases) {
    const nc = noc.cases.find((x) => x.id === cc.id);
    const mc = nocMock ? nocMock.cases.find((x) => x.id === cc.id) : null;
    cc.queries.forEach((cq, i) => {
      const nq = nc.queries[i];
      const mq = mc ? mc.queries[i] : null;
      for (const [ask, ca] of Object.entries(cq.answers)) {
        const na = nq.answers[ask];
        const r = { id: cc.id, role: cc.role, label: cq.label, ask, crm: ca.key, nocActiveAt: na.key };
        if (ask === 'tt' || ask === 'override_tx') {
          r.nocList = na.keySet;
          r.agreeList = ca.key === na.keySet;
          if (ask === 'tt' && na.keyActiveState !== na.key) r.nocActiveState = na.keyActiveState;
          if (mq && mq.answers[ask].keySet !== na.keySet) r.nocListMockDedup = mq.answers[ask].keySet;
        }
        r.agreeActiveAt = ca.key === na.key;
        out.push(r);
      }
    });
  }
  return out;
}

function table (rs) {
  const yn = (b) => (b === undefined ? '' : b ? 'yes' : '**no**');
  const lines = [
    '| case | role | t | ask | cgm-remote-monitor | Nocturne GetActiveAt | Nocturne list read | agree (GetActiveAt / list) | note |',
    '|---|---|---|---|---|---|---|---|---|',
  ];
  for (const r of rs) {
    const notes = [];
    if (r.nocActiveState) notes.push('GetActiveAt(state "Active") = `' + r.nocActiveState + '`');
    if (r.nocListMockDedup) notes.push('list read with dedup mocked = `' + r.nocListMockDedup + '`');
    lines.push(`| ${r.id} | ${r.role} | ${r.label} | ${r.ask} | \`${r.crm}\` | \`${r.nocActiveAt}\` | ${r.nocList ? '`' + r.nocList + '`' : '—'} | ${yn(r.agreeActiveAt)}${r.agreeList === undefined ? '' : ' / ' + yn(r.agreeList)} | ${notes.join('; ')} |`);
  }
  return lines.join('\n');
}

const argv = process.argv.slice(2);
if (argv[0] === '--selftest') {
  const crm = load(argv[1]);
  const asNoc = (src) => ({ cases: src.cases.map((c) => ({ id: c.id, queries: c.queries.map((q) => ({ answers: Object.fromEntries(
    Object.entries(q.answers).map(([k, v]) => [k, { key: v.key, keySet: v.key, keyActiveState: v.key }])) })) })) });
  const same = rows(crm, asNoc(crm));
  const bad = same.filter((r) => !r.agreeActiveAt || r.agreeList === false).length;
  const mutated = asNoc(crm);
  const q0 = mutated.cases[0].queries[0];
  const k0 = Object.keys(q0.answers)[0];
  q0.answers[k0].key = q0.answers[k0].key + '-changed';
  const one = rows(crm, mutated).filter((r) => !r.agreeActiveAt).length;
  console.log(`selftest: identical inputs -> ${bad} disagreements (want 0); one changed answer -> ${one} disagreement(s) (want 1)`);
  process.exit(bad === 0 && one === 1 ? 0 : 1);
}

const [crmP, nocP, mockP] = argv;
const rs = rows(load(crmP), load(nocP), mockP ? load(mockP) : null);
console.log(table(rs));
const n = (f) => rs.filter(f).length;
console.log('\n' + [
  `rows: ${rs.length}`,
  `cases rows agreeing on GetActiveAt: ${n((r) => r.role === 'case' && r.agreeActiveAt)}/${n((r) => r.role === 'case')}`,
  `control rows agreeing on every reading: ${n((r) => r.role === 'control' && r.agreeActiveAt && r.agreeList !== false)}/${n((r) => r.role === 'control')}`,
].join('; '));
