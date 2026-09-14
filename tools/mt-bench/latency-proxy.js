// A TCP proxy that adds a fixed one-way delay in each direction, so EXP-MT-026's
// arms can be re-run against an emulated remote database without root, without
// NET_ADMIN, and without reloading the corpus.
//
// WHY THIS EXISTS, AND WHAT IT IS NOT. The question EXP-MT-026 has to answer is
// whether the deployment cost model survives a real network hop. Loopback RTT is
// ~0.05 ms; a managed database in the same region is 1-3 ms and cross-region is
// 20-80 ms. Running only on loopback would measure the one case no hoster has.
//
// This is NOT a network emulator. It delays application-level chunks as they pass
// through userspace. It therefore reproduces the thing that matters here — added
// round-trip latency per operation — and does NOT reproduce TCP slow-start,
// congestion-window behaviour under loss, MTU effects, jitter, or reordering.
// `tc netem` inside the database container does all of that properly and is the
// right tool if NET_ADMIN is available. Numbers taken through this proxy should be
// read as "latency was added", not "a WAN was simulated".
//
// Delay is applied in BOTH directions, so an added RTT of 2 x delayMs is what an
// operation sees.
//
// Usage:
//   node latency-proxy.js <listenPort> <targetPort> <oneWayDelayMs> [targetHost]

'use strict';

const net = require('net');

const LISTEN = parseInt(process.argv[2], 10) || 27098;
const TARGET = parseInt(process.argv[3], 10) || 27099;
const DELAY = parseFloat(process.argv[4]) || 1;
const HOST = process.argv[5] || '127.0.0.1';

// Chunks must arrive in order. A per-chunk setTimeout does not guarantee that
// under load, so each socket keeps a serial queue and each chunk waits out the
// remainder of its own delay after its predecessor has been written.
function pipeDelayed (from, to) {
  let chain = Promise.resolve();
  from.on('data', (chunk) => {
    const due = Date.now() + DELAY;
    chain = chain.then(() => new Promise((resolve) => {
      const wait = Math.max(0, due - Date.now());
      const send = () => { if (!to.destroyed) to.write(chunk); resolve(); };
      if (wait === 0) send(); else setTimeout(send, wait);
    }));
  });
  from.on('end', () => { chain = chain.then(() => { if (!to.destroyed) to.end(); }); });
  from.on('error', () => { if (!to.destroyed) to.destroy(); });
}

const server = net.createServer((client) => {
  const upstream = net.connect(TARGET, HOST);
  upstream.on('error', () => client.destroy());
  client.on('error', () => upstream.destroy());
  client.setNoDelay(true);
  upstream.setNoDelay(true);
  pipeDelayed(client, upstream);
  pipeDelayed(upstream, client);
});

server.listen(LISTEN, '127.0.0.1', () => {
  console.log(`latency-proxy: 127.0.0.1:${LISTEN} -> ${HOST}:${TARGET}, ` +
    `${DELAY} ms each way (${DELAY * 2} ms added RTT)`);
});
