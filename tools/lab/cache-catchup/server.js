'use strict';
// One cgm-remote-monitor tree booted as lib/server/server.js boots it, driven
// by lab.js over HTTP and IPC. Spawned by the lab, not by hand:
//   node server.js <tree> <mongo uri with db>
// BENCH_SECRET comes from the parent; nothing secret is written. CACHE_CATCHUP,
// CACHE_CATCHUP_OVERLAP_MS and CACHE_CATCHUP_BREAK reach the tree through the
// environment (proto/cache-catchup reads them; dev ignores them).
//
// IPC:
//   {cmd: 'cache'}  -> the bench-tagged records each cache holds: [_id, srvModified, bench]
//   {cmd: 'filterUpdate', type, tag, set}
//       an update by filter that names no records, as a write by filter does:
//       stamped through the tree's srv-dates, then announced the way the tree
//       announces a write by filter ('catchup' on the prototype, which flushes
//       unless CACHE_CATCHUP=watermark; a 'remove' with no changes on dev).
//       With CACHE_CATCHUP=resolve the update reads its ids first, is scoped
//       to them, and the 'catchup' names them
//   {cmd: 'inflight', type, first, second, gapMs}
//       two updates by filter; the first is stamped, then gapMs later the second
//       is stamped, written and announced, and only then is the first written
//       and announced: a write stamped before another that commits after it
//   {cmd: 'resync'} -> drop every cache and reload it (the lab's reset after a
//       check found errors, so they are not counted again; not measured)
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
process.chdir(tree);
const R = p => require(path.join(tree, p));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const env = R('lib/server/env')();
const language = R('lib/language')();
R('lib/server/bootevent')(env, language).boot(async function booted (ctx) {
  if (ctx.bootErrors && ctx.bootErrors.length) { console.error('boot errors', ctx.bootErrors); process.exit(2); }
  const app = R('lib/server/app')(env, ctx);
  const server = http.createServer(app);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  R('lib/server/websocket')(env, ctx, server);
  const srvDates = R('lib/server/srv-dates');
  const proto = typeof ctx.cache.catchUpStats === 'function';

  // CACHE_CATCHUP=resolve (proto/cache-resolve): a write by filter reads its
  // ids first, writes {filter AND _id in ids} and names them.
  const resolveMode = proto && process.env.CACHE_CATCHUP === 'resolve';
  const catchupIds = resolveMode ? R('lib/server/cache-catchup-ids') : null;

  // Announce a write by filter and wait for the cache to take it in.
  function announce (type, ids) {
    return new Promise(resolve => {
      if (proto) ctx.bus.emit('data-update', { type, op: 'catchup', ids: ids || undefined, done: resolve });
      else { ctx.bus.emit('data-update', { type, op: 'remove' }); resolve(); }
    }).then(() => ctx.bus.emit('data-received'));
  }
  const col = type => ctx.store.collection(env[type + '_collection'] || type);
  const stamped = set => { const s = Object.assign({}, set); srvDates.stampModified(s); return s; };
  // An update by filter with a set already stamped; returns what to name (resolve) or null.
  async function filterWrite (type, tag, set) {
    const filter = { bench: tag };
    if (!resolveMode) return { r: await col(type).updateMany(filter, { $set: set }), ids: null };
    const ids = await catchupIds.idsBefore(ctx, env, type, filter);
    const r = await col(type).updateMany(catchupIds.scope(filter, ids), { $set: set });
    return { r, ids: ids && catchupIds.named(ids) };
  }

  process.on('message', async m => {
    try {
      if (m.cmd === 'cache') {
        const out = {};
        for (const type of ['entries', 'treatments', 'devicestatus']) {
          out[type] = ctx.cache.getDataRef(type).filter(d => d.bench).map(d => [String(d._id), d.srvModified, d.bench]);
        }
        process.send({ cmd: 'cache', id: m.id, cache: out, stats: proto ? ctx.cache.catchUpStats() : null });
      }
      if (m.cmd === 'filterUpdate') {
        const w = await filterWrite(m.type, m.tag, stamped(m.set));
        await announce(m.type, w.ids);
        process.send({ cmd: 'filterUpdate', id: m.id, modified: w.r.modifiedCount });
      }
      if (m.cmd === 'inflight') {
        const first = stamped(m.first.set);
        await sleep(m.gapMs);
        const second = stamped(m.second.set);
        const w2 = await filterWrite(m.type, m.second.tag, second);
        await announce(m.type, w2.ids);
        const w1 = await filterWrite(m.type, m.first.tag, first);
        await announce(m.type, w1.ids);
        process.send({ cmd: 'inflight', id: m.id, first: first.srvModified, second: second.srvModified });
      }
      if (m.cmd === 'resync') {
        for (const type of ['entries', 'treatments', 'devicestatus']) ctx.cache.invalidate(type);
        ctx.bus.emit('data-received');
        process.send({ cmd: 'resync', id: m.id });
      }
      if (m.cmd === 'exit') process.exit(0);
    } catch (e) {
      process.send({ cmd: m.cmd, id: m.id, error: String(e && e.message || e) });
    }
  });
  process.send({ cmd: 'ready', port: server.address().port, proto });
});
