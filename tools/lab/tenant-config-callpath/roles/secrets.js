'use strict';
// Secrets service (D22): each secret encrypted at rest (AES-256-GCM under a
// key-encryption key the store file never holds); plaintext released only to
// the consuming process (consume) or through the logged reveal operation.
// The operator port provisions and never reveals.
//
// Three listeners:
//   sec_public   (A, C)  owner reveal and owner write, owner token required
//   sec_internal         consume (the tenant-owner listener, its signing keys);
//                        in B also the orchestrator's reveal and write
//   sec_operator         provision a signing key; write-only
const fs = require('fs');
const path = require('path');
const { matrix, serve } = require('../lib/net');
const c = require('../lib/crypto');
const { loadRun, key, audit } = require('../lib/store');

const run = loadRun(process.argv[2]);
const mx = matrix(run.design, run.breaks);
const B = run.design === 'B0' || run.design === 'B1';
const kek = key(run.runDir, 'kek'); // held by this process only
const svcTenantAdmin = key(run.runDir, 'svc-tenant-admin').toString(); // to recognise the consumer
const svcOrchestrator = key(run.runDir, 'svc-orchestrator').toString(); // B1: to recognise the orchestrator
const installWide = run.has('install-wide-key') ? key(run.runDir, 'installwide.key') : null;
const dbPath = path.join(run.runDir, 'secrets.enc.json');

const db = () => { try { return JSON.parse(fs.readFileSync(dbPath, 'utf8')); } catch (e) { return {}; } };
const put = (tenant, kind, plaintext) => {
  const d = db(); d[tenant] = d[tenant] || {};
  d[tenant][kind] = c.encrypt(kek, plaintext);
  fs.writeFileSync(dbPath, JSON.stringify(d, null, 2));
};
const get = (tenant, kind) => { const r = (db()[tenant] || {})[kind]; return r ? c.decrypt(kek, r) : null; };
const svc = (req) => (req.headers.authorization || '').replace(/^Service /, '');
const revealable = (kind) => /^plugin:/.test(kind); // the signing key is never revealed

// Verify an owner token for the tenant named by the ADDRESS (D14).
function verifyOwner (req, slug) {
  const tok = (req.headers.authorization || '').replace(/^Bearer /, '');
  let v;
  if (run.has('no-sig-verify')) {
    const d = c.decode(tok); v = d ? { ok: true, payload: d.payload } : { ok: false, reason: 'malformed' };
  } else {
    const k = installWide || get(slug, 'jwt');
    if (!k) return { ok: false, reason: 'unknown-tenant' };
    v = c.verifyHS256(tok, Buffer.from(k, 'base64url'));
  }
  if (!v.ok) return v;
  if (v.payload.tenant !== slug) return { ok: false, reason: 'claim' };
  if (v.payload.exp < c.now()) return { ok: false, reason: 'expired' };
  return v;
}

function freshEnough (authTime) {
  if (run.revealPolicy !== 'fresh') return true;
  return c.now() - authTime <= run.freshSeconds;
}

const publicRoutes = [];
const internalRoutes = [
  ['POST', /^\/t\/([a-z0-9-]+)\/consume$/, async (req, m, b) => {
    // Only the tenant-owner listener consumes, and only signing keys.
    if (svc(req) !== svcTenantAdmin) return [401, { error: 'not-a-consumer' }];
    if (b.kind !== 'jwt') return [403, { error: 'kind-not-consumable-by-caller' }];
    const v = get(m[1], 'jwt');
    return v ? [200, { key: v }] : [404, { error: 'no-secret' }];
  }]
];

if (!B) {
  publicRoutes.push(
    ['PUT', /^\/t\/([a-z0-9-]+)\/secret\/(plugin:[a-z0-9-]+)$/, async (req, m, b) => {
      const v = verifyOwner(req, m[1]);
      if (!v.ok) return [401, { error: 'owner-token', reason: v.reason }];
      put(m[1], m[2], String(b.value));
      audit(run.runDir, 'secrets', { action: 'secret-write', tenant: m[1], kind: m[2], actor: { kind: 'human', id: v.payload.sub, verifiedBy: 'tenant-key-signature' } });
      return [200, { ok: true }];
    }],
    ['POST', /^\/t\/([a-z0-9-]+)\/reveal$/, async (req, m, b) => {
      if (!revealable(b.kind)) return [403, { error: 'not-revealable' }];
      let sub = 'unverified';
      if (!run.has('reveal-no-auth')) {
        const v = verifyOwner(req, m[1]);
        if (!v.ok) return [401, { error: 'owner-token', reason: v.reason }];
        if (!freshEnough(v.payload.auth_time)) return [401, { error: 'reauth-required' }];
        sub = v.payload.sub;
      }
      const val = get(m[1], b.kind);
      if (val === null) return [404, { error: 'no-secret' }];
      audit(run.runDir, 'secrets', { action: 'reveal', tenant: m[1], kind: b.kind, actor: { kind: 'human', id: sub, verifiedBy: run.has('reveal-no-auth') ? null : 'tenant-key-signature' } });
      return [200, { value: val }];
    }]
  );
} else {
  // B: the orchestrator reveals and writes on the owner's behalf. The secrets
  // service cannot see the human; it records what the caller asserts.
  const serviceOk = (req) => run.design === 'B0' || run.has('b1-no-service-token') || svc(req) === svcOrchestrator;
  const actor = (req, b) => ({
    kind: run.design === 'B0' ? 'none' : 'service',
    id: run.design === 'B0' ? null : 'orchestrator',
    onBehalfOf: b.on_behalf_of || null,
    verifiedBy: null
  });
  internalRoutes.push(
    ['PUT', /^\/internal\/t\/([a-z0-9-]+)\/secret\/(plugin:[a-z0-9-]+)$/, async (req, m, b) => {
      if (!serviceOk(req)) return [401, { error: 'service-token' }];
      put(m[1], m[2], String(b.value));
      audit(run.runDir, 'secrets', { action: 'secret-write', tenant: m[1], kind: m[2], actor: actor(req, b) });
      return [200, { ok: true }];
    }],
    ['POST', /^\/internal\/t\/([a-z0-9-]+)\/reveal$/, async (req, m, b) => {
      if (!serviceOk(req)) return [401, { error: 'service-token' }];
      if (!revealable(b.kind)) return [403, { error: 'not-revealable' }];
      const val = get(m[1], b.kind);
      if (val === null) return [404, { error: 'no-secret' }];
      audit(run.runDir, 'secrets', { action: 'reveal', tenant: m[1], kind: b.kind, actor: actor(req, b) });
      return [200, { value: val }];
    }]
  );
}

const operatorRoutes = [
  ['POST', /^\/t\/([a-z0-9-]+)\/provision$/, async (req, m, b) => {
    if (b.kind !== 'jwt') return [400, { error: 'kind' }];
    if (get(m[1], 'jwt')) return [409, { error: 'exists' }]; // generated here, never accepted from the caller
    put(m[1], 'jwt', c.random(32));
    audit(run.runDir, 'secrets', { action: 'provision', tenant: m[1], kind: 'jwt', actor: { kind: 'operator-plane', id: null, verifiedBy: null } });
    return [200, { ok: true }];
  }]
];
if (run.has('operator-reveal')) {
  // CONTROL: D22 says the operator plane never reveals. This adds the route.
  operatorRoutes.push(['POST', /^\/t\/([a-z0-9-]+)\/reveal$/, async (req, m, b) => {
    const val = get(m[1], b.kind);
    return val === null ? [404, { error: 'no-secret' }] : [200, { value: val }];
  }]);
}

serve('secrets', 'sec_public', mx, publicRoutes);
serve('secrets', 'sec_internal', mx, internalRoutes);
serve('secrets', 'sec_operator', mx, operatorRoutes);
