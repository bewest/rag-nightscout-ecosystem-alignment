// EXP-MT-045a: what bounds a REALTIME fan-out process?
//
// Nightscout broadcasts one room to every follower:
//     io.to('DataReceivers').compress(true).emit('dataUpdate', delta)   (websocket.js:150)
// The tenant-scoped version is one room per tenant (§2.4). This measures:
//   - marginal RSS per connected socket on the SERVER process
//   - broadcast latency for a realistic delta, one big room vs many small rooms
//
// The server runs as a child process so client overhead never lands in its RSS.
// Clients are split across several child processes for the same reason.
//
// Usage: node realtime.js [totalSockets] [roomCount] [clientProcs]

'use strict';

const path = require('path');
const fs = require('fs');
const { fork } = require('child_process');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');
const TOTAL = Number(process.argv[2]) || 2000;
const ROOMS = Number(process.argv[3]) || 1;
const CLIENT_PROCS = Number(process.argv[4]) || 4;
const PORT = 31700 + (process.pid % 2000);

// A dataUpdate delta shaped like a routine 5-minute update: one new SGV, one
// devicestatus with a 72-point prediction. This is the common case; a delta
// carrying a treatment change is larger and rarer.
function delta () {
  const now = Date.now();
  const iso = new Date(now).toISOString();
  return { delta: true, lastUpdated: now,
    sgvs: [{ _id: 'a'.repeat(24), mgdl: 120, mills: now, device: 'xDrip-DexcomG6',
      direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000, noise: 1, rssi: 100 }],
    devicestatus: [{ _id: 'b'.repeat(24), device: 'loop://iPhone', mills: now,
      loop: { name: 'Loop', version: '3.4', timestamp: iso, iob: { iob: 1.2, timestamp: iso },
        cob: { cob: 12, timestamp: iso },
        predicted: { startDate: iso, values: Array.from({ length: 72 }, (_, k) => 80 + k) } } }] };
}

if (process.argv[2] === '--server-child') {
  const { Server } = require(path.join(NS_ROOT, 'node_modules/socket.io'));
  const http = require('http');
  const srv = http.createServer();
  const io = new Server(srv, { cors: { origin: '*' } });
  const port = Number(process.argv[3]);
  const rooms = Number(process.argv[4]);
  let joined = 0;
  io.on('connection', socket => {
    socket.join('DataReceivers:' + (joined++ % rooms));
    socket.on('ping-probe', ts => socket.emit('pong-probe', ts));
  });
  srv.listen(port, () => process.send({ ready: true }));
  process.on('message', m => {
    if (m.cmd === 'rss') {
      const rss = /^VmRSS:\s+(\d+) kB/m.exec(fs.readFileSync('/proc/self/status', 'utf8'))[1];
      process.send({ rss: Number(rss) * 1024, sockets: io.engine.clientsCount });
    }
    if (m.cmd === 'broadcast') {
      const payload = delta();
      const t0 = process.hrtime.bigint();
      for (let r = 0; r < rooms; r++) {
        io.to('DataReceivers:' + r).compress(true).emit('dataUpdate', payload);
      }
      const t1 = process.hrtime.bigint();
      process.send({ emitMs: Number(t1 - t0) / 1e6 });
    }
    if (m.cmd === 'stop') process.exit(0);
  });
  return;
}

if (process.argv[2] === '--client-child') {
  const { io: connect } = require(path.join(NS_ROOT, 'node_modules/socket.io-client'));
  const port = Number(process.argv[3]);
  const count = Number(process.argv[4]);
  const socks = [];
  let ready = 0, received = 0;
  for (let i = 0; i < count; i++) {
    const s = connect(`http://127.0.0.1:${port}`, { transports: ['websocket'], forceNew: true });
    s.on('connect', () => { if (++ready === count) process.send({ ready: true }); });
    s.on('dataUpdate', () => { received++; });
    socks.push(s);
  }
  process.on('message', m => {
    if (m.cmd === 'received') process.send({ received });
    if (m.cmd === 'stop') { socks.forEach(s => s.close()); process.exit(0); }
  });
  return;
}

// ---- orchestrator ----------------------------------------------------------

const ask = (child, cmd) => new Promise(res => {
  child.once('message', res); child.send({ cmd });
});
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main () {
  const server = fork(__filename, ['--server-child', String(PORT), String(ROOMS)]);
  await new Promise(r => server.once('message', r));

  const baseline = await ask(server, 'rss');

  const per = Math.floor(TOTAL / CLIENT_PROCS);
  const clients = [];
  for (let i = 0; i < CLIENT_PROCS; i++) {
    const c = fork(__filename, ['--client-child', String(PORT), String(per)]);
    await new Promise(r => c.once('message', r));
    clients.push(c);
  }
  await sleep(500);

  const loaded = await ask(server, 'rss');

  // warm up, then measure broadcast cost
  for (let i = 0; i < 5; i++) { await ask(server, 'broadcast'); await sleep(50); }
  const emits = [];
  for (let i = 0; i < 20; i++) { emits.push((await ask(server, 'broadcast')).emitMs); await sleep(60); }
  await sleep(500);

  let delivered = 0;
  for (const c of clients) delivered += (await ask(c, 'received')).received;

  clients.forEach(c => c.send({ cmd: 'stop' }));
  server.send({ cmd: 'stop' });

  emits.sort((a, b) => a - b);
  const sockets = loaded.sockets;
  console.log(JSON.stringify({
    experiment: 'EXP-MT-045a realtime fan-out',
    requestedSockets: TOTAL, connectedSockets: sockets, rooms: ROOMS,
    serverBaselineRssMB: +(baseline.rss / 1048576).toFixed(1),
    serverLoadedRssMB: +(loaded.rss / 1048576).toFixed(1),
    marginalKBPerSocket: +(((loaded.rss - baseline.rss) / Math.max(1, sockets)) / 1024).toFixed(1),
    broadcastMs: { p50: +emits[10].toFixed(3), p95: +emits[18].toFixed(3), max: +emits[19].toFixed(3) },
    broadcastMsPerSocketUs: +(((emits[10] / Math.max(1, sockets)) * 1000).toFixed(2)),
    deliveredPerBroadcast: Math.round(delivered / 25)
  }, null, 2));
  process.exit(0);
}

main();
