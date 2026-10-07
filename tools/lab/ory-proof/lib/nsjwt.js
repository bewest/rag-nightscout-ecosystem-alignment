'use strict';
/*
 * nsjwt - the Nightscout side of the exchange (D17: ours to write under any vendor).
 *
 * Order is the property under test (D14): resolve the tenant from Host FIRST, then examine a
 * credential (Kratos session cookie, Kratos session token, or a Hydra access token), then check
 * membership in tenant_members, then mint a Nightscout JWT signed with THAT tenant's key.
 *
 * NSJWT_BREAK (comma list) deliberately removes one defence, for the break-it controls:
 *   skip-membership    - mint for any authenticated subject
 *   shared-key         - one deployment-wide signing key instead of one per tenant
 *   no-claim-check     - verify checks the signature only, not the tenant claim
 *   skip-client-check  - accept a Hydra token issued to ANY OAuth client, not this tenant's
 */
const crypto = require('crypto');
const jwt = require('./jwt');

const SCHEMA = `
CREATE TABLE IF NOT EXISTS tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE NOT NULL CHECK (slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'),
  oauth_client_id text
);
CREATE TABLE IF NOT EXISTS tenant_members (
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  subject_id uuid NOT NULL,           -- the Kratos identity id; no FK: it lives in another database
  role text NOT NULL DEFAULT 'owner',
  PRIMARY KEY (tenant_id, subject_id)
);`;

function parseCookies (h) {
  const out = {};
  for (const part of String(h || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}

function create (opts) {
  const { pool, env } = opts;
  const breaks = new Set(String(opts.breaks || '').split(',').map((s) => s.trim()).filter(Boolean));
  const rule = new RegExp(env.TENANT_HOST_RULE);
  const keys = new Map(); // tenant id -> signing key, generated at boot, held in memory only
  const shared = crypto.randomBytes(32);
  const stats = { resolved: 0, unknownHost: 0, credentialExaminations: 0, minted: 0, events: [] };
  const keyFor = (t) => {
    if (breaks.has('shared-key')) return shared;
    if (!keys.has(t.id)) keys.set(t.id, crypto.randomBytes(32));
    return keys.get(t.id);
  };
  const ev = (e) => { stats.events.push(Object.assign({ t: Date.now() }, e)); if (stats.events.length > 500) stats.events.shift(); };

  async function init () { await pool.query(SCHEMA); }

  async function resolveTenant (host) {
    const m = rule.exec(String(host || '').toLowerCase());
    if (!m) return null;
    const r = await pool.query('SELECT id, slug, oauth_client_id FROM tenants WHERE slug = $1', [m[1]]);
    return r.rows[0] || null;
  }

  // -> {subject, via, client_id?} or {error, status}
  async function authenticate (req, tenant) {
    stats.credentialExaminations++;
    const cookies = parseCookies(req.headers.cookie);
    const tokenHdr = req.headers['x-session-token'];
    const auth = req.headers.authorization || '';
    if (tokenHdr || cookies.ory_kratos_session) {
      const headers = tokenHdr ? { 'X-Session-Token': tokenHdr } : { Cookie: `ory_kratos_session=${cookies.ory_kratos_session}` };
      const r = await fetch(`${env.KRATOS_PUBLIC}/sessions/whoami`, { headers });
      if (r.status !== 200) return { status: 401, error: 'no-kratos-session', upstream: r.status };
      const s = await r.json();
      return { subject: s.identity.id, via: tokenHdr ? 'kratos-session-token' : 'kratos-session-cookie' };
    }
    if (/^Bearer /i.test(auth)) {
      const tok = auth.slice(7).trim();
      const r = await fetch(`${env.HYDRA_ADMIN}/admin/oauth2/introspect`, {
        method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ token: tok })
      });
      const it = await r.json();
      if (!it.active) return { status: 401, error: 'hydra-token-inactive' };
      if (!breaks.has('skip-client-check') && it.client_id !== tenant.oauth_client_id) {
        return { status: 401, error: 'hydra-token-other-client', client_id: it.client_id };
      }
      return { subject: it.sub, via: 'hydra-access-token', client_id: it.client_id };
    }
    return { status: 401, error: 'no-credential' };
  }

  function send (res, status, body) {
    res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    res.end(JSON.stringify(body));
  }

  async function handle (req, res) {
    const host = req.headers.host;
    const url = new URL(req.url, 'http://x');
    // 1. tenant FIRST - nothing below runs for a host that does not resolve
    const tenant = await resolveTenant(host);
    if (!tenant) { stats.unknownHost++; ev({ k: 'unknown-host', host }); return send(res, 404, { error: 'unknown-tenant', host }); }
    stats.resolved++;

    if (url.pathname === '/__health') return send(res, 200, { ok: true, tenant: tenant.slug });

    if (url.pathname === '/api/echo') {
      const c = parseCookies(req.headers.cookie);
      const names = Object.keys(c);
      // a digest, never the value: lets a probe prove WHICH session reached this host
      const sessionDigest = c.ory_kratos_session ? crypto.createHash('sha256').update(c.ory_kratos_session).digest('hex').slice(0, 16) : null;
      ev({ k: 'echo', tenant: tenant.slug, cookieNames: names, sessionDigest, origin: req.headers.origin || null, method: req.method });
      return send(res, 200, { tenant: tenant.slug, cookieNames: names, sessionDigest, origin: req.headers.origin || null });
    }

    if (url.pathname === '/api/nsjwt/exchange' && req.method === 'POST') {
      const a = await authenticate(req, tenant);              // 2. credential
      if (a.error) { ev({ k: 'exchange-deny', tenant: tenant.slug, why: a.error, origin: req.headers.origin || null }); return send(res, a.status, a); }
      if (!breaks.has('skip-membership')) {                   // 3. membership in THIS tenant
        const r = await pool.query('SELECT role FROM tenant_members WHERE tenant_id = $1 AND subject_id = $2', [tenant.id, a.subject]);
        if (!r.rows.length) { ev({ k: 'exchange-deny', tenant: tenant.slug, why: 'not-a-member', subject: a.subject }); return send(res, 403, { error: 'not-a-member', tenant: tenant.slug, subject: a.subject }); }
      }
      const now = Math.floor(Date.now() / 1000);              // 4. mint with THIS tenant's key
      const token = jwt.sign({ sub: a.subject, tenant: tenant.slug, tid: tenant.id, via: a.via, iat: now, exp: now + 3600 }, keyFor(tenant));
      stats.minted++;
      ev({ k: 'minted', tenant: tenant.slug, subject: a.subject, via: a.via, origin: req.headers.origin || null });
      return send(res, 200, { token, tenant: tenant.slug, subject: a.subject, via: a.via });
    }

    if (url.pathname === '/api/nsjwt/verify') {
      const auth = req.headers.authorization || '';
      const v = jwt.verify(auth.replace(/^Bearer /i, ''), keyFor(tenant));
      if (!v.ok) return send(res, 401, { error: v.reason, tenant: tenant.slug });
      if (!breaks.has('no-claim-check') && v.payload.tenant !== tenant.slug) {
        return send(res, 401, { error: 'tenant-claim', tenant: tenant.slug, claim: v.payload.tenant });
      }
      return send(res, 200, { ok: true, tenant: tenant.slug, sub: v.payload.sub, claim: v.payload.tenant });
    }

    return send(res, 404, { error: 'no-route', tenant: tenant.slug });
  }

  return { init, handle, stats, breaks: [...breaks] };
}

module.exports = { create, parseCookies, SCHEMA };
