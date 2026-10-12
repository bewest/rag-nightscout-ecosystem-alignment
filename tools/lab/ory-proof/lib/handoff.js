'use strict';
/*
 * handoff.js - variant H2: host-only Kratos cookie on the auth host, plus our own hand-off.
 *
 * Auth host (auth.apex.test):
 *   GET  /exchange?tenant=<slug>&return_to=<url>&state=<nonce>
 *        in order: resolve the tenant (404) -> state well-formed (400) -> return_to's origin is
 *        exactly the tenant's registered origin (400) -> Kratos session from the host-only cookie
 *        (none: 303 to the Kratos login with return_to = this URL) -> tenant_members row (403,
 *        rendered at the auth host, no redirect) -> issue a code -> 302 return_to?code=&state=
 *        A code is 32 random bytes (base64url), held in memory, bound to {tenant, subject,
 *        Kratos session id, state}, valid HANDOFF_CODE_TTL_MS (default 60 s), single use.
 *   POST /exchange/redeem   {code, state}   Authorization: Bearer <the tenant's redeem secret>
 *        server-to-server. In order: redeemer credential (401) -> code known (400 invalid-code) ->
 *        unused (400 code-used) -> unexpired (400 code-expired) -> [mark used] -> code's tenant is
 *        the redeemer's tenant (400 wrong-tenant) -> state matches (400 state-mismatch) -> mint a
 *        Nightscout token with the REDEEMER's tenant key. A failed attempt on a live code burns it.
 *        Membership is checked once, at issue; redemption does not re-check it.
 * Tenant host (<slug>.user-content.apex.test), on the nsjwt stand-in:
 *   GET /                    tenant session -> app page; else set a host-only state cookie and
 *                            302 to the auth host's /exchange
 *   GET /handoff/callback    state == state cookie (400 tenant-state-mismatch) -> redeem
 *                            server-to-server -> host-only tenant session cookie (HttpOnly,
 *                            SameSite=Lax; HANDOFF_SESSION_SAMESITE overrides, diagnostic) -> 302 /
 *   POST /api/nsjwt/exchange authenticates with the tenant session (then nsjwt's membership check)
 * The registered origin of a tenant is http://<slug>.user-content.apex.test:44480 (computed from
 * the slug in the lab; a column in production). Redeem secrets are 32 random bytes per tenant per
 * process; the control host exposes them so a probe can act as a tenant backend.
 *
 * HANDOFF_BREAK (comma list) removes one defence:
 *   no-tenant-binding  - redeem does not compare the code's tenant to the redeemer's
 *   no-single-use      - a redeemed code stays redeemable
 *   no-return-to-check - /exchange redirects to any return_to
 */
const http = require('http');
const crypto = require('crypto');
const { parseCookies } = require('./nsjwt');

const SESSION_COOKIE = 'ns_session';
const STATE_COOKIE = 'ns_handoff_state';
const rand = () => crypto.randomBytes(32).toString('base64url');
const hash = (v) => crypto.createHash('sha256').update(v).digest('hex');

function create (opts) {
  const { env, ns, pool } = opts;
  const breaks = new Set(String(opts.breaks || '').split(',').map((s) => s.trim()).filter(Boolean));
  const ttl = parseInt(opts.ttlMs || process.env.HANDOFF_CODE_TTL_MS || '60000', 10);
  // diagnostic only (probes/cookie-handoff.js): the tenant session cookie's SameSite attribute
  const sameSite = process.env.HANDOFF_SESSION_SAMESITE || 'Lax';
  const codes = new Map();      // sha256(code) -> {tenantId, slug, subject, sid, state, returnTo, exp, used}
  const secrets = new Map();    // slug -> redeem secret (the tenant backend's credential)
  const sessions = new Map();   // `${tenantId}:${sid}` -> {subject, kratosSid, created}
  const AUTH = env.ORIGIN(env.AUTH_HOST);
  const registeredOrigin = (slug) => env.ORIGIN(env.tenantHost(slug));
  const secretFor = (slug) => { if (!secrets.has(slug)) secrets.set(slug, rand()); return secrets.get(slug); };
  const ev = (e) => ns.ev(Object.assign({ at: 'handoff' }, e));

  function json (res, status, body) { res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' }); res.end(JSON.stringify(body)); }
  function redirect (res, status, to, cookies = []) { res.writeHead(status, { location: to, 'set-cookie': cookies, 'cache-control': 'no-store' }); res.end(); }

  async function tenantBySlug (slug) {
    if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(String(slug || ''))) return null;
    return ns.resolveTenant(env.tenantHost(slug));
  }

  // ---------------- auth host ----------------
  async function authHandle (req, res) {
    const url = new URL(req.url, AUTH);
    if (url.pathname === '/exchange' && req.method === 'GET') {
      const slug = url.searchParams.get('tenant');
      const state = url.searchParams.get('state') || '';
      const returnTo = url.searchParams.get('return_to') || '';
      const tenant = await tenantBySlug(slug);
      if (!tenant) { ev({ k: 'issue-deny', why: 'unknown-tenant', slug }); return json(res, 404, { error: 'unknown-tenant', at: 'auth-host' }); }
      if (!/^[A-Za-z0-9_-]{16,128}$/.test(state)) { ev({ k: 'issue-deny', why: 'bad-state', tenant: tenant.slug }); return json(res, 400, { error: 'bad-state', at: 'auth-host' }); }
      if (!breaks.has('no-return-to-check')) {
        let o = null;
        try { o = new URL(returnTo).origin; } catch (e) { /* unparsable */ }
        if (o !== registeredOrigin(tenant.slug)) { ev({ k: 'issue-deny', why: 'return-to', tenant: tenant.slug, returnTo }); return json(res, 400, { error: 'return-to-not-tenant-origin', at: 'auth-host', origin: o }); }
      }
      const c = parseCookies(req.headers.cookie);
      let s = null;
      if (c.ory_kratos_session) {
        const r = await fetch(`${env.KRATOS_PUBLIC}/sessions/whoami`, { headers: { Cookie: `ory_kratos_session=${c.ory_kratos_session}` } });
        if (r.status === 200) s = await r.json();
      }
      if (!s) { ev({ k: 'issue-login', tenant: tenant.slug }); return redirect(res, 303, `${AUTH}/self-service/login/browser?return_to=${encodeURIComponent(`${AUTH}${req.url}`)}`); }
      const m = await pool.query('SELECT 1 FROM tenant_members WHERE tenant_id = $1 AND subject_id = $2', [tenant.id, s.identity.id]);
      if (!m.rows.length) { ev({ k: 'issue-deny', why: 'not-a-member', tenant: tenant.slug, subject: s.identity.id }); return json(res, 403, { error: 'not-a-member', at: 'auth-host', tenant: tenant.slug }); }
      const code = rand();
      codes.set(hash(code), { tenantId: tenant.id, slug: tenant.slug, subject: s.identity.id, sid: s.id, state, returnTo, exp: Date.now() + ttl, used: false });
      const to = new URL(returnTo);
      to.searchParams.set('code', code);
      to.searchParams.set('state', state);
      ev({ k: 'issued', tenant: tenant.slug, subject: s.identity.id, returnToHost: to.host });
      return redirect(res, 302, to.toString());
    }
    if (url.pathname === '/exchange/redeem' && req.method === 'POST') {
      const bearer = String(req.headers.authorization || '').replace(/^Bearer /i, '');
      const slug = [...secrets.entries()].find(([, v]) => bearer && v.length === bearer.length && crypto.timingSafeEqual(Buffer.from(v), Buffer.from(bearer)));
      if (!slug) return json(res, 401, { error: 'redeemer-unauthenticated' });
      const redeemer = await tenantBySlug(slug[0]);
      const body = await new Promise((resolve) => { let d = ''; req.on('data', (x) => { d += x; }); req.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { resolve({}); } }); });
      const deny = (status, error) => { ev({ k: 'redeem-deny', why: error, redeemer: redeemer.slug }); return json(res, status, { error, at: 'auth-host', redeemer: redeemer.slug }); };
      const rec = codes.get(hash(String(body.code || '')));
      if (!rec) return deny(400, 'invalid-code');
      if (rec.used) return deny(400, 'code-used');
      if (Date.now() > rec.exp) return deny(400, 'code-expired');
      if (!breaks.has('no-single-use')) rec.used = true;
      if (!breaks.has('no-tenant-binding') && rec.tenantId !== redeemer.id) return deny(400, 'wrong-tenant');
      if (String(body.state || '') !== rec.state) return deny(400, 'state-mismatch');
      const token = ns.mint(redeemer, rec.subject, 'handoff-code');
      ev({ k: 'redeemed', redeemer: redeemer.slug, codeTenant: rec.slug, subject: rec.subject });
      return json(res, 200, { token, tenant: redeemer.slug, subject: rec.subject, kratosSid: rec.sid });
    }
    return false;
  }

  // ---------------- tenant host (nsjwt routes + authenticator) ----------------
  function tenantSession (req, tenant) {
    const c = parseCookies(req.headers.cookie);
    return c[SESSION_COOKIE] ? sessions.get(`${tenant.id}:${c[SESSION_COOKIE]}`) || null : null;
  }

  async function authenticator (req, tenant) {
    const s = tenantSession(req, tenant);
    return s ? { subject: s.subject, via: 'tenant-session' } : null;
  }

  function redeem (slug, code, state) {
    return new Promise((resolve, reject) => {
      const body = JSON.stringify({ code, state });
      const r = http.request({ host: '127.0.0.1', port: env.LAB_PORT, method: 'POST', path: '/exchange/redeem',
        headers: { host: `${env.AUTH_HOST}:${env.LAB_PORT}`, 'content-type': 'application/json', authorization: `Bearer ${secretFor(slug)}` } }, (x) => {
        let d = ''; x.on('data', (c) => { d += c; }); x.on('end', () => resolve({ status: x.statusCode, body: JSON.parse(d) }));
      });
      r.on('error', reject); r.end(body);
    });
  }

  async function routes (req, res, tenant, url, send) {
    const own = registeredOrigin(tenant.slug);
    if (url.pathname === '/' && req.method === 'GET') {
      const s = tenantSession(req, tenant);
      if (s) {
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
        res.end(`<!doctype html><title>${tenant.slug}</title><pre id="app">${JSON.stringify({ tenant: tenant.slug, sub: s.subject })}</pre>`);
        return true;
      }
      const state = rand();
      redirect(res, 302, `${AUTH}/exchange?tenant=${tenant.slug}&return_to=${encodeURIComponent(`${own}/handoff/callback`)}&state=${state}`,
        [`${STATE_COOKIE}=${state}; Path=/; HttpOnly; SameSite=Lax; Max-Age=600`]);
      return true;
    }
    if (url.pathname === '/handoff/callback' && req.method === 'GET') {
      const c = parseCookies(req.headers.cookie);
      const state = url.searchParams.get('state') || '';
      if (!c[STATE_COOKIE] || c[STATE_COOKIE] !== state) { ev({ k: 'callback-deny', why: 'tenant-state-mismatch', tenant: tenant.slug }); send(res, 400, { error: 'tenant-state-mismatch', at: 'tenant', tenant: tenant.slug }); return true; }
      const r = await redeem(tenant.slug, url.searchParams.get('code') || '', state);
      if (r.status !== 200) { send(res, r.status, Object.assign({ at: 'tenant-callback' }, r.body)); return true; }
      const sid = rand();
      sessions.set(`${tenant.id}:${sid}`, { subject: r.body.subject, kratosSid: r.body.kratosSid, created: Date.now() });
      redirect(res, 302, `${own}/`, [`${SESSION_COOKIE}=${sid}; Path=/; HttpOnly; SameSite=${sameSite}`, `${STATE_COOKIE}=; Path=/; Max-Age=0`]);
      return true;
    }
    return false;
  }

  return { authHandle, authenticator, routes, secretFor, breaks: [...breaks], ttl, sameSite, codes };
}

module.exports = { create, SESSION_COOKIE, STATE_COOKIE };
