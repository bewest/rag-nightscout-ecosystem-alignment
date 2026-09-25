#!/usr/bin/env node
'use strict';
// proxy.js - pass-through HTTP proxy in front of one arm, adapted from
// tools/lab/connector-soak/proxy.js. It exists for fault injection: with
// DROP_RATE > 0 it SILENTLY drops that fraction of requests whose method and
// path match DROP_MATCH (default POST /api/v1/devicestatus), answering 200 with
// the request body echoed back, as if the server had stored it. The server
// never sees the request. Only the database checks can catch this, which is
// the point: it proves the ledger and parity checks are not vacuous.
//
// Run a proxy in front of BOTH arms (the other with DROP_RATE=0) so latency
// stays comparable. Logs one JSON line per dropped request (never headers,
// query strings or bodies). Websocket traffic does not go through the proxy.
//
// Environment: UPSTREAM (http://127.0.0.1:<port>), PORT, DROP_RATE (0..1),
// DROP_MATCH (regex over "METHOD /path", default ^POST /api/v1/devicestatus).
const http = require('http');
const crypto = require('crypto');

const UP = new URL(process.env.UPSTREAM);
const PORT = Number(process.env.PORT);
const RATE = Number(process.env.DROP_RATE || 0);
const MATCH = new RegExp(process.env.DROP_MATCH || '^POST /api/v1/devicestatus');
let seen = 0;
let dropped = 0;

function drop () { // deterministic: the same sequence drops the same requests
  seen += 1;
  const x = parseInt(crypto.createHash('md5').update('drop' + seen).digest('hex').slice(0, 8), 16) / 0xffffffff;
  return x < RATE;
}

http.createServer((req, res) => {
  const path = req.url.split('?')[0];
  if (RATE > 0 && MATCH.test(req.method + ' ' + path) && drop()) {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      dropped += 1;
      let body = Buffer.concat(chunks).toString('utf8');
      try { const j = JSON.parse(body); body = JSON.stringify(Array.isArray(j) ? j : [j]); } catch (e) { body = '[]'; }
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(body);
      console.log(JSON.stringify({ t: new Date().toISOString(), dropped, of_matching: seen, method: req.method, path }));
    });
    return;
  }
  const up = http.request({ hostname: UP.hostname, port: UP.port, path: req.url, method: req.method,
    headers: { ...req.headers, host: UP.host }, timeout: 60000 }, (upRes) => {
    res.writeHead(upRes.statusCode, upRes.headers);
    upRes.pipe(res);
  });
  up.on('timeout', () => up.destroy(new Error('upstream timeout')));
  up.on('error', () => req.socket.destroy());
  req.pipe(up);
}).listen(PORT, '127.0.0.1', () => console.log(JSON.stringify({ t: new Date().toISOString(), listening: PORT, upstream: UP.host, drop_rate: RATE, drop_match: MATCH.source })));
