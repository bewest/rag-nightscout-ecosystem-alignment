'use strict';
// Ports, the reachability matrix, and a small HTTP client/server.
//
// THIS IS A MODEL OF NETWORK SEPARATION, NOT ISOLATION. Every listener binds
// 127.0.0.1, so any local process could connect to any port. The matrix is
// enforced twice in code: the client refuses to dial a port its zone may not
// reach, and each server refuses a request whose declared zone (x-lab-from)
// may not reach that port. The attack harness declares its zone truthfully.
const http = require('http');

const HOST = '127.0.0.1';
const PORTS = {
  idp: 47410,
  dashboard: 47411,
  ta_public: 47412,   // ns-tenant-admin, owner API (D16)
  ta_internal: 47413, // ns-tenant-admin, service API (design B only)
  ns_admin: 47414,    // platform operator plane (D7): no credential
  orchestrator: 47415,
  sec_public: 47416,  // secrets: owner reveal / owner write (A, C)
  sec_internal: 47417,// secrets: consume by the consuming process; B's reveal
  sec_operator: 47418 // secrets: provision only, never reveal (D22)
};

// zone -> port names it may reach, per design.
function matrix (design, breaks) {
  const m = {
    internet: ['idp', 'dashboard'],
    dashboard: ['idp'],
    'tenant-admin': ['idp', 'sec_internal'],
    'ns-admin': ['sec_operator'],
    operator: ['ns_admin'],
    orchestrator: [],
    secrets: [],
    harness: Object.keys(PORTS) // health checks and the lab-only state probe
  };
  if (design === 'A' || design === 'C') {
    m.internet.push('ta_public', 'sec_public');
    m.dashboard.push('ta_public', 'sec_public');
  }
  if (design === 'B0' || design === 'B1') {
    m.dashboard.push('orchestrator');
    m.orchestrator.push('idp', 'ta_internal', 'sec_internal', 'ns_admin');
    m.operator.push('orchestrator');
  }
  if (design === 'C') {
    m.operator.push('orchestrator');
    m.orchestrator.push('ns_admin');
  }
  if (breaks.includes('open-matrix')) {
    // CONTROL: the operator plane and internal ports become reachable from the dashboard.
    m.dashboard.push('ta_internal', 'ns_admin', 'sec_internal', 'sec_operator', 'orchestrator');
  }
  for (const k of Object.keys(m)) m[k] = [...new Set(m[k])];
  return m;
}

function canReach (mx, zone, portName) {
  return (mx[zone] || []).includes(portName);
}

// Outbound call. ctx (optional) accumulates call counts for the effort measure.
function call (mx, zone, portName, method, path, body, headers, ctx) {
  if (!canReach(mx, zone, portName)) {
    return Promise.resolve({ status: 0, blocked: true, body: { error: 'blocked-by-matrix', zone, portName } });
  }
  if (ctx) ctx.direct += 1;
  return new Promise((resolve) => {
    const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const req = http.request({
      host: HOST, port: PORTS[portName], method, path,
      headers: Object.assign({ 'content-type': 'application/json', 'x-lab-from': zone },
        data ? { 'content-length': data.length } : {}, headers || {})
    }, (res) => {
      let buf = '';
      res.on('data', (c) => { buf += c; });
      res.on('end', () => {
        let parsed = null;
        try { parsed = buf ? JSON.parse(buf) : null; } catch (e) { parsed = { raw: buf }; }
        if (ctx) ctx.total += 1 + ((parsed && parsed._lab && parsed._lab.total) || 0);
        resolve({ status: res.statusCode, body: parsed });
      });
    });
    req.on('error', (e) => resolve({ status: 0, error: e.code || String(e), body: { error: e.code } }));
    if (data) req.write(data);
    req.end();
  });
}

// Tiny router. routes: [[method, regex, handler(req, match, body, ctx)]].
// A handler returns [status, body].
function serve (role, portName, mx, routes) {
  const server = http.createServer((req, res) => {
    let buf = '';
    req.on('data', (c) => { buf += c; });
    req.on('end', async () => {
      const send = (status, body) => {
        res.writeHead(status, { 'content-type': 'application/json' });
        res.end(JSON.stringify(body));
      };
      const zone = req.headers['x-lab-from'] || 'internet';
      if (!canReach(mx, zone, portName)) return send(403, { error: 'blocked-by-matrix', zone, portName });
      if (req.method === 'GET' && req.url === '/health') return send(200, { role, port: portName, pid: process.pid });
      let body = {};
      try { body = buf ? JSON.parse(buf) : {}; } catch (e) { return send(400, { error: 'bad-json' }); }
      const ctx = { direct: 0, total: 0, zone };
      for (const [m, re, h] of routes) {
        const match = req.method === m && re.exec(req.url.split('?')[0]);
        if (match) {
          try {
            const [status, out] = await h(req, match, body, ctx);
            const o = Object.assign({}, out, { _lab: { direct: ctx.direct, total: ctx.total } });
            return send(status, o);
          } catch (e) {
            return send(500, { error: 'internal', message: e.message });
          }
        }
      }
      send(404, { error: 'no-route' });
    });
  });
  server.listen(PORTS[portName], HOST);
  return server;
}

module.exports = { HOST, PORTS, matrix, canReach, call, serve };
