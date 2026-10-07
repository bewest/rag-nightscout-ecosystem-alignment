#!/usr/bin/env node
'use strict';
/*
 * probes/hydra.js - one Hydra, one OAuth client per tenant: can tenant A's client obtain
 * consent or tokens usable at B?
 *
 * Kratos must be in the host-only cookie configuration (the default compose file).
 * Clients: client-A (redirect + audience on tenant-a), client-B (same on tenant-b).
 * U is a member of BOTH tenants here, so the only thing that can stop A's token on B is the
 * client binding - membership is held constant on purpose. Each negative is paired with the
 * positive on the identical setup, and the binding is broken on purpose at the end.
 */
const crypto = require('crypto');
const { chromium } = require('playwright');
const H = require('../lib/harness');

const rec = H.recorder('hydra');
const P = H.env.LAB_PORT;
const A = H.env.tenantHost('tenant-a');
const B = H.env.tenantHost('tenant-b');
const OA = `http://${A}:${P}`;
const OB = `http://${B}:${P}`;
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';

const { mkClient, authUrl, firstHop, codeFlow } = require('../lib/oauth');

const decode = (t, i) => JSON.parse(Buffer.from(t.split('.')[i], 'base64url').toString());
const bearer = (host, tok) => H.req(host, 'POST', '/api/nsjwt/exchange', { headers: { authorization: `Bearer ${tok}` } });

async function main () {
  const pool = H.db();
  await H.ensureSchema(pool);
  const cA = await mkClient(OA, 'tenant-a');
  const cB = await mkClient(OB, 'tenant-b');
  const ta = await H.tenant(pool, 'tenant-a', cA.client_id);
  const tb = await H.tenant(pool, 'tenant-b', cB.client_id);
  const U = await H.createIdentity('u');
  await H.addMember(pool, ta, U.id);
  await H.addMember(pool, tb, U.id);
  rec.note('fixture', { U: 'member of tenant-a AND tenant-b (client binding is the only variable)' });

  const srv = await H.startServer('', 'hydra-intact');
  // H1/H7 - redirect and audience cross-use at the authorize endpoint (configuration)
  const okA = await firstHop(authUrl(cA, OA, OA));
  const xRedirect = await firstHop(authUrl(cA, OB, OA));
  const xAud = await firstHop(authUrl(cA, OA, OB));
  rec.check('authorize.positive', "client-A with A's redirect and A's audience is handed to the login app", { toLogin: true }, okA, okA.toLogin);
  rec.check('authorize.redirect-cross', "client-A asking to redirect to B's callback is refused by Hydra (exact redirect_uri match)", { toLogin: false, error: 'invalid_request', locationHostIsNot: B }, xRedirect, !xRedirect.toLogin && !!xRedirect.error && xRedirect.locationHost !== B);
  rec.check('authorize.audience-cross', "client-A asking for B's audience is refused by Hydra (audience allow-list per client)", { toLogin: false, error: 'invalid_request' }, xAud, !xAud.toLogin && !!xAud.error);

  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--host-resolver-rules=MAP *.apex.test 127.0.0.1'] });
  const page = await (await browser.newContext()).newPage();
  page.__who = U;
  let tokA, tokB;
  try {
    await H.req(H.env.CONTROL_HOST, 'GET', '/reset');
    const fa = await codeFlow(page, cA, OA);
    rec.check('flow.a', 'browser authorization-code flow for client-A completes through Kratos login and lands on A', { status: 200, callbackHost: A }, { status: fa.status, callbackHost: fa.callbackHost }, fa.status === 200 && fa.callbackHost === A);
    tokA = fa.body.access_token;
    const fb = await codeFlow(page, cB, OB);
    rec.check('flow.b', 'the same browser then completes client-B on B', { status: 200, callbackHost: B }, { status: fb.status, callbackHost: fb.callbackHost }, fb.status === 200 && fb.callbackHost === B);
    tokB = fb.body.access_token;
    const lab = (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body.lab;
    // the login app sees A's challenge twice (before and after the Kratos login), so keep the last per client
    const lastBy = (k) => ['A', 'B'].map((c) => lab.filter((e) => e.k === k && (e.client_id === cA.client_id ? 'A' : 'B') === c).pop()).filter(Boolean).map((e) => ({ client: e.client_id === cA.client_id ? 'A' : 'B', skip: e.skip }));
    const logins = lastBy('hydra-login');
    const consents = lab.filter((e) => e.k === 'hydra-consent').map((e) => ({ client: e.client_id === cA.client_id ? 'A' : 'B', skip: e.skip }));
    rec.check('sso.login-skip', "Hydra's login session is cohort-wide: client-B's login request arrives with skip=true after logging in for client-A", { logins: [{ client: 'A', skip: false }, { client: 'B', skip: true }] }, { logins }, logins.length === 2 && logins[0].skip === false && logins[1].client === 'B' && logins[1].skip === true);
    rec.check('consent.per-client', 'consent is remembered per client: client-B gets its own consent request (skip=false)', { consents: [{ client: 'A', skip: false }, { client: 'B', skip: false }] }, { consents }, consents.length === 2 && consents[1].client === 'B' && consents[1].skip === false);
    // second run of client-A: remembered consent should skip
    await H.req(H.env.CONTROL_HOST, 'GET', '/reset');
    await codeFlow(page, cA, OA);
    const again = (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body.lab.filter((e) => e.k === 'hydra-consent');
    rec.check('consent.remembered', 'control: a second client-A flow sees its remembered consent (skip=true), so skip=false for B above is the per-client boundary, not a consent app that never remembers', true, again.length === 1 && again[0].skip, again.length === 1 && again[0].skip === true);

    // NRG registered its clients with subject_type: pairwise
    const pw = await H.hydraAdmin('POST', '/admin/clients', { client_name: 'pairwise', redirect_uris: [`${OA}/oauth/callback`], subject_type: 'pairwise' });
    rec.check('pairwise.refused-under-jwt', "with JWT access tokens (this config), Hydra refuses a pairwise client - NRG's client shape (probes/hydra-pairwise.js runs the opaque variant)",
      { status: 400, error: 'invalid_client_metadata' }, { status: pw.status, error: pw.body && pw.body.error }, pw.status === 400 && pw.body.error === 'invalid_client_metadata');
    if (pw.status === 201) await H.hydraAdmin('DELETE', `/admin/clients/${pw.body.client_id}`);

    const ha = decode(tokA, 0); const pa = decode(tokA, 1); const hb = decode(tokB, 0); const pb = decode(tokB, 1);
    rec.note('tokens', { A: { kid: ha.kid, iss: pa.iss, aud: pa.aud, client_id: pa.client_id, sub_is_kratos_id: pa.sub === U.id }, B: { kid: hb.kid, iss: pb.iss, aud: pb.aud, client_id: pb.client_id, sub_is_kratos_id: pb.sub === U.id } });
    rec.check('one-issuer', "both tenants' access tokens carry the same issuer and the same signing key id (OSS Hydra: one issuer, one key set)", { sameIss: true, sameKid: true }, { sameIss: pa.iss === pb.iss, sameKid: ha.kid === hb.kid }, pa.iss === pb.iss && ha.kid === hb.kid);
    const jwks = await fetch(`${H.env.HYDRA_PUBLIC}/.well-known/jwks.json`).then((r) => r.json());
    const key = crypto.createPublicKey({ key: jwks.keys.find((k) => k.kid === ha.kid), format: 'jwk' });
    const [h64, p64, s64] = tokA.split('.');
    const sigOk = crypto.verify('RSA-SHA256', Buffer.from(`${h64}.${p64}`), key, Buffer.from(s64, 'base64url'));
    rec.check('jwks-verifies-anywhere', "A's Hydra token verifies against the one JWKS any tenant would fetch: a signature check alone cannot separate tenants (D14 needs our own mint)", true, sigOk, sigOk === true);
    rec.check('aud-scoped', "Hydra puts the client's audience in the token: A's token names A's origin and not B's", { aud: [OA] }, { aud: pa.aud }, Array.isArray(pa.aud) && pa.aud.includes(OA) && !pa.aud.includes(OB));

    // H3/H4 - the nsjwt exchange with a Hydra bearer token, client binding intact
    const ea = await bearer(A, tokA);
    const eb = await bearer(B, tokA);
    const ebb = await bearer(B, tokB);
    rec.check('exchange.a', "positive: A's Hydra token exchanges on A", { status: 200, via: 'hydra-access-token' }, { status: ea.status, via: ea.body && ea.body.via }, ea.status === 200);
    rec.check('exchange.a-token-at-b', "probe: A's Hydra token on B is refused because it was issued to another client (U IS a member of B)", { status: 401, error: 'hydra-token-other-client' }, { status: eb.status, error: eb.body && eb.body.error }, eb.status === 401 && eb.body.error === 'hydra-token-other-client');
    rec.check('exchange.b-own', "control in the same run: B's own token exchanges on B", 200, ebb.status, ebb.status === 200);
  } finally {
    await browser.close();
    await srv.stop();
  }

  // break: remove the client binding; introspection alone says active:true for A's token
  const srv2 = await H.startServer('skip-client-check', 'hydra-skip-client-check');
  const live = await bearer(A, tokA);
  const red = await bearer(B, tokA);
  rec.check('break.skip-client-check.live', 'liveness in the break run', 200, live.status, live.status === 200);
  rec.check('break.skip-client-check.red', "BREAK skip-client-check: the probe goes red - A's Hydra token mints a B Nightscout token", { status: 200, tenant: 'tenant-b' }, { status: red.status, tenant: red.body && red.body.tenant }, red.status === 200 && red.body.tenant === 'tenant-b');
  await H.removeMember(pool, tb, U.id);
  const red2 = await bearer(B, tokA);
  rec.check('break.skip-client-check.membership', '...and with U removed from B the membership check still refuses (the two defences are independent)', 403, red2.status, red2.status === 403);
  await srv2.stop();

  await H.hydraAdmin('DELETE', `/admin/clients/${cA.client_id}`);
  await H.hydraAdmin('DELETE', `/admin/clients/${cB.client_id}`);
  await pool.end();
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
