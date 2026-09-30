#!/usr/bin/env node
'use strict';
// ws_probe.js - one socket.io / upgrade observation for ws_chain.sh.
//
// Runs inside the lab's node client container. socket.io-client comes from a
// Nightscout tree's node_modules mounted read-only (NODE_PATH). The public
// name is resolved to the lab entry address by a custom lookup, so the Host
// header is the real one on both transports (XHR polling may not set Host).
//
// PROBE (JSON in the environment):
//   mode        auth | idle | http | raw
//   entry       entry address (the L4 front)       host   public name (Host)
//   transports  ["polling","websocket"] | ["websocket"] | ["polling"]
//   secret      wrong secret for auth/http          headers extra handshake headers
//   idleMs      idle window for mode=idle           timeoutMs overall budget
//
// Prints one JSON line. Header VALUES are never printed (disclosure rule).
const http = require('http');

const P = JSON.parse(process.env.PROBE || '{}');
const timeoutMs = P.timeoutMs || 10000;
const headers = P.headers || {};
const out = { mode: P.mode, transports: P.transports };

function lookup (hostname, opts, cb) {
  if (typeof opts === 'function') { cb = opts; opts = {}; }
  if (opts && opts.all) return cb(null, [{ address: P.entry, family: 4 }]);
  return cb(null, P.entry, 4);
}
const agent = new http.Agent({ lookup });

function done (extra) {
  Object.assign(out, extra || {});
  process.stdout.write(JSON.stringify(out) + '\n');
  process.exit(0);
}
setTimeout(() => done({ error: 'probe-timeout' }), timeoutMs + (P.idleMs || 0)).unref();

// Headers the XHR polling transport refuses to send (xmlhttprequest-ssl). A
// polling handshake that needs one of them is vacuous, so say so.
const XHR_FORBIDDEN = ['accept-charset', 'accept-encoding', 'access-control-request-headers',
  'access-control-request-method', 'connection', 'content-length', 'content-transfer-encoding',
  'cookie', 'cookie2', 'date', 'expect', 'host', 'keep-alive', 'origin', 'referer', 'te',
  'trailer', 'transfer-encoding', 'upgrade', 'via'];
function unsendable () {
  if (!(P.transports || []).includes('polling')) return [];
  return Object.keys(headers).filter(h => XHR_FORBIDDEN.includes(h.toLowerCase()));
}

// raw: a bare HTTP/1.1 Upgrade with no socket.io, for the selftest echo
// backend. Reports the status and the echo header the backend returns.
function raw () {
  const req = http.request({
    host: P.host, port: 80, path: '/socket.io/?EIO=4&transport=websocket', agent,
    headers: Object.assign({ Connection: 'Upgrade', Upgrade: 'websocket',
      'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'bGFiLXByb2JlLWtleS0wMQ==' }, headers)
  });
  req.on('upgrade', (res, sock) => { sock.destroy(); done({ status: res.statusCode, echo: res.headers['x-echo'] || '' }); });
  req.on('response', res => done({ status: res.statusCode, echo: res.headers['x-echo'] || '' }));
  req.on('error', e => done({ error: e.code || e.message }));
  req.end();
}

function httpGet () {
  const req = http.get({ host: P.host, port: 80, path: '/api/v1/entries.json', agent,
    headers: Object.assign({ 'api-secret': P.secret }, headers) },
  res => { res.resume(); done({ status: res.statusCode }); });
  req.on('error', e => done({ error: e.code || e.message }));
}

function sio () {
  const { io } = require('socket.io-client');
  const skipped = unsendable();
  if (skipped.length) return done({ error: 'unsendable-on-polling', unsendable: skipped.length });
  const socket = io('http://' + P.host, {
    transports: P.transports || ['polling', 'websocket'],
    agent, extraHeaders: headers, forceNew: true, timeout: timeoutMs,
    reconnection: P.mode === 'idle', reconnectionDelay: 500, reconnectionDelayMax: 1000
  });
  const engineEvents = [];
  let upgraded = false;
  socket.io.on('open', () => {
    const eng = socket.io.engine;
    engineEvents.push('open:' + eng.transport.name);
    eng.on('upgrade', t => { upgraded = true; engineEvents.push('upgrade:' + t.name); });
  });
  socket.on('connect_error', e => { if (P.mode !== 'idle') done({ error: 'connect_error', detail: String(e.message || e) }); });

  if (P.mode === 'auth') {
    socket.on('connect', () => {
      // give polling a chance to upgrade before authorizing, so the transport
      // the result names is the one the authorize travelled on
      setTimeout(() => {
        const transport = socket.io.engine.transport.name;
        let settled = false;
        const finish = (how) => {
          if (settled) return; settled = true;
          setTimeout(() => { socket.close(); done({ transport, upgraded, events: engineEvents, auth: how }); }, 300);
        };
        socket.on('disconnect', () => finish('disconnected'));
        socket.emit('authorize', { client: 'web', secret: P.secret, history: 0 }, () => finish('ack'));
        setTimeout(() => finish('no-reply'), 5000);
      }, (P.transports || []).length > 1 ? 1500 : 200);
    });
  } else if (P.mode === 'idle') {
    const disconnects = [];
    let firstTransport = null;
    let closing = false;
    socket.on('connect', () => {
      if (firstTransport === null) {
        setTimeout(() => { firstTransport = socket.io.engine.transport.name; }, 1500);
        setTimeout(() => {
          const connected = socket.connected;
          closing = true; // our own close() emits 'io client disconnect'; not a drop
          socket.close();
          done({ transport: firstTransport, upgraded, events: engineEvents, idleMs: P.idleMs,
            disconnects: disconnects.length, reasons: [...new Set(disconnects)], connectedAtEnd: connected });
        }, P.idleMs);
      }
    });
    socket.on('disconnect', reason => { if (!closing) disconnects.push(reason); });
  } else {
    done({ error: 'unknown mode' });
  }
}

({ raw, http: httpGet, auth: sio, idle: sio }[P.mode] || (() => done({ error: 'unknown mode' })))();
