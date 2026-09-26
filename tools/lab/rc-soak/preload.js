'use strict';
// preload.js - loaded into each Nightscout arm with NODE_OPTIONS=--require,
// so the build under test is not modified. Every SOAK_METRICS_SEC it appends
// one JSON line to SOAK_METRICS: memory (rss, heap, external), event-loop
// delay (p50/p99/max over the interval, ms), event-loop utilisation and the
// active handle count.
//
// Fault injection (non-vacuity only; never set these in a real soak):
//   SOAK_FAULT_LEAK_KB=<k>  retain about k KB of JS heap per HTTP request, so
//                           the analyser's leak check has something to find.
const fs = require('fs');
const { monitorEventLoopDelay, performance } = require('perf_hooks');

const OUT = process.env.SOAK_METRICS;

// SOAK_APNS_PORT: send this server's APNs pushes to the lab's fake APNs server on 127.0.0.1
// instead of Apple. Neither build has a setting for the APNs host, so this wraps the tree's
// @parse/node-apn Provider the way tools/lab/apns-shutdown/probe.js and PR #8419's test do
// (address, port, and accept the test TLS certificate). Only the destination changes; every
// provider is still built, used and (or not) shut down by the build's own lib/server/loop.js.
let apnsProviders = 0;
if (process.env.SOAK_APNS_PORT) {
  const apn = require(require('path').join(process.cwd(), 'node_modules/@parse/node-apn'));
  const Original = apn.Provider;
  apn.Provider = function SoakProvider (options) {
    apnsProviders += 1;
    options.address = 'localhost'; // as the probe; the fake server listens on 127.0.0.1
    options.port = Number(process.env.SOAK_APNS_PORT);
    options.rejectUnauthorized = false;
    return new Original(options);
  };
}
const EVERY = Number(process.env.SOAK_METRICS_SEC || 10) * 1000;

if (OUT) {
  const h = monitorEventLoopDelay({ resolution: 10 });
  h.enable();
  let elu = performance.eventLoopUtilization();
  let requests = 0;
  const http = require('http');
  const emit = http.Server.prototype.emit;
  const keep = [];
  const leakKb = Number(process.env.SOAK_FAULT_LEAK_KB || 0);
  http.Server.prototype.emit = function (ev) {
    if (ev === 'request') {
      requests += 1;
      if (leakKb > 0) keep.push(new Array(Math.ceil(leakKb * 128)).fill(requests + 0.5));
    }
    return emit.apply(this, arguments);
  };
  const ms = (ns) => Math.round(ns / 1e4) / 100;
  setInterval(() => {
    const m = process.memoryUsage();
    const e = performance.eventLoopUtilization(elu);
    elu = performance.eventLoopUtilization();
    const line = {
      t: new Date().toISOString(), pid: process.pid, rss: m.rss, heapUsed: m.heapUsed, heapTotal: m.heapTotal,
      external: m.external, arrayBuffers: m.arrayBuffers,
      lag_p50: ms(h.percentile(50)), lag_p99: ms(h.percentile(99)), lag_max: ms(h.max),
      elu: Math.round(e.utilization * 1000) / 1000, handles: process._getActiveHandles().length, requests, apnsProviders,
      ...(leakKb ? { fault_leak_kb: leakKb } : {})
    };
    h.reset();
    try { fs.appendFileSync(OUT, JSON.stringify(line) + '\n'); } catch (err) { /* metrics must never stop the server */ }
  }, EVERY).unref();
}
