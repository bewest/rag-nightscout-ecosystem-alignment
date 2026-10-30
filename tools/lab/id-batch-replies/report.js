'use strict';
// Markdown tables from a lab run: node report.js results/run.json
// Per item, one letter:
//   S  stored once, and the client counts it uploaded
//   r  stored once, but the client keeps re-sending it (each re-send matched, not stored again)
//   R  not stored, and the client keeps re-sending it
//   L  not stored, and the client counts it uploaded: dropped without a trace on the client
//   D  stored more than once
//   -  (nightscout-connect) never sent: older than its bookmark before the run
// A refused item is one the server meant to refuse (marked * in the scenario text).

const path = require('path');
const run = require(path.resolve(process.argv[2]));

function letter (it) {
  if (it.stored > 1) return 'D';
  if (it.stored === 1) return it.pending ? 'r' : 'S';
  return it.pending ? 'R' : 'L';
}

function retryWord (r) {
  if (!r.items.some(i => i.pending)) return 'no';
  return 'yes: ' + r.retry;
}

function idWord (r) {
  if (!r.readsId) return 'no';
  const kept = r.items.map(i => i.idKept).filter(x => x !== 'n/a');
  if (!kept.length || kept.every(x => x === null)) return 'yes (none kept)';
  const na = kept.filter(x => x === 'NA').length;
  const right = r.items.filter(i => i.idRight === true).length;
  const wrong = r.items.filter(i => i.idRight === false).length;
  return 'yes: ' + right + ' right' + (wrong ? ', ' + wrong + ' WRONG' : '') + (na ? ', ' + na + ' "NA"' : '');
}

const lines = [];
lines.push('| scenario | reply variant | client | 1st reply | items | marks uploaded | retries | reads `_id` |');
lines.push('|---|---|---|---|---|---|---|---|');
for (const r of run.runs) {
  if (r.na) continue;
  const c = r.cycles[0];
  const first = c.status + (c.length !== null ? ' [' + c.length + ']' : ' {}') + (c.errCode ? ' code ' + c.errCode : '');
  const marked = r.items.filter(i => i.marked).length + '/' + r.items.length;
  lines.push('| ' + [r.scenario, r.variant, r.client, first, r.items.map(letter).join(''), marked, retryWord(r), idWord(r)].join(' | ') + ' |');
}
lines.push('');
lines.push('Not a v1 batch client on these paths:');
const na = new Map();
run.runs.filter(r => r.na).forEach(r => { const k = r.client + ': ' + r.na; na.set(k, (na.get(k) || []).concat(r.scenario)); });
for (const [k, v] of na) lines.push('- ' + k + ' (' + [...new Set(v)].join(', ') + ')');
lines.push('');
lines.push('### nightscout-connect, run for real');
lines.push('');
lines.push('| scenario | reply variant | posts per cycle (status [length]) | items (sent x times) | items |');
lines.push('|---|---|---|---|---|');
for (const r of run.connect) {
  const posts = (r.cycles || []).map(c => c.posts.length ? c.posts.map(p => p.status + (p.length !== null ? ' [' + p.length + ']' : '')).join(',') : '-').join(' / ');
  const items = r.items.map(i => (i.late ? 'late:' : '') + 'x' + i.sentTimes + (i.stored === 1 ? ' stored' : i.stored > 1 ? ' DUP' : ' not stored')).join('; ');
  // '-': a batch item connect itself never sent (older than its bookmark
  // before the run: the seed's time). A late item never sent is L: it was
  // available and the bookmark had already passed it.
  const letters = r.items.map(i => i.stored > 1 ? 'D' : (i.sentTimes === 0 && !i.late) ? '-'
    : i.stored === 1 ? (i.sentTimes > 1 ? 'r' : 'S') : (i.sentTimes >= run.meta.cycles ? 'R' : 'L')).join('');
  lines.push('| ' + [r.scenario, r.variant, r.crash ? 'CRASH' : posts, items, letters].join(' | ') + ' |');
}
lines.push('');
lines.push('### Opt-in forms, open question (ii)');
lines.push('');
lines.push('| form | status | content type | reply | Warning | first item stored | query string in the server log |');
lines.push('|---|---|---|---|---|---|---|');
for (const f of run.optInForms) {
  lines.push('| ' + [f.name, f.status, '`' + f.contentType + '`', f.shape, f.warning ? '`' + f.warning + '`' : '-', f.storedFirst, f.urlInServerLog ? 'yes' : 'no'].join(' | ') + ' |');
}
lines.push('');
lines.push('### Profile update permission, open question (iii)');
lines.push('');
lines.push('| variant | status | slots | changed re-send applied | new profile stored |');
lines.push('|---|---|---|---|---|');
for (const p of run.profile) {
  lines.push('| ' + [p.name, p.status, Array.isArray(p.body) ? p.body.map(b => b.refused ? 'refused ' + b.refused : '_id').join(', ') : '`' + (p.body.description || p.body.message) + '`', p.changedApplied ? 'yes' : 'no', p.newStored].join(' | ') + ' |');
}
console.log(lines.join('\n'));
