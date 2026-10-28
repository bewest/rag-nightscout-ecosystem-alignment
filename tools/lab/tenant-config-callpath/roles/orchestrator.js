'use strict';
// The orchestrator.
//   B0, B1: reachable from the dashboard. Owner routes verify the owner's
//           identity-provider assertion, check ownership itself, then write
//           any tenant through ns-tenant-admin's service API and reveal
//           through the secrets service's internal API. Operator routes
//           (create, suspend, policy) forward to the operator plane.
//           B0: no internal call carries an identity. B1: the dashboard and the
//           operator console each present a service token to the orchestrator,
//           and the orchestrator presents its own downstream.
//   C:      exists only on the operator plane (D7): operator routes only,
//           reachable only from the operator zone, no credential.
const { matrix, serve, call } = require('../lib/net');
const c = require('../lib/crypto');
const { loadRun, key } = require('../lib/store');

const run = loadRun(process.argv[2]);
const mx = matrix(run.design, run.breaks);
const B = run.design === 'B0' || run.design === 'B1';
const B1 = run.design === 'B1' && !run.has('b1-no-service-token');
const idpPub = key(run.runDir, 'idp.pub');
const svcSelf = key(run.runDir, 'svc-orchestrator').toString(); // its own service identity
const svcDashboard = key(run.runDir, 'svc-dashboard').toString(); // B1: to recognise callers
const svcOperator = key(run.runDir, 'svc-operator').toString();
const down = () => (B1 ? { authorization: 'Service ' + svcSelf } : {});
const caller = (req) => (req.headers.authorization || '').replace(/^Service /, '');

async function owns (sub, slug, ctx) {
  if (run.has('no-ownership-check')) return true; // CONTROL
  const r = await call(mx, 'orchestrator', 'ta_internal', 'GET', `/internal/t/${slug}/members`, undefined, down(), ctx);
  return r.status === 200 && r.body.members.includes(sub);
}

// Common gate for owner routes: B1 caller identity, assertion, ownership.
async function ownerGate (req, b, ctx) {
  if (B1 && caller(req) !== svcDashboard) return { err: [401, { error: 'caller-token' }] };
  const a = c.verifyEd(b.assertion, idpPub);
  if (!a.ok || a.payload.exp < c.now()) return { err: [401, { error: 'assertion' }] };
  if (!(await owns(a.payload.sub, b.tenant, ctx))) return { err: [403, { error: 'not-an-owner', reason: 'membership' }] };
  return { sub: a.payload.sub, authTime: a.payload.auth_time };
}

const operatorGate = (req) => (B1 && caller(req) !== svcOperator) ? [401, { error: 'caller-token' }] : null;
const relay = (r) => [r.status || 502, r.body || {}];

const routes = [
  ['POST', /^\/operator\/tenants$/, async (req, m, b, ctx) => operatorGate(req) ||
    relay(await call(mx, 'orchestrator', 'ns_admin', 'POST', '/tenants', b, {}, ctx))],
  ['POST', /^\/operator\/(suspend|activate)$/, async (req, m, b, ctx) => operatorGate(req) ||
    relay(await call(mx, 'orchestrator', 'ns_admin', 'POST', `/tenants/${b.tenant}/${m[1]}`, {}, {}, ctx))],
  ['POST', /^\/operator\/policy$/, async (req, m, b, ctx) => operatorGate(req) ||
    relay(await call(mx, 'orchestrator', 'ns_admin', 'PUT', `/tenants/${b.tenant}/policy/${b.key}`, b.row, {}, ctx))]
];

if (B) {
  routes.push(
    ['POST', /^\/owner\/read$/, async (req, m, b, ctx) => {
      const g = await ownerGate(req, b, ctx); if (g.err) return g.err;
      return relay(await call(mx, 'orchestrator', 'ta_internal', 'GET', `/internal/t/${b.tenant}/config`, undefined, down(), ctx));
    }],
    ['POST', /^\/owner\/edit$/, async (req, m, b, ctx) => {
      const g = await ownerGate(req, b, ctx); if (g.err) return g.err;
      return relay(await call(mx, 'orchestrator', 'ta_internal', 'PUT', `/internal/t/${b.tenant}/config/${b.key}`,
        { value: b.value, confirm: b.confirm, on_behalf_of: g.sub }, down(), ctx));
    }],
    ['POST', /^\/owner\/secret$/, async (req, m, b, ctx) => {
      const g = await ownerGate(req, b, ctx); if (g.err) return g.err;
      return relay(await call(mx, 'orchestrator', 'sec_internal', 'PUT', `/internal/t/${b.tenant}/secret/${b.kind}`,
        { value: b.value, on_behalf_of: g.sub }, down(), ctx));
    }],
    ['POST', /^\/owner\/reveal$/, async (req, m, b, ctx) => {
      const g = await ownerGate(req, b, ctx); if (g.err) return g.err;
      if (run.revealPolicy === 'fresh' && c.now() - g.authTime > run.freshSeconds) return [401, { error: 'reauth-required' }];
      return relay(await call(mx, 'orchestrator', 'sec_internal', 'POST', `/internal/t/${b.tenant}/reveal`,
        { kind: b.kind, on_behalf_of: g.sub }, down(), ctx));
    }]
  );
}

serve('orchestrator', 'orchestrator', mx, routes);
