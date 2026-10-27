'use strict';
// Which driver calls (and so which storage-write-committed events) each shape
// issues on a tree. Usage: node inventory.js <tree> <mongo uri, no db>
const L = require('./lib');
const [tree, mongo] = process.argv.slice(2);
(async () => {
  const a = await L.startArm('inv', tree, mongo, 'devent_inv_' + L.hex().slice(0, 6), 'capture');
  const out = {};
  for (const [name, s] of Object.entries(Object.assign({}, L.SHAPES, L.BULK))) {
    const tag = name + '-' + L.hex().slice(0, 6);
    const seeded = s.seed ? await s.seed(a, tag) : undefined;
    await L.sleep(50); await a.events();
    const r = await s.run(a, tag, seeded);
    await L.sleep(100);
    const evs = (await a.events()).events.map(x => x.e);
    out[name] = { reply: r.s || (Array.isArray(r) ? 'ack[' + r.length + ']' : JSON.stringify(r).slice(0, 40)),
      events: evs.map(e => e.source + ' ' + e.operation + ' ' + JSON.stringify(e.counts) + (e.records ? ' records=' + e.records.length : '')) };
    console.log(name.padEnd(32), String(out[name].reply).padEnd(8), out[name].events.join(' | '));
  }
  await a.stop();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
