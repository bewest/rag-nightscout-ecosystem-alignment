#!/usr/bin/env node
'use strict';
/*
 * probes/hydra-pairwise.js - run with Hydra in the opaque access-token variant
 * (LAB_VARIANT=hydra-opaque ./lab.sh recreate-hydra). NRG registered one pairwise client per site;
 * this measures what subject each tenant then sees, against the Kratos identity id that
 * tenant_members.subject_id stores. Positive control: a public client on the identical setup.
 */
const { chromium } = require('playwright');
const H = require('../lib/harness');
const { mkClient, codeFlow } = require('../lib/oauth');

const rec = H.recorder('hydra-pairwise');
const P = H.env.LAB_PORT;
const OA = `http://${H.env.tenantHost('tenant-a')}:${P}`;
const OB = `http://${H.env.tenantHost('tenant-b')}:${P}`;
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const decode = (t, i) => JSON.parse(Buffer.from(t.split('.')[i], 'base64url').toString());
const introspect = async (tok) => (await fetch(`${H.env.HYDRA_ADMIN}/admin/oauth2/introspect`, { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ token: tok }) })).json();

async function main () {
  const U = await H.createIdentity('u');
  const pubA = await mkClient(OA, 'tenant-a-public');
  const pwA = await mkClient(OA, 'tenant-a-pairwise', { subject_type: 'pairwise' });
  const pwB = await mkClient(OB, 'tenant-b-pairwise', { subject_type: 'pairwise' });
  const srv = await H.startServer('', 'hydra-pairwise');
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--host-resolver-rules=MAP *.apex.test 127.0.0.1'] });
  const page = await (await browser.newContext()).newPage();
  page.__who = U;
  try {
    const fpub = await codeFlow(page, pubA, OA);
    const fa = await codeFlow(page, pwA, OA);
    const fb = await codeFlow(page, pwB, OB);
    rec.check('flows', 'three code flows complete (public A, pairwise A, pairwise B)', [200, 200, 200], [fpub.status, fa.status, fb.status], fpub.status === 200 && fa.status === 200 && fb.status === 200);
    const opaque = fa.body.access_token.split('.').length !== 3;
    rec.check('opaque', 'access tokens are opaque in this variant (not JWTs)', true, opaque, opaque);
    const idPub = decode(fpub.body.id_token, 1).sub;
    const idA = decode(fa.body.id_token, 1).sub;
    const idB = decode(fb.body.id_token, 1).sub;
    const inA = await introspect(fa.body.access_token);
    const inB = await introspect(fb.body.access_token);
    const got = { publicIdTokenSubIsKratosId: idPub === U.id, pairwiseIdTokenSubIsKratosId: idA === U.id, pairwiseSubsDifferAcrossTenants: idA !== idB, introspectionSubIsKratosId: inA.sub === U.id && inB.sub === U.id };
    rec.check('subjects', "pairwise: each tenant's ID token carries a different sub, neither the Kratos id; introspection still returns the Kratos id; the public client's ID token sub IS the Kratos id",
      { publicIdTokenSubIsKratosId: true, pairwiseIdTokenSubIsKratosId: false, pairwiseSubsDifferAcrossTenants: true, introspectionSubIsKratosId: true }, got,
      got.publicIdTokenSubIsKratosId && !got.pairwiseIdTokenSubIsKratosId && got.pairwiseSubsDifferAcrossTenants && got.introspectionSubIsKratosId);
  } finally {
    await browser.close();
    await srv.stop();
    for (const c of [pubA, pwA, pwB]) await H.hydraAdmin('DELETE', `/admin/clients/${c.client_id}`);
  }
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
