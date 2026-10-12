'use strict';
/*
 * edge.js - variant E: apex Kratos cookie, hardened edge in front of every tenant host.
 *
 * The edge is the only browser-facing path to a tenant backend. Per request, in order:
 *   1. resolve the tenant from Host (D10 rule + tenants row); unknown -> 404, nothing forwarded
 *   2. validate the Kratos session cookie at the edge (whoami); on success, attach an identity
 *      assertion  X-Edge-Identity: b64url({sub, sid, tenant, iat, exp}).HMAC-SHA256(edgeKey)
 *      exp = iat + 30 s; edgeKey is 32 random bytes per process, shared with the backend in
 *      memory (production: a secret or mTLS on a private network). Any client-supplied
 *      X-Edge-Identity is always removed first.
 *   3. remove the Kratos session cookie and the Kratos CSRF cookies from Cookie
 *   4. refuse a request whose method is not GET/HEAD/OPTIONS when its Origin is not the tenant's
 *      own origin; when Origin is absent, Sec-Fetch-Site must be "same-origin"; when both are
 *      absent (a non-browser client: uploaders, curl) the request is allowed
 *   then proxy to the tenant backend (lib/nsjwt.js on its own port), Host preserved.
 * A GET of "/" with no valid session is redirected to the Kratos login with return_to = that URL.
 *
 * EDGE_BREAK (comma list) removes one defence for the break-it controls:
 *   no-strip         - forward the Kratos cookies to the backend unchanged
 *   no-origin-check  - forward state-changing requests whatever their Origin
 */
const http = require('http');
const crypto = require('crypto');
const { parseCookies } = require('./nsjwt');

const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);
const ASSERT_TTL = 30;
const isKratosCookie = (n) => n === 'ory_kratos_session' || /^csrf_token_/.test(n);
const digest = (v) => crypto.createHash('sha256').update(v).digest('hex').slice(0, 16);

function signAssertion (key, payload) {
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  return `${body}.${crypto.createHmac('sha256', key).update(body).digest('base64url')}`;
}

// -> {ok, payload} | {ok:false, reason}
function verifyAssertion (key, value, now = Math.floor(Date.now() / 1000)) {
  const [body, sig] = String(value || '').split('.');
  if (!body || !sig) return { ok: false, reason: 'malformed' };
  const expect = crypto.createHmac('sha256', key).update(body).digest();
  const got = Buffer.from(sig, 'base64url');
  if (got.length !== expect.length || !crypto.timingSafeEqual(got, expect)) return { ok: false, reason: 'signature' };
  const p = JSON.parse(Buffer.from(body, 'base64url').toString());
  if (p.exp < now) return { ok: false, reason: 'expired' };
  return { ok: true, payload: p };
}

const decodeAssertion = (value) => { try { return JSON.parse(Buffer.from(String(value).split('.')[0], 'base64url').toString()); } catch (e) { return null; } };

function create (opts) {
  const { env, resolveTenant, backendPort } = opts;
  const breaks = new Set(String(opts.breaks || '').split(',').map((s) => s.trim()).filter(Boolean));
  const key = crypto.randomBytes(32);
  const stats = { events: [] };
  const ev = (e) => { stats.events.push(Object.assign({ t: Date.now() }, e)); if (stats.events.length > 500) stats.events.shift(); };

  // the backend side: nsjwt authenticator that accepts only a valid assertion for THIS tenant
  async function authenticator (req, tenant) {
    const h = req.headers['x-edge-identity'];
    if (!h) return null;
    const v = verifyAssertion(key, h);
    if (!v.ok) return { status: 401, error: `edge-assertion-${v.reason}` };
    if (v.payload.tenant !== tenant.slug) return { status: 401, error: 'edge-assertion-tenant', claim: v.payload.tenant };
    return { subject: v.payload.sub, via: 'edge-assertion', sid: v.payload.sid };
  }
  // the raw assertion is echoed so a probe can replay exactly what this backend received
  const echoExtra = (req) => ({ edgeIdentity: req.headers['x-edge-identity'] ? decodeAssertion(req.headers['x-edge-identity']) : null, edgeIdentityRaw: req.headers['x-edge-identity'] || null });

  function send (res, status, body) { res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' }); res.end(JSON.stringify(body)); }

  async function handle (req, res) {
    const hostHdr = String(req.headers.host || '');
    const host = hostHdr.toLowerCase().replace(/:\d+$/, '');
    const tenant = await resolveTenant(hostHdr);                       // 1
    if (!tenant) { ev({ k: 'edge-unknown-host', host }); return send(res, 404, { error: 'unknown-tenant', host, at: 'edge' }); }
    const own = env.ORIGIN(host);
    const origin = req.headers.origin || null;
    const sfs = req.headers['sec-fetch-site'] || null;
    const cookies = parseCookies(req.headers.cookie);
    const seen = { tenant: tenant.slug, method: req.method, path: req.url.split('?')[0], origin, secFetchSite: sfs, cookieNames: Object.keys(cookies).map((n) => n.replace(/^csrf_token_.*/, 'csrf_token_*')), sessionDigest: cookies.ory_kratos_session ? digest(cookies.ory_kratos_session) : null };

    if (!SAFE.has(req.method) && !breaks.has('no-origin-check')) {     // 4 (checked before any credential work)
      const ok = origin ? origin === own : (sfs ? sfs === 'same-origin' : true);
      if (!ok) { ev(Object.assign({ k: 'edge-refused', why: origin ? 'origin-mismatch' : 'sec-fetch-site' }, seen)); return send(res, 403, { error: 'cross-origin-refused', at: 'edge', origin, secFetchSite: sfs, tenant: tenant.slug }); }
    }

    const headers = Object.assign({}, req.headers);
    delete headers['x-edge-identity'];
    let identity = null;
    if (cookies.ory_kratos_session) {                                   // 2
      const r = await fetch(`${env.KRATOS_PUBLIC}/sessions/whoami`, { headers: { Cookie: `ory_kratos_session=${cookies.ory_kratos_session}` } });
      if (r.status === 200) {
        const s = await r.json();
        const now = Math.floor(Date.now() / 1000);
        identity = { sub: s.identity.id, sid: s.id, tenant: tenant.slug, iat: now, exp: now + ASSERT_TTL };
        headers['x-edge-identity'] = signAssertion(key, identity);
      }
    }
    if (!breaks.has('no-strip')) {                                      // 3
      const kept = Object.entries(cookies).filter(([n]) => !isKratosCookie(n)).map(([n, v]) => `${n}=${v}`);
      if (kept.length) headers.cookie = kept.join('; '); else delete headers.cookie;
    }
    ev(Object.assign({ k: 'edge-forward', identity: !!identity, stripped: !breaks.has('no-strip') }, seen));

    if (!identity && req.method === 'GET' && req.url.split('?')[0] === '/') {
      const rt = `${own}${req.url}`;
      res.writeHead(302, { location: `${env.ORIGIN(env.AUTH_HOST)}/self-service/login/browser?return_to=${encodeURIComponent(rt)}` });
      return res.end();
    }

    const up = http.request({ host: '127.0.0.1', port: backendPort, method: req.method, path: req.url, headers }, (r) => {
      res.writeHead(r.statusCode, r.headers);
      r.pipe(res);
    });
    up.on('error', (e) => send(res, 502, { error: String(e), at: 'edge' }));
    req.pipe(up);
  }

  // the backend's own app page: who the edge says this is
  async function routes (req, res, tenant, url, sendJson) {
    if (url.pathname !== '/' || req.method !== 'GET') return false;
    const a = await authenticator(req, tenant);
    if (!a || a.error) { sendJson(res, 401, { error: (a && a.error) || 'no-credential', tenant: tenant.slug }); return true; }
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    res.end(`<!doctype html><title>${tenant.slug}</title><pre id="app">${JSON.stringify({ tenant: tenant.slug, sub: a.subject })}</pre>`);
    return true;
  }

  return { handle, authenticator, echoExtra, routes, stats, breaks: [...breaks] };
}

module.exports = { create, verifyAssertion, decodeAssertion };
