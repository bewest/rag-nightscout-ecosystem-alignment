#!/usr/bin/env node
'use strict';
/*
 * probes/return-to.js - Kratos self-service return_to allow-list across tenants.
 * kratos.yml allows http://auth.apex.test:44480/ and http://*.user-content.apex.test:44480/.
 * Each candidate is offered to the login, registration and recovery browser flows; the flow
 * either starts (200, flow.return_to echoed) or is refused (400). The first candidate is the
 * positive control and is re-asked last, so a dead or refusing Kratos cannot pass this probe.
 */
const H = require('../lib/harness');

const rec = H.recorder('return-to');
const P = H.env.LAB_PORT;
const T = (s) => `http://${s}.user-content.apex.test:${P}`;

const cases = [
  ['own-tenant', `${T('tenant-a')}/after`, 'allowed'],
  ['sibling-tenant', `${T('tenant-b')}/after`, 'allowed'],
  ['unregistered-slug', `${T('tenant-zz')}/after`, 'allowed'],
  ['two-labels-deep', `http://x.tenant-a.user-content.apex.test:${P}/after`, null],
  ['bare-suffix', `http://user-content.apex.test:${P}/after`, null],
  ['other-port', 'http://tenant-a.user-content.apex.test:9999/after', null],
  ['https-scheme', 'https://tenant-a.user-content.apex.test:44480/after', null],
  ['foreign', 'http://evil.test/after', 'refused'],
  ['suffix-append', `http://tenant-a.user-content.apex.test.evil.test:${P}/after`, 'refused'],
  ['userinfo', `http://tenant-a.user-content.apex.test:${P}@evil.test/after`, 'refused'],
  ['path-embed', `http://evil.test/${T('tenant-a')}`, 'refused'],
  ['scheme-relative', '//evil.test/after', 'refused'],
  ['javascript', 'javascript:alert(1)', 'refused'],
  ['own-tenant-again', `${T('tenant-a')}/after`, 'allowed']
];

async function offer (flow, rt) {
  const r = await H.req(H.env.AUTH_HOST, 'GET', `/self-service/${flow}/browser?return_to=${encodeURIComponent(rt)}`, { headers: { accept: 'application/json' } });
  return { status: r.status, outcome: r.status === 200 ? 'allowed' : (r.status === 400 ? 'refused' : `http-${r.status}`), echoed: r.body && r.body.return_to, reason: r.body && r.body.error && r.body.error.reason };
}

async function main () {
  const srv = await H.startServer('', 'return-to');
  const table = [];
  try {
    for (const [id, rt, expect] of cases) {
      const row = { id, return_to: rt };
      for (const flow of ['login', 'registration', 'recovery']) row[flow] = await offer(flow, rt);
      table.push(row);
      const outs = ['login', 'registration', 'recovery'].map((f) => row[f].outcome);
      const consistent = outs.every((o) => o === outs[0]);
      if (expect) {
        rec.check(`rt.${id}`, `${rt} -> ${expect} by all three flows`, expect, outs, consistent && outs[0] === expect);
      } else {
        rec.check(`rt.${id}`, `${rt} -> recorded (no prediction; flows must agree)`, 'consistent', outs, consistent);
      }
    }
  } finally { await srv.stop(); }
  rec.note('table', table.map((r) => ({ id: r.id, return_to: r.return_to, login: r.login.outcome, registration: r.registration.outcome, recovery: r.recovery.outcome, reason: r.login.reason || null })));
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
