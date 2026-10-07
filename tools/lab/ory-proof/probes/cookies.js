#!/usr/bin/env node
'use strict';
/*
 * probes/cookies.js - Kratos session cookie scope across tenant subdomains, in a real browser.
 *
 * VARIANT names the Kratos cookie configuration the stack was (re)started with (run-all.sh):
 *   host-only     - session.cookie.domain and cookies.domain unset
 *   apex          - both set to apex.test (variants/cookie-apex.yaml)
 *   user-content  - both set to user-content.apex.test, a domain the auth host is not inside
 * The browser (Chrome, --host-resolver-rules maps *.apex.test to 127.0.0.1) logs U in through a
 * Kratos browser flow on auth.apex.test with return_to on tenant-a, then asks each tenant host
 * which cookies it received and tries the cookie-path exchange on each. U is a member of A only.
 * Every negative is paired with a positive in the same run.
 */
const { chromium } = require('playwright');
const H = require('../lib/harness');

const VARIANT = process.env.VARIANT || 'host-only';
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const rec = H.recorder(`cookies-${VARIANT}`);
const P = H.env.LAB_PORT;
const AUTH = `http://${H.env.AUTH_HOST}:${P}`;
const A = H.env.tenantHost('tenant-a');
const B = H.env.tenantHost('tenant-b');
const OA = `http://${A}:${P}`;
const OB = `http://${B}:${P}`;

async function browserLogin (page, who, returnTo) {
  await page.goto(`${AUTH}/self-service/login/browser?return_to=${encodeURIComponent(returnTo)}`);
  const onForm = await page.locator('form#f input[name=identifier]').count();
  if (!onForm) return { formShown: false, url: page.url(), body: (await page.content()).slice(0, 600) };
  await page.fill('input[name=identifier]', who.email);
  await page.fill('input[name=password]', who.password);
  await Promise.all([page.waitForLoadState('load'), page.click('button[name=method][value=password]')]);
  await page.waitForLoadState('load');
  return { formShown: true, url: page.url(), body: (await page.content()).replace(/<[^>]+>/g, ' ').slice(0, 600) };
}

async function echoFrom (page, origin) {
  await page.goto(`${origin}/api/echo`);
  return JSON.parse(await page.locator('body').innerText());
}

async function main () {
  const pool = H.db();
  await H.ensureSchema(pool);
  const ta = await H.tenant(pool, 'tenant-a');
  const tb = await H.tenant(pool, 'tenant-b');
  const U = await H.createIdentity('u');
  await H.addMember(pool, ta, U.id);
  rec.note('variant', VARIANT);

  const srv = await H.startServer('', `cookies-${VARIANT}`);
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--host-resolver-rules=MAP *.apex.test 127.0.0.1'] });
  rec.note('browser', `Chrome ${browser.version()}`);
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  try {
    const login = await browserLogin(page, U, `${OA}/api/echo`);
    const jar = (await ctx.cookies()).map((c) => ({ name: c.name.replace(/^csrf_token_.*/, 'csrf_token_*'), domain: c.domain, httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite }));
    rec.note('login', { formShown: login.formShown, finalUrl: login.url, excerpt: login.body.slice(0, 300) });
    rec.note('cookieJar', jar);
    const sess = (await ctx.cookies()).find((c) => c.name === 'ory_kratos_session');

    const whoami = await page.goto(`${AUTH}/ui/home`).then(() => page.locator('#whoami').getAttribute('data-status'));
    if (VARIANT === 'user-content') {
      rec.check('login.fails', 'cookie domain outside the auth host: the browser login cannot complete and no session cookie is stored',
        { sessionCookie: false, whoamiOnAuthHost: '401' }, { sessionCookie: !!sess, whoamiOnAuthHost: whoami, finalUrl: login.url }, !sess && whoami === '401');
      // liveness for this variant: Kratos itself is up and the native (cookie-less) path still works
      const n = await H.nativeLogin(U);
      const ex = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { 'x-session-token': n.token } });
      rec.check('live', 'liveness in this run: Kratos native login and the A exchange still succeed', [200, 200], [n.status, ex.status], n.status === 200 && ex.status === 200);
    } else {
      rec.check('login.ok', 'browser login through the ONE pool succeeds and lands on tenant-a', { session: true, whoami: '200' }, { session: !!sess, whoami, sessionCookieDomain: sess && sess.domain }, !!sess && whoami === '200');
    }

    const ea = await echoFrom(page, OA);
    const eb = await echoFrom(page, OB);
    const hasA = ea.cookieNames.includes('ory_kratos_session');
    const hasB = eb.cookieNames.includes('ory_kratos_session');
    rec.note('echo', { tenantA: ea.cookieNames.map((n) => n.replace(/^csrf_token_.*/, 'csrf_token_*')), tenantB: eb.cookieNames.map((n) => n.replace(/^csrf_token_.*/, 'csrf_token_*')) });

    if (VARIANT === 'apex') {
      rec.check('scope.reaches-both', 'apex cookie domain: the session cookie reaches BOTH tenant hosts', { A: true, B: true }, { A: hasA, B: hasB }, hasA && hasB);
      // cookie-path exchange, same-origin, from each tenant's page
      await page.goto(`${OA}/__health`);
      const xa = await page.evaluate(async () => { const r = await fetch('/api/nsjwt/exchange', { method: 'POST' }); return { status: r.status, body: await r.json() }; });
      await page.goto(`${OB}/__health`);
      const xb = await page.evaluate(async () => { const r = await fetch('/api/nsjwt/exchange', { method: 'POST' }); return { status: r.status, body: await r.json() }; });
      rec.check('exchange.a', 'positive: cookie-path exchange on A mints an A token', { status: 200, via: 'kratos-session-cookie' }, { status: xa.status, via: xa.body.via }, xa.status === 200 && xa.body.via === 'kratos-session-cookie');
      rec.check('exchange.b', 'probe: the same cookie arrives at B and B refuses for non-membership', { status: 403, error: 'not-a-member' }, { status: xb.status, error: xb.body.error }, xb.status === 403 && xb.body.error === 'not-a-member');
      await H.addMember(pool, tb, U.id);
      const xb2 = await page.evaluate(async () => { const r = await fetch('/api/nsjwt/exchange', { method: 'POST' }); return { status: r.status, body: await r.json() }; });
      await H.removeMember(pool, tb, U.id);
      rec.check('exchange.b.control', 'control: U added to B, the identical browser state now mints a B token', { status: 200, tenant: 'tenant-b' }, { status: xb2.status, tenant: xb2.body.tenant }, xb2.status === 200 && xb2.body.tenant === 'tenant-b');

      // cross-origin: a page on B's origin calls A's exchange with credentials
      await H.req(H.env.CONTROL_HOST, 'GET', '/reset');
      const cross = await page.evaluate(async (oa) => {
        try { const r = await fetch(`${oa}/api/nsjwt/exchange`, { method: 'POST', credentials: 'include' }); return { readable: true, status: r.status }; } catch (e) { return { readable: false, error: String(e) }; }
      }, OA);
      const evs = (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body.nsjwt.events.filter((e) => e.tenant === 'tenant-a');
      const minted = evs.find((e) => e.k === 'minted');
      rec.check('cross-origin.b-to-a', "a script on B's origin POSTs to A's exchange: the session cookie is sent (tenants are same-site) and A mints; the browser withholds the response from B's script (no CORS)",
        { serverMinted: true, viaCookie: true, originSeen: OB, scriptCouldRead: false },
        { serverMinted: !!minted, viaCookie: !!minted && minted.via === 'kratos-session-cookie', originSeen: minted && minted.origin, scriptCouldRead: cross.readable },
        !!minted && minted.via === 'kratos-session-cookie' && minted.origin === OB && cross.readable === false);

      // replay: whoever receives B's request headers holds a credential that works at A
      const digest = require('crypto').createHash('sha256').update(sess.value).digest('hex').slice(0, 16);
      const replay = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${sess.value}` } });
      rec.check('replay.b-cookie-at-a', "the session cookie B's host received (same digest), replayed by a non-browser client to A, mints an A token",
        { sameSessionAtB: true, status: 200, tenant: 'tenant-a' }, { sameSessionAtB: eb.sessionDigest === digest, status: replay.status, tenant: replay.body && replay.body.tenant },
        eb.sessionDigest === digest && replay.status === 200 && replay.body.tenant === 'tenant-a');
      rec.check('attrs', 'session cookie attributes as set by Kratos --dev over http (production sets Secure)', { httpOnly: true, sameSite: 'Lax' }, { httpOnly: sess.httpOnly, sameSite: sess.sameSite, secure: sess.secure }, sess.httpOnly && sess.sameSite === 'Lax');
    } else if (VARIANT === 'host-only') {
      rec.check('scope.neither', 'host-only cookie on auth.apex.test: the session cookie reaches NEITHER tenant host', { A: false, B: false }, { A: hasA, B: hasB }, !hasA && !hasB);
      await page.goto(`${OA}/__health`);
      const xa = await page.evaluate(async () => { const r = await fetch('/api/nsjwt/exchange', { method: 'POST' }); return { status: r.status, body: await r.json() }; });
      rec.check('exchange.a.no-cookie', 'so a tenant host cannot use the cookie path at all: A answers no-credential', { status: 401, error: 'no-credential' }, { status: xa.status, error: xa.body.error }, xa.status === 401 && xa.body.error === 'no-credential');
      // positive control in the same run: the session IS live; replayed explicitly, A accepts it
      const replay = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${sess.value}` } });
      rec.check('exchange.a.explicit', 'control: the same session, handed to A explicitly, mints an A token (the session is live; only the scope withheld it)', 200, replay.status, replay.status === 200);

      // probe C: Kratos served under each tenant host by the edge (/.ory/*): one base_url
      const r = await H.req(A, 'GET', '/.ory/self-service/login/browser', { headers: { accept: 'application/json' } });
      const action = r.body && r.body.ui && new URL(r.body.ui.action);
      const setCookie = [].concat(r.headers['set-cookie'] || []).map((c) => c.replace(/^csrf_token_[^=]*=[^;]*/, 'csrf_token_*=…'));
      rec.check('per-tenant-proxy', "Kratos proxied under A's host still names its single base_url in the flow: form actions go to the auth host, while the CSRF cookie was set host-only on A",
        { status: 200, actionHost: H.env.AUTH_HOST, csrfCookieDomainAttr: 'none (host-only on tenant-a)' },
        { status: r.status, actionHost: action && action.hostname, setCookie },
        r.status === 200 && action.hostname === H.env.AUTH_HOST && setCookie.every((c) => !/domain=/i.test(c)));
    } else {
      rec.check('scope.neither', 'user-content cookie domain: no session exists, so neither tenant host receives one', { A: false, B: false }, { A: hasA, B: hasB }, !hasA && !hasB);
    }
  } finally {
    await browser.close();
    await srv.stop();
    await pool.end();
  }
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
