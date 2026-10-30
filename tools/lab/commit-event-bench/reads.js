'use strict';
// Round 3: what each naming arm reads per write. Every arm is a server.js
// child with one listener (identity reads run only when someone listens) and
// its own database. Identity reads (a find projected to exactly
// {_id: 1, identifier: 1}, which only the naming prototypes issue) are counted
// in the arm's process by readtap.js: queries, documents and BSON bytes per
// write. The database profiler (level 2) gives the context: every other read
// (the route's own, the loader's), and a cross-check of the identity count. It
// cannot count large calls: its 1 MB capped collection drops the identity
// read's entry behind a backfill's per-operation entries (seen in the first
// round-3 run, which reported 0 identity reads on every re-send backfill).
//
//   node reads.js --mongo mongodb://127.0.0.1:27601 --reps 10 --out results/round3/reads.json \
//     --arm base=<tree> --arm pre=<tree> --arm post=<tree> --arm since=<tree>
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = []; argv.forEach((a, i) => { if (a === '--arm') { const [name, tree] = argv[i + 1].split('='); arms.push({ name, tree }); } });
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27601');
const REPS = +opt('--reps', 10);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'round3', 'reads.json')));

function projectionOf (p) {
  const c = p.command || {};
  if (c.find) return c.projection;
  if (c.getMore && p.originatingCommand) return p.originatingCommand.projection;
  return undefined;
}
const identity = proj => !!proj && Object.keys(proj).length === 2 && proj._id === 1 && proj.identifier === 1;
process.env.NODE_OPTIONS = ((process.env.NODE_OPTIONS || '') + ' --require ' + path.join(__dirname, 'readtap.js')).trim();
let tapSeq = 0;
const tap = a => new Promise(resolve => {
  const id = ++tapSeq;
  const on = m => { if (m && m.cmd === 'reads' && m.id === id) { a.child.off('message', on); resolve(m.tally); } };
  a.child.on('message', on); a.child.send({ cmd: 'reads', id });
});
const isRead = p => p.op === 'query' || p.op === 'getmore' || (p.op === 'command' && p.command && (p.command.aggregate || p.command.count || p.command.distinct));

(async () => {
  const { MongoClient } = require(path.join(arms[0].tree, 'node_modules/mongodb'));
  const cli = await MongoClient.connect(MONGO + '/' + L.QS);
  const run = L.hex().slice(0, 6);
  const live = [];
  for (const a of arms) {
    const arm = await L.startArm(a.name, a.tree, MONGO, 'devent_rd_' + a.name + '_' + run, 'count');
    await cli.db(arm.db).command({ profile: 2 });
    live.push(arm);
  }
  const all = Object.assign({}, L.SHAPES, L.BULK, { 'v1-entries-query-delete-100': L.queryDelete(100), 'v1-entries-query-delete-1000': L.queryDelete(1000) });
  const only = opt('--only', null);
  const shapes = Object.entries(all).filter(([n]) => !only || only.split(',').includes(n));
  const res = {};
  for (const [name, s] of shapes) {
    res[name] = {};
    const reps = /10000/.test(name) ? Math.max(2, Math.round(REPS / 5)) : REPS;
    for (const a of live) {
      const db = cli.db(a.db);
      const agg = { calls: 0, identityQueries: 0, identityDocs: 0, identityBytes: 0, profiledIdentity: 0, otherReads: 0, otherBytes: 0, failed: 0 };
      for (let rep = 0; rep < reps; rep++) {
        const tag = name + '-' + run + '-' + rep + '-' + a.name;
        const seeded = s.seed ? await s.seed(a, tag) : undefined;
        await L.sleep(400);
        const t = new Date();
        const t0 = await tap(a);
        const r = await s.run(a, tag, seeded);
        if (!r || r.s >= 400 || r === 'NO-ACK') agg.failed++;
        await L.sleep(400);
        const t1 = await tap(a);
        agg.identityQueries += t1.queries - t0.queries; agg.identityDocs += t1.docs - t0.docs; agg.identityBytes += t1.bytes - t0.bytes;
        const prof = await db.collection('system.profile').find({ ts: { $gte: t } }).toArray();
        agg.calls++;
        for (const p of prof) {
          if (!isRead(p)) continue;
          if (identity(projectionOf(p))) { if (p.op === 'query') agg.profiledIdentity++; } else { agg.otherReads++; agg.otherBytes += p.responseLength || 0; }
        }
      }
      res[name][a.name] = agg;
    }
    console.error(name + ' ' + JSON.stringify(Object.fromEntries(Object.entries(res[name]).map(([k, v]) => [k, [v.identityQueries, v.identityDocs, v.identityBytes].join('/')]))));
  }
  for (const a of live) await a.stop();
  await cli.close();
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({ run, reps: REPS, node: process.version, arms: arms.map(a => Object.assign({}, a, { since: process.env['CEB_SINCE_' + a.name] || null, head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim() })), shapes: res }, null, 1));
  console.log('Per write (mean over calls): identity queries / documents returned / BSON bytes returned (readtap); other reads per write (profiler) in brackets; [profiler identity queries] where they differ from readtap.');
  console.log('| shape | ' + arms.map(a => a.name).join(' | ') + ' |');
  console.log('|---|' + arms.map(() => '---').join('|') + '|');
  const f = (x, c) => (x / c).toFixed(x / c < 10 ? 2 : 0);
  for (const [name, byArm] of Object.entries(res)) {
    console.log('| ' + name + ' | ' + arms.map(a => { const g = byArm[a.name]; return f(g.identityQueries, g.calls) + ' / ' + f(g.identityDocs, g.calls) + ' / ' + f(g.identityBytes, g.calls) + ' B (' + f(g.otherReads, g.calls) + ')' + (g.profiledIdentity !== g.identityQueries ? ' [' + f(g.profiledIdentity, g.calls) + ']' : '') + (g.failed ? ' FAILED ' + g.failed : ''); }).join(' | ') + ' |');
  }
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
