#!/usr/bin/env node
'use strict';
// fake-apns.js - a local stand-in for Apple's push service (APNs), one per arm, so the Loop
// remote-command path builds real APNs providers without anything leaving 127.0.0.1.
// The server setup is the one tools/lab/apns-shutdown/probe.js uses: HTTP/2 over TLS with the
// tree's own test TLS pair, answering 200 to every push.
//
// Every SAMPLE_SEC it appends one line to OUT: HTTP/2 sessions opened, closed, and still open,
// and pushes answered. A build that leaves one APNs connection open per remote command shows
// `open` growing by one per command; a build that shuts its provider down shows `open` near 0.
//
// Environment: PORT, TREE (a cgm-remote-monitor tree with the TLS fixtures), OUT, PIDFILE,
// SAMPLE_SEC (default 10).
const fs = require('fs');
const path = require('path');
const http2 = require('http2');

const TREE = process.env.TREE;
function fixture (name) {
  for (const dir of ['tests/fixtures/api3', 'tests/fixtures']) {
    const p = path.join(TREE, dir, name);
    if (fs.existsSync(p)) return fs.readFileSync(p);
  }
  throw new Error('no TLS fixture ' + name + ' under ' + TREE);
}
if (process.env.PIDFILE) fs.writeFileSync(process.env.PIDFILE, String(process.pid));

let opened = 0; let closed = 0; let pushes = 0;
const server = http2.createSecureServer({ key: fixture('localhost.key'), cert: fixture('localhost.crt') });
server.on('session', (s) => { opened += 1; s.on('close', () => { closed += 1; }); s.on('error', () => {}); });
server.on('stream', (stream) => {
  stream.on('data', () => {});
  stream.on('end', () => { pushes += 1; stream.respond({ ':status': 200, 'content-type': 'application/json' }); stream.end(); });
  stream.on('error', () => {});
});
const line = () => JSON.stringify({ t: new Date().toISOString(), opened, closed, open: opened - closed, pushes }) + '\n';
server.listen(Number(process.env.PORT), '127.0.0.1', () => {
  fs.appendFileSync(process.env.OUT, line());
  setInterval(() => fs.appendFileSync(process.env.OUT, line()), Number(process.env.SAMPLE_SEC || 10) * 1000);
});
process.on('SIGTERM', () => { fs.appendFileSync(process.env.OUT, line()); process.exit(0); });
