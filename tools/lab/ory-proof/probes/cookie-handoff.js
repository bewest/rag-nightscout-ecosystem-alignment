#!/usr/bin/env node
'use strict';
/*
 * probes/cookie-handoff.js - variant H2: host-only Kratos cookie on the auth host plus our own
 * hand-off (lib/handoff.js). Kratos must be running with its default cookie config (host-only).
 *
 * U is a member of tenant-a only; W of tenant-a, tenant-b and tenant-c (W measures the flow and
 * the logout). The browser is Chrome; the refusal matrix is sent by a non-browser client carrying
 * U's real Kratos cookie (taken from the browser) or acting as a tenant backend at the redeem
 * endpoint with that tenant's redeem secret (from the lab control host).
 * Phases: intact; expiry (code TTL 1500 ms); break no-tenant-binding; break no-single-use;
 * break no-return-to-check. Each check records the outcome PREDICTED for its phase; the
 * cross-origin prediction is the brief's ("nothing to send, no cookie").
 */
const H = require('../lib/harness');
const B_ = require('../lib/browser');
const jwt = require('../lib/jwt');

const rec = H.recorder('cookie-handoff');
const P = H.env.LAB_PORT;
const A = H.env.tenantHost('tenant-a');
const B = H.env.tenantHost('tenant-b');
const OA = `http://${A}:${P}`;
const OB = `http://${B}:${P}`;
const OC = `http://${H.env.tenantHost('tenant-c')}:${P}`;
const MODE = { LAB_MODE: 'handoff' };
const STATE = () => require('crypto').randomBytes(24).toString('base64url');

const events = async () => (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body;
const reset = () => H.req(H.env.CONTROL_HOST, 'GET', '/reset');
const secret = async (slug) => (await H.req(H.env.CONTROL_HOST, 'GET', `/handoff/redeem-secret?tenant=${slug}`)).body.secret;

// GET /exchange on the auth host with U's Kratos cookie -> {status, location, code, error}
async function issue (cookie, slug, returnTo, state) {
  const r = await H.req(H.env.AUTH_HOST, 'GET', `/exchange?tenant=${slug}&return_to=${encodeURIComponent(returnTo)}&state=${state}`, { headers: { cookie: `ory_kratos_session=${cookie}` } });
  const loc = r.headers.location || null;
  let code = null; let locHost = null;
  if (loc) { const u = new URL(loc); code = u.searchParams.get('code'); locHost = u.host; }
  return { status: r.status, location: loc, locHost, code, error: r.body && r.body.error };
}
// POST /exchange/redeem as tenant `slug`'s backend
async function redeem (slug, code, state) {
  const r = await H.req(H.env.AUTH_HOST, 'POST', '/exchange/redeem', { headers: { authorization: `Bearer ${await secret(slug)}` }, body: { code, state } });
  return { status: r.status, error: r.body && r.body.error, tenant: r.body && r.body.tenant, subject: r.body && r.body.subject, token: r.body && r.body.token };
}
const verify = (host, tok) => H.req(host, 'GET', '/api/nsjwt/verify', { headers: { authorization: `Bearer ${tok}` } });

async function liveness (phase, cookie, U) {
  const st = STATE();
  const i = await issue(cookie, 'tenant-a', `${OA}/handoff/callback`, st);
  const r = i.code ? await redeem('tenant-a', i.code, st) : { status: 0 };
  const v = r.token ? await verify(A, r.token) : { status: 0, body: {} };
  rec.check(`${phase}.live`, 'liveness in this run: U is issued an A code, A redeems it, the token verifies on A',
    { issue: 302, redeem: 200, verify: 200, sub: 'U' }, { issue: i.status, redeem: r.status, verify: v.status, sub: r.subject === U.id ? 'U' : r.subject },
    i.status === 302 && r.status === 200 && v.status === 200 && r.subject === U.id);
}

async function main () {
  const pool = H.db();
  await H.ensureSchema(pool);
  const ta = await H.tenant(pool, 'tenant-a');
  const tb = await H.tenant(pool, 'tenant-b');
  const tc = await H.tenant(pool, 'tenant-c');
  const U = await H.createIdentity('u');
  const W = await H.createIdentity('w');
  await H.removeMember(pool, tb, U.id);
  await H.addMember(pool, ta, U.id);
  for (const t of [ta, tb, tc]) await H.addMember(pool, t, W.id);
  rec.note('fixture', { U: 'member of tenant-a only', W: 'member of tenant-a, tenant-b, tenant-c', kratosCookie: 'host-only on auth.apex.test (default config)' });

  const browser = await B_.launch();
  rec.note('browser', `Chrome ${browser.version()}`);
  let srv = await H.startServer('', 'cookie-handoff-intact', MODE);
  try {
    // ================= intact =================
    // --- user-visible flow (W) ---
    const cw = await browser.newContext();
    const pw = await cw.newPage();
    const nw = B_.navRecorder(pw);
    const coldA = await B_.visit(pw, nw, `${OA}/`, W);
    const thenB = await B_.visit(pw, nw, `${OB}/`, W);
    const xbW = await B_.sameOriginFetch(pw, OB, '/api/nsjwt/exchange');
    rec.note('flow', { coldA, thenB });
    rec.note('cookieJarW', await B_.jarSummary(cw));
    rec.check('intact.flow.cold-a', 'cold start on A: A -> auth /exchange -> Kratos login (one password) -> auth /exchange -> A callback -> A',
      { passwordEntered: true, lands: 'tenant-a app' }, { passwordEntered: coldA.passwordEntered, redirects: coldA.redirects, navigations: coldA.navigations, lands: coldA.app && coldA.app.tenant },
      coldA.passwordEntered && coldA.app && coldA.app.tenant === 'tenant-a');
    rec.check('intact.flow.then-b', 'then B: SSO without a password (auth host already holds the Kratos session); B mints for W',
      { passwordEntered: false, lands: 'tenant-b app', exchange: 200 }, { passwordEntered: thenB.passwordEntered, redirects: thenB.redirects, navigations: thenB.navigations, lands: thenB.app && thenB.app.tenant, exchange: xbW.status },
      !thenB.passwordEntered && thenB.app && thenB.app.tenant === 'tenant-b' && xbW.status === 200);

    // --- U: happy path on A ---
    const cu = await browser.newContext();
    const pu = await cu.newPage();
    const nu = B_.navRecorder(pu);
    const hA = await B_.visit(pu, nu, `${OA}/`, U);
    const sess = (await cu.cookies()).find((c) => c.name === 'ory_kratos_session');
    const xa = await B_.sameOriginFetch(pu, OA, '/api/nsjwt/exchange');
    const va = xa.body && xa.body.token ? await verify(A, xa.body.token) : { status: 0 };
    rec.check('intact.happy-a', "happy path on A: host-only Kratos cookie on the auth host; A gets its own session and mints from it",
      { kratosCookieDomain: H.env.AUTH_HOST, lands: 'tenant-a', exchange: 200, via: 'tenant-session', verify: 200 },
      { kratosCookieDomain: sess && sess.domain, lands: hA.app && hA.app.tenant, exchange: xa.status, via: xa.body && xa.body.via, verify: va.status },
      sess && sess.domain === H.env.AUTH_HOST && hA.app && hA.app.tenant === 'tenant-a' && xa.status === 200 && xa.body.via === 'tenant-session' && va.status === 200);

    // --- what a tenant backend receives ---
    await pu.goto(`${OA}/api/echo`); const ea = JSON.parse(await pu.locator('body').innerText());
    await pu.goto(`${OB}/api/echo`); const eb = JSON.parse(await pu.locator('body').innerText());
    rec.note('backendReceives', { A: { cookieNames: ea.cookieNames, headerNames: ea.headerNames }, B: { cookieNames: eb.cookieNames, headerNames: eb.headerNames } });
    rec.check('intact.backend-receives', "tenant backends never receive the Kratos cookie: A receives only its own tenant session cookie, B (no session there) receives no cookie",
      { A: ['ns_session'], B: [] }, { A: ea.cookieNames, B: eb.cookieNames }, ea.cookieNames.join() === 'ns_session' && eb.cookieNames.length === 0);

    // --- replay: A's own tenant session cookie, sent by a non-browser client to B and to A ---
    {
      const nsA = (await cu.cookies()).find((c) => c.name === 'ns_session' && c.domain === A);
      const atB = await H.req(B, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ns_session=${nsA.value}` } });
      const atA = await H.req(A, 'POST', '/api/nsjwt/exchange', { headers: { cookie: `ns_session=${nsA.value}` } });
      rec.check('intact.replay.a-session-at-b', "A's tenant session cookie replayed to B: not a session there (sessions are keyed by tenant); control: the same value replayed to A mints",
        { atB: { status: 401, error: 'no-credential' }, atA: 200 }, { atB: { status: atB.status, error: atB.body && atB.body.error }, atA: atA.status },
        atB.status === 401 && atB.body.error === 'no-credential' && atA.status === 200);
    }

    // --- U not a member of B: refused at the auth host ---
    const toB = await B_.visit(pu, nu, `${OB}/`, null);
    const bState = ((await cu.cookies()).find((c) => c.name === 'ns_handoff_state' && c.domain === B) || {}).value;
    rec.check('intact.b-not-member', 'U on B: B redirects to the auth host, which refuses (403 not-a-member) and does not redirect back; no password asked',
      { finalHost: H.env.AUTH_HOST, error: 'not-a-member', passwordEntered: false }, { finalUrl: toB.finalUrl, body: toB.body, redirects: toB.redirects, passwordEntered: toB.passwordEntered },
      toB.finalUrl.startsWith(`${H.env.AUTH_HOST}:${P}/exchange`) && /not-a-member/.test(toB.body) && !toB.passwordEntered);

    // --- code bound to tenant: A's code at B ---
    {
      const ok = await liveness('intact.bind', sess.value, U);
      // browser path: A's code delivered to B's callback with B's own state cookie value
      const ia = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, bState);
      await pu.goto(`${OB}/handoff/callback?code=${ia.code}&state=${bState}`);
      const atB = JSON.parse(await pu.locator('body').innerText());
      // server-to-server: B's backend redeems A's code with A's state (both are in the callback URL)
      const st = STATE();
      const ia2 = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st);
      const rb = await redeem('tenant-b', ia2.code, st);
      const raAfter = await redeem('tenant-a', ia2.code, st);
      rec.check('intact.code-for-a-at-b', "a code issued for A redeemed at B: refused wrong-tenant, through B's callback and server-to-server; the attempt burns the code (A's own redemption afterwards: code-used)",
        { viaBCallback: { status: 400, error: 'wrong-tenant' }, serverToServer: { status: 400, error: 'wrong-tenant' }, aAfter: 'code-used' },
        { viaBCallback: { status: atB.error ? 400 : 200, error: atB.error, at: atB.at }, serverToServer: { status: rb.status, error: rb.error }, aAfter: raAfter.error },
        atB.error === 'wrong-tenant' && rb.status === 400 && rb.error === 'wrong-tenant' && raAfter.error === 'code-used');
      void ok;
    }
    // --- single use ---
    {
      const st = STATE();
      const i = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st);
      const r1 = await redeem('tenant-a', i.code, st);
      const r2 = await redeem('tenant-a', i.code, st);
      rec.check('intact.twice', 'a code redeemed twice: the first succeeds, the second is refused code-used', { first: 200, second: { status: 400, error: 'code-used' } },
        { first: r1.status, second: { status: r2.status, error: r2.error } }, r1.status === 200 && r2.status === 400 && r2.error === 'code-used');
    }
    // --- return_to ---
    {
      const cases = [
        ['own-tenant', `${OA}/handoff/callback`, 302],
        ['sibling-tenant', `${OB}/handoff/callback`, 400],
        ['unregistered-slug', `http://tenant-zz.user-content.apex.test:${P}/handoff/callback`, 400],
        ['foreign', 'http://evil.test/cb', 400],
        ['suffix-append', `http://tenant-a.user-content.apex.test.evil.test:${P}/cb`, 400],
        ['userinfo', `http://tenant-a.user-content.apex.test:${P}@evil.test/cb`, 400],
        ['other-port', 'http://tenant-a.user-content.apex.test:9999/cb', 400],
        ['https-scheme', 'https://tenant-a.user-content.apex.test:44480/cb', 400],
        ['scheme-relative', '//evil.test/cb', 400],
        ['own-tenant-again', `${OA}/handoff/callback`, 302]
      ];
      const got = [];
      for (const [name, rt, want] of cases) {
        const r = await issue(sess.value, 'tenant-a', rt, STATE());
        got.push({ name, want, status: r.status, error: r.error || null, locHost: r.locHost });
      }
      rec.note('returnTo', got);
      rec.check('intact.return-to', "return_to must be on A's registered origin: own origin redirected (first and last); sibling tenant, unregistered slug, foreign host and the tricks refused at the auth host",
        cases.map(([n, , w]) => `${n}:${w}`), got.map((g) => `${g.name}:${g.status}${g.error ? ' ' + g.error : ''}`),
        got.every((g) => g.status === g.want && (g.want === 302 ? g.locHost === `${A}:${P}` : g.error === 'return-to-not-tenant-origin')));
    }
    // --- state mismatch ---
    {
      const st = STATE();
      const i = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st);
      await pu.goto(`${OA}/handoff/callback?code=${i.code}&state=${STATE()}`);
      const atA = JSON.parse(await pu.locator('body').innerText());
      const wrong = await redeem('tenant-a', (await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st)).code, STATE());
      const stillGood = await redeem('tenant-a', i.code, st);
      rec.check('intact.state-mismatch', "state mismatch: A's callback refuses a state that is not its state cookie (before redeeming: the code stays redeemable with the right state); the auth host refuses a redemption whose state is not the code's",
        { atTenant: 'tenant-state-mismatch', atAuthHost: { status: 400, error: 'state-mismatch' }, codeStillRedeemable: 200 },
        { atTenant: atA.error, atAuthHost: { status: wrong.status, error: wrong.error }, codeStillRedeemable: stillGood.status },
        atA.error === 'tenant-state-mismatch' && wrong.status === 400 && wrong.error === 'state-mismatch' && stillGood.status === 200);
    }
    // --- cross-origin from B ---
    {
      // (i) the browser holds an A tenant session (U, after the happy path)
      rec.note('cookieJarU', await B_.jarSummary(cu));
      await reset();
      const cr = await B_.crossOriginFetch(pu, OB, `${OA}/api/nsjwt/exchange`);
      let ev = await events();
      const atA = ev.nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k));
      rec.note('crossOriginWithTenantSession', { events: atA.map((e) => ({ k: e.k, via: e.via || null, why: e.why || null, origin: e.origin })), scriptCouldRead: cr.readable });
      rec.check('intact.cross-origin.with-a-session', "brief's prediction: a script on B's origin POSTing to A with credentials has nothing to send and A mints nothing",
        { reachedAWithCredential: false, minted: false },
        { reachedAWithCredential: atA.some((e) => e.k === 'minted'), minted: atA.some((e) => e.k === 'minted'), via: (atA.find((e) => e.k === 'minted') || {}).via, originSeen: (atA.find((e) => e.k === 'minted') || {}).origin, scriptCouldRead: cr.readable },
        !atA.some((e) => e.k === 'minted'));
      await reset();
      const fm = await B_.crossOriginForm(pu, OB, `${OA}/api/nsjwt/exchange`);
      ev = await events();
      const atAf = ev.nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k));
      rec.check('intact.cross-origin.form-with-a-session', "brief's prediction, as a form POST from B's origin (a navigation): nothing sent, nothing minted",
        { minted: false }, { status: fm.status, minted: atAf.some((e) => e.k === 'minted'), via: (atAf.find((e) => e.k === 'minted') || {}).via, originSeen: (atAf.find((e) => e.k === 'minted') || {}).origin },
        !atAf.some((e) => e.k === 'minted'));
      // (ii) the browser holds only the Kratos session (fresh context, logged in at the auth host)
      const cf = await browser.newContext();
      const pf = await cf.newPage();
      await pf.goto(`${B_.AUTH}/self-service/login/browser`);
      await pf.fill('input[name=identifier]', U.email); await pf.fill('input[name=password]', U.password);
      await Promise.all([pf.waitForLoadState('load'), pf.click('button[name=method][value=password]')]);
      await reset();
      const cr2 = await B_.crossOriginFetch(pf, OB, `${OA}/api/nsjwt/exchange`);
      const ev2 = (await events()).nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k));
      const hasKratos = (await cf.cookies()).some((c) => c.name === 'ory_kratos_session');
      rec.check('intact.cross-origin.kratos-only', "with only the Kratos session in the browser (host-only on the auth host), B's script has nothing to send: A refuses no-credential",
        { kratosSessionInBrowser: true, atA: 'no-credential', minted: false }, { kratosSessionInBrowser: hasKratos, atA: ev2.map((e) => e.why || e.k).join(), minted: ev2.some((e) => e.k === 'minted'), scriptCouldRead: cr2.readable },
        hasKratos && ev2.length === 1 && ev2[0].why === 'no-credential');
      await cf.close();
    }
    // --- control: U added to B ---
    {
      await H.addMember(pool, tb, U.id);
      const v2 = await B_.visit(pu, nu, `${OB}/`, null);
      const x2 = await B_.sameOriginFetch(pu, OB, '/api/nsjwt/exchange');
      await H.removeMember(pool, tb, U.id);
      const x3 = await B_.sameOriginFetch(pu, OB, '/api/nsjwt/exchange');
      rec.check('intact.control.b-member', "control: U added to B, the same browser reaches B's app without a password and B mints; U removed again, B's exchange refuses (B's tenant session stays, its membership check does not)",
        { lands: 'tenant-b', passwordEntered: false, exchange: 200, removed: 403 }, { lands: v2.app && v2.app.tenant, passwordEntered: v2.passwordEntered, redirects: v2.redirects, exchange: x2.status, removed: x3.status, removedError: x3.body && x3.body.error },
        v2.app && v2.app.tenant === 'tenant-b' && !v2.passwordEntered && x2.status === 200 && x3.status === 403);
    }
    await cu.close();

    // --- logout (W: sessions on A and B) ---
    {
      const before = await B_.sameOriginFetch(pw, OA, '/api/nsjwt/exchange');
      const lo = await B_.kratosLogout(pw);
      const homeA = await B_.visit(pw, nw, `${OA}/`, null);
      const homeB = await B_.visit(pw, nw, `${OB}/`, null);
      const after = await B_.sameOriginFetch(pw, OA, '/api/nsjwt/exchange');
      const old = await verify(A, before.body.token);
      const coldC = await B_.visit(pw, nw, `${OC}/`, null);
      rec.check('intact.logout', "Kratos browser logout at the auth host ends the Kratos session only: A's and B's own tenant sessions survive (apps load, A still mints NEW tokens), a token minted before logout verifies; a tenant with no session yet (C) now asks for the password",
        { whoamiAfter: '401', aApp: true, bApp: true, aMintsAfterLogout: 200, tokenMintedBefore: 200, coldCAsksPassword: true },
        { whoamiAfter: lo.whoamiAfter, aApp: !!homeA.app, bApp: !!homeB.app, aMintsAfterLogout: after.status, tokenMintedBefore: old.status, coldCAsksPassword: !!coldC.loginFormShown, coldCRedirects: coldC.redirects },
        lo.whoamiAfter === '401' && !!homeA.app && !!homeB.app && after.status === 200 && old.status === 200 && coldC.loginFormShown);
    }
    await cw.close();
    await srv.stop();

    // ================= expiry =================
    srv = await H.startServer('', 'cookie-handoff-expiry', Object.assign({ HANDOFF_CODE_TTL_MS: '1500' }, MODE));
    {
      await liveness('expiry', sess.value, U);
      const st = STATE();
      const i = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st);
      await H.sleep(2200);
      const r = await redeem('tenant-a', i.code, st);
      rec.check('expiry.expired', 'a code redeemed after its TTL (1500 ms in this phase, 2200 ms wait) is refused code-expired', { status: 400, error: 'code-expired' }, { status: r.status, error: r.error }, r.status === 400 && r.error === 'code-expired');
    }
    await srv.stop();

    // ================= diagnostic: tenant session cookie SameSite=Strict =================
    // Characterises the cross-origin mismatch above; changes no default. Tenants are same-site
    // (apex.test; .test is not on the Public Suffix List), so Strict is predicted to change nothing.
    srv = await H.startServer('', 'cookie-handoff-strict', Object.assign({ HANDOFF_SESSION_SAMESITE: 'Strict' }, MODE));
    {
      await liveness('diag.strict', sess.value, U);
      const cs = await browser.newContext();
      const ps = await cs.newPage();
      const ns = B_.navRecorder(ps);
      const v = await B_.visit(ps, ns, `${OA}/`, U);
      const jar = (await cs.cookies()).find((c) => c.name === 'ns_session');
      await reset();
      const cr = await B_.crossOriginFetch(ps, OB, `${OA}/api/nsjwt/exchange`);
      const evs = (await events()).nsjwt.events.filter((e) => e.tenant === 'tenant-a' && /minted|exchange-deny/.test(e.k));
      const m = evs.find((e) => e.k === 'minted');
      rec.check('diag.strict.cross-origin', "diagnostic: with the tenant session cookie SameSite=Strict, B's script POSTing to A still sends it (same site) and A mints",
        { cookieSameSite: 'Strict', minted: true, via: 'tenant-session', originSeen: OB }, { lands: v.app && v.app.tenant, cookieSameSite: jar && jar.sameSite, minted: !!m, via: m && m.via, originSeen: m && m.origin, scriptCouldRead: cr.readable },
        jar && jar.sameSite === 'Strict' && !!m && m.via === 'tenant-session' && m.origin === OB);
      await cs.close();
    }
    await srv.stop();

    // ================= break: no-tenant-binding =================
    srv = await H.startServer('', 'cookie-handoff-no-tenant-binding', Object.assign({ HANDOFF_BREAK: 'no-tenant-binding' }, MODE));
    {
      await liveness('break.no-tenant-binding', sess.value, U);
      const st = STATE();
      const i = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st);
      const r = await redeem('tenant-b', i.code, st);
      const v = r.token ? await verify(B, r.token) : { status: 0, body: {} };
      const p = r.token ? jwt.decode(r.token) : {};
      rec.check('break.no-tenant-binding.red', "BREAK no-tenant-binding: B's backend redeems A's code and gets a B token for U, who is not a member of B; B accepts it",
        { redeem: 200, tenant: 'tenant-b', sub: 'U', verifyOnB: 200 }, { redeem: r.status, error: r.error, tenant: p.tenant, sub: p.sub === U.id ? 'U' : p.sub, verifyOnB: v.status },
        r.status === 200 && p.tenant === 'tenant-b' && p.sub === U.id && v.status === 200);
    }
    await srv.stop();

    // ================= break: no-single-use =================
    srv = await H.startServer('', 'cookie-handoff-no-single-use', Object.assign({ HANDOFF_BREAK: 'no-single-use' }, MODE));
    {
      await liveness('break.no-single-use', sess.value, U);
      const st = STATE();
      const i = await issue(sess.value, 'tenant-a', `${OA}/handoff/callback`, st);
      const r1 = await redeem('tenant-a', i.code, st);
      const r2 = await redeem('tenant-a', i.code, st);
      const r3 = await redeem('tenant-a', i.code, st);
      rec.check('break.no-single-use.red', 'BREAK no-single-use: the same code redeems again and again, each time for an A token (identical tokens when minted in the same second: same claims, deterministic HS256)', { first: 200, second: 200, third: 200 },
        { first: r1.status, second: r2.status, third: r3.status, distinctTokens: new Set([r1.token, r2.token, r3.token]).size }, r1.status === 200 && r2.status === 200 && r3.status === 200);
    }
    await srv.stop();

    // ================= break: no-return-to-check =================
    srv = await H.startServer('', 'cookie-handoff-no-return-to-check', Object.assign({ HANDOFF_BREAK: 'no-return-to-check' }, MODE));
    {
      await liveness('break.no-return-to-check', sess.value, U);
      const f = await issue(sess.value, 'tenant-a', 'http://evil.test/cb', STATE());
      const s = await issue(sess.value, 'tenant-a', `${OB}/handoff/callback`, STATE());
      rec.check('break.no-return-to-check.red', "BREAK no-return-to-check: the auth host redirects to a foreign host and to a sibling tenant, each carrying a live A code (an open redirect that leaks codes)",
        { foreign: { status: 302, host: 'evil.test', code: true }, sibling: { status: 302, host: `${B}:${P}`, code: true } },
        { foreign: { status: f.status, host: f.locHost, code: !!f.code }, sibling: { status: s.status, host: s.locHost, code: !!s.code } },
        f.status === 302 && f.locHost === 'evil.test' && !!f.code && s.status === 302 && s.locHost === `${B}:${P}` && !!s.code);
    }
  } finally {
    await browser.close();
    await srv.stop().catch(() => {});
    await pool.end();
  }
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
