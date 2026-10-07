#!/usr/bin/env node
'use strict';
/*
 * probes/nrg-port.js - does nightscout-roles-gateway's decision pipeline still work against
 * Kratos 1.x / Hydra 2.x? Run via probes/nrg-port.sh, which prepares nrg-run/ (an unmodified copy).
 *
 * Part 1, SDK level: NRG's own @ory/kratos-client 0.9.0-alpha.3 and @ory/hydra-client 1.11.8,
 *   loaded from nrg-run/node_modules, against this lab's servers.
 * Part 2, pipeline level: NRG's server (node 22 container, host network, :44486), unmodified,
 *   with KRATOS_API/HYDRA_API pointed at the lab. Two tenants (sites nrg-a, nrg-b) in NRG's own
 *   tables; U joined to nrg-a only, V to nrg-b only; the warden called with REAL Kratos 1.x cookies.
 * Positive controls: the portal route (no Kratos in the chain) on the identical fixtures, and V on B.
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const H = require('../lib/harness');

const NRG = path.join(H.ROOT, 'nrg-run');
const rec = H.recorder('nrg-port');
const NODE_IMAGE = process.env.NODE_IMAGE || 'node:22-bookworm-slim';
const NRG_PORT = 44486;
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const nrequire = (m) => require(path.join(NRG, 'node_modules', m));

function startNrg (hydraApi, label) {
  execSync('docker rm -f ory-proof-nrg >/dev/null 2>&1 || true');
  execSync(['docker run -d --name ory-proof-nrg --network host', `--env-file ${NRG}/.lab.env`,
    `-e PORT=${NRG_PORT} -e BIND_IFACE=127.0.0.1 -e KRATOS_API=http://127.0.0.1:44433 -e HYDRA_API=${hydraApi}`,
    `-e GATEWAY_APEX=apex.test -e GATEWAY_WWW=http://auth.apex.test:44480 -e SELF_API=http://127.0.0.1:${NRG_PORT}`,
    `-v ${NRG}:/app -w /app ${NODE_IMAGE} node server.js`].join(' '));
  rec.note(`nrg.${label}`, { HYDRA_API: hydraApi });
}
async function nrgUp () {
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`http://127.0.0.1:${NRG_PORT}/warden/v1/active/backend/for/does-not-exist`); return r.status; } catch (e) { await H.sleep(200); }
  }
  throw new Error('NRG did not come up');
}
const warden = async (name, cookie) => (await fetch(`http://127.0.0.1:${NRG_PORT}/warden/v1/active/backend/for/${name}`, { headers: cookie ? { cookie } : {} })).status;
// the error NRG logged for a registration request (bunyan audit line), so a 500 is red for a KNOWN reason
function loggedError (label, name) {
  const log = execSync(`docker logs ory-proof-nrg 2>&1 || true`).toString().split('\n');
  fs.writeFileSync(path.join(H.ROOT, 'results', 'raw', `nrg-server-${label}.log`), log.join('\n'));
  for (const l of log) {
    if (!l.includes(`registrations/${name}`)) continue;
    try { const d = JSON.parse(l); if (d.err) return d.err.code || d.err.message; } catch (e) { /* not json */ }
  }
  return null;
}
const portal = async (subject, name) => (await fetch(`http://127.0.0.1:${NRG_PORT}/warden/v1/portal/${subject}/backend/for/${name}`)).status;

async function browserCookie (browser, who) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`http://${H.env.AUTH_HOST}:${H.env.LAB_PORT}/self-service/login/browser`);
  await page.fill('input[name=identifier]', who.email);
  await page.fill('input[name=password]', who.password);
  await Promise.all([page.waitForLoadState('load'), page.click('button[name=method][value=password]')]);
  const c = (await ctx.cookies()).find((x) => x.name === 'ory_kratos_session');
  await ctx.close();
  return c && `ory_kratos_session=${c.value}`;
}

async function fixtures (knex, U, V) {
  const fx = require(path.join(NRG, 'test', 'setup', 'fixtures'));
  for (const t of ['registered_sites', 'group_definitions', 'nightscout_authenticity_records']) await knex.raw(`TRUNCATE TABLE ${t} CASCADE`);
  const mk = async (name, who) => {
    const site = await fx.createSite(knex, { expected_name: name, upstream_origin: `https://${name}.example.test`, owner_ref: `owner-${name}`, is_enabled: true, require_identities: true });
    const group = await fx.createGroup(knex, { owner_ref: `owner-${name}`, nickname: 'viewers' });
    const spec = await fx.createInclusionSpec(knex, { group_definition_id: group.id, identity_type: 'email', identity_spec: who.email });
    const policy = await fx.createPolicy(knex, { site_id: site.id, group_definition_id: group.id, policy_type: 'default', policy_spec: 'allow' });
    await fx.createJoinedGroup(knex, { subject: who.id, expected_name: name, group_id: group.id, group_spec_id: spec.id, policy_id: policy.id });
  };
  await mk('nrg-a', U);
  await mk('nrg-b', V);
}

async function main () {
  rec.note('nrg_commit', fs.readFileSync(path.join(NRG, '.nrg-commit'), 'utf8').trim());
  const Kratos = nrequire('@ory/kratos-client');
  const Hydra = nrequire('@ory/hydra-client');
  rec.note('sdk', { kratos: nrequire('@ory/kratos-client/package.json').version, hydra: nrequire('@ory/hydra-client/package.json').version });
  const U = await H.createIdentity('u');
  const V = await H.createIdentity('v');

  // ---- part 1: SDK level ----
  rec.check('sdk.kratos.class', 'NRG constructs V0alpha2Api (lib/privy/index.js:20): it exists in the SDK NRG pins', true, typeof Kratos.V0alpha2Api === 'function', typeof Kratos.V0alpha2Api === 'function');
  const pub = new Kratos.V0alpha2Api(new Kratos.Configuration({ basePath: H.env.KRATOS_PUBLIC }));
  const adm = new Kratos.V0alpha2Api(new Kratos.Configuration({ basePath: H.env.KRATOS_ADMIN }));
  const s = await H.nativeLogin(U);
  const ts = await pub.toSession(s.token).then((r) => ({ status: r.status, same: r.data.identity.id === U.id, email: r.data.identity.traits.email === U.email })).catch((e) => ({ error: e.message }));
  rec.check('sdk.kratos.toSession', 'toSession (GET /sessions/whoami) from SDK 0.9.0-alpha.3 against Kratos 1.x returns the identity with traits.email', { status: 200, same: true, email: true }, ts, ts.status === 200 && ts.same && ts.email);
  const ga = await adm.adminGetIdentity(U.id).then((r) => ({ status: r.status })).catch((e) => ({ error: e.message }));
  rec.check('sdk.kratos.adminGetIdentity.admin', 'adminGetIdentity against the ADMIN port works', { status: 200 }, ga, ga.status === 200);
  const gp = await pub.adminGetIdentity(U.id).then((r) => ({ status: r.status })).catch((e) => ({ error: e.message.slice(0, 80) }));
  rec.check('sdk.kratos.adminGetIdentity.public', "adminGetIdentity against the PUBLIC port, as NRG does (one KRATOS_API for both): Kratos 1.x redirects /admin/* to serve.admin.base_url, which must then resolve from NRG", { error: 'getaddrinfo ... kratos' }, gp, !!gp.error && /kratos/.test(gp.error));

  const legacy = new Hydra.AdminApi(new Hydra.Configuration({ basePath: H.env.HYDRA_ADMIN }));
  const suffixed = new Hydra.AdminApi(new Hydra.Configuration({ basePath: `${H.env.HYDRA_ADMIN}/admin` }));
  const plain = { client_name: 'nrg-probe', redirect_uris: ['http://auth.apex.test:44480/invitations/x/rsvp'] };
  const c1 = await legacy.createOAuth2Client(plain).then((r) => ({ status: r.status, id: r.data.client_id })).catch((e) => ({ error: e.code || e.message, url: e.config && e.config.url }));
  rec.check('sdk.hydra.legacy-path', "hydra-client 1.11.8 POSTs /clients; Hydra 2.x answers 307 to /admin/clients on its OWN listen address (localhost:4445), unreachable through a mapped port", { error: 'ECONNREFUSED' }, c1, c1.error === 'ECONNREFUSED');
  if (c1.id) await suffixed.deleteOAuth2Client(c1.id).catch(() => null); // v26 serves the legacy path directly
  const c2 = await suffixed.createOAuth2Client(plain).then((r) => ({ status: r.status, id: r.data.client_id })).catch((e) => ({ error: e.code || e.message }));
  rec.check('sdk.hydra.admin-suffix', "the same SDK with basePath + '/admin' creates the client (status 201): the 1.x request shape is accepted by 2.x", { status: 201 }, { status: c2.status }, c2.status === 201);
  const d2 = c2.id ? await suffixed.deleteOAuth2Client(c2.id).then((r) => r.status).catch((e) => e.message) : null;
  rec.check('sdk.hydra.delete', 'deleteOAuth2Client through the suffixed basePath', 204, d2, d2 === 204);
  const nrgShape = Object.assign({}, plain, { subject_type: 'pairwise', sector_identifier_url: `http://127.0.0.1:${NRG_PORT}/api/v1/owner/o/sites/x/oauth/sector_identifier`, token_endpoint_auth_method: 'client_secret_post', scope: 'openid email offline profile rsvp' });
  const c3 = await suffixed.createOAuth2Client(nrgShape).then((r) => ({ status: r.status })).catch((e) => ({ status: e.response && e.response.status, error: e.response && e.response.data && e.response.data.error }));
  rec.check('sdk.hydra.nrg-client-shape', "NRG's client shape (subject_type pairwise + sector_identifier_url) is refused by this Hydra (JWT access tokens)", { status: 400, error: 'invalid_client_metadata' }, c3, c3.status === 400);

  // ---- part 2: pipeline level ----
  const knex = nrequire('knex')({ client: 'pg', connection: fs.readFileSync(path.join(NRG, '.lab.env'), 'utf8').match(/KNEX_CONNECT=(.*)/)[1] });
  const mig = await knex('knex_migrations').count('* as n');
  rec.check('nrg.migrations', "NRG's 31 knex migrations apply cleanly to Postgres 16", 31, Number(mig[0].n), Number(mig[0].n) === 31);
  await fixtures(knex, U, V);

  const lab = await H.startServer('', 'nrg-port');
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--host-resolver-rules=MAP *.apex.test 127.0.0.1'] });
  const cu = await browserCookie(browser, U);
  const cv = await browserCookie(browser, V);
  await browser.close();
  await lab.stop();
  rec.check('nrg.cookies', 'real Kratos 1.x browser sessions for U and V', true, !!cu && !!cv, !!cu && !!cv);

  startNrg(H.env.HYDRA_ADMIN, 'as-documented');
  try {
    await nrgUp();
    const pa = await portal(U.id, 'nrg-a');
    rec.check('nrg.portal.control', 'positive control, no Kratos in the chain: the portal route allows U on nrg-a', 200, pa, pa === 200);
    const r = { uA: await warden('nrg-a', cu), anonA: await warden('nrg-a', null), uB: await warden('nrg-b', cu), vB: await warden('nrg-b', cv) };
    rec.check('nrg.warden.kratos1x', "NRG's warden chain (find site -> Kratos whoami -> ACL by identity -> policy -> decision) with real Kratos 1.x cookies: U allowed on nrg-a; anonymous denied; U denied on nrg-b; V allowed on nrg-b",
      { uA: 200, anonA: 403, uB: 403, vB: 200 }, r, r.uA === 200 && r.anonA === 403 && r.uB === 403 && r.vB === 200);
    const reg = await fetch(`http://127.0.0.1:${NRG_PORT}/api/v1/workflows/site/registrations/nrg-c`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ owner_ref: 'owner-nrg-c', upstream_origin: 'https://nrg-c.example.test' }) });
    const why = loggedError('as-documented', 'nrg-c');
    rec.check('nrg.register.as-documented', 'site registration (creates the per-site Hydra client) with HYDRA_API at the admin port as NRG documents it: fails on the 307 to localhost:4445', { status: 500, logged: 'ECONNREFUSED' }, { status: reg.status, logged: why }, reg.status === 500 && why === 'ECONNREFUSED');
  } finally { execSync('docker rm -f ory-proof-nrg >/dev/null 2>&1 || true'); }

  startNrg(`${H.env.HYDRA_ADMIN}/admin`, 'admin-suffix');
  try {
    await nrgUp();
    const pa = await portal(U.id, 'nrg-a');
    rec.check('nrg.portal.control.2', 'liveness: portal route allows U on nrg-a in the second server run', 200, pa, pa === 200);
    const reg = await fetch(`http://127.0.0.1:${NRG_PORT}/api/v1/workflows/site/registrations/nrg-d`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ owner_ref: 'owner-nrg-d', upstream_origin: 'https://nrg-d.example.test' }) });
    const body = await reg.text();
    const why = loggedError('admin-suffix', 'nrg-d');
    rec.check('nrg.register.admin-suffix', "site registration with HYDRA_API + '/admin': the path is fixed and Hydra now answers 400 to NRG's client payload (sdk.hydra.nrg-client-shape shows the same payload refused as pairwise-under-JWT)", { status: 500, logged: 'Request failed with status code 400' }, { status: reg.status, logged: why }, reg.status === 500 && why === 'Request failed with status code 400');
    rec.note('register.admin-suffix.body', body.slice(0, 300));
  } finally { execSync('docker rm -f ory-proof-nrg >/dev/null 2>&1 || true'); }

  await knex.destroy();
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); try { execSync('docker rm -f ory-proof-nrg >/dev/null 2>&1'); } catch (x) {} process.exit(2); });
