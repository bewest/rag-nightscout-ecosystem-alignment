'use strict';
// One cgm-remote-monitor tree booted in this process exactly as
// lib/server/server.js boots it (bootevent, app, http listener, websocket),
// driven by bench.js over HTTP and socket.io. Every module is require()d by
// path from the tree, so two of these children run two builds side by side.
//
// Usage (spawned by the lab, not by hand):
//   node server.js <tree> <mongo uri with db> [--listener none|count|capture]
// The API secret comes from BENCH_SECRET; nothing secret is written here.
//
// Listeners on `storage-write-committed` (the event under decision):
//   none     no listener at all (production today: nothing subscribes)
//   count    one trivial listener (counts events)
//   capture  keeps every event (plain JSON copy) for the parent to read over IPC
// IPC: {cmd:'events'} -> {events} and clears; {cmd:'exit'}.
const path = require('path');
const crypto = require('crypto');
const http = require('http');
const argv = process.argv.slice(2);
const [tree, uri] = argv;
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const LISTENER = opt('--listener', 'count');
const SECRET = process.env.BENCH_SECRET;
if (!SECRET || SECRET.length < 12) { console.error('BENCH_SECRET required'); process.exit(2); }

process.env.MONGODB_URI = uri;
process.env.API_SECRET = SECRET;
process.env.AUTH_DEFAULT_ROLES = 'denied';
process.env.ENABLE = 'careportal api';
process.env.INSECURE_USE_HTTP = 'true';
process.env.DISPLAY_UNITS = 'mg/dl';
process.chdir(tree);
const R = p => require(path.join(tree, p));
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');

const env = R('lib/server/env')();
const language = R('lib/language')();
R('lib/server/bootevent')(env, language).boot(async function booted (ctx) {
  if (ctx.bootErrors && ctx.bootErrors.length) { console.error('boot errors', ctx.bootErrors); process.exit(2); }
  const app = R('lib/server/app')(env, ctx);
  const server = http.createServer(app);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  R('lib/server/websocket')(env, ctx, server);
  const port = server.address().port;

  let events = [];
  let count = 0;
  if (LISTENER === 'count') ctx.bus.on('storage-write-committed', () => { count++; });
  if (LISTENER === 'capture') ctx.bus.on('storage-write-committed', e => { count++; events.push({ t: Date.now(), e: JSON.parse(JSON.stringify(e)) }); });

  // An admin subject's JWT for API v3 (same steps as tools/qc/write-contract-matrix.js).
  const base = 'http://127.0.0.1:' + port;
  const H = { 'api-secret': HASH, 'content-type': 'application/json' };
  await fetch(base + '/api/v2/authorization/subjects', { method: 'POST', headers: H, body: JSON.stringify({ name: 'bench-admin', roles: ['admin'] }) });
  const subjects = await (await fetch(base + '/api/v2/authorization/subjects', { headers: H })).json();
  const subj = subjects.find(x => x.name === 'bench-admin');
  const jwt = (await (await fetch(base + '/api/v2/authorization/request/' + subj.accessToken, { headers: H })).json()).token;

  process.on('message', m => {
    if (m.cmd === 'events') { process.send({ cmd: 'events', id: m.id, events, count }); events = []; }
    if (m.cmd === 'internal' && m.op === 'moveOut') {
      const col = R('lib/storage/write-step').collection(ctx.store.collection(env.entries_collection), { name: 'entries', source: 'internal', bus: ctx.bus });
      col.updateMany({ bench: m.tag }, { $set: { bench: m.tag + '-moved' } })
        .then(r => process.send({ cmd: 'internal', id: m.id, ok: true, modified: r.modifiedCount }), e => process.send({ cmd: 'internal', id: m.id, ok: false, err: String(e.message) }));
    }
    if (m.cmd === 'exit') process.exit(0);
  });
  process.send({ cmd: 'ready', port, jwt, collections: { entries: env.entries_collection, treatments: env.treatments_collection, devicestatus: env.devicestatus_collection } });
});
