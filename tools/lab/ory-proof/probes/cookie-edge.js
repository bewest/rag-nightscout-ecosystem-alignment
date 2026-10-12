#!/usr/bin/env node
'use strict';
/*
 * probes/cookie-edge.js - variant E: apex Kratos cookie behind a hardened edge (lib/edge.js).
 * Kratos must be running with variants/cookie-apex.yaml (run-variants.sh does this).
 *
 * U is a member of tenant-a only; W of tenant-a and tenant-b (W measures the user-visible flow).
 * Phases (lab-server restarted between them):
 *   intact            - what a backend receives; replay; cross-origin; controls; bypass; logout; flow
 *   break no-strip    - the edge forwards the Kratos cookie: B's backend holds a replayable session
 *   break no-origin-check - a script on B's origin makes A mint again
 * Each check records the outcome PREDICTED for its phase. Exit 0 = every prediction held.
 */
const crypto = require('crypto');
const H = require('../lib/harness');
const B_ = require('../lib/browser');
const jwt = require('../lib/jwt');

const rec = H.recorder('cookie-edge');
const P = H.env.LAB_PORT;
const A = H.env.tenantHost('tenant-a');
const B = H.env.tenantHost('tenant-b');
const OA = `http://${A}:${P}`;
const OB = `http://${B}:${P}`;
const BACKEND = 44481;
const MODE = { LAB_MODE: 'edge' };

const events = async () => (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body;
const reset = () => H.req(H.env.CONTROL_HOST, 'GET', '/reset');
const echo = async (page, origin) => { await page.goto(`${origin}/api/echo`); return JSON.parse(await page.locator('body').innerText()); };
const pick = (e) => ({ cookieNames: e.cookieNames.map((n) => n.replace(/^csrf_token_.*/, 'csrf_token_*')), sessionDigest: e.sessionDigest, headerNames: e.headerNames, edgeIdentity: e.edgeIdentity && { tenant: e.edgeIdentity.tenant, ttl: e.edgeIdentity.exp - e.edgeIdentity.iat } });
// direct to the backend port: only a process inside the edge's network could do this
function backendReq (host, method, p, headers = {}) {
  return new Promise((resolve, reject) => {
    const r = require('http').request({ host: '127.0.0.1', port: BACKEND, method, path: p, headers: Object.assign({ host: `${host}:${P}` }, headers) }, (res) => {
      let d = ''; res.on('data', (c) => { d += c; }); res.on('end', () => resolve({ status: res.statusCode, body: (() => { try { return JSON.parse(d); } catch (e) { return d; } })() }));
    });
    r.on('error', reject); r.end();
  });
}

async function loginU (browser, U) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const nav = B_.navRecorder(page);
  const v = await B_.visit(page, nav, `${OA}/`, U);
  const sess = (await ctx.cookies()).find((c) => c.name === 'ory_kratos_session');
  return { ctx, page, v, sess };
}

async function main () {
  const pool = H.db();
  await H.ensureSchema(pool);
  const ta = await H.tenant(pool, 'tenant-a');
  const tb = await H.tenant(pool, 'tenant-b');
  const U = await H.createIdentity('u');
  const W = await H.createIdentity('w');
  await H.removeMember(pool, tb, U.id);
  await H.addMember(pool, ta, U.id);
  await H.addMember(pool, ta, W.id);
  await H.addMember(pool, tb, W.id);
  rec.note('fixture', { U: 'member of tenant-a only', W: 'member of tenant-a and tenant-b', kratosCookie: 'apex (variants/cookie-apex.yaml)' });
  rec.note('edgeDesign', 'tenant from Host; Kratos whoami at the edge; X-Edge-Identity = b64url({sub,sid,tenant,iat,exp=iat+30}).HMAC-SHA256(per-process edge key shared in memory with the backend); ory_kratos_session and csrf_token_* removed from Cookie; non-GET/HEAD/OPTIONS refused unless Origin == tenant origin, or (no Origin) Sec-Fetch-Site == same-origin; both absent = allowed');

  const browser = await B_.launch();
  rec.note('browser', `Chrome ${browser.version()}`);
  let srv = await H.startServer('', 'cookie-edge-intact', MODE);
  try {
    // ================= intact =================
    // --- user-visible flow (W, member of both) ---
    {
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      const nav = B_.navRecorder(page);
      const coldA = await B_.visit(page, nav, `${OA}/`, W);
      const thenB = await B_.visit(page, nav, `${OB}/`, W);
      const xb = await B_.sameOriginFetch(page, OB, '/api/nsjwt/exchange');
      rec.note('flow', { coldA, thenB });
      rec.check('intact.flow.cold-a', 'cold start on A: edge redirects to the Kratos login, one password entry, back on A',
        { passwordEntered: true, lands: 'tenant-a app' }, { passwordEntered: coldA.passwordEntered, redirects: coldA.redirects, navigations: coldA.navigations, lands: coldA.app && coldA.app.tenant },
        coldA.passwordEntered && coldA.app && coldA.app.tenant === 'tenant-a');
      rec.check('intact.flow.then-b', 'then B: the apex session is already present, no redirect, no password; B mints for W',
        { passwordEntered: false, redirects: 0, lands: 'tenant-b app', exchange: 200 }, { passwordEntered: thenB.passwordEntered, redirects: thenB.redirects, lands: thenB.app && thenB.app.tenant, exchange: xb.status },
        !thenB.passwordEntered && thenB.redirects === 0 && thenB.app && thenB.app.tenant === 'tenant-b' && xb.status === 200);
      await ctx.close();
    }

    const { ctx, page, v, sess } = await loginU(browser, U);
    rec.check('intact.login', 'U logs in through the edge redirect; apex session cookie stored', { session: true, domain: '.apex.test', lands: 'tenant-a' },
      { session: !!sess, domain: sess && sess.domain, lands: v.app && v.app.tenant }, !!sess && sess.domain === '.apex.test' && v.app && v.app.tenant === 'tenant-a');
    rec.note('cookieJar', await B_.jarSummary(ctx));
    const dig = B_.digest(sess.value);

    // --- what a tenant backend receives ---
    await reset();
    const ea = await echo(page, OA);
    const eb = await echo(page, OB);
    const edgeSaw = (await events()).edge.events.filter((e) => e.k === 'edge-forward' && e.path === '/api/echo');
    rec.note('backendReceives', { A: pick(ea), B: pick(eb), edgeSaw: edgeSaw.map((e) => ({ tenant: e.tenant, cookieNames: e.cookieNames, sessionDigestMatchesBrowser: e.sessionDigest === dig })) });
    const noKratos = (e) => !e.cookieNames.some((n) => n === 'ory_kratos_session' || /^csrf_token_/.test(n)) && e.sessionDigest === null && !e.headerNames.includes('cookie');
    rec.check('intact.backend-receives', "neither tenant backend receives the Kratos session or CSRF cookie (no Cookie header at all); each receives an edge assertion naming its own tenant and U",
      { A: { kratosCookie: false, assertionTenant: 'tenant-a' }, B: { kratosCookie: false, assertionTenant: 'tenant-b' } },
      { A: { kratosCookie: !noKratos(ea), assertionTenant: ea.edgeIdentity && ea.edgeIdentity.tenant, sub: ea.edgeIdentity && ea.edgeIdentity.sub === U.id }, B: { kratosCookie: !noKratos(eb), assertionTenant: eb.edgeIdentity && eb.edgeIdentity.tenant, sub: eb.edgeIdentity && eb.edgeIdentity.sub === U.id } },
      noKratos(ea) && noKratos(eb) && ea.edgeIdentity.tenant === 'tenant-a' && eb.edgeIdentity.tenant === 'tenant-b' && ea.edgeIdentity.sub === U.id && eb.edgeIdentity.sub === U.id);
    rec.check('intact.edge-holds-session', 'the edge itself receives the session on both tenant hosts (same digest as the browser): the edge is the one process that holds a cross-tenant credential',
      { A: true, B: true }, { A: edgeSaw.some((e) => e.tenant === 'tenant-a' && e.sessionDigest === dig), B: edgeSaw.some((e) => e.tenant === 'tenant-b' && e.sessionDigest === dig) },
      edgeSaw.some((e) => e.tenant === 'tenant-a' && e.sessionDigest === dig) && edgeSaw.some((e) => e.tenant === 'tenant-b' && e.sessionDigest === dig));

    // --- controls ---
    const xa = await B_.sameOriginFetch(page, OA, '/api/nsjwt/exchange');
    const va = xa.body && xa.body.token ? await H.req(A, 'GET', '/api/nsjwt/verify', { headers: { authorization: `Bearer ${xa.body.token}` } }) : { status: 0 };
    rec.check('intact.control.same-origin-a', 'control: a same-origin POST on A passes the edge and mints an A token from the edge assertion',
      { status: 200, via: 'edge-assertion', verify: 200 }, { status: xa.status, via: xa.body && xa.body.via, verify: va.status }, xa.status === 200 && xa.body.via === 'edge-assertion' && va.status === 200);
    const xb = await B_.sameOriginFetch(page, OB, '/api/nsjwt/exchange');
    rec.check('intact.control.b-not-member', 'U is a member of A only: a same-origin POST on B passes the edge and B refuses for non-membership',
      { status: 403, error: 'not-a-member' }, { status: xb.status, error: xb.body && xb.body.error }, xb.status === 403 && xb.body.error === 'not-a-member');
    await H.addMember(pool, tb, U.id);
    const xb2 = await B_.sameOriginFetch(page, OB, '/api/nsjwt/exchange');
    await H.removeMember(pool, tb, U.id);
    const xb3 = await B_.sameOriginFetch(page, OB, '/api/nsjwt/exchange');
    rec.check('intact.control.b-member', 'control: U added to B, the identical browser state mints a B token; removed again, refused',
      { added: 200, tenant: 'tenant-b', removed: 403 }, { added: xb2.status, tenant: xb2.body && xb2.body.tenant, removed: xb3.status }, xb2.status === 200 && xb2.body.tenant === 'tenant-b' && xb3.status === 403);

    // Sec-Fetch-* is sent only to potentially trustworthy origins; record what arrived over http
    rec.note('secFetchSiteSeenByEdge', [...new Set((await events()).edge.events.filter((e) => e.method === 'POST').map((e) => `${e.method} origin=${e.origin ? 'present' : 'absent'} sec-fetch-site=${e.secFetchSite}`))]);

    // --- cross-origin from B ---
    await reset();
    const cross = await B_.crossOriginFetch(page, OB, `${OA}/api/nsjwt/exchange`);
    let ev = await events();
    const refused = ev.edge.events.find((e) => e.k === 'edge-refused' && e.tenant === 'tenant-a');
    const reachedA = ev.nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k));
    rec.check('intact.cross-origin.fetch', "a script on B's origin POSTs to A's exchange with credentials: the edge refuses it (Origin is B's) and A's backend never sees it",
      { edgeRefused: true, why: 'origin-mismatch', originSeen: OB, reachedBackend: 0, scriptCouldRead: false },
      { edgeRefused: !!refused, why: refused && refused.why, originSeen: refused && refused.origin, secFetchSite: refused && refused.secFetchSite, cookieSentToEdge: refused && refused.sessionDigest === dig, reachedBackend: reachedA.length, scriptCouldRead: cross.readable },
      !!refused && refused.why === 'origin-mismatch' && refused.origin === OB && reachedA.length === 0 && cross.readable === false);
    await reset();
    const form = await B_.crossOriginForm(page, OB, `${OA}/api/nsjwt/exchange`);
    ev = await events();
    const refusedF = ev.edge.events.find((e) => e.k === 'edge-refused' && e.tenant === 'tenant-a');
    rec.check('intact.cross-origin.form', "a form on B's origin POSTs to A's exchange (a navigation, no CORS): refused at the edge",
      { status: 403, error: 'cross-origin-refused', originSeen: OB, reachedBackend: 0 },
      { status: form.status, error: form.body && form.body.error, originSeen: refusedF && refusedF.origin, reachedBackend: ev.nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k)).length },
      form.status === 403 && form.body.error === 'cross-origin-refused' && refusedF && refusedF.origin === OB && ev.nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k)).length === 0);

    // --- replay ---
    rec.check('intact.replay.b-backend-cookie', "replay of the cookie as received by B's backend: B's backend received no session, so there is nothing to replay",
      { sessionAtBBackend: null }, { sessionAtBBackend: eb.sessionDigest, cookieNames: eb.cookieNames }, eb.sessionDigest === null);
    const asB = eb.edgeIdentityRaw;
    const ra1 = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { 'x-edge-identity': asB } });
    const ra2 = await backendReq(A, 'POST', '/api/nsjwt/exchange', { 'x-edge-identity': asB });
    const rb2 = await backendReq(B, 'POST', '/api/nsjwt/exchange', { 'x-edge-identity': asB });
    rec.check('intact.replay.b-assertion', "what B's backend DID receive (its edge assertion), replayed to A: through the edge it is removed (no credential); straight to A's backend it fails the tenant binding. Control: the same assertion on B's backend authenticates U (then B's membership check refuses)",
      { viaEdge: { status: 401, error: 'no-credential' }, toABackend: { status: 401, error: 'edge-assertion-tenant' }, onBBackend: { status: 403, error: 'not-a-member' } },
      { viaEdge: { status: ra1.status, error: ra1.body && ra1.body.error }, toABackend: { status: ra2.status, error: ra2.body && ra2.body.error }, onBBackend: { status: rb2.status, error: rb2.body && rb2.body.error } },
      ra1.status === 401 && ra1.body.error === 'no-credential' && ra2.status === 401 && ra2.body.error === 'edge-assertion-tenant' && rb2.status === 403 && rb2.body.error === 'not-a-member');
    const rc1 = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${sess.value}` } });
    const rc2 = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${sess.value}`, origin: OB } });
    const rc3 = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${sess.value}`, origin: OA } });
    rec.check('intact.replay.edge-cookie', 'the cookie as captured AT THE EDGE (same digest), replayed by a non-browser client to A: mints an A token (no Origin is allowed for non-browser clients); with Origin B refused; with a forged Origin A mints',
      { noOrigin: 200, originB: 403, forgedOriginA: 200, tenant: 'tenant-a' },
      { noOrigin: rc1.status, originB: rc2.status, forgedOriginA: rc3.status, tenant: rc1.body && rc1.body.tenant },
      rc1.status === 200 && rc1.body.tenant === 'tenant-a' && rc2.status === 403 && rc3.status === 200);

    // --- bypass: the backend trusts only the assertion ---
    const forged = (() => { const body = Buffer.from(JSON.stringify({ sub: U.id, sid: 'x', tenant: 'tenant-a', iat: 0, exp: 9999999999 })).toString('base64url'); return `${body}.${crypto.createHmac('sha256', crypto.randomBytes(32)).update(body).digest('base64url')}`; })();
    const by1 = await backendReq(A, 'POST', '/api/nsjwt/exchange', { cookie: `ory_kratos_session=${sess.value}` });
    const by2 = await backendReq(A, 'POST', '/api/nsjwt/exchange', { 'x-edge-identity': forged });
    rec.check('intact.bypass', "straight to A's backend (not through the edge): the Kratos cookie is not a credential there, and an assertion signed with another key fails",
      { cookie: { status: 401, error: 'no-credential' }, forged: { status: 401, error: 'edge-assertion-signature' } },
      { cookie: { status: by1.status, error: by1.body && by1.body.error }, forged: { status: by2.status, error: by2.body && by2.body.error } },
      by1.status === 401 && by1.body.error === 'no-credential' && by2.status === 401 && by2.body.error === 'edge-assertion-signature');

    // --- logout ---
    const before = await B_.sameOriginFetch(page, OA, '/api/nsjwt/exchange');
    const lo = await B_.kratosLogout(page);
    const jarAfter = (await ctx.cookies()).filter((c) => c.name === 'ory_kratos_session').length;
    const oldTok = await H.req(A, 'GET', '/api/nsjwt/verify', { headers: { authorization: `Bearer ${before.body.token}` } });
    const after = await B_.sameOriginFetch(page, OA, '/api/nsjwt/exchange');
    const nav = B_.navRecorder(page);
    const home = await B_.visit(page, nav, `${OA}/`, null);
    const oldCookie = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${sess.value}` } });
    rec.check('intact.logout', 'Kratos browser logout: the session ends everywhere at once (the edge asks Kratos each request) — new exchanges on A fail, A redirects to the login, the old cookie value is dead; a token minted BEFORE logout still verifies on A until its own exp',
      { whoamiAfter: '401', cookieLeft: 0, exchangeAfter: 401, homeShowsLogin: true, oldCookieReplay: 401, tokenMintedBefore: 200 },
      { whoamiAfter: lo.whoamiAfter, cookieLeft: jarAfter, exchangeAfter: after.status, homeShowsLogin: !!home.loginFormShown, oldCookieReplay: oldCookie.status, tokenMintedBefore: oldTok.status, tokenExpIn: jwt.decode(before.body.token).exp - Math.floor(Date.now() / 1000) },
      lo.whoamiAfter === '401' && jarAfter === 0 && after.status === 401 && home.loginFormShown && oldCookie.status === 401 && oldTok.status === 200);
    await ctx.close();
    await srv.stop();

    // ================= break: no-strip =================
    srv = await H.startServer('', 'cookie-edge-no-strip', Object.assign({ EDGE_BREAK: 'no-strip' }, MODE));
    {
      const { ctx: c2, page: p2, sess: s2 } = await loginU(browser, U);
      const live = await B_.sameOriginFetch(p2, OA, '/api/nsjwt/exchange');
      const e2 = await echo(p2, OB);
      const rp = e2.sessionDigest ? await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ory_kratos_session=${s2.value}` } }) : { status: 0, body: {} };
      rec.check('break.no-strip.live', 'liveness in this run: same-origin exchange on A', 200, live.status, live.status === 200);
      rec.check('break.no-strip.red', "BREAK no-strip: B's backend now receives U's session (same digest as the browser) and that cookie, replayed to A, mints an A token",
        { sessionAtBBackend: B_.digest(s2.value), replay: 200, tenant: 'tenant-a' }, { sessionAtBBackend: e2.sessionDigest, replay: rp.status, tenant: rp.body && rp.body.tenant },
        e2.sessionDigest === B_.digest(s2.value) && rp.status === 200 && rp.body.tenant === 'tenant-a');
      const cr = await B_.crossOriginFetch(p2, OB, `${OA}/api/nsjwt/exchange`);
      rec.check('break.no-strip.origin-still-holds', 'the origin check is independent of the strip: cross-origin from B still refused', { scriptCouldRead: false, edgeRefused: true },
        { scriptCouldRead: cr.readable, edgeRefused: (await events()).edge.events.some((e) => e.k === 'edge-refused' && e.origin === OB) }, cr.readable === false && (await events()).edge.events.some((e) => e.k === 'edge-refused' && e.origin === OB));
      await c2.close();
    }
    await srv.stop();

    // ================= break: no-origin-check =================
    srv = await H.startServer('', 'cookie-edge-no-origin-check', Object.assign({ EDGE_BREAK: 'no-origin-check' }, MODE));
    {
      const { ctx: c3, page: p3 } = await loginU(browser, U);
      const live = await B_.sameOriginFetch(p3, OA, '/api/nsjwt/exchange');
      rec.check('break.no-origin-check.live', 'liveness in this run: same-origin exchange on A', 200, live.status, live.status === 200);
      await reset();
      const cr = await B_.crossOriginFetch(p3, OB, `${OA}/api/nsjwt/exchange`);
      const ev3 = await events();
      const minted = ev3.nsjwt.events.find((e) => e.k === 'minted' && e.tenant === 'tenant-a');
      rec.check('break.no-origin-check.red', "BREAK no-origin-check: the script on B's origin makes A's backend mint again (from the edge assertion; Origin B); the browser still withholds the response",
        { minted: true, via: 'edge-assertion', originSeen: OB, scriptCouldRead: false }, { minted: !!minted, via: minted && minted.via, originSeen: minted && minted.origin, scriptCouldRead: cr.readable },
        !!minted && minted.via === 'edge-assertion' && minted.origin === OB && cr.readable === false);
      const e3 = await echo(p3, OB);
      rec.check('break.no-origin-check.strip-still-holds', "the strip is independent of the origin check: B's backend still receives no session", null, e3.sessionDigest, e3.sessionDigest === null);
      await c3.close();
    }
  } finally {
    await browser.close();
    await srv.stop().catch(() => {});
    await pool.end();
  }
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
