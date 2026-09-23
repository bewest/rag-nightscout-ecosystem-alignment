#!/usr/bin/env node
'use strict';
/*
 * proxy.js - a pass-through HTTP proxy between the sink connectors and the
 * source Nightscout, so the lab can count every request a connector makes,
 * including the ones it makes while the source is down.
 *
 * It logs one JSON line per request: time, client address, method, a
 * REDACTED path, status and duration. It never logs headers, query strings or
 * bodies, and it replaces the access-token segment of
 * /api/v2/authorization/request/<token> with <redacted>, because that path
 * carries a credential.
 *
 * When the upstream cannot be reached it destroys the client socket, so the
 * connector sees a transport error (ECONNRESET / socket hang up) rather than
 * an HTTP status. That is close to, but not the same as, the ECONNREFUSED /
 * ENOTFOUND a connector sees when the source host itself is gone.
 *
 * Environment: UPSTREAM (e.g. http://cksoak-s:1337), PORT (default 1337).
 */
const http = require('http');

const UP = new URL(process.env.UPSTREAM);
const PORT = Number(process.env.PORT || 1337);

function redact (path) {
  const p = path.split('?')[0];
  return p.replace(/(\/api\/v2\/authorization\/request\/)[^/]+/, '$1<redacted>');
}

http.createServer((req, res) => {
  const start = Date.now();
  const rec = { t: new Date(start).toISOString(), client: req.socket.remoteAddress, method: req.method, path: redact(req.url) };
  const up = http.request({ hostname: UP.hostname, port: UP.port, path: req.url, method: req.method,
    headers: { ...req.headers, host: UP.host }, timeout: 30000 }, (upRes) => {
    res.writeHead(upRes.statusCode, upRes.headers);
    upRes.pipe(res);
    upRes.on('end', () => console.log(JSON.stringify({ ...rec, status: upRes.statusCode, ms: Date.now() - start })));
  });
  up.on('timeout', () => up.destroy(new Error('upstream timeout')));
  up.on('error', (err) => {
    console.log(JSON.stringify({ ...rec, status: 0, error: err.code || 'ERR', ms: Date.now() - start }));
    req.socket.destroy();
  });
  req.pipe(up);
}).listen(PORT, () => console.log(JSON.stringify({ t: new Date().toISOString(), listening: PORT })));
