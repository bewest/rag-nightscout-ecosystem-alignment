'use strict';
// The owner dashboard backend. Logs the owner in at the identity provider and
// then, per design:
//   A, C: exchanges the assertion for a per-tenant owner token at
//         ns-tenant-admin (D14, D17) and calls ns-tenant-admin and the secrets
//         service directly with it.
//   B0, B1: forwards the assertion to the orchestrator (B1 adds the
//         dashboard's service token).
// It also applies a UI-level check (hidden keys) that a crafted request can
// skip; the lab measures whether anything behind it holds the line.
const { matrix, serve, call } = require('../lib/net');
const c = require('../lib/crypto');
const { loadRun, key } = require('../lib/store');

const run = loadRun(process.argv[2]);
const mx = matrix(run.design, run.breaks);
const B = run.design === 'B0' || run.design === 'B1';
const idpPub = key(run.runDir, 'idp.pub');
const svcSelf = run.design === 'B1' ? key(run.runDir, 'svc-dashboard').toString() : null; // B1 only
const UI_HIDDEN = ['TRUST_PROXY', 'DEBUG_LOGGING'];
const sessions = {};
const Z = 'dashboard';

function newSession (assertion) {
  const a = c.verifyEd(assertion, idpPub);
  if (!a.ok) return null;
  const id = c.random(16);
  sessions[id] = { sub: a.payload.sub, assertion, tokens: {} };
  return id;
}

async function ownerToken (sess, slug, ctx) {
  if (sess.tokens[slug] && !run.has('no-token-cache')) return sess.tokens[slug];
  const r = await call(mx, Z, 'ta_public', 'POST', `/t/${slug}/token`, { assertion: sess.assertion }, {}, ctx);
  if (r.status !== 200) return null;
  sess.tokens[slug] = r.body.token;
  return r.body.token;
}

const orch = (path, body, ctx) => call(mx, Z, 'orchestrator', 'POST', path, body,
  svcSelf ? { authorization: 'Service ' + svcSelf } : {}, ctx);
const relay = (r) => [r.status || 502, r.body || {}];
const credsHandled = () => (B ? (svcSelf ? 2 : 1) : 2); // assertion (+ owner token | + service token)

async function withSession (b, fn) {
  const s = sessions[b.session];
  if (!s) return [401, { error: 'no-session' }];
  const [st, out] = await fn(s);
  return [st, Object.assign({}, out, { credentialsHandled: credsHandled() })];
}

serve('dashboard', 'dashboard', mx, [
  ['POST', /^\/session\/login$/, async (req, m, b, ctx) => {
    const r = await call(mx, Z, 'idp', 'POST', '/login', { user: b.user, password: b.password }, {}, ctx);
    if (r.status !== 200) return [401, { error: 'login' }];
    return [200, { session: newSession(r.body.assertion) }];
  }],
  ['POST', /^\/session\/assertion$/, async (req, m, b) => {
    const id = newSession(b.assertion);
    return id ? [200, { session: id }] : [401, { error: 'assertion' }];
  }],
  ['POST', /^\/session\/logout$/, async (req, m, b) => { delete sessions[b.session]; return [200, { ok: true }]; }],
  ['POST', /^\/session\/reauth$/, async (req, m, b, ctx) => withSession(b, async (s) => {
    const r = await call(mx, Z, 'idp', 'POST', '/login', { user: s.sub, password: b.password }, {}, ctx);
    if (r.status !== 200) return [401, { error: 'login' }];
    s.assertion = r.body.assertion; s.tokens = {};
    return [200, { ok: true }];
  })],
  ['POST', /^\/read$/, async (req, m, b, ctx) => withSession(b, async (s) => {
    if (B) return relay(await orch('/owner/read', { assertion: s.assertion, tenant: b.tenant }, ctx));
    const t = await ownerToken(s, b.tenant, ctx); if (!t) return [403, { error: 'no-owner-token' }];
    return relay(await call(mx, Z, 'ta_public', 'GET', `/t/${b.tenant}/config`, undefined, { authorization: 'Bearer ' + t }, ctx));
  })],
  ['POST', /^\/edit$/, async (req, m, b, ctx) => withSession(b, async (s) => {
    if (UI_HIDDEN.includes(b.key)) return [422, { error: 'ui-refused' }];
    if (B) return relay(await orch('/owner/edit', { assertion: s.assertion, tenant: b.tenant, key: b.key, value: b.value, confirm: b.confirm }, ctx));
    const t = await ownerToken(s, b.tenant, ctx); if (!t) return [403, { error: 'no-owner-token' }];
    return relay(await call(mx, Z, 'ta_public', 'PUT', `/t/${b.tenant}/config/${b.key}`, { value: b.value, confirm: b.confirm }, { authorization: 'Bearer ' + t }, ctx));
  })],
  ['POST', /^\/secret$/, async (req, m, b, ctx) => withSession(b, async (s) => {
    if (B) return relay(await orch('/owner/secret', { assertion: s.assertion, tenant: b.tenant, kind: b.kind, value: b.value }, ctx));
    const t = await ownerToken(s, b.tenant, ctx); if (!t) return [403, { error: 'no-owner-token' }];
    return relay(await call(mx, Z, 'sec_public', 'PUT', `/t/${b.tenant}/secret/${b.kind}`, { value: b.value }, { authorization: 'Bearer ' + t }, ctx));
  })],
  ['POST', /^\/reveal$/, async (req, m, b, ctx) => withSession(b, async (s) => {
    if (B) return relay(await orch('/owner/reveal', { assertion: s.assertion, tenant: b.tenant, kind: b.kind }, ctx));
    const t = await ownerToken(s, b.tenant, ctx); if (!t) return [403, { error: 'no-owner-token' }];
    return relay(await call(mx, Z, 'sec_public', 'POST', `/t/${b.tenant}/reveal`, { kind: b.kind }, { authorization: 'Bearer ' + t }, ctx));
  })],
  // LAB ONLY: what an attacker who controls this process holds. Reachable
  // only from the harness zone.
  ['GET', /^\/__lab\/held$/, async (req) => {
    if (req.headers['x-lab-from'] !== 'harness') return [403, { error: 'harness-only' }];
    return [200, {
      assertions: Object.values(sessions).map((s) => s.assertion),
      ownerTokens: Object.values(sessions).flatMap((s) => Object.values(s.tokens)),
      serviceTokens: svcSelf ? { dashboard: svcSelf } : {}
    }];
  }]
]);
