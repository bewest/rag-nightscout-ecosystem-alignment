'use strict';
// ns-tenant-admin (D16): the tenant-owner configuration listener.
//   ta_public   (A, C)  Nightscout's own token exchange (D17) and the owner API.
//                       The tenant is resolved from the ADDRESS before any
//                       credential is read; the owner token is verified with
//                       that tenant's key (D14).
//   ta_internal (B)     the orchestrator's service API: B0 no identity, B1 a
//                       service token. The human is whatever the caller says.
// Policy and floors (D22) are enforced here for every owner write.
const { matrix, serve, call } = require('../lib/net');
const c = require('../lib/crypto');
const P = require('../lib/policy');
const { loadRun, key, load, save, audit } = require('../lib/store');

const run = loadRun(process.argv[2]);
const mx = matrix(run.design, run.breaks);
const B = run.design === 'B0' || run.design === 'B1';
const AK = run.design === 'AK';
const ttl = run.tokenTtl || 900;
const idpPub = key(run.runDir, 'idp.pub'); // public key, to verify assertions
const svcSelf = key(run.runDir, 'svc-tenant-admin').toString(); // to consume signing keys
const svcOrchestrator = key(run.runDir, 'svc-orchestrator').toString(); // B1: to recognise the orchestrator
const installWide = run.has('install-wide-key') ? key(run.runDir, 'installwide.key') : null;
const opts = { noPolicy: run.has('no-policy'), noFloors: run.has('no-floors') };

const keyCache = {};
async function tenantKey (slug, ctx) {
  if (installWide) return installWide; // CONTROL: one install-wide key
  if (keyCache[slug]) return keyCache[slug];
  const r = await call(mx, 'tenant-admin', 'sec_internal', 'POST', `/t/${slug}/consume`, { kind: 'jwt' }, { authorization: 'Service ' + svcSelf }, ctx);
  if (r.status !== 200) return null;
  keyCache[slug] = Buffer.from(r.body.key, 'base64url');
  return keyCache[slug];
}

function resolve (slug) {
  const s = load(run.runDir);
  const t = s.tenants[slug];
  if (!t) return { err: [404, { error: 'unknown-tenant' }] };
  if (!t.active) return { err: [403, { error: 'suspended' }] };
  return { s, t };
}

async function verifyOwner (req, slug, t, ctx) {
  const tok = (req.headers.authorization || '').replace(/^Bearer /, '');
  let v;
  if (run.has('no-sig-verify')) {
    const d = c.decode(tok); v = d ? { ok: true, payload: d.payload } : { ok: false, reason: 'malformed' };
  } else if (AK) {
    const r = await call(mx, 'tenant-admin', 'sec_internal', 'POST', `/t/${slug}/verify`, { token: tok }, { authorization: 'Service ' + svcSelf }, ctx);
    v = r.status === 200 ? r.body : { ok: false, reason: 'verify-unavailable' };
  } else {
    const k = await tenantKey(slug, ctx);
    if (!k) return { ok: false, reason: 'no-key' };
    v = c.verifyHS256(tok, k);
  }
  if (!v.ok) return v;
  if (v.payload.tenant !== slug) return { ok: false, reason: 'claim' };
  if (v.payload.scope !== 'owner') return { ok: false, reason: 'scope' };
  if (v.payload.exp < c.now()) return { ok: false, reason: 'expired' };
  if (!t.members.includes(v.payload.sub)) return { ok: false, reason: 'membership' };
  return v;
}

function ownerWrite (s, slug, k, b, actor) {
  const row = (s.policy[slug] || {})[k];
  const refused = P.checkOwnerWrite(k, b.value, row, opts);
  if (refused) {
    audit(run.runDir, 'tenant-admin', { action: 'owner-write-refused', tenant: slug, key: k, reason: refused, actor });
    return [422, { error: 'policy', reason: refused }];
  }
  if (P.SETTINGS[k].needsConfirmation && !run.has('no-confirmation')) { // the break is a CONTROL
    const phrase = `DELETE ENTRIES OLDER THAN ${b.value} DAYS`;
    if (b.confirm !== phrase) {
      s.pruneOffers[slug] = { key: k, value: b.value, exportOffered: `/t/${slug}/export` };
      save(run.runDir, s);
      return [409, { error: 'confirmation-required', confirmPhrase: phrase, exportOffered: `/t/${slug}/export` }];
    }
    const offer = s.pruneOffers[slug];
    if (!offer || offer.value !== b.value) return [409, { error: 'export-not-offered' }];
    delete s.pruneOffers[slug];
  }
  s.owner[slug] = s.owner[slug] || {};
  s.owner[slug][k] = b.value;
  save(run.runDir, s);
  audit(run.runDir, 'tenant-admin', { action: 'owner-write', tenant: slug, key: k, value: b.value, actor });
  return [200, { ok: true, effective: P.effective(s.policy[slug], s.owner[slug])[k] }];
}

const view = (s, slug) => ({ effective: P.effective(s.policy[slug] || {}, s.owner[slug] || {}), owner: s.owner[slug] || {} });

const publicRoutes = [];
const internalRoutes = [];

if (!B) {
  publicRoutes.push(
    ['POST', /^\/t\/([a-z0-9-]+)\/token$/, async (req, m, b, ctx) => {
      const r = resolve(m[1]); if (r.err) return r.err;
      const a = c.verifyEd(b.assertion, idpPub);
      if (!a.ok || a.payload.aud !== 'nightscout-lab' || a.payload.exp < c.now()) return [401, { error: 'assertion' }];
      if (!r.t.members.includes(a.payload.sub)) return [403, { error: 'not-an-owner' }];
      let token;
      if (AK) {
        const r = await call(mx, 'tenant-admin', 'sec_internal', 'POST', `/t/${m[1]}/sign`, { sub: a.payload.sub, auth_time: a.payload.auth_time }, { authorization: 'Service ' + svcSelf }, ctx);
        if (r.status !== 200) return [500, { error: 'sign' }];
        token = r.body.token;
      } else {
        const k = await tenantKey(m[1], ctx); if (!k) return [500, { error: 'no-key' }];
        const t = c.now();
        token = c.signHS256({ sub: a.payload.sub, tenant: m[1], scope: 'owner', auth_time: a.payload.auth_time, iat: t, exp: t + ttl }, k);
      }
      audit(run.runDir, 'tenant-admin', { action: 'token-minted', tenant: m[1], actor: { kind: 'human', id: a.payload.sub, verifiedBy: 'idp-assertion' } });
      return [200, { token }];
    }],
    ['GET', /^\/t\/([a-z0-9-]+)\/config$/, async (req, m, b, ctx) => {
      const r = resolve(m[1]); if (r.err) return r.err;
      const v = await verifyOwner(req, m[1], r.t, ctx);
      if (!v.ok) return [401, { error: 'owner-token', reason: v.reason }];
      return [200, view(r.s, m[1])];
    }],
    ['PUT', /^\/t\/([a-z0-9-]+)\/config\/([A-Z0-9_]+)$/, async (req, m, b, ctx) => {
      const r = resolve(m[1]); if (r.err) return r.err;
      const v = await verifyOwner(req, m[1], r.t, ctx);
      if (!v.ok) return [401, { error: 'owner-token', reason: v.reason }];
      const actor = run.has('actor-from-body') && b.on_behalf_of
        ? { kind: 'human', id: b.on_behalf_of, verifiedBy: null } // CONTROL: trusts the body
        : { kind: 'human', id: v.payload.sub, verifiedBy: 'tenant-key-signature' };
      return ownerWrite(r.s, m[1], m[2], b, actor);
    }]
  );
} else {
  const serviceOk = (req) => run.design === 'B0' || run.has('b1-no-service-token') ||
    (req.headers.authorization || '') === 'Service ' + svcOrchestrator;
  const actor = (b) => ({
    kind: run.design === 'B0' ? 'none' : 'service',
    id: run.design === 'B0' ? null : 'orchestrator',
    onBehalfOf: b.on_behalf_of || null,
    verifiedBy: null
  });
  internalRoutes.push(
    ['GET', /^\/internal\/t\/([a-z0-9-]+)\/members$/, async (req, m) => {
      if (!serviceOk(req)) return [401, { error: 'service-token' }];
      const r = resolve(m[1]); if (r.err) return r.err;
      return [200, { members: r.t.members }];
    }],
    ['GET', /^\/internal\/t\/([a-z0-9-]+)\/config$/, async (req, m) => {
      if (!serviceOk(req)) return [401, { error: 'service-token' }];
      const r = resolve(m[1]); if (r.err) return r.err;
      return [200, view(r.s, m[1])];
    }],
    ['PUT', /^\/internal\/t\/([a-z0-9-]+)\/config\/([A-Z0-9_]+)$/, async (req, m, b) => {
      if (!serviceOk(req)) return [401, { error: 'service-token' }];
      const r = resolve(m[1]); if (r.err) return r.err;
      return ownerWrite(r.s, m[1], m[2], b, actor(b));
    }]
  );
}

serve('tenant-admin', 'ta_public', mx, publicRoutes);
serve('tenant-admin', 'ta_internal', mx, internalRoutes);
