#!/usr/bin/env node
'use strict';
/*
 * pair-reads-coercion.js — P0-D + P0-E, the ATOMIC UNIT (#8737 + #8738).
 *
 * This probe exists to measure ONE thing the merge order cannot: whether the
 * pair is whole. Run it with --candidate pointed at the integration branch and
 * --base at dev, and additionally with --candidate pointed at each half alone
 * to see the half-merged states.
 *
 * MEASURED 2026-09-17 on an identical 582-document seed (577 sgv, 5 mbg):
 *
 *   surface                              BASE      COERCION   READS      PAIR
 *   -----------------------------------  --------  --------   --------   --------
 *   list   find[mbg][$exists]=false      n=5 ✗     n=577 ✓    n=5 ✗      n=577 ✓
 *   count/where find[mbg][$exists]=false [] dead   [] dead    count=5 ✗  count=577 ✓
 *   count/where find[type]=sgv           [] dead   [] dead    count=577  count=577
 *
 * THREE CONCLUSIONS, none of them available by reading:
 *
 * 1. bf/coercion FIXES BF-40 (the $exists inversion) on the list surface. The
 *    queue's BFQ-40 row says the defect "stays wrong after the query
 *    type-conversion fix"; that is read-derived and measurement refutes it.
 *    The fix is `BOOLEAN_OPERANDS`/`readBooleanOperand` in lib/server/query.js,
 *    applied over the BUILT query — not the NON_VALUE_OPERATORS exclusion in
 *    query-coercion.js, which is a different mechanism and does something else.
 *
 * 2. bf/reads ALONE IS STRICTLY WORSE THAN DEV ON THE COUNT SURFACE, and this
 *    is the measured version of a claim an earlier draft made on bad evidence
 *    and had to withdraw. On dev, /count/entries/where returns `[]` for every
 *    filter — uniformly dead, and OBVIOUSLY so. On bf/reads alone it returns a
 *    confident `count=5` for a filter whose true answer is 577. A plausible
 *    wrong number is worse than a visible failure, because nothing downstream
 *    can tell it is wrong.
 *
 * 3. THE "COUNT EQUALS LIST" CRITERION IS VACUOUS. On bf/reads alone the count
 *    endpoint returns 5 and the list endpoint returns 5 — they agree, and both
 *    are wrong. Any arm comparing a build against itself passes here. Every
 *    arm below therefore asserts against the SEEDED EXPECTATION from the
 *    manifest, never against the same instance's other endpoint.
 */

const { args, fetch, compare } = require('../lib/nsprobe.js');

const Q_EXISTS_FALSE = 'find%5Bmbg%5D%5B%24exists%5D=false';
const Q_EXISTS_TRUE = 'find%5Bmbg%5D%5B%24exists%5D=true';
const Q_TYPE_SGV = 'find%5Btype%5D=sgv';

// Seeded truth. Overridden from the manifest when one is supplied.
const D = { sgv: 577, mbg: 5, total: 582 };

async function listLen(url, sha1, path) {
  const r = await fetch(url, `/api/v1/entries.json?count=99999&${path}`, sha1);
  if (r.code !== 200) throw new Error(`HTTP ${r.code}`);
  return (r.json || []).length;
}

// `[]` (the dead-endpoint shape) is reported as null, NOT as 0 — they are
// different failures and collapsing them would hide which one happened.
async function whereCount(url, sha1, path) {
  const r = await fetch(url, `/api/v1/count/entries/where?${path}`, sha1);
  if (r.code !== 200) throw new Error(`HTTP ${r.code}`);
  const j = r.json;
  if (!Array.isArray(j) || j.length === 0) return null;
  return j[0].count;
}

const num = v => (v === null ? 'DEAD (returned [])' : String(v));

(async () => {
  const o = args();
  const e = o.expect || {};
  const sgv = e.mbgExistsFalse || D.sgv;
  const mbg = e.mbgExistsTrue || D.mbg;

  await compare('pair: bf/coercion + bf/reads (#8737 + #8738, BF-01/40 et al)', o, [
    {
      kind: 'discriminates',
      what: `BF-40 list: $exists=false returns the ${sgv} docs WITHOUT mbg, not the ${mbg} with it`,
      measure: (u, s) => listLen(u, s, Q_EXISTS_FALSE),
      ok: v => v === sgv,
      describe: v => `${v} documents (seeded truth ${sgv}; ${mbg} would be the inversion)`,
    },
    {
      kind: 'invariant',
      what: '$exists=true is correct on every build and must stay so',
      measure: (u, s) => listLen(u, s, Q_EXISTS_TRUE),
      ok: v => v === mbg,
      describe: v => `${v} documents (seeded truth ${mbg})`,
    },
    {
      kind: 'discriminates',
      what: `BF-01 count/where answers a plain filter at all (type=sgv -> ${sgv})`,
      measure: (u, s) => whereCount(u, s, Q_TYPE_SGV),
      ok: v => v === sgv,
      describe: v => `${num(v)} (seeded truth ${sgv})`,
    },
    {
      // THE PAIR ARM. Red on BASE (dead), red on READS-only (inverted, 5),
      // red on COERCION-only (dead), green ONLY on the pair. This is the one
      // arm that detects a half-merged integration branch.
      kind: 'discriminates',
      what: `PAIR-WHOLE: count/where $exists=false -> ${sgv}, the arm that detects a half-merge`,
      measure: (u, s) => whereCount(u, s, Q_EXISTS_FALSE),
      ok: v => v === sgv,
      describe: v => (v === null ? 'DEAD (returned []) — bf/reads absent'
        : v === mbg ? `${v} — INVERTED: plausible, confident, and wrong (bf/coercion absent)`
        : `${v} (seeded truth ${sgv})`),
    },
    {
      kind: 'discriminates',
      what: 'BF-14/33 bad ?count= spellings are rejected, not answered',
      measure: async (u, s) => {
        const out = {};
        for (const c of ['0', 'abc', '-3', '0x10', '1e2']) {
          const r = await fetch(u, `/api/v1/entries.json?count=${c}`, s);
          out[c] = r.code;
        }
        return out;
      },
      ok: v => Object.values(v).every(c => c === 400),
      describe: v => Object.entries(v).map(([k, c]) => `${k}:${c}`).join(' '),
    },
    {
      kind: 'invariant',
      what: 'a normal ?count=10 still works (rejection did not over-reach)',
      measure: async (u, s) => {
        const r = await fetch(u, '/api/v1/entries.json?count=10', s);
        return { code: r.code, n: (r.json || []).length };
      },
      ok: v => v.code === 200 && v.n === 10,
      describe: v => `HTTP ${v.code}, ${v.n} documents`,
    },
  ]);
})().catch(e => { console.error('probe failed:', e.message); process.exit(2); });
