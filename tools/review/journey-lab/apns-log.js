#!/usr/bin/env node
'use strict';
// apns-log.js — a local stand-in for Apple's push service for the journey lab. It answers 200 to
// every push and appends one JSON line per push to OUT: the time, the device token in the path
// (each lab Loop site uses its own fake token, so the line says which site sent it), the
// apns-* headers and the payload. This is what the Loop app would have received.
// Env: PORT, TREE (a cgm-remote-monitor tree with tests/fixtures TLS pair), OUT, PIDFILE.
const fs = require('fs');
const path = require('path');
const http2 = require('http2');
function fixture (name) {
  for (const dir of ['tests/fixtures/api3', 'tests/fixtures']) {
    const p = path.join(process.env.TREE, dir, name);
    if (fs.existsSync(p)) return fs.readFileSync(p);
  }
  throw new Error('no TLS fixture ' + name);
}
if (process.env.PIDFILE) fs.writeFileSync(process.env.PIDFILE, String(process.pid));
const server = http2.createSecureServer({ key: fixture('localhost.key'), cert: fixture('localhost.crt') });
server.on('session', s => s.on('error', () => {}));
server.on('stream', (stream, headers) => {
  let body = '';
  stream.on('data', c => { body += c; });
  stream.on('end', () => {
    let payload = body; try { payload = JSON.parse(body); } catch (e) {}
    const h = {}; for (const k of Object.keys(headers)) if (k.startsWith('apns-')) h[k] = headers[k];
    fs.appendFileSync(process.env.OUT, JSON.stringify({ t: new Date().toISOString(), token: String(headers[':path']).split('/').pop(), headers: h, payload }) + '\n');
    stream.respond({ ':status': 200, 'apns-id': 'lab-' + Date.now() }); stream.end();
  });
  stream.on('error', () => {});
});
server.listen(Number(process.env.PORT), '127.0.0.1');
