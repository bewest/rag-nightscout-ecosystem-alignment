#!/usr/bin/env node
'use strict';
/*
 * probes/proof.js - the T30-ORY-PROOF gate.
 *
 * One Kratos pool, two tenants. U is a member of tenant-a only.
 *   (a) positive: U's Kratos session on A's host -> an A token, which verifies on A.
 *   (b) probe:    U's session on B's host -> refused; an A token presented to B -> signature failure.
 *   control:      identical setup with U added to B -> B now mints; the A token still fails on B
 *                 as a signature failure (keys, not membership); remove U -> refused again.
 *   break-it:     restart nsjwt with one defence removed and confirm the probe goes red with the
 *                 predicted symptom.
 * Every phase asserts liveness (a positive request) in the same run as its negative probes.
 * Each check records the outcome PREDICTED for that phase, so a phase passes when the system
 * behaves as predicted - including the break phases, where the prediction is the red symptom.
 * Exit 0 = every prediction held; 1 = a mismatch (stop and report); 2 = could not run.
 */
const H = require('../lib/harness');
const jwt = require('../lib/jwt');

const A = H.env.tenantHost('tenant-a');
const B = H.env.tenantHost('tenant-b');
const rec = H.recorder('proof');

const exchange = (host, token) => H.req(host, 'POST', '/api/nsjwt/exchange', { headers: { 'x-session-token': token } });
const verify = (host, nsjwt) => H.req(host, 'GET', '/api/nsjwt/verify', { headers: { authorization: `Bearer ${nsjwt}` } });

async function liveness (phase, sess) {
  const ha = await H.req(A, 'GET', '/__health');
  const hb = await H.req(B, 'GET', '/__health');
  const ex = await exchange(A, sess.token);
  const v = ex.body && ex.body.token ? await verify(A, ex.body.token) : { status: 0 };
  rec.check(`${phase}.live`, 'liveness in this run: both tenant hosts answer, U exchanges and verifies on A',
    [200, 200, 200, 200], [ha.status, hb.status, ex.status, v.status],
    ha.status === 200 && hb.status === 200 && ex.status === 200 && v.status === 200);
  return ex.body && ex.body.token;
}

async function main () {
  const pool = H.db();
  await H.ensureSchema(pool);
  const ta = await H.tenant(pool, 'tenant-a');
  const tb = await H.tenant(pool, 'tenant-b');
  const U = await H.createIdentity('u');
  const V = await H.createIdentity('v');
  await H.removeMember(pool, tb, U.id);
  await H.addMember(pool, ta, U.id);
  await H.addMember(pool, tb, V.id);
  const su = await H.nativeLogin(U);
  const sv = await H.nativeLogin(V);
  rec.check('setup.sessions', 'both identities hold a Kratos session from the ONE pool', [200, 200], [su.status, sv.status], su.status === 200 && sv.status === 200 && su.subject === U.id);
  rec.note('fixture', { tenants: ['tenant-a', 'tenant-b'], U: 'member of tenant-a only', V: 'member of tenant-b only' });

  // ---------------- phase 1: intact boundary ----------------
  let srv = await H.startServer('', 'proof-intact');
  const tokA = await liveness('intact', su);
  const payA = jwt.decode(tokA);
  rec.check('intact.a.claims', 'the A token names tenant-a and U', { tenant: 'tenant-a', sub: U.id }, { tenant: payA && payA.tenant, sub: payA && payA.sub }, payA && payA.tenant === 'tenant-a' && payA.sub === U.id);

  const exB = await exchange(B, su.token);
  rec.check('intact.b.exchange', "U's session on B's host is refused for non-membership", { status: 403, error: 'not-a-member' }, { status: exB.status, error: exB.body && exB.body.error }, exB.status === 403 && exB.body.error === 'not-a-member');
  const vB = await verify(B, tokA);
  rec.check('intact.b.verify', 'the A token presented to B fails as a SIGNATURE failure', { status: 401, error: 'signature' }, { status: vB.status, error: vB.body && vB.body.error }, vB.status === 401 && vB.body.error === 'signature');
  const exVB = await exchange(B, sv.token);
  rec.check('intact.b.live', "B's own member V exchanges on B in the same run (B is alive, not just refusing)", 200, exVB.status, exVB.status === 200);
  const vVA = exVB.body && exVB.body.token ? await verify(A, exVB.body.token) : { status: 0, body: {} };
  rec.check('intact.b-to-a.verify', 'a B token presented to A fails as a signature failure (the reverse direction)', { status: 401, error: 'signature' }, { status: vVA.status, error: vVA.body && vVA.body.error }, vVA.status === 401 && vVA.body.error === 'signature');

  const before = (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body.nsjwt.credentialExaminations;
  const unk = await exchange(H.env.tenantHost('tenant-zz'), su.token);
  const foreign = await H.req('tenant-a.apex.test', 'POST', '/api/nsjwt/exchange', { headers: { 'x-session-token': su.token } });
  const after = (await H.req(H.env.CONTROL_HOST, 'GET', '/events')).body.nsjwt.credentialExaminations;
  rec.check('intact.resolve-first', 'an unknown slug and a host outside the rule are refused BEFORE any credential is examined',
    { unknownSlug: 404, offRule: 404, credentialExaminationsDelta: 0 }, { unknownSlug: unk.status, offRule: foreign.status, credentialExaminationsDelta: after - before },
    unk.status === 404 && foreign.status === 404 && after === before);

  const none = await H.req(A, 'POST', '/api/nsjwt/exchange');
  const junk = await exchange(A, 'ory_st_not-a-real-token');
  rec.check('intact.no-credential', 'on A, no credential -> 401 and a junk session token -> 401 (A refuses without a session)',
    { none: 401, junk: 401 }, { none: none.status, junk: junk.status }, none.status === 401 && junk.status === 401);

  // ---------------- control: identical setup, U added to B ----------------
  await H.addMember(pool, tb, U.id);
  const cB = await exchange(B, su.token);
  const cBv = cB.body && cB.body.token ? await verify(B, cB.body.token) : { status: 0, body: {} };
  rec.check('control.b.exchange', "CONTROL: with U added to B, the same session on B's host mints a B token that verifies on B",
    { exchange: 200, verify: 200, claim: 'tenant-b' }, { exchange: cB.status, verify: cBv.status, claim: cBv.body && cBv.body.claim },
    cB.status === 200 && cBv.status === 200 && cBv.body.claim === 'tenant-b');
  const cAonB = await verify(B, tokA);
  rec.check('control.b.verify-a-token', 'CONTROL: membership in B does not make the A token valid on B (still a signature failure)',
    { status: 401, error: 'signature' }, { status: cAonB.status, error: cAonB.body && cAonB.body.error }, cAonB.status === 401 && cAonB.body.error === 'signature');
  await H.removeMember(pool, tb, U.id);
  const rB = await exchange(B, su.token);
  rec.check('control.b.restored', 'U removed from B -> refused again (the refusal tracks the membership row)', 403, rB.status, rB.status === 403);

  // ---------------- revocation: Kratos session ended, minted token not ----------------
  const tokA2 = (await exchange(A, su.token)).body.token;
  const sessions = await H.kratosAdmin('GET', `/admin/identities/${U.id}/sessions`);
  const del = await H.kratosAdmin('DELETE', `/admin/identities/${U.id}/sessions`);
  const afterRevoke = await exchange(A, su.token);
  const oldStill = await verify(A, tokA2);
  rec.check('revoke.kratos', 'after Kratos revokes all of U\'s sessions, U can no longer exchange on A',
    { listSessions: 200, revoke: 204, exchange: 401 }, { listSessions: sessions.status, revoke: del.status, exchange: afterRevoke.status },
    sessions.status === 200 && del.status === 204 && afterRevoke.status === 401);
  rec.check('revoke.minted-survives', 'a Nightscout token minted before the revocation still verifies on A until its own exp (nsjwt has no revocation link to Kratos)',
    200, oldStill.status, oldStill.status === 200);
  await srv.stop();

  // fresh session for the break phases
  const su2 = await H.nativeLogin(U);

  // ---------------- break 1: skip the membership check ----------------
  srv = await H.startServer('skip-membership', 'proof-skip-membership');
  await liveness('break.skip-membership', su2);
  const b1 = await exchange(B, su2.token);
  const b1p = b1.body && b1.body.token ? jwt.decode(b1.body.token) : null;
  rec.check('break.skip-membership.red', "BREAK skip-membership: the probe goes red - U's session on B mints a B token for a non-member",
    { status: 200, tenant: 'tenant-b', sub: U.id }, { status: b1.status, tenant: b1p && b1p.tenant, sub: b1p && b1p.sub },
    b1.status === 200 && b1p.tenant === 'tenant-b' && b1p.sub === U.id);
  const b1v = await verify(B, b1.body.token);
  rec.check('break.skip-membership.usable', 'and that token is accepted by B (a working cross-tenant credential)', 200, b1v.status, b1v.status === 200);
  await srv.stop();

  // ---------------- break 2: claim check off, per-tenant keys intact ----------------
  srv = await H.startServer('no-claim-check', 'proof-no-claim-check');
  const tA3 = await liveness('break.no-claim-check', su2);
  const b2 = await verify(B, tA3);
  rec.check('break.no-claim-check.still-green', 'claim check removed, per-tenant keys intact: the A token on B is STILL a signature failure (D14 alone holds)',
    { status: 401, error: 'signature' }, { status: b2.status, error: b2.body && b2.body.error }, b2.status === 401 && b2.body.error === 'signature');
  await srv.stop();

  // ---------------- break 3: one deployment-wide key, claim check on ----------------
  srv = await H.startServer('shared-key', 'proof-shared-key');
  const tA4 = await liveness('break.shared-key', su2);
  const b3 = await verify(B, tA4);
  rec.check('break.shared-key.claim-catches', 'BREAK shared-key: the signature now passes on B; only the tenant-claim check refuses it',
    { status: 401, error: 'tenant-claim' }, { status: b3.status, error: b3.body && b3.body.error }, b3.status === 401 && b3.body.error === 'tenant-claim');
  await srv.stop();

  // ---------------- break 4: one key and no claim check ----------------
  srv = await H.startServer('shared-key,no-claim-check', 'proof-shared-key-no-claim');
  const tA5 = await liveness('break.shared-key+no-claim-check', su2);
  const b4 = await verify(B, tA5);
  rec.check('break.shared-key+no-claim-check.red', 'BREAK shared-key + no claim check: the probe goes red - the A token is accepted by B',
    { status: 200, claim: 'tenant-a' }, { status: b4.status, claim: b4.body && b4.body.claim }, b4.status === 200 && b4.body.claim === 'tenant-a');
  await srv.stop();

  await pool.end();
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
