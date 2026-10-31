'use strict';
// Round 3: one cgm-remote-monitor tree booted as lib/server/server.js boots it,
// driven by lab-v3.js over HTTP (API v1 and API v3) and IPC. Spawned by the lab:
//   node server-v3.js <tree> <mongo uri with db>
// BENCH_SECRET comes from the parent; nothing secret is written.
// API3_AUTOPRUNE_TREATMENTS=2: autoPrune removes treatments older than 2 days
// (the round's prune targets are 50-55 h old; its other records 1-20 h).
// V3LAB_BREAK=drop-last (the break-it arm, sketch only): the treatments
// collection's announce() names one record fewer, of those removed and of those
// updated, as a resolved write that misses one of its ids would.
//
// IPC:
//   {cmd: 'cache'}  -> the bench-tagged treatments the cache holds: [_id, srvModified, bench]
//   {cmd: 'prune'}  -> run the treatments collection's autoPrune now (as a v3 create
//       does once an hour); answers when its write has been announced
//   {cmd: 'resync'} -> drop the cache and reload it (the lab's reset; not measured)
//   {cmd: 'exit'}
const path = require('path');
const http = require('http');
const [tree, uri] = process.argv.slice(2);
const SECRET = process.env.BENCH_SECRET;
if (!SECRET || SECRET.length < 12) { console.error('BENCH_SECRET required'); process.exit(2); }

process.env.MONGODB_URI = uri;
process.env.API_SECRET = SECRET;
process.env.AUTH_DEFAULT_ROLES = 'denied';
process.env.ENABLE = 'careportal api';
process.env.INSECURE_USE_HTTP = 'true';
process.env.DISPLAY_UNITS = 'mg/dl';
process.env.API3_AUTOPRUNE_TREATMENTS = '2';
process.chdir(tree);
const R = p => require(path.join(tree, p));

// Keep the API v3 treatments collection (for its autoPrune): wrap the
// Collection constructor before anything loads lib/api3/generic/setup.js.
const made = {};
const colPath = require.resolve(path.join(tree, 'lib/api3/generic/collection'));
const Collection = require(colPath);
require.cache[colPath].exports = function LabCollection (opts) { const c = new Collection(opts); made[c.colName] = c; return c; };

const env = R('lib/server/env')();
const language = R('lib/language')();
R('lib/server/bootevent')(env, language).boot(async function booted (ctx) {
  if (ctx.bootErrors && ctx.bootErrors.length) { console.error('boot errors', ctx.bootErrors); process.exit(2); }

  const app = R('lib/server/app')(env, ctx);
  const server = http.createServer(app);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  R('lib/server/websocket')(env, ctx, server);

  const treatments = made.treatments;

  if (process.env.V3LAB_BREAK === 'drop-last') {
    const storage = treatments && treatments.storage;
    if (!storage || typeof storage.announce !== 'function') { console.error('V3LAB_BREAK needs the sketch\'s announce()'); process.exit(2); }
    const announce = storage.announce;
    storage.announce = function ({ updated, removed }) {
      return announce.call(this, { updated: updated && updated.slice(0, -1), removed: Array.isArray(removed) ? removed.slice(0, -1) : removed });
    };
  }


  process.on('message', async m => {
    try {
      if (m.cmd === 'cache') {
        const held = ctx.cache.getDataRef('treatments').filter(d => d.bench).map(d => [String(d._id), d.srvModified, d.bench]);
        process.send({ cmd: 'cache', id: m.id, cache: { treatments: held } });
      }
      if (m.cmd === 'prune') {
        // autoPrune does not return its write; the announcement (data-update) is
        // the end of it on both trees, followed by data-received.
        const done = new Promise(resolve => {
          const on = e => { if (e && e.type === 'treatments') { ctx.bus.removeListener('data-update', on); resolve(); } };
          ctx.bus.on('data-update', on);
          setTimeout(() => { ctx.bus.removeListener('data-update', on); resolve(); }, 5000);
        });
        treatments.nextAutoPrune = new Date(0);
        treatments.autoPrune();
        await done;
        process.send({ cmd: 'prune', id: m.id });
      }
      if (m.cmd === 'resync') {
        ctx.cache.invalidate('treatments');
        ctx.bus.emit('data-received');
        process.send({ cmd: 'resync', id: m.id });
      }
      if (m.cmd === 'exit') process.exit(0);
    } catch (e) {
      process.send({ cmd: m.cmd, id: m.id, error: String(e && e.message || e) });
    }
  });
  process.send({ cmd: 'ready', port: server.address().port, prune: !!treatments });
});
